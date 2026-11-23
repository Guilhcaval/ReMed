"""Rotas do app pontos_coleta (Specs 05, 06 e 07)."""

from django.urls import path

from pontos_coleta.views import (
    AdminDocumentoListaView,
    AdminPontoColetaAlterarCnpjView,
    AdminPontoColetaAnalisarView,
    AdminPontoColetaDetalheView,
    AdminPontoColetaListaView,
    AdminPontoColetaRevisarView,
    AdminPontoColetaSituacaoView,
    MeusPontosColetaView,
    PontoColetaCadastrarView,
    PontoColetaConviteResponderView,
    PontoColetaEditarView,
    PontoColetaInativarView,
    PontoColetaListaPublicaView,
    PontoColetaResponsaveisView,
    PontoDocumentoAcessarView,
    PontoDocumentoListaEnviarView,
)

app_name = "pontos_coleta"

urlpatterns = [
    path("pontos-coleta/", PontoColetaListaPublicaView.as_view(), name="lista_publica"),
    path("pontos-coleta/cadastrar/", PontoColetaCadastrarView.as_view(), name="cadastrar"),
    path("pontos-coleta/meus/", MeusPontosColetaView.as_view(), name="meus_pontos"),
    path(
        "pontos-coleta/<int:ponto_id>/editar/",
        PontoColetaEditarView.as_view(),
        name="editar",
    ),
    path(
        "pontos-coleta/<int:ponto_id>/inativar/",
        PontoColetaInativarView.as_view(),
        name="inativar",
    ),
    path(
        "pontos-coleta/<int:ponto_id>/responsaveis/",
        PontoColetaResponsaveisView.as_view(),
        name="responsaveis",
    ),
    path(
        "pontos-coleta/convites/<int:convite_id>/responder/",
        PontoColetaConviteResponderView.as_view(),
        name="convite_responder",
    ),
    path(
        "pontos-coleta/<int:ponto_id>/documentos/",
        PontoDocumentoListaEnviarView.as_view(),
        name="documentos",
    ),
    path(
        "pontos-coleta/documentos/<int:doc_id>/acessar/",
        PontoDocumentoAcessarView.as_view(),
        name="documento_acessar",
    ),
    path(
        "admin-remed/pontos-coleta/",
        AdminPontoColetaListaView.as_view(),
        name="admin_lista",
    ),
    path(
        "admin-remed/pontos-coleta/documentos/",
        AdminDocumentoListaView.as_view(),
        name="admin_documentos",
    ),
    path(
        "admin-remed/pontos-coleta/<int:ponto_id>/",
        AdminPontoColetaDetalheView.as_view(),
        name="admin_detalhe",
    ),
    path(
        "admin-remed/pontos-coleta/<int:ponto_id>/cnpj/",
        AdminPontoColetaAlterarCnpjView.as_view(),
        name="admin_alterar_cnpj",
    ),
    path(
        "admin-remed/pontos-coleta/<int:ponto_id>/analisar/",
        AdminPontoColetaAnalisarView.as_view(),
        name="admin_analisar",
    ),
    path(
        "admin-remed/pontos-coleta/<int:ponto_id>/situacao/",
        AdminPontoColetaSituacaoView.as_view(),
        name="admin_situacao",
    ),
    path(
        "admin-remed/pontos-coleta/<int:ponto_id>/revisar/",
        AdminPontoColetaRevisarView.as_view(),
        name="admin_revisar",
    ),
]
