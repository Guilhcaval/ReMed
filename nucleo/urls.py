from django.urls import path

from nucleo.views import ArquivoPrivadoTemporarioView, CepConsultarView, HomeView

app_name = "nucleo"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("enderecos/cep/<str:cep>/", CepConsultarView.as_view(), name="cep_consultar"),
    path(
        "arquivos/privados/<str:token>/",
        ArquivoPrivadoTemporarioView.as_view(),
        name="arquivo_privado_baixar",
    ),
]
