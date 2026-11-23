from django.contrib import admin

from contas.models import (
    AcaoGestaoUsuario,
    AceiteTermo,
    DispositivoTotp,
    RegistroAcesso,
    SessaoUsuario,
    Usuario,
)


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


@admin.register(RegistroAcesso)
class RegistroAcessoAdmin(admin.ModelAdmin):
    list_display = ("id", "criado_em", "usuario_id", "ip_origem", "etapa", "resultado")
    list_filter = ("etapa", "resultado")
    readonly_fields = (
        "criado_em",
        "identificador_hash",
        "usuario",
        "ip_origem",
        "etapa",
        "resultado",
        "motivo_interno",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DispositivoTotp)
class DispositivoTotpAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario_id", "confirmado_em", "criado_em")
    readonly_fields = (
        "usuario",
        "confirmado_em",
        "ultimo_passo_usado",
        "criado_em",
        "atualizado_em",
    )
    exclude = ("segredo",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SessaoUsuario)
class SessaoUsuarioAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario_id", "criado_em")
    readonly_fields = ("usuario", "criado_em")
    exclude = ("session_key",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AcaoGestaoUsuario)
class AcaoGestaoUsuarioAdmin(admin.ModelAdmin):
    list_display = ("id", "criado_em", "acao", "usuario_alvo_id", "responsavel_id")
    list_filter = ("acao", "status_novo")
    readonly_fields = (
        "usuario_alvo",
        "responsavel",
        "acao",
        "status_anterior",
        "status_novo",
        "funcoes_anteriores",
        "funcoes_novas",
        "motivo",
        "criado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
