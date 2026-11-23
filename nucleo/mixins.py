"""Mixins declarativos de controle de acesso e 2FA para CBVs (ADRs 0007, 0009 e 0010)."""

from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse

from contas.models import FUNCOES_ADMINISTRATIVAS, StatusUsuario
from contas.services import AutenticacaoService

SESSAO_CHAVE_2FA_VERIFICADO = "2fa_verificado"

MAPA_CAMPOS_PERFIL: dict[str, str] = {
    "doador": "perfil_doador",
    "solicitante": "perfil_solicitante",
    "cuidador": "perfil_cuidador",
}


def _conta_ativa_valida(usuario) -> bool:
    return (
        getattr(usuario, "status", None) == StatusUsuario.ATIVO
        and getattr(usuario, "email_confirmado_em", None) is not None
        and getattr(usuario, "anonimizado_em", None) is None
    )


class VisitanteObrigatorioMixin:
    """Redireciona usuários já autenticados para a tela de perfil."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("contas:perfil_editar")
        return super().dispatch(request, *args, **kwargs)


class AutenticadoAtivoMixin:
    """Exige usuário autenticado, ativo, com e-mail confirmado e não anonimizado."""

    def _verificar_acesso_adicional(self, request):
        return None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

        if not _conta_ativa_valida(request.user):
            return HttpResponseForbidden(
                "Sua conta não tem permissão para acessar este recurso no estado atual."
            )

        negacao = self._verificar_acesso_adicional(request)
        if negacao is not None:
            return negacao
        return super().dispatch(request, *args, **kwargs)


class PerfilObrigatorioMixin(AutenticadoAtivoMixin):
    """Exige ao menos um dos perfis de cidadão declarados em perfis_permitidos (deny by default)."""

    perfis_permitidos: tuple[str, ...] = ()

    def _verificar_acesso_adicional(self, request):
        if not self.perfis_permitidos:
            return HttpResponseForbidden("Perfil de acesso não configurado para esta rota.")
        for perfil in self.perfis_permitidos:
            campo = MAPA_CAMPOS_PERFIL.get(perfil)
            if campo and getattr(request.user, campo, False):
                return None
        return HttpResponseForbidden(
            "Você não possui o perfil necessário para acessar esta página."
        )


class ContaAdminPendente2faMixin(AutenticadoAtivoMixin):
    """Exige conta ativa com ao menos uma das 8 funções administrativas (ignora is_superuser)."""

    def _verificar_acesso_adicional(self, request):
        if not AutenticacaoService.possui_funcao_administrativa(request.user):
            return HttpResponseForbidden(
                "Apenas contas com função administrativa explícita podem acessar esta página."
            )
        return None


class FuncaoAdminObrigatoriaMixin(AutenticadoAtivoMixin):
    """Exige função administrativa explícita + 2FA concluído na sessão (ADR 0009 / ADR 0010).

    Aceita uma função única em `funcao_admin` ou múltiplas em `funcoes_admin_permitidas`.
    `is_superuser` NÃO concede atalho nem dispensa 2FA.
    """

    funcao_admin: str = ""
    funcoes_admin_permitidas: tuple[str, ...] = ()

    def _obter_funcoes_exigidas(self) -> tuple[str, ...]:
        if self.funcoes_admin_permitidas:
            return tuple(self.funcoes_admin_permitidas)
        if self.funcao_admin:
            return (self.funcao_admin,)
        return ()

    def _verificar_acesso_adicional(self, request):
        funcoes = self._obter_funcoes_exigidas()
        if not funcoes or any(f not in FUNCOES_ADMINISTRATIVAS for f in funcoes):
            return HttpResponseForbidden("Função administrativa inválida para esta rota.")

        autorizado = any(
            AutenticacaoService.possui_funcao(request.user, nome_funcao) for nome_funcao in funcoes
        )
        if not autorizado:
            return HttpResponseForbidden(
                "Você não possui a função administrativa necessária para acessar este recurso."
            )

        if request.session.get(SESSAO_CHAVE_2FA_VERIFICADO) is not True:
            destino_2fa = (
                reverse("contas:totp_verificar")
                if AutenticacaoService.possui_totp_ativo(request.user)
                else reverse("contas:totp_configurar")
            )
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{destino_2fa}?{query}")

        return None
