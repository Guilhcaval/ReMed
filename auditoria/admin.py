from django.contrib import admin

from auditoria.models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("id", "criado_em", "acao", "entidade_tipo", "entidade_id", "ator_id", "origem")
    list_filter = ("origem", "acao", "entidade_tipo")
    search_fields = ("acao", "entidade_tipo", "entidade_id")
    readonly_fields = (
        "criado_em",
        "ator",
        "acao",
        "entidade_tipo",
        "entidade_id",
        "motivo",
        "detalhes",
        "origem",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
