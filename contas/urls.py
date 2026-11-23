from django.urls import path

from contas.views import (
    AdminUsuarioAlterarStatusView,
    AdminUsuarioDetalheView,
    AdminUsuarioFuncoesView,
    AdminUsuarioListaView,
    AdminUsuarioResetar2faView,
    ConfirmarEmailView,
    LoginView,
    LogoutView,
    RecuperarSenhaEmBreveView,
    ReenviarConfirmacaoEmailView,
    TotpConfigurarView,
    TotpRegenerarCodigosView,
    TotpVerificarView,
    UsuarioCadastroView,
    UsuarioEncerrarContaView,
    UsuarioPerfilEditarView,
)

app_name = "contas"

urlpatterns = [
    path("contas/cadastro/", UsuarioCadastroView.as_view(), name="cadastro"),
    path(
        "contas/confirmar-email/<str:token>/",
        ConfirmarEmailView.as_view(),
        name="confirmar_email",
    ),
    path(
        "contas/reenviar-confirmacao/",
        ReenviarConfirmacaoEmailView.as_view(),
        name="reenviar_confirmacao",
    ),
    path("contas/meu-perfil/", UsuarioPerfilEditarView.as_view(), name="perfil_editar"),
    path("contas/encerrar-conta/", UsuarioEncerrarContaView.as_view(), name="encerrar_conta"),
    path("contas/entrar/", LoginView.as_view(), name="login"),
    path("contas/sair/", LogoutView.as_view(), name="logout"),
    path(
        "contas/esqueci-minha-senha/",
        RecuperarSenhaEmBreveView.as_view(),
        name="recuperar_senha_em_breve",
    ),
    path("contas/2fa/configurar/", TotpConfigurarView.as_view(), name="totp_configurar"),
    path("contas/2fa/verificar/", TotpVerificarView.as_view(), name="totp_verificar"),
    path(
        "contas/2fa/codigos-recuperacao/",
        TotpRegenerarCodigosView.as_view(),
        name="totp_regenerar_codigos",
    ),
    # Gestão administrativa de usuários (Spec 04 / RF004)
    path("admin-remed/usuarios/", AdminUsuarioListaView.as_view(), name="admin_usuario_lista"),
    path(
        "admin-remed/usuarios/<int:usuario_id>/",
        AdminUsuarioDetalheView.as_view(),
        name="admin_usuario_detalhe",
    ),
    path(
        "admin-remed/usuarios/<int:usuario_id>/status/",
        AdminUsuarioAlterarStatusView.as_view(),
        name="admin_usuario_status",
    ),
    path(
        "admin-remed/usuarios/<int:usuario_id>/funcoes/",
        AdminUsuarioFuncoesView.as_view(),
        name="admin_usuario_funcoes",
    ),
    path(
        "admin-remed/usuarios/<int:usuario_id>/resetar-2fa/",
        AdminUsuarioResetar2faView.as_view(),
        name="admin_usuario_resetar_2fa",
    ),
]
