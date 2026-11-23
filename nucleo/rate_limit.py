"""Controle simples de limite de taxa sobre o cache nativo do Django."""

import hashlib

from django.core.cache import cache

from nucleo.exceptions import LimiteTaxaExcedido


def obter_ip_cliente(request) -> str:
    """Retorna o endereço remoto da requisição sem confiar em cabeçalhos forjáveis."""
    ip = (request.META.get("REMOTE_ADDR") or "").strip()
    return ip or "desconhecido"


def _chave_cache(escopo: str, identificador: str) -> str:
    identificador_hash = hashlib.sha256(identificador.strip().lower().encode("utf-8")).hexdigest()
    return f"remed:rl:{escopo}:{identificador_hash}"


def consumir_limite_taxa(
    *,
    escopo: str,
    identificador: str,
    limite: int,
    janela_segundos: int,
) -> bool:
    """Incrementa o contador da janela e retorna True enquanto estiver dentro do limite."""
    chave = _chave_cache(escopo, identificador)
    cache.add(chave, 0, timeout=janela_segundos)
    try:
        contagem = cache.incr(chave)
    except ValueError:
        cache.set(chave, 1, timeout=janela_segundos)
        contagem = 1
    return contagem <= limite


def exigir_limite_taxa(
    *,
    escopo: str,
    identificador: str,
    limite: int,
    janela_segundos: int,
    mensagem: str = "Muitas solicitações em pouco tempo. Aguarde alguns minutos e tente novamente.",
) -> None:
    permitido = consumir_limite_taxa(
        escopo=escopo,
        identificador=identificador,
        limite=limite,
        janela_segundos=janela_segundos,
    )
    if not permitido:
        raise LimiteTaxaExcedido(mensagem)
