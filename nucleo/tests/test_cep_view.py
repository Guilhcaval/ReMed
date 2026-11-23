"""Testes de integração da view proxy de CEP (ADR 0018)."""

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from nucleo.exceptions import CepNaoEncontrado, ServicoCepIndisponivel
from nucleo.models import FonteCep
from nucleo.services import DadosCep


class CepConsultarViewTest(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_cep_valido_retorna_json_sem_coordenadas(self):
        dados_fake = DadosCep(
            cep="01001000",
            logradouro="Praça da Sé",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            latitude_aprox=Decimal("-23.55"),
            longitude_aprox=Decimal("-46.63"),
            fonte=FonteCep.BRASILAPI,
            do_cache=True,
        )
        with patch("nucleo.views.CepService.consultar", return_value=dados_fake):
            resposta = self.client.get(reverse("nucleo:cep_consultar", kwargs={"cep": "01001000"}))

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["logradouro"], "Praça da Sé")
        self.assertEqual(corpo["municipio"], "São Paulo")
        self.assertEqual(corpo["estado"], "SP")
        self.assertNotIn("latitude_aprox", corpo)
        self.assertNotIn("longitude_aprox", corpo)

    def test_cep_malformado_retorna_400(self):
        resposta = self.client.get(reverse("nucleo:cep_consultar", kwargs={"cep": "123"}))
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("erro", resposta.json())

    def test_cep_nao_encontrado_retorna_404(self):
        with patch(
            "nucleo.views.CepService.consultar",
            side_effect=CepNaoEncontrado("CEP não encontrado."),
        ):
            resposta = self.client.get(reverse("nucleo:cep_consultar", kwargs={"cep": "99999999"}))
        self.assertEqual(resposta.status_code, 404)
        self.assertTrue(resposta.json()["preenchimento_manual"])

    def test_servico_indisponivel_retorna_503_com_preenchimento_manual(self):
        with patch(
            "nucleo.views.CepService.consultar",
            side_effect=ServicoCepIndisponivel("Indisponível"),
        ):
            resposta = self.client.get(reverse("nucleo:cep_consultar", kwargs={"cep": "01001000"}))
        self.assertEqual(resposta.status_code, 503)
        self.assertTrue(resposta.json()["preenchimento_manual"])

    @override_settings(REMED_CEP_RATE_LIMIT_IP_MINUTO=2)
    def test_rate_limit_por_ip_retorna_429(self):
        dados_fake = DadosCep(
            cep="01001000",
            logradouro="Praça da Sé",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            latitude_aprox=None,
            longitude_aprox=None,
            fonte=FonteCep.BRASILAPI,
            do_cache=True,
        )
        url = reverse("nucleo:cep_consultar", kwargs={"cep": "01001000"})
        with patch("nucleo.views.CepService.consultar", return_value=dados_fake):
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.get(url).status_code, 200)
            terceira = self.client.get(url)
        self.assertEqual(terceira.status_code, 429)
        self.assertTrue(terceira.json()["preenchimento_manual"])
