"""Configuração raiz de URLs do ReMed."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("contas.urls")),
    path("notificacoes/", include("notificacoes.urls")),
    path("enderecos/", include("nucleo.urls")),
]
