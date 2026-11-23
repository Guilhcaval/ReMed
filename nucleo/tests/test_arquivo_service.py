"""Testes unitários e de segurança de ArquivoService e entrega assinada (ADR 0016 / Spec 06)."""

import io
import tempfile
import time as modulo_tempo
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.core.signing import TimestampSigner
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from contas.models import Usuario
from nucleo.arquivos import (
    SAL_ASSINATURA_ARQUIVO_PRIVADO,
    ArquivoService,
)
from nucleo.exceptions import (
    ArquivoFormatoInvalido,
    ArquivoMalwareDetectado,
    ArquivoScannerIndisponivel,
    ArquivoTamanhoExcedido,
    LinkArquivoExpirado,
)


def _gerar_pdf_valido(tamanho_extra: int = 0) -> bytes:
    corpo = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    if tamanho_extra > 0:
        corpo += b"%" + (b"A" * tamanho_extra) + b"\n"
    return corpo + b"%%EOF\n"


def _gerar_jpeg_com_exif() -> bytes:
    img = Image.new("RGB", (40, 30), color=(23, 70, 107))
    exif = img.getexif()
    exif[271] = "Camera Teste Secreta"
    exif[34853] = {1: "S", 3: "W"}  # GPSInfo sub-IFD (tag 0x8825)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _gerar_png_valido() -> bytes:
    img = Image.new("RGBA", (24, 24), color=(30, 122, 82, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _ScannerInfectado:
    def verificar(self, conteudo: bytes, *, nome_seguro: str) -> None:
        _ = (conteudo, nome_seguro)
        raise ArquivoMalwareDetectado()


class _ScannerIndisponivel:
    def verificar(self, conteudo: bytes, *, nome_seguro: str) -> None:
        _ = (conteudo, nome_seguro)
        raise ConnectionError("clamd fora do ar")


class _BackendS3ContratoDuble:
    def __init__(self):
        self.salvos: dict[str, bytes] = {}
        self.excluidos: list[str] = []

    def salvar(self, chave: str, conteudo: bytes) -> None:
        self.salvos[chave] = conteudo

    def excluir(self, chave: str) -> None:
        self.excluidos.append(chave)
        self.salvos.pop(chave, None)

    def gerar_url_temporaria(
        self,
        chave: str,
        *,
        usuario_id: int,
        mime_verificado: str,
        nome_download: str,
        validade_segundos: int,
    ) -> str:
        _ = (usuario_id, mime_verificado, nome_download)
        return f"https://s3.exemplo.interno/{chave}?expires={validade_segundos}"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ArquivoServiceTest(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta_privada = Path(self._tmp.name)
        self._override = override_settings(PRIVATE_STORAGE_ROOT=self.pasta_privada)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._tmp.cleanup()

    def _criar_usuario(self, email: str, cpf: str) -> Usuario:
        return Usuario.objects.create_user(
            email=email,
            cpf=cpf,
            password="Rm3d!Senha1",
            nome_completo=f"Usuário {email}",
            data_nascimento=date(1990, 1, 1),
            celular="11988887777",
            perfil_doador=True,
            email_confirmado_em=timezone.now(),
        )

    def test_limite_5mb_exato_vs_excedido(self):
        """CA-06-02: aceita até 5 MB exatos e rejeita 5 MB + 1 byte com mensagem literal."""
        pdf_base = _gerar_pdf_valido()
        faltam = (5 * 1024 * 1024) - len(pdf_base)
        pdf_5mb = _gerar_pdf_valido(tamanho_extra=faltam - 2)
        self.assertEqual(len(pdf_5mb), 5 * 1024 * 1024)

        salvo = ArquivoService.armazenar_privado(
            conteudo=pdf_5mb,
            nome_original="alvara.pdf",
            categoria="pontos_coleta",
        )
        self.assertTrue(salvo.chave.startswith("pontos_coleta/"))
        self.assertTrue(salvo.chave.endswith(".pdf"))
        self.assertEqual(salvo.mime_verificado, "application/pdf")

        with self.assertRaises(ArquivoTamanhoExcedido) as ctx:
            ArquivoService.armazenar_privado(
                conteudo=pdf_5mb + b"x",
                nome_original="grande.pdf",
                categoria="pontos_coleta",
            )
        self.assertEqual(str(ctx.exception), "O arquivo deve ter no máximo 5 MB")

    def test_magic_bytes_falsificados_e_pdf_sem_eof_rejeitados(self):
        """CA-06-02: .exe renomeado, extensão trocada e PDF truncado sem %%EOF falham."""
        for conteudo, nome in (
            (b"MZ\x90\x00executavel", "alvara.pdf"),
            (b"%PDF-1.4\nsem marcador final", "truncado.pdf"),
            (_gerar_png_valido(), "falso.jpg"),
            (_gerar_pdf_valido(), "doc.exe"),
        ):
            with self.subTest(nome=nome):
                with self.assertRaises(ArquivoFormatoInvalido) as ctx:
                    ArquivoService.armazenar_privado(
                        conteudo=conteudo,
                        nome_original=nome,
                        categoria="pontos_coleta",
                    )
                self.assertEqual(str(ctx.exception), "Envie o arquivo em PDF, JPG ou PNG")

    def test_pillow_remove_exif_gps_e_bloqueia_decompression_bomb(self):
        """ADR 0016: remove EXIF/GPS de JPEG e bloqueia imagem acima do limite de pixels."""
        jpeg_com_exif = _gerar_jpeg_com_exif()
        with Image.open(io.BytesIO(jpeg_com_exif)) as antes:
            exif_antes = antes.getexif()
            self.assertEqual(exif_antes.get(271), "Camera Teste Secreta")
            self.assertTrue(bool(exif_antes.get_ifd(34853)))

        armazenado = ArquivoService.armazenar_privado(
            conteudo=jpeg_com_exif,
            nome_original="licenca.jpg",
            categoria="pontos_coleta",
        )
        salvo_bytes = (self.pasta_privada / armazenado.chave).read_bytes()
        with Image.open(io.BytesIO(salvo_bytes)) as depois:
            exif_depois = depois.getexif()
            self.assertEqual(len(exif_depois), 0)
            self.assertEqual(exif_depois.get_ifd(34853), {})
            self.assertNotIn(b"Camera Teste Secreta", salvo_bytes)

        # Proteção contra decompression bomb (dimensão/pixels acima do teto)
        with patch("nucleo.arquivos.MAX_PIXELS_IMAGEM", 100):
            with self.assertRaises(ArquivoFormatoInvalido):
                ArquivoService.armazenar_privado(
                    conteudo=jpeg_com_exif,
                    nome_original="bomba.jpg",
                    categoria="pontos_coleta",
                )

    def test_antimalware_duble_infectado_e_fail_closed(self):
        """ADR 0016: arquivo infectado e scanner indisponível bloqueiam sem gravar em disco."""
        pdf = _gerar_pdf_valido()

        with self.assertRaises(ArquivoMalwareDetectado):
            ArquivoService.armazenar_privado(
                conteudo=pdf,
                nome_original="infectado.pdf",
                categoria="pontos_coleta",
                scanner=_ScannerInfectado(),
            )

        with self.assertRaises(ArquivoScannerIndisponivel):
            ArquivoService.armazenar_privado(
                conteudo=pdf,
                nome_original="erro.pdf",
                categoria="pontos_coleta",
                scanner=_ScannerIndisponivel(),
            )

        self.assertEqual(list(self.pasta_privada.rglob("*")), [])

    def test_contrato_adaptador_s3_duble(self):
        """ADR 0016: contrato de backend privado suporta adaptador S3 por injeção."""
        backend = _BackendS3ContratoDuble()
        armazenado = ArquivoService.armazenar_privado(
            conteudo=_gerar_png_valido(),
            nome_original="foto.png",
            categoria="pontos_coleta",
            backend=backend,
        )
        self.assertIn(armazenado.chave, backend.salvos)
        url = ArquivoService.gerar_url_temporaria(
            armazenado.chave,
            usuario_id=42,
            mime_verificado=armazenado.mime_verificado,
            nome_download="doc.png",
            validade_segundos=60,
            backend=backend,
        )
        self.assertIn("expires=60", url)
        ArquivoService.remover_silencioso(armazenado.chave, backend=backend)
        self.assertNotIn(armazenado.chave, backend.salvos)

    def test_rota_local_assinada_60s_path_traversal_vinculo_usuario_e_cabecalhos(self):
        """ADR 0016: token assinado 60 s, vínculo ao usuário, anti-path-traversal e headers."""
        u1 = self._criar_usuario("u1@exemplo.com", "52998224725")
        u2 = self._criar_usuario("u2@exemplo.com", "11144477735")

        armazenado = ArquivoService.armazenar_privado(
            conteudo=_gerar_pdf_valido(),
            nome_original="licenca.pdf",
            categoria="pontos_coleta",
        )
        url = ArquivoService.gerar_url_temporaria(
            armazenado.chave,
            usuario_id=u1.pk,
            mime_verificado=armazenado.mime_verificado,
            nome_download="licenca_v1",
        )

        # 1. Visitante -> redireciona para login
        self.assertEqual(self.client.get(url).status_code, 302)

        # 2. Outro usuário autenticado tentando usar token de u1 -> 404
        self.client.force_login(u2)
        self.assertEqual(self.client.get(url).status_code, 404)

        # 3. Usuário autorizado -> 200 com nosniff, no-store e Content-Disposition attachment
        self.client.force_login(u1)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp["Cache-Control"], "no-store")
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertIn("licenca_v1.pdf", resp["Content-Disposition"])
        self.assertTrue(b"".join(resp.streaming_content).startswith(b"%PDF-"))
        for closer in resp._resource_closers:
            closer()
        resp._resource_closers.clear()

        # 4. Path traversal assinado (simulando chave maliciosa) -> bloqueado
        signer = TimestampSigner(salt=SAL_ASSINATURA_ARQUIVO_PRIVADO)
        token_traversal = signer.sign_object(
            {"c": "../manage.py", "u": u1.pk, "m": "text/plain", "n": "x.pdf"}
        )
        url_trav = reverse("nucleo:arquivo_privado_baixar", kwargs={"token": token_traversal})
        self.assertEqual(self.client.get(url_trav).status_code, 404)

        # 5. Token expirado (> 60 s) -> LinkArquivoExpirado / 404
        token_expiravel = url.rstrip("/").rsplit("/", 1)[-1]
        with patch("django.core.signing.time.time", return_value=modulo_tempo.time() + 120):
            with self.assertRaises(LinkArquivoExpirado):
                ArquivoService.abrir_por_token_temporario(
                    token_expiravel, usuario_id=u1.pk, validade_segundos=60
                )
