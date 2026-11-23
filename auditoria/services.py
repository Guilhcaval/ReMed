"""Service append-only de auditoria imutável (ADR 0011 / RNF14)."""

from collections.abc import Mapping
from typing import Any

from auditoria.models import OrigemAuditoria, RegistroAuditoria
from nucleo.exceptions import RegraNegocioViolada

CHAVES_PROIBIDAS_DETALHES: frozenset[str] = frozenset(
    {
        "password",
        "senha",
        "senha_atual",
        "nova_senha",
        "totp",
        "totp_secret",
        "segredo",
        "secret",
        "token",
        "codigo_recuperacao",
        "cpf",
        "email",
        "celular",
        "telefone",
        "endereco",
        "logradouro",
        "receita",
        "texto_mensagem",
    }
)


def _validar_detalhes_seguros(valor: Any) -> None:
    if isinstance(valor, Mapping):
        for chave, subvalor in valor.items():
            chave_norm = str(chave).strip().lower()
            if chave_norm in CHAVES_PROIBIDAS_DETALHES:
                raise RegraNegocioViolada(
                    f"Chave sensível não permitida nos detalhes de auditoria: {chave}"
                )
            _validar_detalhes_seguros(subvalor)
    elif isinstance(valor, list | tuple):
        for item in valor:
            _validar_detalhes_seguros(item)


class AuditoriaService:
    """Expõe somente inserção (append-only) e consulta; sem edição ou exclusão."""

    @staticmethod
    def registrar(
        *,
        acao: str,
        entidade_tipo: str,
        entidade_id: str | int,
        ator=None,
        motivo: str = "",
        detalhes: Mapping[str, Any] | None = None,
        origem: str = OrigemAuditoria.WEB,
    ) -> RegistroAuditoria:
        payload = dict(detalhes) if detalhes is not None else {}
        _validar_detalhes_seguros(payload)
        return RegistroAuditoria.objects.create(
            ator=ator,
            acao=acao,
            entidade_tipo=entidade_tipo,
            entidade_id=str(entidade_id),
            motivo=motivo,
            detalhes=payload,
            origem=origem,
        )
