"""Exceções de domínio do app contas (Spec 01 / RF001 e Spec 02 / RF002)."""

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


class CredenciaisInvalidas(RegraNegocioViolada):
    """E-mail/CPF inexistente ou senha incorreta (mensagem literal RF002)."""

    def __init__(self, mensagem: str = "E-mail/CPF ou senha incorretos") -> None:
        super().__init__(mensagem)


class ContaBloqueadaTemporariamente(RegraNegocioViolada):
    """Conta ou IP atingiu o limite de tentativas inválidas (mensagem literal RF002)."""

    def __init__(
        self,
        mensagem: str = "Muitas tentativas. Tente novamente mais tarde",
    ) -> None:
        super().__init__(mensagem)


class EmailNaoConfirmado(RegraNegocioViolada):
    """Senha correta, mas o e-mail ainda não foi confirmado (ADR 0007 / FE-03)."""

    def __init__(
        self,
        mensagem: str = (
            "Confirme seu e-mail pelo link enviado no cadastro antes de entrar. "
            "Se necessário, solicite um novo link de confirmação."
        ),
    ) -> None:
        super().__init__(mensagem)


class ContaIndisponivel(RegraNegocioViolada):
    """Senha correta, mas a conta está inativa, suspensa ou bloqueada (FE-03)."""

    def __init__(self, status: str, mensagem: str) -> None:
        self.status = status
        super().__init__(mensagem)


class TotpJaAtivado(RegraNegocioViolada):
    """Conta administrativa já possui dispositivo TOTP confirmado."""

    def __init__(
        self,
        mensagem: str = "A autenticação em dois fatores já está ativa para esta conta.",
    ) -> None:
        super().__init__(mensagem)


class TotpNaoConfigurado(RegraNegocioViolada):
    """Conta administrativa ainda não possui dispositivo TOTP confirmado."""

    def __init__(
        self,
        mensagem: str = "Configure a autenticação em dois fatores antes de continuar.",
    ) -> None:
        super().__init__(mensagem)


class CodigoTotpInvalido(RegraNegocioViolada):
    """Código TOTP incorreto ou já utilizado na mesma janela de 30 s (anti-replay)."""

    def __init__(
        self,
        mensagem: str = "Código de verificação inválido ou já utilizado. Aguarde o próximo código.",
    ) -> None:
        super().__init__(mensagem)


class CodigoRecuperacaoInvalido(RegraNegocioViolada):
    """Código de recuperação inexistente ou já utilizado."""

    def __init__(
        self,
        mensagem: str = "Código de recuperação inválido ou já utilizado.",
    ) -> None:
        super().__init__(mensagem)


class TotpBloqueadoTemporariamente(RegraNegocioViolada):
    """Limite de falhas de 2FA atingido; sessão pendente deve ser encerrada (RN-02-07)."""

    def __init__(
        self,
        mensagem: str = "Muitas tentativas. Tente novamente mais tarde",
    ) -> None:
        super().__init__(mensagem)


class ResetTotpNaoPermitido(PermissaoNegada):
    """Reset de 2FA recusado (auto-reset, permissão ausente ou < 2 Admins ativos — ADR 0009)."""


class MotivoObrigatorio(RegraNegocioViolada):
    """Motivo ausente em ação administrativa (RF004 regra 3 / RN-04-03)."""

    def __init__(
        self,
        mensagem: str = "Informe o motivo da suspensão ou do bloqueio",
    ) -> None:
        super().__init__(mensagem)


class AcumuloFuncoesProibido(RegraNegocioViolada):
    """Proibição técnica de acumular gestao_usuarios e verificacao_receitas (ADR 0010)."""

    def __init__(
        self,
        mensagem: str = (
            "Uma mesma conta não pode acumular as funções gestão de usuários e "
            "verificação de receitas (segregação de funções — RS015 / ADR 0010)."
        ),
    ) -> None:
        super().__init__(mensagem)


class UltimoAdministradorAtivo(RegraNegocioViolada):
    """Tentativa de remover ou desativar o último Administrador ativo (RF004 regra 4)."""

    def __init__(
        self,
        mensagem: str = "Não é possível remover o último Administrador ativo",
    ) -> None:
        super().__init__(mensagem)


class ContaAnonimizadaImutavel(RegraNegocioViolada):
    """Tentativa de reativar ou alterar conta já anonimizada pela LGPD (ADR 0007)."""

    def __init__(
        self,
        mensagem: str = "Contas encerradas e anonimizadas pela LGPD não podem ser reativadas.",
    ) -> None:
        super().__init__(mensagem)
