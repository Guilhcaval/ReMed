"""Exceções de domínio do app medicamentos (Specs 08, 09, 10, 11 e 14)."""

from nucleo.exceptions import ConflitoConcorrencia, RegraNegocioViolada


class EmbalagemNaoIntegra(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = "Apenas medicamentos com embalagem íntegra podem ser doados",
    ):
        super().__init__(mensagem)


class MedicamentoControleEspecialBloqueado(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = (
            "Medicamentos de controle especial (Portaria SVS/MS nº 344/1998) "
            "não podem ser doados na plataforma."
        ),
    ):
        super().__init__(mensagem)


class ValidadeDoacaoInvalida(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = (
            "Não é permitido cadastrar medicamento vencido. "
            "Faça o descarte conforme a legislação sanitária"
        ),
    ):
        super().__init__(mensagem)


class DadosRefrigeracaoObrigatorios(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = (
            "Para medicamentos refrigerados, informe a faixa de temperatura da bula "
            "e confirme a declaração de conservação"
        ),
    ):
        super().__init__(mensagem)


class JanelaRefrigeradoInvalida(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = (
            "Para medicamentos refrigerados, a janela de retirada deve ocorrer no mesmo dia "
            "dentro do limite máximo permitido"
        ),
    ):
        super().__init__(mensagem)


class CienciaRefrigeradoObrigatoria(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = (
            "Confirme ciência das orientações de transporte refrigerado antes de confirmar "
            "o agendamento"
        ),
    ):
        super().__init__(mensagem)


class FotoDoacaoObrigatoria(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = "Envie ao menos uma foto da embalagem em JPG ou PNG.",
    ):
        super().__init__(mensagem)


class FotoDoacaoFormatoInvalido(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = "Envie a foto da embalagem em JPG ou PNG",
    ):
        super().__init__(mensagem)


class MotivoReprovacaoObrigatorio(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = "Informe o motivo da reprovação da doação",
    ):
        super().__init__(mensagem)


class DoacaoIndisponivel(ConflitoConcorrencia):
    def __init__(
        self,
        mensagem: str = "Esta doação atingiu o limite de validade e não está mais disponível",
    ):
        super().__init__(mensagem)


class DoacaoVencidaIrreversivel(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = "Uma doação marcada como vencida não pode voltar a ficar disponível.",
    ):
        super().__init__(mensagem)


class ServicoIaIndisponivel(RegraNegocioViolada):
    def __init__(
        self,
        mensagem: str = (
            "Não foi possível ler a embalagem automaticamente no momento. "
            "Preencha os campos manualmente — nada do que você digitou foi perdido."
        ),
    ):
        super().__init__(mensagem)
