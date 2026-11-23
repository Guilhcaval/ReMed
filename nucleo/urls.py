from django.urls import path

from nucleo.views import CepConsultarView

app_name = "nucleo"

urlpatterns = [
    path("cep/<str:cep>/", CepConsultarView.as_view(), name="cep_consultar"),
]
