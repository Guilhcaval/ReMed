from django.urls import path

from contas.views import (
    ConfirmarEmailView,
    ReenviarConfirmacaoEmailView,
    UsuarioCadastroView,
    UsuarioEncerrarContaView,
    UsuarioPerfilEditarView,
)

app_name = "contas"

urlpatterns = [
    path("cadastro/", UsuarioCadastroView.as_view(), name="cadastro"),
    path("confirmar-email/<str:token>/", ConfirmarEmailView.as_view(), name="confirmar_email"),
    path(
        "reenviar-confirmacao/",
        ReenviarConfirmacaoEmailView.as_view(),
        name="reenviar_confirmacao",
    ),
    path("meu-perfil/", UsuarioPerfilEditarView.as_view(), name="perfil_editar"),
    path("encerrar-conta/", UsuarioEncerrarContaView.as_view(), name="encerrar_conta"),
]
