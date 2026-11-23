"""Mixins declarativos de controle de acesso para CBVs (ADR 0007 / ADR 0010)."""

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from contas.models import StatusUsuario


class VisitanteObrigatorioMixin:
    """Redireciona usuários já autenticados para a tela de perfil."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("contas:perfil_editar")
        return super().dispatch(request, *args, **kwargs)


class AutenticadoAtivoMixin:
    """Exige usuário autenticado, ativo, com e-mail confirmado e não anonimizado."""

    def dispatch(self, request, *args, **kwargs):
        usuario = request.user
        if not usuario.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

        conta_valida = (
            getattr(usuario, "status", None) == StatusUsuario.ATIVO
            and getattr(usuario, "email_confirmado_em", None) is not None
            and getattr(usuario, "anonimizado_em", None) is None
        )
        if not conta_valida:
            return HttpResponseForbidden(
                "Sua conta não tem permissão para acessar este recurso no estado atual."
            )
        return super().dispatch(request, *args, **kwargs)
