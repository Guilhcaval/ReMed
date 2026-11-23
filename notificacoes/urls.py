from django.urls import path

from notificacoes.views import (
    NotificacaoListaView,
    NotificacaoMarcarLidaView,
    NotificacaoMarcarTodasLidasView,
)

app_name = "notificacoes"

urlpatterns = [
    path("", NotificacaoListaView.as_view(), name="lista"),
    path("<int:notificacao_id>/ler/", NotificacaoMarcarLidaView.as_view(), name="marcar_lida"),
    path("ler-todas/", NotificacaoMarcarTodasLidasView.as_view(), name="marcar_todas_lidas"),
]
