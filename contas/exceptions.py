"""Exceções de domínio do app contas (Spec 01 / RF001)."""

from nucleo.exceptions import PermissaoNegada, RegraNegocioViolada


class CpfJaCadastrado(RegraNegocioViolada):
    """CPF já vinculado a uma conta não anonimizada."""

    def __init__(self, mensagem: str = "CPF já cadastrado") -> None:
        super().__init__(mensagem)


class EmailJaCadastrado(RegraNegocioViolada):
    """E-mail já vinculado a uma conta não anonimizada (case-insensitive)."""

    def __init__(self, mensagem: str = "E-mail já cadastrado") -> None:
        super().__init__(mensagem)


class TokenConfirmacaoInvalido(RegraNegocioViolada):
    """Token de confirmação inexistente, já utilizado ou expirado."""

    def __init__(
        self,
        mensagem: str = (
            "Link de confirmação inválido, já utilizado ou expirado. "
            "Solicite um novo link de confirmação."
        ),
    ) -> None:
        super().__init__(mensagem)


class AlteracaoCpfProibida(RegraNegocioViolada):
    """Tentativa de alterar o CPF após o cadastro (RN-01-03)."""

    def __init__(self, mensagem: str = "O CPF não pode ser alterado após o cadastro.") -> None:
        super().__init__(mensagem)


class SenhaAtualInvalida(RegraNegocioViolada):
    """Reconfirmação de senha incorreta no encerramento da conta."""

    def __init__(self, mensagem: str = "Senha atual incorreta.") -> None:
        super().__init__(mensagem)


class EncerramentoContaBloqueado(PermissaoNegada):
    """Encerramento vedado para contas suspensas ou bloqueadas (ADR 0007 / RN-01-14)."""

    def __init__(
        self,
        mensagem: str = "Contas suspensas ou bloqueadas não podem ser encerradas pelo usuário.",
    ) -> None:
        super().__init__(mensagem)
