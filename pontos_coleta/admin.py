"""Registro somente leitura / operacional no Django Admin para pontos_coleta."""

from django.contrib import admin

from pontos_coleta.models import (
    AnalisePontoColeta,
    DocumentoPontoColeta,
    HorarioFuncionamentoPonto,
    PontoColeta,
    PontoColetaResponsavel,
)


class _SomenteLeituraAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PontoColeta)
class PontoColetaAdmin(_SomenteLeituraAdmin):
    list_display = ("id", "nome_fantasia", "cnpj", "municipio", "estado", "status", "criado_em")
    list_filter = ("status", "estado", "possui_refrigeracao")
    search_fields = ("nome_fantasia", "razao_social", "cnpj", "municipio")


@admin.register(HorarioFuncionamentoPonto)
class HorarioFuncionamentoPontoAdmin(_SomenteLeituraAdmin):
    list_display = ("ponto_coleta", "dia_semana", "hora_abertura", "hora_fechamento")


@admin.register(PontoColetaResponsavel)
class PontoColetaResponsavelAdmin(_SomenteLeituraAdmin):
    list_display = ("ponto_coleta", "usuario", "status", "vinculado_em", "desvinculado_em")
    list_filter = ("status",)


@admin.register(DocumentoPontoColeta)
class DocumentoPontoColetaAdmin(_SomenteLeituraAdmin):
    list_display = (
        "id",
        "ponto_coleta",
        "tipo_documento",
        "versao",
        "data_validade",
        "status",
        "enviado_em",
    )
    list_filter = ("status", "tipo_documento")


@admin.register(AnalisePontoColeta)
class AnalisePontoColetaAdmin(_SomenteLeituraAdmin):
    list_display = (
        "id",
        "ponto_coleta",
        "tipo_acao",
        "resultado",
        "status_anterior",
        "status_novo",
        "responsavel",
        "criado_em",
    )
    list_filter = ("tipo_acao", "resultado", "status_novo")
