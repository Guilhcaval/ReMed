"""Armazenamento seguro de arquivos privados, validação e antimalware (ADR 0016 / Spec 06).

Em desenvolvimento e testes, utiliza armazenamento local privado em `PRIVATE_STORAGE_ROOT`
(fora de `static/` e sem `MEDIA_URL` pública), com entrega exclusiva via token assinado
(`TimestampSigner`, validade padrão de 60 s) e `FileResponse` com cabeçalhos `nosniff` e
`no-store`. O adaptador S3 (`django-storages` + `boto3`) e o daemon `clamd` entram na Etapa 9
implementando os mesmos contratos (`BackendArmazenamentoPrivado` e `AntimalwareScanner`).
"""

import io
import logging
import re
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.urls import reverse
from PIL import Image, UnidentifiedImageError

from nucleo.exceptions import (
    ArquivoFormatoInvalido,
    ArquivoMalwareDetectado,
    ArquivoScannerIndisponivel,
    LinkArquivoExpirado,
)
from nucleo.exceptions import (
    ArquivoTamanhoExcedido as ErroTamanhoArquivo,
)

logger = logging.getLogger(__name__)

SAL_ASSINATURA_ARQUIVO_PRIVADO = "remed.arquivo_privado.v1"
CATEGORIA_REGEX = re.compile(r"^[a-z0-9_]{2,40}$")
CHAVE_ARQUIVO_REGEX = re.compile(r"^[a-z0-9_]{2,40}/[a-f0-9]{32}\.(pdf|jpg|png)$")
MAX_PIXELS_IMAGEM = 25_000_000
MAX_DIMENSAO_IMAGEM = 8000
EXTENSOES_PERMITIDAS_PADRAO: frozenset[str] = frozenset({"pdf", "jpg", "jpeg", "png"})

_MAPA_EXT_CANONICA: dict[str, str] = {
    "pdf": "pdf",
    "jpg": "jpg",
    "jpeg": "jpg",
    "png": "png",
}


@dataclass(frozen=True)
class ArquivoArmazenado:
    chave: str
    mime_verificado: str
    tamanho_bytes: int
    extensao: str


@dataclass(frozen=True)
class ArquivoPrivadoAberto:
    caminho: Path
    mime_verificado: str
    nome_download: str


@dataclass(frozen=True)
class ImagemSanitizada:
    conteudo: bytes
    mime_verificado: str
    tamanho_bytes: int
    extensao: str


class AntimalwareScanner(Protocol):
    """Contrato de varredura antimalware antes da persistência (ADR 0016)."""

    def verificar(self, conteudo: bytes, *, nome_seguro: str) -> None:
        """Lança ArquivoMalwareDetectado se houver ameaça ou erro se indisponível."""


class NoopAntimalwareScanner:
    """Implementação padrão para desenvolvimento e testes no MVP (clamd entra na Etapa 9)."""

    def verificar(self, conteudo: bytes, *, nome_seguro: str) -> None:
        _ = (conteudo, nome_seguro)


class BackendArmazenamentoPrivado(Protocol):
    """Contrato de backend privado (local em dev/testes; S3 com SSE na Etapa 9)."""

    def salvar(self, chave: str, conteudo: bytes) -> None: ...

    def excluir(self, chave: str) -> None: ...

    def gerar_url_temporaria(
        self,
        chave: str,
        *,
        usuario_id: int,
        mime_verificado: str,
        nome_download: str,
        validade_segundos: int,
    ) -> str: ...


def _sanitizar_nome_download(nome: str, extensao: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (nome or "").strip()).strip("._")
    if not base:
        base = "documento"
    if not base.lower().endswith(f".{extensao}"):
        base = f"{base}.{extensao}"
    return base[:100]


def _resolver_caminho_seguro(chave: str) -> Path:
    if not CHAVE_ARQUIVO_REGEX.match(chave or ""):
        raise LinkArquivoExpirado("Arquivo indisponível.")
    raiz = Path(settings.PRIVATE_STORAGE_ROOT).resolve()
    alvo = (raiz / chave).resolve()
    if alvo == raiz or not alvo.is_relative_to(raiz):
        raise LinkArquivoExpirado("Arquivo indisponível.")
    return alvo


class ArmazenamentoLocalPrivado:
    """Backend local privado sobre FileSystemStorage + TimestampSigner 60 s (ADR 0016)."""

    def _storage(self) -> FileSystemStorage:
        raiz = Path(settings.PRIVATE_STORAGE_ROOT)
        raiz.mkdir(parents=True, exist_ok=True)
        return FileSystemStorage(location=str(raiz))

    def salvar(self, chave: str, conteudo: bytes) -> None:
        destino = _resolver_caminho_seguro(chave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        storage = self._storage()
        storage.save(chave, ContentFile(conteudo))

    def excluir(self, chave: str) -> None:
        try:
            alvo = _resolver_caminho_seguro(chave)
        except LinkArquivoExpirado:
            return
        if alvo.is_file():
            alvo.unlink(missing_ok=True)

    def gerar_url_temporaria(
        self,
        chave: str,
        *,
        usuario_id: int,
        mime_verificado: str,
        nome_download: str,
        validade_segundos: int,
    ) -> str:
        _ = validade_segundos
        ext = chave.rsplit(".", 1)[-1].lower()
        signer = TimestampSigner(salt=SAL_ASSINATURA_ARQUIVO_PRIVADO)
        token = signer.sign_object(
            {
                "c": chave,
                "u": int(usuario_id),
                "m": mime_verificado,
                "n": _sanitizar_nome_download(nome_download, ext),
            }
        )
        return reverse("nucleo:arquivo_privado_baixar", kwargs={"token": token})


def _extrair_extensao(nome_arquivo: str) -> str:
    if not nome_arquivo or "." not in nome_arquivo:
        return ""
    return nome_arquivo.rsplit(".", 1)[-1].strip().lower()


def _detectar_tipo_por_magic_bytes(conteudo: bytes) -> tuple[str, str]:
    """Detecta formato real pela assinatura binária (PDF, JPG ou PNG)."""
    if conteudo.startswith(b"%PDF-"):
        # Acréscimo da especificação (aprovado): confirma marcador %%EOF na cauda do PDF.
        if b"%%EOF" not in conteudo[-1024:]:
            raise ArquivoFormatoInvalido()
        return "pdf", "application/pdf"
    if conteudo.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    raise ArquivoFormatoInvalido()


def _reprocessar_imagem_sem_exif(conteudo: bytes, extensao_esperada: str) -> bytes:
    """Valida integridade via Pillow (com proteção a decompression bomb) e remove EXIF/GPS."""
    anterior_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS_IMAGEM
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(conteudo)) as imagem:
                formato = (imagem.format or "").upper()
                if extensao_esperada == "jpg" and formato != "JPEG":
                    raise ArquivoFormatoInvalido()
                if extensao_esperada == "png" and formato != "PNG":
                    raise ArquivoFormatoInvalido()

                largura, altura = imagem.size
                if (
                    largura <= 0
                    or altura <= 0
                    or largura > MAX_DIMENSAO_IMAGEM
                    or altura > MAX_DIMENSAO_IMAGEM
                    or (largura * altura) > MAX_PIXELS_IMAGEM
                ):
                    raise ArquivoFormatoInvalido()

                imagem.load()
                if extensao_esperada == "jpg":
                    convertida = imagem.convert("RGB")
                    limpa = Image.new("RGB", convertida.size)
                    limpa.paste(convertida)
                    saida = io.BytesIO()
                    limpa.save(saida, format="JPEG", quality=90, optimize=True)
                    return saida.getvalue()

                modo_png = "RGBA" if imagem.mode in {"RGBA", "LA", "PA"} else "RGB"
                convertida = imagem.convert(modo_png)
                limpa = Image.new(modo_png, convertida.size)
                limpa.paste(convertida)
                saida = io.BytesIO()
                limpa.save(saida, format="PNG", optimize=True)
                return saida.getvalue()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as erro:
        raise ArquivoFormatoInvalido() from erro
    finally:
        Image.MAX_IMAGE_PIXELS = anterior_max_pixels


class ArquivoService:
    """Serviço único de upload, validação, sanitização e acesso privado (ADR 0016)."""

    @staticmethod
    def validar_e_sanitizar_imagem(
        *,
        conteudo: bytes,
        nome_original: str,
        extensoes_permitidas: frozenset[str] = frozenset({"jpg", "jpeg", "png"}),
        scanner: AntimalwareScanner | None = None,
    ) -> ImagemSanitizada:
        """Valida JPG/PNG (<= 5 MB), remove EXIF/GPS e roda antimalware sem gravar em disco."""
        limite_bytes = settings.REMED_ARQUIVO_TAMANHO_MAX_BYTES
        if not conteudo:
            raise ArquivoFormatoInvalido()
        if len(conteudo) > limite_bytes:
            raise ErroTamanhoArquivo()

        ext_declarada = _extrair_extensao(nome_original)
        permitidas_norm = {e.lower() for e in extensoes_permitidas} & {"jpg", "jpeg", "png"}
        if not ext_declarada or ext_declarada not in permitidas_norm:
            raise ArquivoFormatoInvalido()

        ext_detectada, mime_verificado = _detectar_tipo_por_magic_bytes(conteudo)
        if ext_detectada not in {"jpg", "png"} or _MAPA_EXT_CANONICA.get(ext_declarada) != (
            ext_detectada
        ):
            raise ArquivoFormatoInvalido()

        conteudo_limpo = _reprocessar_imagem_sem_exif(conteudo, ext_detectada)
        if len(conteudo_limpo) > limite_bytes:
            raise ErroTamanhoArquivo()

        nome_seguro = f"memoria/{uuid.uuid4().hex}.{ext_detectada}"
        verificador = scanner if scanner is not None else NoopAntimalwareScanner()
        try:
            verificador.verificar(conteudo_limpo, nome_seguro=nome_seguro)
        except ArquivoMalwareDetectado:
            logger.warning("Imagem bloqueada por detecção de malware (chave=%s).", nome_seguro)
            raise
        except Exception as erro:
            logger.warning(
                "Falha no scanner antimalware em modo fail-closed (chave=%s): %s",
                nome_seguro,
                erro.__class__.__name__,
            )
            raise ArquivoScannerIndisponivel() from erro

        return ImagemSanitizada(
            conteudo=conteudo_limpo,
            mime_verificado=mime_verificado,
            tamanho_bytes=len(conteudo_limpo),
            extensao=ext_detectada,
        )

    @staticmethod
    def armazenar_privado(
        *,
        conteudo: bytes,
        nome_original: str,
        categoria: str,
        extensoes_permitidas: frozenset[str] = EXTENSOES_PERMITIDAS_PADRAO,
        scanner: AntimalwareScanner | None = None,
        backend: BackendArmazenamentoPrivado | None = None,
    ) -> ArquivoArmazenado:
        if not CATEGORIA_REGEX.match(categoria or ""):
            raise ValueError("Categoria de armazenamento privada inválida.")

        limite_bytes = settings.REMED_ARQUIVO_TAMANHO_MAX_BYTES
        if not conteudo:
            raise ArquivoFormatoInvalido()
        if len(conteudo) > limite_bytes:
            raise ErroTamanhoArquivo()

        ext_declarada = _extrair_extensao(nome_original)
        permitidas_norm = {e.lower() for e in extensoes_permitidas}
        if not ext_declarada or ext_declarada not in permitidas_norm:
            raise ArquivoFormatoInvalido()

        ext_detectada, mime_verificado = _detectar_tipo_por_magic_bytes(conteudo)
        if _MAPA_EXT_CANONICA.get(ext_declarada) != ext_detectada:
            raise ArquivoFormatoInvalido()

        conteudo_final = conteudo
        if ext_detectada in {"jpg", "png"}:
            conteudo_final = _reprocessar_imagem_sem_exif(conteudo, ext_detectada)
            if len(conteudo_final) > limite_bytes:
                raise ErroTamanhoArquivo()

        chave = f"{categoria}/{uuid.uuid4().hex}.{ext_detectada}"

        verificador = scanner if scanner is not None else NoopAntimalwareScanner()
        try:
            verificador.verificar(conteudo_final, nome_seguro=chave)
        except ArquivoMalwareDetectado:
            logger.warning("Upload bloqueado por detecção de malware (chave=%s).", chave)
            raise
        except Exception as erro:
            logger.warning(
                "Falha no scanner antimalware em modo fail-closed (chave=%s): %s",
                chave,
                erro.__class__.__name__,
            )
            raise ArquivoScannerIndisponivel() from erro

        armazenamento = backend if backend is not None else ArmazenamentoLocalPrivado()
        armazenamento.salvar(chave, conteudo_final)
        return ArquivoArmazenado(
            chave=chave,
            mime_verificado=mime_verificado,
            tamanho_bytes=len(conteudo_final),
            extensao=ext_detectada,
        )

    @staticmethod
    def remover_silencioso(
        chave: str,
        *,
        backend: BackendArmazenamentoPrivado | None = None,
    ) -> None:
        """Remove arquivo físico em rollback/erro de gravação no banco sem mascarar o erro."""
        armazenamento = backend if backend is not None else ArmazenamentoLocalPrivado()
        try:
            armazenamento.excluir(chave)
        except Exception:
            logger.warning("Não foi possível remover arquivo órfão %s após rollback.", chave)

    @staticmethod
    def gerar_url_temporaria(
        chave: str,
        *,
        usuario_id: int,
        mime_verificado: str,
        nome_download: str,
        validade_segundos: int | None = None,
        backend: BackendArmazenamentoPrivado | None = None,
    ) -> str:
        ttl = (
            validade_segundos
            if validade_segundos is not None
            else settings.REMED_ARQUIVO_URL_TEMPORARIA_SEGUNDOS
        )
        armazenamento = backend if backend is not None else ArmazenamentoLocalPrivado()
        return armazenamento.gerar_url_temporaria(
            chave,
            usuario_id=usuario_id,
            mime_verificado=mime_verificado,
            nome_download=nome_download,
            validade_segundos=ttl,
        )

    @staticmethod
    def abrir_por_token_temporario(
        token: str,
        *,
        usuario_id: int,
        validade_segundos: int | None = None,
    ) -> ArquivoPrivadoAberto:
        ttl = (
            validade_segundos
            if validade_segundos is not None
            else settings.REMED_ARQUIVO_URL_TEMPORARIA_SEGUNDOS
        )
        signer = TimestampSigner(salt=SAL_ASSINATURA_ARQUIVO_PRIVADO)
        try:
            payload = signer.unsign_object(token, max_age=ttl)
        except (BadSignature, SignatureExpired) as erro:
            raise LinkArquivoExpirado("Link temporário expirado ou inválido.") from erro

        if not isinstance(payload, dict) or payload.get("u") != int(usuario_id):
            raise LinkArquivoExpirado("Link temporário não autorizado para esta sessão.")

        chave = str(payload.get("c") or "")
        mime = str(payload.get("m") or "application/octet-stream")
        nome = str(payload.get("n") or "documento")

        caminho = _resolver_caminho_seguro(chave)
        if not caminho.is_file():
            raise LinkArquivoExpirado("Arquivo não encontrado no armazenamento privado.")

        ext = chave.rsplit(".", 1)[-1].lower()
        return ArquivoPrivadoAberto(
            caminho=caminho,
            mime_verificado=mime,
            nome_download=_sanitizar_nome_download(nome, ext),
        )
