"""Hierarquia base de exceções de domínio do ReMed (arquitetura.md seção 4.2)."""


class ErroDominio(Exception):
    """Base de todas as exceções de negócio do ReMed."""


class RecursoNaoEncontrado(ErroDominio):
    """Traduzida pela view para HTTP 404 (inclui recurso pertencente a terceiros)."""


class PermissaoNegada(ErroDominio):
    """Traduzida pela view para HTTP 403."""


class RegraNegocioViolada(ErroDominio):
    """Violação de regra de negócio com mensagem clara ao usuário."""


class ConflitoConcorrencia(RegraNegocioViolada):
    """Disputa ou estado inválido em operação transacional (ADR 0013)."""


class LimiteTaxaExcedido(RegraNegocioViolada):
    """Traduzida pela view para HTTP 429 quando um limite de taxa é excedido."""


class CepInvalido(RegraNegocioViolada):
    """CEP fora do formato de 8 dígitos."""


class CepNaoEncontrado(RecursoNaoEncontrado):
    """CEP inexistente nos serviços externos de consulta."""


class ServicoCepIndisponivel(ErroDominio):
    """Falha ou timeout nos provedores externos de CEP (libera preenchimento manual)."""


class ArquivoTamanhoExcedido(RegraNegocioViolada):
    """Arquivo acima do limite máximo permitido (5 MB — RF006 / ADR 0016)."""

    def __init__(self, mensagem: str = "O arquivo deve ter no máximo 5 MB"):
        super().__init__(mensagem)


class ArquivoFormatoInvalido(RegraNegocioViolada):
    """Extensão, assinatura (magic bytes) ou conteúdo de arquivo inválido."""

    def __init__(self, mensagem: str = "Envie o arquivo em PDF, JPG ou PNG"):
        super().__init__(mensagem)


class ArquivoMalwareDetectado(RegraNegocioViolada):
    """Scanner antimalware identificou ameaça no arquivo enviado (ADR 0016)."""

    def __init__(
        self,
        mensagem: str = "O arquivo foi recusado pela verificação de segurança.",
    ):
        super().__init__(mensagem)


class ArquivoScannerIndisponivel(RegraNegocioViolada):
    """Falha ou indisponibilidade do scanner antimalware (modo fail-closed — ADR 0016)."""

    def __init__(
        self,
        mensagem: str = (
            "Não foi possível concluir a verificação de segurança do arquivo no momento. "
            "Tente novamente em instantes."
        ),
    ):
        super().__init__(mensagem)


class LinkArquivoExpirado(RecursoNaoEncontrado):
    """Link temporário assinado expirado, adulterado ou pertencente a outro usuário."""
