"""Context processor único de navegação global do ReMed (ADRs 0001, 0009 e 0010)."""

from dataclasses import dataclass

from django.urls import reverse

from contas.models import StatusUsuario
from contas.services import AutenticacaoService
from notificacoes.services import NotificacaoService
from nucleo.mixins import SESSAO_CHAVE_2FA_VERIFICADO
from pontos_coleta.services import PontoColetaService

MAPA_VIEW_SECAO: dict[str, str] = {
    "medicamentos:busca": "medicamentos_busca",
    "medicamentos:definir_localizacao": "medicamentos_busca",
    "medicamentos:limpar_localizacao": "medicamentos_busca",
    "medicamentos:minhas_doacoes": "minhas_doacoes",
    "medicamentos:doacao_criar": "minhas_doacoes",
    "medicamentos:doacao_editar": "minhas_doacoes",
    "medicamentos:doacao_cancelar": "minhas_doacoes",
    "pontos_coleta:lista_publica": "pontos_publicos",
    "pontos_coleta:meus_pontos": "meus_pontos",
    "pontos_coleta:cadastrar": "meus_pontos",
    "pontos_coleta:editar": "meus_pontos",
    "pontos_coleta:inativar": "meus_pontos",
    "pontos_coleta:responsaveis": "meus_pontos",
    "pontos_coleta:documentos": "meus_pontos",
    "pontos_coleta:convite_responder": "meus_pontos",
    "notificacoes:lista": "notificacoes",
    "contas:perfil_editar": "meu_perfil",
    "contas:encerrar_conta": "meu_perfil",
    "contas:totp_regenerar_codigos": "meu_perfil",
    "contas:login": "entrar",
    "contas:recuperar_senha_em_breve": "entrar",
    "contas:cadastro": "cadastro",
    "contas:confirmar_email": "cadastro",
    "contas:reenviar_confirmacao": "cadastro",
    "contas:admin_usuario_lista": "admin_usuarios",
    "contas:admin_usuario_detalhe": "admin_usuarios",
    "contas:admin_usuario_status": "admin_usuarios",
    "contas:admin_usuario_funcoes": "admin_usuarios",
    "contas:admin_usuario_resetar_2fa": "admin_usuarios",
    "pontos_coleta:admin_lista": "admin_pontos",
    "pontos_coleta:admin_detalhe": "admin_pontos",
    "pontos_coleta:admin_alterar_cnpj": "admin_pontos",
    "pontos_coleta:admin_analisar": "admin_pontos",
    "pontos_coleta:admin_situacao": "admin_pontos",
    "pontos_coleta:admin_revisar": "admin_pontos",
    "pontos_coleta:admin_documentos": "admin_documentos",
    "medicamentos:admin_conferencia_lista": "admin_conferencia",
    "medicamentos:admin_conferencia_detalhe": "admin_conferencia",
    "medicamentos:admin_conferencia_registrar": "admin_conferencia",
    "medicamentos:admin_conferencia_vencer": "admin_conferencia",
    "medicamentos:admin_vencimento_parametros": "admin_vencimento_parametros",
    "medicamentos:admin_vencimento_execucoes": "admin_vencimento_execucoes",
}


@dataclass(frozen=True)
class ItemNavegacaoAdmin:
    rotulo: str
    url: str
    secao: str


def _conta_ativa_valida(usuario) -> bool:
    return (
        getattr(usuario, "status", None) == StatusUsuario.ATIVO
        and getattr(usuario, "email_confirmado_em", None) is not None
        and getattr(usuario, "anonimizado_em", None) is None
    )


def _resolver_secao_ativa(request) -> str:
    match = getattr(request, "resolver_match", None)
    if match is None or not match.view_name:
        return ""
    return MAPA_VIEW_SECAO.get(match.view_name, "")


def _montar_itens_admin(funcoes: frozenset[str]) -> tuple[ItemNavegacaoAdmin, ...]:
    itens: list[ItemNavegacaoAdmin] = []
    if "gestao_usuarios" in funcoes or "gestao_administradores" in funcoes:
        itens.append(
            ItemNavegacaoAdmin(
                rotulo="Gestão de usuários",
                url=reverse("contas:admin_usuario_lista"),
                secao="admin_usuarios",
            )
        )
    if "aprovacao_pontos_coleta" in funcoes:
        itens.append(
            ItemNavegacaoAdmin(
                rotulo="Aprovação de pontos",
                url=reverse("pontos_coleta:admin_lista"),
                secao="admin_pontos",
            )
        )
        itens.append(
            ItemNavegacaoAdmin(
                rotulo="Documentos de pontos",
                url=reverse("pontos_coleta:admin_documentos"),
                secao="admin_documentos",
            )
        )
    if "conferencia_doacoes" in funcoes:
        itens.append(
            ItemNavegacaoAdmin(
                rotulo="Conferência de doações",
                url=reverse("medicamentos:admin_conferencia_lista"),
                secao="admin_conferencia",
            )
        )
    if "metricas_e_parametros" in funcoes:
        itens.append(
            ItemNavegacaoAdmin(
                rotulo="Parâmetros de vencimento",
                url=reverse("medicamentos:admin_vencimento_parametros"),
                secao="admin_vencimento_parametros",
            )
        )
        itens.append(
            ItemNavegacaoAdmin(
                rotulo="Execuções de vencimento",
                url=reverse("medicamentos:admin_vencimento_execucoes"),
                secao="admin_vencimento_execucoes",
            )
        )
    return tuple(itens)


def navegacao_global(request) -> dict:
    """Fornece estado consistente da barra superior sem ORM direto.

    Garante 0 consultas adicionais ao banco para visitantes anônimos, contas
    inativas/não confirmadas/anonimizadas e sessões pendentes de 2FA.
    """
    secao_ativa = _resolver_secao_ativa(request)
    base_visitante = {
        "nav_autenticado": False,
        "nav_pendente_2fa": False,
        "nav_exibir_minhas_doacoes": False,
        "nav_exibir_meus_pontos": False,
        "notificacoes_nao_lidas": 0,
        "nav_admin_itens": (),
        "nav_admin_ativo": False,
        "nav_secao_ativa": secao_ativa,
    }

    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated or not _conta_ativa_valida(usuario):
        return base_visitante

    sessao = getattr(request, "session", None)
    status_2fa = sessao.get(SESSAO_CHAVE_2FA_VERIFICADO) if sessao is not None else None
    if status_2fa is False:
        return {
            "nav_autenticado": True,
            "nav_pendente_2fa": True,
            "nav_exibir_minhas_doacoes": False,
            "nav_exibir_meus_pontos": False,
            "notificacoes_nao_lidas": 0,
            "nav_admin_itens": (),
            "nav_admin_ativo": False,
            "nav_secao_ativa": "",
        }

    funcoes_admin = AutenticacaoService.obter_funcoes_administrativas(usuario)
    if funcoes_admin and status_2fa is not True:
        return {
            "nav_autenticado": True,
            "nav_pendente_2fa": True,
            "nav_exibir_minhas_doacoes": False,
            "nav_exibir_meus_pontos": False,
            "notificacoes_nao_lidas": 0,
            "nav_admin_itens": (),
            "nav_admin_ativo": False,
            "nav_secao_ativa": "",
        }

    itens_admin = _montar_itens_admin(funcoes_admin) if status_2fa is True else ()
    secoes_admin = {item.secao for item in itens_admin}
    return {
        "nav_autenticado": True,
        "nav_pendente_2fa": False,
        "nav_exibir_minhas_doacoes": bool(getattr(usuario, "perfil_doador", False)),
        "nav_exibir_meus_pontos": PontoColetaService.usuario_possui_vinculo_ou_convite(usuario),
        "notificacoes_nao_lidas": NotificacaoService.contar_nao_lidas(usuario.pk),
        "nav_admin_itens": itens_admin,
        "nav_admin_ativo": secao_ativa in secoes_admin,
        "nav_secao_ativa": secao_ativa,
    }
