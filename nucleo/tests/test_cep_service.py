"""Testes unitários do CepService com dublês HTTP (zero acesso à rede — ADR 0018)."""

import json
from datetime import timedelta
from decimal import Decimal
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from nucleo.exceptions import CepInvalido, CepNaoEncontrado, ServicoCepIndisponivel
from nucleo.models import CacheCep, FonteCep
from nucleo.services import CepService


class _RespostaHttpFalsa:
    def __init__(self, payload: dict, status: int = 200):
        self._bytes = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class CepServiceTest(TestCase):
    def test_retorna_do_cache_sem_chamada_http(self):
        CacheCep.objects.create(
            cep="01001000",
            logradouro="Praça da Sé",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            latitude_aprox=Decimal("-23.55"),
            longitude_aprox=Decimal("-46.63"),
            fonte=FonteCep.BRASILAPI,
        )

        def _nao_deve_chamar(_req, timeout):
            raise AssertionError("Não deveria consultar HTTP em cache hit.")

        dados = CepService.consultar("01001-000", http_opener=_nao_deve_chamar)
        self.assertTrue(dados.do_cache)
        self.assertEqual(dados.logradouro, "Praça da Sé")
        self.assertEqual(dados.municipio, "São Paulo")
        self.assertEqual(dados.estado, "SP")

    def test_miss_consulta_brasilapi_salva_cache_e_arredonda_coordenadas(self):
        chamadas = []

        def _opener(req, timeout):
            chamadas.append((req.full_url, req.get_header("User-agent"), timeout))
            return _RespostaHttpFalsa(
                {
                    "cep": "01001000",
                    "street": "Praça da Sé",
                    "neighborhood": "Sé",
                    "city": "São Paulo",
                    "state": "SP",
                    "location": {
                        "coordinates": {
                            "latitude": "-23.550520",
                            "longitude": "-46.633308",
                        }
                    },
                }
            )

        dados = CepService.consultar("01001000", http_opener=_opener)
        self.assertFalse(dados.do_cache)
        self.assertEqual(dados.fonte, FonteCep.BRASILAPI)
        self.assertEqual(dados.latitude_aprox, Decimal("-23.55"))
        self.assertEqual(dados.longitude_aprox, Decimal("-46.63"))
        self.assertEqual(len(chamadas), 1)
        self.assertIn("brasilapi.com.br", chamadas[0][0])
        self.assertEqual(chamadas[0][1], settings.REMED_CEP_USER_AGENT)
        self.assertEqual(chamadas[0][2], settings.REMED_CEP_TIMEOUT_SEGUNDOS)
        self.assertTrue(CacheCep.objects.filter(cep="01001000").exists())

    def test_fallback_para_viacep_quando_brasilapi_falha(self):
        """CA-01-10: timeout/erro na BrasilAPI aciona fallback ViaCEP e salva cache."""
        urls_chamadas = []

        def _opener(req, timeout):
            urls_chamadas.append(req.full_url)
            if "brasilapi.com.br" in req.full_url:
                raise TimeoutError("timeout simulado")
            return _RespostaHttpFalsa(
                {
                    "cep": "30140-071",
                    "logradouro": "Avenida Afonso Pena",
                    "bairro": "Centro",
                    "localidade": "Belo Horizonte",
                    "uf": "MG",
                }
            )

        dados = CepService.consultar("30140-071", http_opener=_opener)
        self.assertEqual(len(urls_chamadas), 2)
        self.assertEqual(dados.fonte, FonteCep.VIACEP)
        self.assertEqual(dados.municipio, "Belo Horizonte")
        self.assertEqual(dados.estado, "MG")
        self.assertTrue(CacheCep.objects.filter(cep="30140071", fonte=FonteCep.VIACEP).exists())

    def test_ambos_provedores_falhando_lanca_indisponivel(self):
        def _opener(_req, timeout):
            raise URLError("sem conexão")

        with self.assertRaises(ServicoCepIndisponivel):
            CepService.consultar("01001000", http_opener=_opener)

    def test_cep_inexistente_em_ambos_lanca_nao_encontrado(self):
        def _opener(req, timeout):
            if "brasilapi.com.br" in req.full_url:
                raise HTTPError(req.full_url, 404, "Not Found", {}, None)
            return _RespostaHttpFalsa({"erro": True})

        with self.assertRaises(CepNaoEncontrado):
            CepService.consultar("99999999", http_opener=_opener)

    def test_cache_expirado_reconsulta_provedor(self):
        CacheCep.objects.create(
            cep="01001000",
            logradouro="Antigo",
            bairro="Sé",
            municipio="São Paulo",
            estado="SP",
            fonte=FonteCep.VIACEP,
        )
        CacheCep.objects.filter(cep="01001000").update(
            atualizado_em=timezone.now() - timedelta(days=settings.REMED_CEP_CACHE_TTL_DIAS + 1)
        )

        def _opener(_req, timeout):
            return _RespostaHttpFalsa(
                {
                    "street": "Praça da Sé Atualizada",
                    "neighborhood": "Sé",
                    "city": "São Paulo",
                    "state": "SP",
                }
            )

        dados = CepService.consultar("01001000", http_opener=_opener)
        self.assertFalse(dados.do_cache)
        self.assertEqual(dados.logradouro, "Praça da Sé Atualizada")

    def test_cep_malformado_lanca_erro_invalido(self):
        with self.assertRaises(CepInvalido):
            CepService.consultar("123")
