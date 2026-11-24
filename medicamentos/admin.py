"""Registro estritamente somente leitura no Django Admin para medicamentos (OWASP A01/A08)."""

from django.contrib import admin

from medicamentos.models import (
    ConferenciaDoacao,
    DadosRefrigeracaoDoacao,
    Doacao,
    ExecucaoVencimento,
    FotoDoacao,
    ParametroVencimento,
)


class _SomenteLeituraAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Doacao)
class DoacaoAdmin(_SomenteLeituraAdmin):
    list_display = (
        "id",
        "nome_medicamento",
        "principio_ativo",
        "concentracao_dosagem",
        "quantidade_disponivel",
        "data_validade",
        "condicao_conservacao",
        "status",
        "criado_em",
    )
    list_filter = ("status", "condicao_conservacao", "sujeito_receita")
    search_fields = ("nome_medicamento", "principio_ativo", "lote", "fabricante")


@admin.register(FotoDoacao)
class FotoDoacaoAdmin(_SomenteLeituraAdmin):
    list_display = ("id", "doacao", "ordem", "mime_verificado", "tamanho_bytes", "criado_em")


@admin.register(DadosRefrigeracaoDoacao)
class DadosRefrigeracaoDoacaoAdmin(_SomenteLeituraAdmin):
    list_display = ("doacao", "faixa_temperatura_bula", "declaracao_doador_em")


@admin.register(ConferenciaDoacao)
class ConferenciaDoacaoAdmin(_SomenteLeituraAdmin):
    list_display = ("id", "doacao", "resultado", "responsavel", "conferido_em")
    list_filter = ("resultado",)


@admin.register(ParametroVencimento)
class ParametroVencimentoAdmin(_SomenteLeituraAdmin):
    list_display = (
        "id",
        "validade_minima_restante_dias",
        "antecedencia_aviso_dias",
        "atualizado_por",
        "atualizado_em",
    )


@admin.register(ExecucaoVencimento)
class ExecucaoVencimentoAdmin(_SomenteLeituraAdmin):
    list_display = (
        "id",
        "executado_em",
        "doacoes_verificadas",
        "doacoes_marcadas_vencidas",
        "reservas_agendamentos_cancelados",
        "notificacoes_enviadas",
        "resultado",
    )
    list_filter = ("resultado",)
