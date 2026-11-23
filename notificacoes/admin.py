from django.contrib import admin

from notificacoes.models import Notificacao, OutboxEmail


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ("id", "destinatario_id", "tipo", "canal", "status", "criada_em")
    list_filter = ("tipo", "canal", "status", "obrigatoria")
    readonly_fields = (
        "destinatario",
        "tipo",
        "canal",
        "obrigatoria",
        "titulo",
        "mensagem",
        "url_destino",
        "status",
        "criada_em",
        "enviada_em",
        "lida_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OutboxEmail)
class OutboxEmailAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo", "critico_seguranca", "status", "tentativas", "criado_em")
    list_filter = ("tipo", "critico_seguranca", "status")
    readonly_fields = (
        "notificacao",
        "destinatario",
        "email_destino",
        "tipo",
        "critico_seguranca",
        "assunto",
        "corpo_texto",
        "status",
        "tentativas",
        "proxima_tentativa_em",
        "criado_em",
        "enviado_em",
        "erro_ultimo",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
