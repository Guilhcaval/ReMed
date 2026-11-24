"""Configuração raiz de URLs do ReMed."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("contas.urls")),
    path("", include("pontos_coleta.urls")),
    path("", include("medicamentos.urls")),
    path("", include("nucleo.urls")),
    path("notificacoes/", include("notificacoes.urls")),
]
