"""Configuração raiz de URLs do ReMed."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("contas/", include("contas.urls")),
    path("enderecos/", include("nucleo.urls")),
]
