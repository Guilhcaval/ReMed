"""Testes unitários e de integração do RF009 — Leitura da Embalagem por IA (Spec 23 / ADR 0021)."""

import io
import json
import logging
from datetime import date, timedelta
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from auditoria.models import RegistroAuditoria
from contas.models import StatusUsuario, Usuario
from medicamentos.exceptions import FotoDoacaoFormatoInvalido, ServicoIaIndisponivel
from medicamentos.ia_embalagem import (
    AVISO_LGPD_IA_EMBALAGEM,
    LeituraEmbalagemIaService,
    ProvedorIaGemini,
    ProvedorIaOpenAiCompat,
)
from medicamentos.models import CondicaoConservacao, Doacao, StatusDoacao
from nucleo.exceptions import (
    ArquivoMalwareDetectado,
    ArquivoScannerIndisponivel,
    ArquivoTamanhoExcedido,
    LimiteTaxaExcedido,
    PermissaoNegada,
    RegraNegocioViolada,
)
from nucleo.models import FormaFarmaceutica


def _gerar_jpeg_bytes(*, com_exif_gps: bool = False) -> bytes:
    img = Image.new("RGB", (60, 40), color=(30, 120, 90))
    buf = io.BytesIO()
    if com_exif_gps:
        exif = img.getexif()
        exif[271] = "CameraTeste"  # Make
        exif[272] = "ModeloGPS"  # Model
        exif[305] = "SoftwarePrivado"  # Software
        img.save(buf, format="JPEG", exif=exif.tobytes())
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


class _FakeHttpResponse:
    def __init__(self, payload: dict | bytes, status: int = 200):
        self.status = status
        if isinstance(payload, bytes):
            self._bytes = payload
        else:
            self._bytes = json.dumps(payload).encode("utf-8")

    def read(self, limit: int = -1) -> bytes:
        if limit is None or limit < 0:
            return self._bytes
        return self._bytes[:limit]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _ProvedorStub:
    nome = "stub_offline"

    def __init__(self, resposta=None, erro: Exception | None = None):
        self.resposta = resposta
        self.erro = erro
        self.chamadas: list[dict] = []

    def analisar_embalagem(self, imagem_bytes: bytes, mime_type: str, *, timeout_segundos: int):
        self.chamadas.append(
            {
                "imagem_bytes": imagem_bytes,
                "mime_type": mime_type,
                "timeout_segundos": timeout_segundos,
            }
        )
        if self.erro is not None:
            raise self.erro
        return self.resposta


class _ScannerMalwareStub:
    def verificar(self, conteudo: bytes, *, nome_seguro: str) -> None:
        _ = (conteudo, nome_seguro)
        raise ArquivoMalwareDetectado()


class _ScannerQuebradoStub:
    def verificar(self, conteudo: bytes, *, nome_seguro: str) -> None:
        _ = (conteudo, nome_seguro)
        raise RuntimeError("clamd fora do ar")


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
    REMED_IA_CONFIANCA_MINIMA=0.80,
    REMED_IA_LEITURAS_MAX_POR_HORA=10,
    REMED_IA_TIMEOUT_SEGUNDOS=12,
)
class LeituraEmbalagemIaServiceTest(TestCase):
    def setUp(self):
        cache.clear()
        self.doador = Usuario.objects.create_user(
            email="doador.ia@exemplo.com",
            cpf="52998224725",
            password="Rm3d!Senha1",
            nome_completo="Ana Doadora",
            data_nascimento=date(1990, 3, 15),
            celular="11988887777",
            perfil_doador=True,
            status=StatusUsuario.ATIVO,
            is_active=True,
            email_confirmado_em=timezone.now(),
        )
        self.solicitante = Usuario.objects.create_user(
            email="sol.ia@exemplo.com",
            cpf="11144477735",
            password="Rm3d!Senha1",
            nome_completo="Carlos Solicitante",
            data_nascimento=date(1991, 6, 10),
            celular="11977776666",
            perfil_doador=False,
            perfil_solicitante=True,
            status=StatusUsuario.ATIVO,
            is_active=True,
            email_confirmado_em=timezone.now(),
        )

    def tearDown(self):
        cache.clear()

    def test_ca_23_01_sugestao_baixa_confianca_validade_obrigatoria_e_campos_nulos(self):
        """CA-23-01: baixa confiança, confirmação de validade, nulos e datas ambíguas vazios."""
        stub = _ProvedorStub(
            resposta={
                "nome_medicamento": {"valor": "Losartana Potássica", "confianca": 0.94},
                "principio_ativo": {"valor": "Losartana potássica", "confianca": 0.91},
                "concentracao_dosagem": {"valor": "50 mg", "confianca": 0.88},
                "lote": {"valor": "L2026B9", "confianca": 0.55},
                "data_validade": {"valor": "2027-08-30", "confianca": 0.95},
                "fabricante": {"valor": None, "confianca": 0.0},
            }
        )
        res = LeituraEmbalagemIaService.extrair_sugestoes(
            self.doador,
            conteudo_imagem=_gerar_jpeg_bytes(),
            nome_arquivo="embalagem.jpg",
            consentimento_envio=True,
            provedor=stub,
        )

        self.assertTrue(res.possui_sugestoes)
        self.assertEqual(res.nome_medicamento.valor, "Losartana Potássica")
        self.assertFalse(res.nome_medicamento.baixa_confianca)
        self.assertEqual(res.lote.valor, "L2026B9")
        self.assertTrue(res.lote.baixa_confianca)
        self.assertTrue(res.lote.exige_confirmacao)
        # Validade exige SEMPRE confirmação mesmo com confiança 0.95
        self.assertEqual(res.data_validade.valor, "2027-08-30")
        self.assertFalse(res.data_validade.baixa_confianca)
        self.assertTrue(res.data_validade.exige_confirmacao)
        self.assertTrue(res.validade_sugerida)
        # Campo nulo permanece em branco
        self.assertEqual(res.fabricante.valor, "")
        self.assertFalse(res.fabricante.baixa_confianca)
        self.assertEqual(res.campos_baixa_confianca, ("lote",))

        aud = RegistroAuditoria.objects.filter(acao="ia_embalagem.executada").first()
        self.assertIsNotNone(aud)
        self.assertTrue(aud.detalhes["sucesso"])
        self.assertIn("lote", aud.detalhes["campos_baixa_confianca"])
        self.assertNotIn("52998224725", str(aud.detalhes))
        self.assertNotIn("doador.ia@exemplo.com", str(aud.detalhes))

        # Data parcial MM/YYYY nunca é estimada -> retorna em branco
        stub_ambiguo = _ProvedorStub(
            resposta={"data_validade": {"valor": "12/2027", "confianca": 0.99}}
        )
        res_amb = LeituraEmbalagemIaService.extrair_sugestoes(
            self.doador,
            conteudo_imagem=_gerar_jpeg_bytes(),
            nome_arquivo="embalagem.jpg",
            consentimento_envio=True,
            provedor=stub_ambiguo,
        )
        self.assertEqual(res_amb.data_validade.valor, "")
        self.assertFalse(res_amb.validade_sugerida)

    def test_ca_23_03_remove_exif_antes_de_enviar_e_bloqueia_arquivos_invalidos(self):
        """CA-23-03: remove EXIF/GPS antes do provedor e bloqueia arquivos inválidos."""
        jpg_com_exif = _gerar_jpeg_bytes(com_exif_gps=True)
        with Image.open(io.BytesIO(jpg_com_exif)) as original:
            self.assertGreater(len(original.getexif()), 0)

        stub = _ProvedorStub(resposta={"nome_medicamento": {"valor": "Dipirona", "confianca": 0.9}})
        LeituraEmbalagemIaService.extrair_sugestoes(
            self.doador,
            conteudo_imagem=jpg_com_exif,
            nome_arquivo="foto_celular.jpg",
            consentimento_envio=True,
            provedor=stub,
        )
        self.assertEqual(len(stub.chamadas), 1)
        enviado = stub.chamadas[0]["imagem_bytes"]
        with Image.open(io.BytesIO(enviado)) as limpa:
            self.assertEqual(len(limpa.getexif()), 0)
        self.assertNotIn(b"CameraTeste", enviado)
        self.assertNotIn(b"ModeloGPS", enviado)

        # PDF, executável renomeado para .jpg e arquivo > 5 MB nunca chegam ao provedor
        stub_vazio = _ProvedorStub(resposta={})
        with self.assertRaises(FotoDoacaoFormatoInvalido):
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.doador,
                conteudo_imagem=b"%PDF-1.4\nconteudo\n%%EOF",
                nome_arquivo="receita.pdf",
                consentimento_envio=True,
                provedor=stub_vazio,
            )
        with self.assertRaises(FotoDoacaoFormatoInvalido):
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.doador,
                conteudo_imagem=b"MZ\x90\x00binario-falso",
                nome_arquivo="falso.jpg",
                consentimento_envio=True,
                provedor=stub_vazio,
            )
        with self.assertRaises(ArquivoTamanhoExcedido):
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.doador,
                conteudo_imagem=b"\xff\xd8\xff" + (b"0" * (5 * 1024 * 1024 + 10)),
                nome_arquivo="grande.jpg",
                consentimento_envio=True,
                provedor=stub_vazio,
            )
        with self.assertRaises(ArquivoMalwareDetectado):
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.doador,
                conteudo_imagem=_gerar_jpeg_bytes(),
                nome_arquivo="foto.jpg",
                consentimento_envio=True,
                provedor=stub_vazio,
                scanner=_ScannerMalwareStub(),
            )
        with self.assertRaises(ArquivoScannerIndisponivel):
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.doador,
                conteudo_imagem=_gerar_jpeg_bytes(),
                nome_arquivo="foto.jpg",
                consentimento_envio=True,
                provedor=stub_vazio,
                scanner=_ScannerQuebradoStub(),
            )
        self.assertEqual(len(stub_vazio.chamadas), 0)

    def test_ca_23_02_fallback_sem_chave_timeout_e_erro_provedor(self):
        """CA-23-02: sem chave configurada ou em erro/timeout devolve ServicoIaIndisponivel."""
        with override_settings(REMED_IA_PROVEDOR="", REMED_IA_API_KEY=""):
            self.assertFalse(LeituraEmbalagemIaService.ia_configurada())
            with self.assertRaises(ServicoIaIndisponivel):
                LeituraEmbalagemIaService.extrair_sugestoes(
                    self.doador,
                    conteudo_imagem=_gerar_jpeg_bytes(),
                    nome_arquivo="foto.jpg",
                    consentimento_envio=True,
                )
        self.assertTrue(RegistroAuditoria.objects.filter(acao="ia_embalagem.indisponivel").exists())

        stub_timeout = _ProvedorStub(erro=TimeoutError("timeout 12s"))
        with self.assertRaises(ServicoIaIndisponivel):
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.doador,
                conteudo_imagem=_gerar_jpeg_bytes(),
                nome_arquivo="foto.jpg",
                consentimento_envio=True,
                provedor=stub_timeout,
            )
        self.assertTrue(RegistroAuditoria.objects.filter(acao="ia_embalagem.falha").exists())

    def test_permissoes_consentimento_e_rate_limit_por_doador(self):
        stub = _ProvedorStub(resposta={})
        with self.assertRaises(PermissaoNegada):
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.solicitante,
                conteudo_imagem=_gerar_jpeg_bytes(),
                nome_arquivo="foto.jpg",
                consentimento_envio=True,
                provedor=stub,
            )
        with self.assertRaises(RegraNegocioViolada):
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.doador,
                conteudo_imagem=_gerar_jpeg_bytes(),
                nome_arquivo="foto.jpg",
                consentimento_envio=False,
                provedor=stub,
            )

        with override_settings(REMED_IA_LEITURAS_MAX_POR_HORA=2):
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.doador,
                conteudo_imagem=_gerar_jpeg_bytes(),
                nome_arquivo="foto.jpg",
                consentimento_envio=True,
                provedor=stub,
            )
            LeituraEmbalagemIaService.extrair_sugestoes(
                self.doador,
                conteudo_imagem=_gerar_jpeg_bytes(),
                nome_arquivo="foto.jpg",
                consentimento_envio=True,
                provedor=stub,
            )
            with self.assertRaises(LimiteTaxaExcedido):
                LeituraEmbalagemIaService.extrair_sugestoes(
                    self.doador,
                    conteudo_imagem=_gerar_jpeg_bytes(),
                    nome_arquivo="foto.jpg",
                    consentimento_envio=True,
                    provedor=stub,
                )

    def test_adaptadores_http_gemini_e_openai_compat_offline(self):
        """Adaptadores stdlib usam header para chave, respeitam timeout e validam HTTPS."""
        requisicoes_capturadas: list[tuple] = []

        def _opener_gemini(req, *, timeout):
            requisicoes_capturadas.append((req, timeout))
            texto_json = (
                '```json\n{"nome_medicamento": {"valor": "Dipirona", "confianca": 0.92}}\n```'
            )
            return _FakeHttpResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": texto_json},
                                ]
                            }
                        }
                    ]
                }
            )

        chave_secreta = "CHAVE-SECRETA-GEMINI-NAO-VAZAR"
        registros_log: list[str] = []

        class _CapturadorLog(logging.Handler):
            def emit(self, record):
                registros_log.append(self.format(record))

        handler = _CapturadorLog()
        logging.getLogger().addHandler(handler)
        try:
            gemini = ProvedorIaGemini(
                api_key=chave_secreta,
                modelo="gemini-2.5-flash",
                http_opener=_opener_gemini,
            )
            dados_g = gemini.analisar_embalagem(
                _gerar_jpeg_bytes(), "image/jpeg", timeout_segundos=12
            )
        finally:
            logging.getLogger().removeHandler(handler)

        self.assertEqual(dados_g["nome_medicamento"]["valor"], "Dipirona")
        req_g, timeout_g = requisicoes_capturadas[0]
        self.assertEqual(timeout_g, 12)
        self.assertEqual(req_g.get_header("X-goog-api-key"), chave_secreta)
        self.assertNotIn(chave_secreta, req_g.full_url)
        for linha in registros_log:
            self.assertNotIn(chave_secreta, linha)

        # OpenAI-compatível com sucesso e falhas HTTP/URLError/resposta gigante
        def _opener_openai(req, *, timeout):
            requisicoes_capturadas.append((req, timeout))
            return _FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"fabricante": {"valor": "Medley", "confianca": 0.87}}
                                )
                            }
                        }
                    ]
                }
            )

        openai_prov = ProvedorIaOpenAiCompat(
            api_key="sk-teste-offline",
            modelo="gpt-4o-mini",
            http_opener=_opener_openai,
        )
        dados_o = openai_prov.analisar_embalagem(
            _gerar_jpeg_bytes(), "image/jpeg", timeout_segundos=10
        )
        self.assertEqual(dados_o["fabricante"]["valor"], "Medley")
        req_o, timeout_o = requisicoes_capturadas[1]
        self.assertEqual(timeout_o, 10)
        self.assertEqual(req_o.get_header("Authorization"), "Bearer sk-teste-offline")

        # HTTP 503 / URLError / resposta > 64 KB -> ServicoIaIndisponivel
        def _opener_503(_req, *, timeout):
            _ = timeout
            raise HTTPError(
                "https://api.openai.com/v1/chat/completions", 503, "Unavailable", {}, None
            )

        def _opener_rede(_req, *, timeout):
            _ = timeout
            raise URLError("sem rede")

        def _opener_gigante(_req, *, timeout):
            _ = timeout
            return _FakeHttpResponse(b"x" * 70_000)

        for opener_erro in (_opener_503, _opener_rede, _opener_gigante):
            prov_err = ProvedorIaOpenAiCompat(api_key="sk-teste", http_opener=opener_erro)
            with self.assertRaises(ServicoIaIndisponivel):
                prov_err.analisar_embalagem(_gerar_jpeg_bytes(), "image/jpeg", timeout_segundos=5)

        # Endpoint HTTP inseguro rejeitado fora de DEBUG
        with override_settings(DEBUG=False):
            prov_http = ProvedorIaOpenAiCompat(
                api_key="sk-teste",
                endpoint="http://127.0.0.1:11434/v1/chat/completions",
                http_opener=_opener_openai,
            )
            with self.assertRaises(ServicoIaIndisponivel):
                prov_http.analisar_embalagem(_gerar_jpeg_bytes(), "image/jpeg", timeout_segundos=5)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REMED_IDENTIFICADOR_HMAC_KEY="chave-hmac-dedicada-testes",
    REMED_IA_CONFIANCA_MINIMA=0.80,
    REMED_IA_LEITURAS_MAX_POR_HORA=10,
)
class DoacaoIaViewsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.doador = Usuario.objects.create_user(
            email="doador.view@exemplo.com",
            cpf="52998224725",
            password="Rm3d!Senha1",
            nome_completo="Ana Doadora",
            data_nascimento=date(1990, 3, 15),
            celular="11988887777",
            perfil_doador=True,
            status=StatusUsuario.ATIVO,
            is_active=True,
            email_confirmado_em=timezone.now(),
        )
        self.solicitante = Usuario.objects.create_user(
            email="sol.view@exemplo.com",
            cpf="11144477735",
            password="Rm3d!Senha1",
            nome_completo="Carlos Solicitante",
            data_nascimento=date(1991, 6, 10),
            celular="11977776666",
            perfil_doador=False,
            perfil_solicitante=True,
            status=StatusUsuario.ATIVO,
            is_active=True,
            email_confirmado_em=timezone.now(),
        )

    def tearDown(self):
        cache.clear()

    def test_acesso_endpoint_ia_restrito_a_doador(self):
        url = reverse("medicamentos:doacao_ler_ia")
        resp_visitante = self.client.post(url)
        self.assertEqual(resp_visitante.status_code, 302)
        self.assertIn(reverse("contas:login"), resp_visitante["Location"])

        self.client.force_login(self.solicitante)
        resp_sol = self.client.post(url)
        self.assertEqual(resp_sol.status_code, 403)

    def test_endpoint_ia_fluxos_validacao_sucesso_e_fallback(self):
        self.client.force_login(self.doador)
        url = reverse("medicamentos:doacao_ler_ia")

        # Sem foto -> 400
        resp_sem_foto = self.client.post(url, data={"consentimento_ia": "sim"})
        self.assertEqual(resp_sem_foto.status_code, 400)

        # Sem consentimento -> 400
        foto = SimpleUploadedFile("emb.jpg", _gerar_jpeg_bytes(), content_type="image/jpeg")
        resp_sem_cons = self.client.post(url, data={"foto": foto})
        self.assertEqual(resp_sem_cons.status_code, 400)

        # Sem chave configurada -> 503 fallback amigável
        with override_settings(REMED_IA_PROVEDOR="", REMED_IA_API_KEY=""):
            foto_fb = SimpleUploadedFile("emb.jpg", _gerar_jpeg_bytes(), content_type="image/jpeg")
            resp_fb = self.client.post(url, data={"foto": foto_fb, "consentimento_ia": "sim"})
            self.assertEqual(resp_fb.status_code, 503)
            self.assertFalse(resp_fb.json()["sucesso"])
            self.assertTrue(resp_fb.json()["fallback_manual"])

        # Com provedor stub -> 200 JSON estruturado
        stub = _ProvedorStub(
            resposta={
                "nome_medicamento": {"valor": "Dipirona Sódica", "confianca": 0.95},
                "principio_ativo": {"valor": "Dipirona monoidratada", "confianca": 0.91},
                "concentracao_dosagem": {"valor": "500 mg", "confianca": 0.90},
                "lote": {"valor": "L99", "confianca": 0.60},
                "data_validade": {"valor": "2027-10-15", "confianca": 0.97},
                "fabricante": {"valor": "EMS", "confianca": 0.85},
            }
        )
        with patch(
            "medicamentos.ia_embalagem.resolver_provedor_ia_configurado",
            return_value=stub,
        ):
            foto_ok = SimpleUploadedFile("emb.jpg", _gerar_jpeg_bytes(), content_type="image/jpeg")
            resp_ok = self.client.post(url, data={"foto": foto_ok, "consentimento_ia": "sim"})
        self.assertEqual(resp_ok.status_code, 200)
        payload = resp_ok.json()
        self.assertTrue(payload["sucesso"])
        self.assertTrue(payload["validade_sugerida"])
        self.assertEqual(payload["campos_baixa_confianca"], ["lote"])
        self.assertEqual(payload["campos"]["nome_medicamento"]["valor"], "Dipirona Sódica")

    def test_formulario_doacao_exibe_aviso_lgpd_e_exige_confirmacao_server_side(self):
        self.client.force_login(self.doador)
        url_criar = reverse("medicamentos:doacao_criar")

        resp_get = self.client.get(url_criar)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, AVISO_LGPD_IA_EMBALAGEM)
        self.assertContains(resp_get, "Ler dados da foto com IA")
        self.assertContains(resp_get, reverse("medicamentos:doacao_ler_ia"))

        forma = FormaFarmaceutica.objects.first()
        validade = (timezone.localdate() + timedelta(days=90)).isoformat()
        base_post = {
            "nome_medicamento": "Dipirona Sódica",
            "principio_ativo": "Dipirona",
            "concentracao_dosagem": "500 mg",
            "forma_farmaceutica": str(forma.pk),
            "quantidade": "20",
            "fabricante": "EMS",
            "lote": "L99",
            "data_validade": validade,
            "embalagem_integra": "sim",
            "controle_especial": "nao",
            "condicao_conservacao": CondicaoConservacao.TEMPERATURA_AMBIENTE,
            "sujeito_receita": "nao",
            "ia_sugestao_utilizada": "sim",
            "ia_validade_sugerida": "sim",
            "ia_campos_baixa_confianca": "lote",
        }

        # Sem marcar confirmações obrigatórias -> bloqueado no servidor
        resp_bloqueado = self.client.post(
            url_criar,
            data={
                **base_post,
                "foto_1": SimpleUploadedFile(
                    "emb.jpg", _gerar_jpeg_bytes(), content_type="image/jpeg"
                ),
            },
        )
        self.assertEqual(resp_bloqueado.status_code, 200)
        self.assertContains(resp_bloqueado, "Confirme explicitamente a data de validade")
        self.assertContains(resp_bloqueado, "Revise e confirme os campos destacados")
        self.assertEqual(Doacao.objects.count(), 0)

        # Com confirmações marcadas -> salva em `em_analise` e registra auxilio_ia=True na auditoria
        resp_ok = self.client.post(
            url_criar,
            data={
                **base_post,
                "confirmar_validade_ia": "on",
                "confirmar_baixa_confianca_ia": "on",
                "foto_1": SimpleUploadedFile(
                    "emb.jpg", _gerar_jpeg_bytes(), content_type="image/jpeg"
                ),
            },
        )
        self.assertEqual(resp_ok.status_code, 302)
        doacao = Doacao.objects.get()
        self.assertEqual(doacao.status, StatusDoacao.EM_ANALISE)
        aud = RegistroAuditoria.objects.filter(
            acao="doacao.cadastrada", entidade_id=str(doacao.pk)
        ).first()
        self.assertIsNotNone(aud)
        self.assertTrue(aud.detalhes["auxilio_ia"])
