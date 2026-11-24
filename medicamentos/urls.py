"""Rotas do app medicamentos (Specs 08, 09, 10, 11 e 14)."""

from django.urls import path

from medicamentos.views import (
    AdminConferenciaDetalheView,
    AdminConferenciaListaView,
    AdminConferenciaMarcarVencidaView,
    AdminConferenciaRegistrarView,
    AdminVencimentoExecucoesView,
    AdminVencimentoParametrosView,
    DefinirLocalizacaoBuscaView,
    DoacaoCancelarView,
    DoacaoCriarView,
    DoacaoEditarView,
    DoacaoFotoAcessarView,
    DoacaoLerEmbalagemIaView,
    LimparLocalizacaoBuscaView,
    MedicamentoBuscaView,
    MinhasDoacoesListaView,
)

app_name = "medicamentos"

urlpatterns = [
    path("medicamentos/", MedicamentoBuscaView.as_view(), name="busca"),
    path(
        "medicamentos/localizacao/",
        DefinirLocalizacaoBuscaView.as_view(),
        name="definir_localizacao",
    ),
    path(
        "medicamentos/localizacao/limpar/",
        LimparLocalizacaoBuscaView.as_view(),
        name="limpar_localizacao",
    ),
    path("doacoes/nova/", DoacaoCriarView.as_view(), name="doacao_criar"),
    path(
        "doacoes/ler-embalagem-ia/",
        DoacaoLerEmbalagemIaView.as_view(),
        name="doacao_ler_ia",
    ),
    path("doacoes/minhas/", MinhasDoacoesListaView.as_view(), name="minhas_doacoes"),
    path("doacoes/<int:doacao_id>/editar/", DoacaoEditarView.as_view(), name="doacao_editar"),
    path("doacoes/<int:doacao_id>/cancelar/", DoacaoCancelarView.as_view(), name="doacao_cancelar"),
    path(
        "doacoes/fotos/<int:foto_id>/acessar/",
        DoacaoFotoAcessarView.as_view(),
        name="doacao_foto_acessar",
    ),
    path(
        "admin-remed/doacoes/conferencia/",
        AdminConferenciaListaView.as_view(),
        name="admin_conferencia_lista",
    ),
    path(
        "admin-remed/doacoes/<int:doacao_id>/conferencia/",
        AdminConferenciaDetalheView.as_view(),
        name="admin_conferencia_detalhe",
    ),
    path(
        "admin-remed/doacoes/<int:doacao_id>/conferencia/registrar/",
        AdminConferenciaRegistrarView.as_view(),
        name="admin_conferencia_registrar",
    ),
    path(
        "admin-remed/doacoes/<int:doacao_id>/conferencia/vencer/",
        AdminConferenciaMarcarVencidaView.as_view(),
        name="admin_conferencia_vencer",
    ),
    path(
        "admin-remed/vencimento/parametros/",
        AdminVencimentoParametrosView.as_view(),
        name="admin_vencimento_parametros",
    ),
    path(
        "admin-remed/vencimento/execucoes/",
        AdminVencimentoExecucoesView.as_view(),
        name="admin_vencimento_execucoes",
    ),
]
