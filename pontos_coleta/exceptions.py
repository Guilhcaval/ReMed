"""Exceções de domínio do app pontos_coleta (Specs 05, 06 e 07)."""

from nucleo.exceptions import RegraNegocioViolada


class CnpjJaCadastrado(RegraNegocioViolada):
    """Tentativa de cadastrar ou alterar para CNPJ já existente."""

    def __init__(self, mensagem: str = "CNPJ já cadastrado"):
        super().__init__(mensagem)


class HorarioInvalido(RegraNegocioViolada):
    """Bloco de dia/horário ausente, invertido ou sobreposto no mesmo dia."""


class UltimoResponsavelAtivo(RegraNegocioViolada):
    """Impede deixar um ponto de coleta sem nenhum responsável ativo (RN-05-07)."""

    def __init__(
        self,
        mensagem: str = "Não é possível desvincular o último responsável ativo do ponto de coleta.",
    ):
        super().__init__(mensagem)


class DocumentoVencido(RegraNegocioViolada):
    """Data de validade anterior à data atual (RF006 — mensagem literal)."""

    def __init__(self, mensagem: str = "Documento vencido. Envie um documento válido"):
        super().__init__(mensagem)


class DocumentosObrigatoriosPendentes(RegraNegocioViolada):
    """Tentativa de aprovar ou reativar ponto sem documentos obrigatórios válidos."""


class MotivoAnaliseObrigatorio(RegraNegocioViolada):
    """Motivo obrigatório em reprovação, pendência ou suspensão/inativação (RF007 literal)."""

    def __init__(self, mensagem: str = "Informe o motivo da reprovação ou da suspensão"):
        super().__init__(mensagem)
