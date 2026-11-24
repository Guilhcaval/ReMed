"""Services transversais do app nucleo (CepService — ADRs 0017 e 0018)."""

import json
import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, Request, build_opener

from django.conf import settings
from django.utils import timezone

from nucleo.exceptions import CepInvalido, CepNaoEncontrado, ServicoCepIndisponivel
from nucleo.models import CacheCep, FonteCep
from nucleo.validators import validar_cep, validar_uf

logger = logging.getLogger(__name__)

BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v2/{cep}"
VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
PRECISAO_COORDENADA_APROX = Decimal("0.01")  # ~1,1 km (ADR 0017 / RS010)
RAIO_TERRA_KM = 6371.0088

_NOMINATIM_LOCK = threading.Lock()
_NOMINATIM_ULTIMO_ACESSO = 0.0


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


@dataclass(frozen=True)
class DadosLocalizacaoCep:
    cep: str
    bairro: str
    municipio: str
    estado: str
    latitude_aprox: Decimal | None
    longitude_aprox: Decimal | None
    fonte: str
    do_cache: bool


@dataclass(frozen=True)
class BoundingBox:
    lat_min: Decimal
    lat_max: Decimal
    lon_min: Decimal
    lon_max: Decimal


def _requisitar_json_generico(url: str, *, http_opener=None) -> tuple[int, dict | list]:
    if not url.startswith("https://"):
        raise ServicoCepIndisponivel("URL de provedor externo deve usar HTTPS.")

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
            if not isinstance(dados, dict | list):
                raise ServicoCepIndisponivel("Resposta inesperada do provedor de geolocalização.")
            return status, dados
    except HTTPError as erro:
        return erro.code, []
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise ServicoCepIndisponivel("Serviço externo de geolocalização indisponível.") from erro


class GeolocalizacaoService:
    """Geocodificação aproximada (BrasilAPI + fallback Nominatim) e distância Haversine (ADR 0017).

    Cumpre estritamente a Nominatim Usage Policy:
    - Cache persistente obrigatório no PostgreSQL (`CacheCep`);
    - Rate limit local <= 1 req/s serializado por lock;
    - Cabeçalho HTTP `User-Agent` identificável do ReMed;
    - Sem geocodificação em massa nem autocomplete no navegador.
    """

    @staticmethod
    def arredondar_coordenada(valor) -> Decimal | None:
        return _arredondar_coordenada(valor)

    @staticmethod
    def resetar_rate_limit_nominatim() -> None:
        global _NOMINATIM_ULTIMO_ACESSO
        with _NOMINATIM_LOCK:
            _NOMINATIM_ULTIMO_ACESSO = 0.0

    @staticmethod
    def _respeitar_rate_limit_nominatim(
        *,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    ) -> None:
        global _NOMINATIM_ULTIMO_ACESSO
        intervalo = max(0.0, float(settings.REMED_NOMINATIM_INTERVALO_SEGUNDOS))
        with _NOMINATIM_LOCK:
            agora = monotonic_fn()
            decorrido = agora - _NOMINATIM_ULTIMO_ACESSO
            if _NOMINATIM_ULTIMO_ACESSO > 0 and decorrido < intervalo:
                sleep_fn(intervalo - decorrido)
                agora = monotonic_fn()
            _NOMINATIM_ULTIMO_ACESSO = agora

    @staticmethod
    def _consultar_nominatim(
        cep: str,
        *,
        bairro: str = "",
        municipio: str = "",
        estado: str = "",
        http_opener=None,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    ) -> tuple[Decimal | None, Decimal | None]:
        partes_consulta = [p for p in (bairro, municipio, estado, "Brasil") if p]
        consulta = ", ".join(partes_consulta) if partes_consulta else f"{cep}, Brasil"
        params = urlencode(
            {
                "q": consulta,
                "format": "jsonv2",
                "limit": "1",
                "countrycodes": "br",
            }
        )
        url = f"{NOMINATIM_SEARCH_URL}?{params}"
        GeolocalizacaoService._respeitar_rate_limit_nominatim(
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
        status, payload = _requisitar_json_generico(url, http_opener=http_opener)
        if status >= 400 or not isinstance(payload, list) or not payload:
            return None, None
        primeiro = payload[0]
        if not isinstance(primeiro, dict):
            return None, None
        lat = _arredondar_coordenada(primeiro.get("lat"))
        lon = _arredondar_coordenada(primeiro.get("lon"))
        return lat, lon

    @staticmethod
    def obter_coordenadas_por_cep(
        cep: str,
        *,
        http_opener=None,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    ) -> DadosLocalizacaoCep:
        try:
            cep_limpo = validar_cep(cep)
        except ValueError as erro:
            raise CepInvalido(str(erro)) from erro

        limite_ttl = timezone.now() - timedelta(days=settings.REMED_CEP_CACHE_TTL_DIAS)
        em_cache = CacheCep.objects.filter(cep=cep_limpo, atualizado_em__gte=limite_ttl).first()
        if (
            em_cache is not None
            and em_cache.latitude_aprox is not None
            and em_cache.longitude_aprox is not None
        ):
            return DadosLocalizacaoCep(
                cep=em_cache.cep,
                bairro=em_cache.bairro,
                municipio=em_cache.municipio,
                estado=em_cache.estado,
                latitude_aprox=em_cache.latitude_aprox,
                longitude_aprox=em_cache.longitude_aprox,
                fonte=em_cache.fonte,
                do_cache=True,
            )

        dados_cep = CepService.consultar(cep_limpo, http_opener=http_opener)
        lat = dados_cep.latitude_aprox
        lon = dados_cep.longitude_aprox
        fonte = dados_cep.fonte

        if lat is None or lon is None:
            try:
                lat_nom, lon_nom = GeolocalizacaoService._consultar_nominatim(
                    cep_limpo,
                    bairro=dados_cep.bairro,
                    municipio=dados_cep.municipio,
                    estado=dados_cep.estado,
                    http_opener=http_opener,
                    sleep_fn=sleep_fn,
                    monotonic_fn=monotonic_fn,
                )
            except ServicoCepIndisponivel:
                logger.warning("Fallback Nominatim indisponível para CEP %s.", cep_limpo)
                lat_nom, lon_nom = None, None

            if lat_nom is not None and lon_nom is not None:
                lat, lon = lat_nom, lon_nom
                fonte = FonteCep.NOMINATIM
                CacheCep.objects.filter(cep=cep_limpo).update(
                    latitude_aprox=lat,
                    longitude_aprox=lon,
                    fonte=FonteCep.NOMINATIM,
                    atualizado_em=timezone.now(),
                )

        return DadosLocalizacaoCep(
            cep=dados_cep.cep,
            bairro=dados_cep.bairro,
            municipio=dados_cep.municipio,
            estado=dados_cep.estado,
            latitude_aprox=lat,
            longitude_aprox=lon,
            fonte=fonte,
            do_cache=dados_cep.do_cache and fonte != FonteCep.NOMINATIM,
        )

    @staticmethod
    def calcular_bounding_box(
        latitude: Decimal | float,
        longitude: Decimal | float,
        raio_km: float,
    ) -> BoundingBox:
        lat_f = float(latitude)
        lon_f = float(longitude)
        raio_seguro = max(0.0, float(raio_km))
        # Margem de segurança de 0.02° (~2,2 km) elimina falsos negativos nas bordas.
        delta_lat = math.degrees(raio_seguro / RAIO_TERRA_KM) + 0.02
        cos_lat = max(math.cos(math.radians(lat_f)), 0.01)
        delta_lon = delta_lat / cos_lat

        lat_min = max(-90.0, lat_f - delta_lat)
        lat_max = min(90.0, lat_f + delta_lat)
        lon_min = max(-180.0, lon_f - delta_lon)
        lon_max = min(180.0, lon_f + delta_lon)
        return BoundingBox(
            lat_min=Decimal(f"{lat_min:.6f}"),
            lat_max=Decimal(f"{lat_max:.6f}"),
            lon_min=Decimal(f"{lon_min:.6f}"),
            lon_max=Decimal(f"{lon_max:.6f}"),
        )

    @staticmethod
    def calcular_distancia_haversine_km(
        lat1: Decimal | float,
        lon1: Decimal | float,
        lat2: Decimal | float,
        lon2: Decimal | float,
    ) -> float:
        phi1 = math.radians(float(lat1))
        phi2 = math.radians(float(lat2))
        d_phi = math.radians(float(lat2) - float(lat1))
        d_lambda = math.radians(float(lon2) - float(lon1))

        a = (
            math.sin(d_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
        return RAIO_TERRA_KM * c

    @staticmethod
    def formatar_faixa_distancia(distancia_km: float) -> str:
        """Formata distância em faixas aproximadas sem revelar distância exata (RS002 / RS010)."""
        if distancia_km < 1.0:
            return "menos de 1 km"
        if distancia_km < 2.5:
            return "cerca de 2 km"
        if distancia_km < 4.0:
            return "cerca de 3 km"
        if distancia_km < 7.5:
            return "cerca de 5 km"
        if distancia_km <= 10.0:
            return "cerca de 10 km"
        return "mais de 10 km"
