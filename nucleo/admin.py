from django.contrib import admin

from nucleo.models import (
    CacheCep,
    ExecucaoRotina,
    FormaFarmaceutica,
    TipoDocumentoPonto,
    TipoEstabelecimento,
)


@admin.register(FormaFarmaceutica)
class FormaFarmaceuticaAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(TipoEstabelecimento)
class TipoEstabelecimentoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(TipoDocumentoPonto)
class TipoDocumentoPontoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "obrigatorio", "ativo")
    list_filter = ("obrigatorio", "ativo")
    search_fields = ("nome",)


@admin.register(CacheCep)
class CacheCepAdmin(admin.ModelAdmin):
    list_display = ("cep", "municipio", "estado", "fonte", "atualizado_em")
    search_fields = ("cep", "municipio", "bairro")
    readonly_fields = ("atualizado_em",)


@admin.register(ExecucaoRotina)
class ExecucaoRotinaAdmin(admin.ModelAdmin):
    list_display = ("nome_rotina", "iniciada_em", "finalizada_em", "tentativa", "resultado")
    list_filter = ("nome_rotina", "resultado")
    readonly_fields = (
        "nome_rotina",
        "iniciada_em",
        "finalizada_em",
        "tentativa",
        "resultado",
        "contadores",
        "resumo_erro",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
