"""Services transversais do app nucleo (CepService — ADRs 0017 e 0018)."""

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, Request, build_opener

from django.conf import settings
from django.utils import timezone

from nucleo.exceptions import CepInvalido, CepNaoEncontrado, ServicoCepIndisponivel
from nucleo.models import CacheCep, FonteCep
from nucleo.validators import validar_cep, validar_uf

logger = logging.getLogger(__name__)

BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v2/{cep}"
VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
PRECISAO_COORDENADA_APROX = Decimal("0.01")  # ~1,1 km (ADR 0017 / RS010)


@dataclass(frozen=True)
class DadosCep:
    cep: str
    logradouro: str
    bairro: str
    municipio: str
    estado: str
    latitude_aprox: Decimal | None
    longitude_aprox: Decimal | None
    fonte: str
    do_cache: bool


def _abrir_url_https(requisicao: Request, *, timeout: int):
    opener = build_opener(HTTPSHandler())
    return opener.open(requisicao, timeout=timeout)


def _arredondar_coordenada(valor) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor)).quantize(PRECISAO_COORDENADA_APROX)
    except InvalidOperation:
        return None


def _requisitar_json(url: str, *, http_opener=None) -> tuple[int, dict]:
    if not url.startswith("https://"):
        raise ServicoCepIndisponivel("URL de provedor de CEP deve usar HTTPS.")

    requisicao = Request(  # noqa: S310  # Esquema validado como https:// acima e via HTTPSHandler
        url,
        headers={
            "User-Agent": settings.REMED_CEP_USER_AGENT,
            "Accept": "application/json",
        },
        method="GET",
    )
    abridor = http_opener if http_opener is not None else _abrir_url_https
    timeout = settings.REMED_CEP_TIMEOUT_SEGUNDOS
    try:
        with abridor(requisicao, timeout=timeout) as resposta:
            status = getattr(resposta, "status", 200)
            corpo = resposta.read().decode("utf-8")
            dados = json.loads(corpo)
            if not isinstance(dados, dict):
                raise ServicoCepIndisponivel("Resposta inesperada do serviço de CEP.")
            return status, dados
    except HTTPError as erro:
        return erro.code, {}
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise ServicoCepIndisponivel("Serviço externo de CEP indisponível.") from erro


class CepService:
    """Proxy de consulta de CEP com cache no PostgreSQL e fallback BrasilAPI -> ViaCEP."""

    @staticmethod
    def _consultar_brasilapi(cep: str, *, http_opener=None) -> DadosCep | None:
        status, payload = _requisitar_json(
            BRASILAPI_CEP_URL.format(cep=cep),
            http_opener=http_opener,
        )
        if status == 404:
            return None
        if status >= 400:
            raise ServicoCepIndisponivel(f"BrasilAPI retornou status {status}.")

        estado = validar_uf(payload.get("state", ""))
        municipio = (payload.get("city") or "").strip()[:100]
        if not municipio:
            raise ServicoCepIndisponivel("Resposta incompleta da BrasilAPI.")

        localizacao = payload.get("location") or {}
        coordenadas = localizacao.get("coordinates") or {}
        return DadosCep(
            cep=cep,
            logradouro=(payload.get("street") or "").strip()[:150],
            bairro=(payload.get("neighborhood") or "").strip()[:100],
            municipio=municipio,
            estado=estado,
            latitude_aprox=_arredondar_coordenada(coordenadas.get("latitude")),
            longitude_aprox=_arredondar_coordenada(coordenadas.get("longitude")),
            fonte=FonteCep.BRASILAPI,
            do_cache=False,
        )

    @staticmethod
    def _consultar_viacep(cep: str, *, http_opener=None) -> DadosCep | None:
        status, payload = _requisitar_json(
            VIACEP_URL.format(cep=cep),
            http_opener=http_opener,
        )
        if status == 404 or payload.get("erro") in {True, "true", "True"}:
            return None
        if status >= 400:
            raise ServicoCepIndisponivel(f"ViaCEP retornou status {status}.")

        estado = validar_uf(payload.get("uf", ""))
        municipio = (payload.get("localidade") or "").strip()[:100]
        if not municipio:
            raise ServicoCepIndisponivel("Resposta incompleta do ViaCEP.")

        return DadosCep(
            cep=cep,
            logradouro=(payload.get("logradouro") or "").strip()[:150],
            bairro=(payload.get("bairro") or "").strip()[:100],
            municipio=municipio,
            estado=estado,
            latitude_aprox=None,
            longitude_aprox=None,
            fonte=FonteCep.VIACEP,
            do_cache=False,
        )

    @staticmethod
    def consultar(cep: str, *, http_opener=None) -> DadosCep:
        try:
            cep_limpo = validar_cep(cep)
        except ValueError as erro:
            raise CepInvalido(str(erro)) from erro

        limite_ttl = timezone.now() - timedelta(days=settings.REMED_CEP_CACHE_TTL_DIAS)
        em_cache = CacheCep.objects.filter(cep=cep_limpo, atualizado_em__gte=limite_ttl).first()
        if em_cache is not None:
            return DadosCep(
                cep=em_cache.cep,
                logradouro=em_cache.logradouro,
                bairro=em_cache.bairro,
                municipio=em_cache.municipio,
                estado=em_cache.estado,
                latitude_aprox=em_cache.latitude_aprox,
                longitude_aprox=em_cache.longitude_aprox,
                fonte=em_cache.fonte,
                do_cache=True,
            )

        resultado: DadosCep | None = None
        try:
            resultado = CepService._consultar_brasilapi(cep_limpo, http_opener=http_opener)
        except ServicoCepIndisponivel, ValueError:
            logger.warning("Falha na consulta primária de CEP (BrasilAPI); tentando fallback.")

        if resultado is None:
            try:
                resultado = CepService._consultar_viacep(cep_limpo, http_opener=http_opener)
            except (ServicoCepIndisponivel, ValueError) as erro:
                logger.warning("Falha na consulta fallback de CEP (ViaCEP).")
                raise ServicoCepIndisponivel(
                    "Não foi possível consultar o CEP no momento. Preencha o endereço manualmente."
                ) from erro

            if resultado is None:
                raise CepNaoEncontrado("CEP não encontrado.")

        CacheCep.objects.update_or_create(
            cep=cep_limpo,
            defaults={
                "logradouro": resultado.logradouro,
                "bairro": resultado.bairro,
                "municipio": resultado.municipio,
                "estado": resultado.estado,
                "latitude_aprox": resultado.latitude_aprox,
                "longitude_aprox": resultado.longitude_aprox,
                "fonte": resultado.fonte,
            },
        )
        return resultado

    @staticmethod
    def obter_coordenadas_em_cache(cep: str) -> tuple[Decimal | None, Decimal | None]:
        """Retorna coordenadas aproximadas já em cache sem bloquear o fluxo com HTTP."""
        try:
            cep_limpo = validar_cep(cep)
        except ValueError:
            return None, None

        registro = (
            CacheCep.objects.filter(cep=cep_limpo).only("latitude_aprox", "longitude_aprox").first()
        )
        if registro is None:
            return None, None
        return registro.latitude_aprox, registro.longitude_aprox
