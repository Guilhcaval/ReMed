"""Context processor fino para contagem de notificações não lidas na barra de navegação."""

from contas.models import StatusUsuario
from notificacoes.services import NotificacaoService


def contador_notificacoes(request) -> dict[str, int]:
    """Retorna contagem de não lidas sem consultar o banco para anônimos/inativos."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"notificacoes_nao_lidas": 0}

    conta_ativa = (
        getattr(usuario, "status", None) == StatusUsuario.ATIVO
        and getattr(usuario, "email_confirmado_em", None) is not None
        and getattr(usuario, "anonimizado_em", None) is None
    )
    if not conta_ativa:
        return {"notificacoes_nao_lidas": 0}

    return {"notificacoes_nao_lidas": NotificacaoService.contar_nao_lidas(usuario.pk)}
