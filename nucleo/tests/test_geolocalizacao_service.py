"""Testes unitários de GeolocalizacaoService (Spec 14 / ADR 0017 / RS010)."""

import io
import json
from decimal import Decimal
from urllib.error import URLError

from django.test import TestCase, override_settings

from nucleo.models import CacheCep, FonteCep
from nucleo.services import GeolocalizacaoService


class _FakeHttpResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._corpo = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class GeolocalizacaoServiceTest(TestCase):
    def setUp(self):
        GeolocalizacaoService.resetar_rate_limit_nominatim()

    def tearDown(self):
        GeolocalizacaoService.resetar_rate_limit_nominatim()

    def test_haversine_e_bounding_box_sem_falso_negativo_nas_bordas(self):
        # Praça da Sé (-23.55, -46.63) até Av. Paulista (-23.56, -46.65) ~2.3 km
        dist = GeolocalizacaoService.calcular_distancia_haversine_km(
            Decimal("-23.55"),
            Decimal("-46.63"),
            Decimal("-23.56"),
            Decimal("-46.65"),
        )
        self.assertGreater(dist, 1.5)
        self.assertLess(dist, 3.5)

        bbox = GeolocalizacaoService.calcular_bounding_box(
            Decimal("-23.55"), Decimal("-46.63"), 3.0
        )
        self.assertLessEqual(bbox.lat_min, Decimal("-23.56"))
        self.assertGreaterEqual(bbox.lat_max, Decimal("-23.56"))
        self.assertLessEqual(bbox.lon_min, Decimal("-46.65"))
        self.assertGreaterEqual(bbox.lon_max, Decimal("-46.65"))

    def test_formatar_faixa_distancia_nunca_expoe_precisao_exata(self):
        self.assertEqual(GeolocalizacaoService.formatar_faixa_distancia(0.42), "menos de 1 km")
        self.assertEqual(GeolocalizacaoService.formatar_faixa_distancia(1.85), "cerca de 2 km")
        self.assertEqual(GeolocalizacaoService.formatar_faixa_distancia(3.10), "cerca de 3 km")
        self.assertEqual(GeolocalizacaoService.formatar_faixa_distancia(6.00), "cerca de 5 km")
        self.assertEqual(GeolocalizacaoService.formatar_faixa_distancia(9.90), "cerca de 10 km")
        self.assertEqual(GeolocalizacaoService.formatar_faixa_distancia(15.2), "mais de 10 km")

    @override_settings(
        REMED_CEP_USER_AGENT="ReMed/1.0 (+https://remed.exemplo)",
        REMED_NOMINATIM_INTERVALO_SEGUNDOS=1,
    )
    def test_fallback_nominatim_envia_user_agent_respeita_rate_limit_e_persiste_cache(self):
        chamadas: list[tuple[str, str]] = []
        esperas: list[float] = []
        tempos = iter([100.0, 100.3, 101.0, 101.0])

        def fake_opener(req, *, timeout):
            _ = timeout
            chamadas.append((req.full_url, req.get_header("User-agent") or ""))
            if "brasilapi.com.br" in req.full_url:
                return _FakeHttpResponse(
                    200,
                    {
                        "cep": "01001000",
                        "state": "SP",
                        "city": "São Paulo",
                        "neighborhood": "Sé",
                        "street": "Praça da Sé",
                        "location": {"coordinates": {}},
                    },
                )
            if "nominatim.openstreetmap.org" in req.full_url:
                return _FakeHttpResponse(
                    200,
                    [{"lat": "-23.550520", "lon": "-46.633308"}],
                )
            raise AssertionError(f"URL inesperada: {req.full_url}")

        res1 = GeolocalizacaoService.obter_coordenadas_por_cep(
            "01001-000",
            http_opener=fake_opener,
            sleep_fn=esperas.append,
            monotonic_fn=lambda: next(tempos),
        )
        self.assertEqual(res1.latitude_aprox, Decimal("-23.55"))
        self.assertEqual(res1.longitude_aprox, Decimal("-46.63"))
        self.assertEqual(res1.fonte, FonteCep.NOMINATIM)
        self.assertTrue(
            any("nominatim.openstreetmap.org" in url and "ReMed/1.0" in ua for url, ua in chamadas)
        )

        # Segunda chamada ao mesmo CEP vem do cache sem nenhuma requisição HTTP
        total_antes = len(chamadas)
        res2 = GeolocalizacaoService.obter_coordenadas_por_cep(
            "01001-000",
            http_opener=fake_opener,
            sleep_fn=esperas.append,
            monotonic_fn=lambda: next(tempos),
        )
        self.assertTrue(res2.do_cache)
        self.assertEqual(len(chamadas), total_antes)

        # Rate limit <= 1 req/s em chamada consecutiva ao Nominatim para outro CEP
        CacheCep.objects.create(
            cep="01310100",
            bairro="Bela Vista",
            municipio="São Paulo",
            estado="SP",
            fonte=FonteCep.VIACEP,
        )
        GeolocalizacaoService.obter_coordenadas_por_cep(
            "01310100",
            http_opener=fake_opener,
            sleep_fn=esperas.append,
            monotonic_fn=lambda: next(tempos),
        )
        self.assertEqual(len(esperas), 1)
        self.assertAlmostEqual(esperas[0], 0.7, places=2)

    def test_degradacao_graciosa_quando_nominatim_falha(self):
        def fake_opener(req, *, timeout):
            _ = timeout
            if "brasilapi.com.br" in req.full_url:
                return _FakeHttpResponse(
                    200,
                    {
                        "cep": "01001000",
                        "state": "SP",
                        "city": "São Paulo",
                        "neighborhood": "Sé",
                        "street": "Praça da Sé",
                        "location": {},
                    },
                )
            raise URLError("timeout simulado")

        res = GeolocalizacaoService.obter_coordenadas_por_cep(
            "01001000",
            http_opener=fake_opener,
            sleep_fn=lambda _: None,
        )
        self.assertEqual(res.municipio, "São Paulo")
        self.assertIsNone(res.latitude_aprox)
        self.assertIsNone(res.longitude_aprox)
        _ = io.BytesIO()
