"""Serviço de leitura de embalagem por IA multimodal (RF009 / Spec 23 / ADR 0021).

Implementado 100% sobre a biblioteca padrão (`urllib.request`) sem novas dependências
externas, com saneamento prévio em memória (remoção de EXIF/GPS e validação via
`ArquivoService`), limite de taxa por usuário, timeout rígido (SLA <= 15 s — RNF04)
e fallback gracioso para preenchimento manual.
"""

import base64
import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings

from auditoria.services import AuditoriaService
from contas.models import StatusUsuario, Usuario
from medicamentos.exceptions import FotoDoacaoFormatoInvalido, ServicoIaIndisponivel
from nucleo.arquivos import AntimalwareScanner, ArquivoService
from nucleo.exceptions import ArquivoFormatoInvalido, PermissaoNegada, RegraNegocioViolada
from nucleo.rate_limit import exigir_limite_taxa

logger = logging.getLogger(__name__)

AVISO_LGPD_IA_EMBALAGEM = (
    "A foto da embalagem será enviada a um serviço externo de IA apenas para sugerir os dados. "
    "Não fotografe etiquetas com nome de paciente ou outros dados pessoais."
)
AVISO_SUGESTAO_IA = "Sugestão da IA — confira os dados e confirme especialmente a data de validade."
MENSAGEM_FALLBACK_IA = (
    "Não foi possível ler a embalagem automaticamente no momento. "
    "Preencha os campos manualmente — nada do que você digitou foi perdido."
)

GEMINI_MODELO_PADRAO = "gemini-2.5-flash"
GEMINI_ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
)
OPENAI_MODELO_PADRAO = "gpt-4o-mini"
OPENAI_ENDPOINT_PADRAO = "https://api.openai.com/v1/chat/completions"

MAX_RESPOSTA_IA_BYTES = 65_536
TIMEOUT_MAXIMO_RNF04_SEGUNDOS = 14
_REGEX_BLOCO_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_REGEX_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_REGEX_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_REGEX_MODELO_SEGURO = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")

PROMPT_EXTRACAO_EMBALAGEM = (
    "Você é um assistente de leitura de embalagens de medicamentos para o sistema ReMed. "
    "Analise apenas a embalagem visível na imagem e retorne ESTRITAMENTE um objeto JSON válido "
    "com as chaves: nome_medicamento, principio_ativo, concentracao_dosagem, lote, "
    "data_validade e fabricante. "
    'Cada chave deve ter o formato {"valor": string_ou_null, "confianca": numero_entre_0_e_1}. '
    "Regras obrigatórias: "
    "1) Nunca estime, chute ou invente valores ilegíveis ou ausentes: devolva valor null e "
    "confianca 0. "
    "2) Para data_validade, devolva no formato YYYY-MM-DD somente se dia, mês e ano estiverem "
    "claramente legíveis; se só houver mês/ano ou estiver borrada, devolva valor null. "
    "3) Ignore e nunca inclua nomes de pacientes, prescrições ou dados pessoais."
)


@dataclass(frozen=True)
class CampoSugeridoIa:
    valor: str
    confianca: float | None
    baixa_confianca: bool
    exige_confirmacao: bool

    def para_dict(self) -> dict[str, Any]:
        return {
            "valor": self.valor,
            "confianca": self.confianca,
            "baixa_confianca": self.baixa_confianca,
            "exige_confirmacao": self.exige_confirmacao,
        }


@dataclass(frozen=True)
class ResultadoLeituraEmbalagemIa:
    nome_medicamento: CampoSugeridoIa
    principio_ativo: CampoSugeridoIa
    concentracao_dosagem: CampoSugeridoIa
    lote: CampoSugeridoIa
    data_validade: CampoSugeridoIa
    fabricante: CampoSugeridoIa
    provedor: str
    latencia_ms: int
    possui_sugestoes: bool
    campos_baixa_confianca: tuple[str, ...]
    validade_sugerida: bool

    def para_dict(self) -> dict[str, Any]:
        return {
            "sucesso": True,
            "aviso_sugestao": AVISO_SUGESTAO_IA,
            "confianca_minima": float(settings.REMED_IA_CONFIANCA_MINIMA),
            "possui_sugestoes": self.possui_sugestoes,
            "validade_sugerida": self.validade_sugerida,
            "campos_baixa_confianca": list(self.campos_baixa_confianca),
            "latencia_ms": self.latencia_ms,
            "campos": {
                "nome_medicamento": self.nome_medicamento.para_dict(),
                "principio_ativo": self.principio_ativo.para_dict(),
                "concentracao_dosagem": self.concentracao_dosagem.para_dict(),
                "lote": self.lote.para_dict(),
                "data_validade": self.data_validade.para_dict(),
                "fabricante": self.fabricante.para_dict(),
            },
        }


class ProvedorIaEmbalagem(Protocol):
    """Protocolo desacoplado de provedor multimodal de leitura de embalagem (ADR 0021)."""

    nome: str

    def analisar_embalagem(
        self,
        imagem_bytes: bytes,
        mime_type: str,
        *,
        timeout_segundos: int,
    ) -> dict[str, Any]: ...


def _validar_url_provedor(url: str) -> str:
    candidato = (url or "").strip()
    parsed = urlparse(candidato)
    if parsed.scheme == "https" and parsed.netloc:
        return candidato
    if settings.DEBUG and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}:
        return candidato
    raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)


def _extrair_objeto_json_de_texto(texto: str) -> dict[str, Any]:
    limpo = (texto or "").strip()
    if not limpo:
        raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
    bloco = _REGEX_BLOCO_JSON.search(limpo)
    if bloco:
        limpo = bloco.group(1).strip()
    try:
        dados = json.loads(limpo)
    except json.JSONDecodeError as erro:
        raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA) from erro
    if not isinstance(dados, dict):
        raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
    return dados


def _requisitar_post_json(
    url: str,
    *,
    cabecalhos: dict[str, str],
    payload: dict[str, Any],
    timeout_segundos: int,
    http_opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    url_validada = _validar_url_provedor(url)
    corpo_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers_finais = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": settings.REMED_CEP_USER_AGENT,
        **cabecalhos,
    }
    requisicao = Request(  # noqa: S310  # Esquema validado por _validar_url_provedor acima
        url_validada,
        data=corpo_bytes,
        headers=headers_finais,
        method="POST",
    )
    abridor = http_opener if http_opener is not None else urlopen
    try:
        with abridor(requisicao, timeout=timeout_segundos) as resposta:
            status = getattr(resposta, "status", 200)
            if status >= 400:
                raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
            bruto = resposta.read(MAX_RESPOSTA_IA_BYTES + 1)
            if len(bruto) > MAX_RESPOSTA_IA_BYTES:
                raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
            dados = json.loads(bruto.decode("utf-8"))
            if not isinstance(dados, dict):
                raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
            return dados
    except ServicoIaIndisponivel:
        raise
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as erro:
        raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA) from erro


class ProvedorIaDesativado:
    """Fallback padrão quando nenhuma chave/provedor de IA estiver configurado."""

    nome = "desativado"

    def __init__(self, motivo: str = "nao_configurado"):
        self.motivo = motivo

    def analisar_embalagem(
        self,
        imagem_bytes: bytes,
        mime_type: str,
        *,
        timeout_segundos: int,
    ) -> dict[str, Any]:
        _ = (imagem_bytes, mime_type, timeout_segundos)
        raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)


class ProvedorIaGemini:
    """Adaptador REST do Google Gemini via `urllib.request` (chave via header x-goog-api-key)."""

    nome = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        modelo: str = GEMINI_MODELO_PADRAO,
        endpoint: str = "",
        http_opener: Callable[..., Any] | None = None,
    ):
        self._api_key = (api_key or "").strip()
        modelo_limpo = (modelo or GEMINI_MODELO_PADRAO).strip()
        if not _REGEX_MODELO_SEGURO.match(modelo_limpo):
            raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
        self._modelo = modelo_limpo
        self._endpoint = (endpoint or "").strip() or GEMINI_ENDPOINT_TEMPLATE.format(
            modelo=self._modelo
        )
        self._http_opener = http_opener

    def analisar_embalagem(
        self,
        imagem_bytes: bytes,
        mime_type: str,
        *,
        timeout_segundos: int,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
        imagem_b64 = base64.b64encode(imagem_bytes).decode("ascii")
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": PROMPT_EXTRACAO_EMBALAGEM},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": imagem_b64,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        resposta = _requisitar_post_json(
            self._endpoint,
            cabecalhos={"x-goog-api-key": self._api_key},
            payload=payload,
            timeout_segundos=timeout_segundos,
            http_opener=self._http_opener,
        )
        candidatos = resposta.get("candidates")
        if not isinstance(candidatos, list) or not candidatos:
            raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
        conteudo = candidatos[0].get("content") if isinstance(candidatos[0], dict) else None
        partes = conteudo.get("parts") if isinstance(conteudo, dict) else None
        if not isinstance(partes, list) or not partes or not isinstance(partes[0], dict):
            raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
        return _extrair_objeto_json_de_texto(str(partes[0].get("text") or ""))


class ProvedorIaOpenAiCompat:
    """Adaptador REST compatível com OpenAI Chat Completions multimodal via `urllib.request`."""

    nome = "openai_compat"

    def __init__(
        self,
        *,
        api_key: str,
        modelo: str = OPENAI_MODELO_PADRAO,
        endpoint: str = "",
        http_opener: Callable[..., Any] | None = None,
    ):
        self._api_key = (api_key or "").strip()
        self._modelo = (modelo or OPENAI_MODELO_PADRAO).strip()
        self._endpoint = (endpoint or "").strip() or OPENAI_ENDPOINT_PADRAO
        self._http_opener = http_opener

    def analisar_embalagem(
        self,
        imagem_bytes: bytes,
        mime_type: str,
        *,
        timeout_segundos: int,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
        imagem_b64 = base64.b64encode(imagem_bytes).decode("ascii")
        data_uri = f"data:{mime_type};base64,{imagem_b64}"
        payload = {
            "model": self._modelo,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT_EXTRACAO_EMBALAGEM},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        }
        resposta = _requisitar_post_json(
            self._endpoint,
            cabecalhos={"Authorization": f"Bearer {self._api_key}"},
            payload=payload,
            timeout_segundos=timeout_segundos,
            http_opener=self._http_opener,
        )
        escolhas = resposta.get("choices")
        if not isinstance(escolhas, list) or not escolhas or not isinstance(escolhas[0], dict):
            raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
        mensagem = escolhas[0].get("message")
        if not isinstance(mensagem, dict):
            raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
        return _extrair_objeto_json_de_texto(str(mensagem.get("content") or ""))


def resolver_provedor_ia_configurado(
    *,
    http_opener: Callable[..., Any] | None = None,
) -> ProvedorIaEmbalagem:
    provedor = (getattr(settings, "REMED_IA_PROVEDOR", "") or "").strip().lower()
    api_key = (getattr(settings, "REMED_IA_API_KEY", "") or "").strip()
    modelo = (getattr(settings, "REMED_IA_MODELO", "") or "").strip()
    endpoint = (getattr(settings, "REMED_IA_ENDPOINT", "") or "").strip()

    if not provedor or provedor == "desativado" or not api_key:
        return ProvedorIaDesativado(motivo="nao_configurado")
    if provedor == "gemini":
        return ProvedorIaGemini(
            api_key=api_key,
            modelo=modelo or GEMINI_MODELO_PADRAO,
            endpoint=endpoint,
            http_opener=http_opener,
        )
    if provedor == "openai_compat":
        return ProvedorIaOpenAiCompat(
            api_key=api_key,
            modelo=modelo or OPENAI_MODELO_PADRAO,
            endpoint=endpoint,
            http_opener=http_opener,
        )
    return ProvedorIaDesativado(motivo="provedor_desconhecido")


def _validar_doador_ativo(usuario: Usuario) -> None:
    if (
        usuario is None
        or not getattr(usuario, "is_authenticated", False)
        or usuario.status != StatusUsuario.ATIVO
        or usuario.email_confirmado_em is None
        or usuario.anonimizado_em is not None
    ):
        raise PermissaoNegada(
            "Somente usuários ativos com e-mail confirmado podem usar este recurso."
        )
    if not usuario.perfil_doador:
        raise PermissaoNegada(
            "Apenas usuários com perfil Doador podem usar a leitura de embalagem por IA."
        )


def _normalizar_confianca(bruto: Any) -> float | None:
    if bruto is None or isinstance(bruto, bool):
        return None
    try:
        valor = float(bruto)
    except TypeError, ValueError:
        return None
    if valor != valor:  # NaN
        return None
    return round(max(0.0, min(1.0, valor)), 2)


def _normalizar_texto(bruto: Any, *, max_len: int) -> str:
    if bruto is None or isinstance(bruto, (bool, dict, list)):
        return ""
    limpo = " ".join(str(bruto).split()).strip()
    return limpo[:max_len]


def _normalizar_data_validade(bruto: Any) -> str:
    """Aceita apenas data completa e válida (YYYY-MM-DD ou DD/MM/YYYY); nunca estima dia."""
    texto = _normalizar_texto(bruto, max_len=20)
    if not texto:
        return ""
    match_iso = _REGEX_DATA_ISO.match(texto)
    if match_iso:
        try:
            return date(
                int(match_iso.group(1)),
                int(match_iso.group(2)),
                int(match_iso.group(3)),
            ).isoformat()
        except ValueError:
            return ""
    match_br = _REGEX_DATA_BR.match(texto)
    if match_br:
        try:
            return date(
                int(match_br.group(3)),
                int(match_br.group(2)),
                int(match_br.group(1)),
            ).isoformat()
        except ValueError:
            return ""
    return ""


def _extrair_campo_normalizado(
    bruto: Mapping[str, Any],
    chave: str,
    *,
    max_len: int,
    confianca_minima: float,
    eh_data: bool = False,
    sempre_confirmar: bool = False,
) -> CampoSugeridoIa:
    item = bruto.get(chave)
    if isinstance(item, Mapping):
        valor_bruto = item.get("valor")
        confianca = _normalizar_confianca(item.get("confianca"))
    else:
        valor_bruto = item
        confianca = None

    valor = (
        _normalizar_data_validade(valor_bruto)
        if eh_data
        else _normalizar_texto(valor_bruto, max_len=max_len)
    )
    if not valor:
        return CampoSugeridoIa(
            valor="",
            confianca=None,
            baixa_confianca=False,
            exige_confirmacao=False,
        )

    baixa = confianca is None or confianca < confianca_minima
    return CampoSugeridoIa(
        valor=valor,
        confianca=confianca,
        baixa_confianca=baixa,
        exige_confirmacao=bool(sempre_confirmar or baixa),
    )


class LeituraEmbalagemIaService:
    """Orquestra saneamento, rate limit, chamada multimodal e auditoria do RF009 (Spec 23)."""

    @staticmethod
    def ia_configurada() -> bool:
        provedor = resolver_provedor_ia_configurado()
        return not isinstance(provedor, ProvedorIaDesativado)

    @staticmethod
    def extrair_sugestoes(
        usuario: Usuario,
        *,
        conteudo_imagem: bytes,
        nome_arquivo: str,
        consentimento_envio: bool,
        provedor: ProvedorIaEmbalagem | None = None,
        scanner: AntimalwareScanner | None = None,
    ) -> ResultadoLeituraEmbalagemIa:
        _validar_doador_ativo(usuario)

        if not consentimento_envio:
            raise RegraNegocioViolada(
                "Confirme a ciência sobre o envio da foto ao serviço externo de IA antes de "
                "continuar."
            )

        exigir_limite_taxa(
            escopo="ia_embalagem_usuario",
            identificador=str(usuario.pk),
            limite=int(settings.REMED_IA_LEITURAS_MAX_POR_HORA),
            janela_segundos=3600,
            mensagem=(
                "Limite horário de leituras automáticas por IA atingido. "
                "Você pode continuar o preenchimento manualmente."
            ),
        )

        try:
            imagem_limpa = ArquivoService.validar_e_sanitizar_imagem(
                conteudo=conteudo_imagem,
                nome_original=nome_arquivo,
                scanner=scanner,
            )
        except ArquivoFormatoInvalido as erro:
            raise FotoDoacaoFormatoInvalido() from erro

        provedor_ativo = provedor if provedor is not None else resolver_provedor_ia_configurado()
        nome_provedor = getattr(provedor_ativo, "nome", "personalizado")[:40]
        timeout_efetivo = max(
            1, min(int(settings.REMED_IA_TIMEOUT_SEGUNDOS), TIMEOUT_MAXIMO_RNF04_SEGUNDOS)
        )

        inicio = time.monotonic()
        try:
            resposta_bruta = provedor_ativo.analisar_embalagem(
                imagem_limpa.conteudo,
                imagem_limpa.mime_verificado,
                timeout_segundos=timeout_efetivo,
            )
            if not isinstance(resposta_bruta, Mapping):
                raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA)
        except ServicoIaIndisponivel:
            latencia_ms = int((time.monotonic() - inicio) * 1000)
            acao_erro = (
                "ia_embalagem.indisponivel"
                if isinstance(provedor_ativo, ProvedorIaDesativado)
                else "ia_embalagem.falha"
            )
            motivo_erro = (
                getattr(provedor_ativo, "motivo", "nao_configurado")
                if isinstance(provedor_ativo, ProvedorIaDesativado)
                else "indisponivel_ou_timeout"
            )
            AuditoriaService.registrar(
                acao=acao_erro,
                entidade_tipo="usuario",
                entidade_id=usuario.pk,
                ator=usuario,
                detalhes={
                    "provedor": nome_provedor,
                    "sucesso": False,
                    "latencia_ms": latencia_ms,
                    "motivo_tecnico": motivo_erro,
                },
            )
            raise
        except Exception as erro:
            latencia_ms = int((time.monotonic() - inicio) * 1000)
            logger.warning(
                "Falha inesperada na leitura de embalagem por IA (provedor=%s, erro=%s).",
                nome_provedor,
                erro.__class__.__name__,
            )
            AuditoriaService.registrar(
                acao="ia_embalagem.falha",
                entidade_tipo="usuario",
                entidade_id=usuario.pk,
                ator=usuario,
                detalhes={
                    "provedor": nome_provedor,
                    "sucesso": False,
                    "latencia_ms": latencia_ms,
                    "motivo_tecnico": erro.__class__.__name__[:60],
                },
            )
            raise ServicoIaIndisponivel(MENSAGEM_FALLBACK_IA) from erro

        latencia_ms = int((time.monotonic() - inicio) * 1000)
        confianca_minima = float(settings.REMED_IA_CONFIANCA_MINIMA)

        bruto_norm = dict(resposta_bruta)
        if "principio_ativo" not in bruto_norm and "principio_ativo_e_concentracao" in bruto_norm:
            bruto_norm["principio_ativo"] = bruto_norm["principio_ativo_e_concentracao"]

        nome_med = _extrair_campo_normalizado(
            bruto_norm, "nome_medicamento", max_len=150, confianca_minima=confianca_minima
        )
        principio = _extrair_campo_normalizado(
            bruto_norm, "principio_ativo", max_len=150, confianca_minima=confianca_minima
        )
        concentracao = _extrair_campo_normalizado(
            bruto_norm, "concentracao_dosagem", max_len=80, confianca_minima=confianca_minima
        )
        lote = _extrair_campo_normalizado(
            bruto_norm, "lote", max_len=60, confianca_minima=confianca_minima
        )
        validade = _extrair_campo_normalizado(
            bruto_norm,
            "data_validade",
            max_len=10,
            confianca_minima=confianca_minima,
            eh_data=True,
            sempre_confirmar=True,
        )
        fabricante = _extrair_campo_normalizado(
            bruto_norm, "fabricante", max_len=120, confianca_minima=confianca_minima
        )

        mapa_campos = {
            "nome_medicamento": nome_med,
            "principio_ativo": principio,
            "concentracao_dosagem": concentracao,
            "lote": lote,
            "data_validade": validade,
            "fabricante": fabricante,
        }
        campos_sugeridos = [k for k, c in mapa_campos.items() if c.valor]
        campos_baixa = tuple(k for k, c in mapa_campos.items() if c.baixa_confianca)

        AuditoriaService.registrar(
            acao="ia_embalagem.executada",
            entidade_tipo="usuario",
            entidade_id=usuario.pk,
            ator=usuario,
            detalhes={
                "provedor": nome_provedor,
                "sucesso": True,
                "latencia_ms": latencia_ms,
                "campos_sugeridos": campos_sugeridos,
                "campos_baixa_confianca": list(campos_baixa),
            },
        )

        return ResultadoLeituraEmbalagemIa(
            nome_medicamento=nome_med,
            principio_ativo=principio,
            concentracao_dosagem=concentracao,
            lote=lote,
            data_validade=validade,
            fabricante=fabricante,
            provedor=nome_provedor,
            latencia_ms=latencia_ms,
            possui_sugestoes=bool(campos_sugeridos),
            campos_baixa_confianca=campos_baixa,
            validade_sugerida=bool(validade.valor),
        )
