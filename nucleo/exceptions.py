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
