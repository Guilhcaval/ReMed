from django.contrib import admin

from contas.models import AceiteTermo, Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "is_staff", "email_confirmado_em", "criado_em")
    list_filter = ("status", "is_staff", "perfil_doador", "perfil_solicitante", "perfil_cuidador")
    readonly_fields = (
        "nome_completo",
        "cpf",
        "data_nascimento",
        "email",
        "email_confirmado_em",
        "celular",
        "perfil_doador",
        "perfil_solicitante",
        "perfil_cuidador",
        "status",
        "is_staff",
        "is_active",
        "is_superuser",
        "criado_em",
        "atualizado_em",
        "anonimizado_em",
        "last_login",
    )
    exclude = ("password",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AceiteTermo)
class AceiteTermoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "usuario_id",
        "versao_termos_uso",
        "versao_politica_privacidade",
        "aceito_em",
    )
    readonly_fields = (
        "usuario",
        "versao_termos_uso",
        "versao_politica_privacidade",
        "aceito_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
