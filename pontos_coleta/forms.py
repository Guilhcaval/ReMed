"""Formulários de entrada do app pontos_coleta (Specs 05, 06 e 07 — validação de formato)."""

from datetime import time

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory

from nucleo.validators import (
    UFS_BRASIL,
    normalizar_email,
    somente_digitos,
    validar_cep,
    validar_cnpj,
    validar_telefone,
    validar_uf,
)
from pontos_coleta.models import (
    DIAS_SEMANA_CURTOS,
    ResultadoAnalisePonto,
    StatusDocumentoPonto,
    StatusPontoColeta,
)
from pontos_coleta.services import (
    DadosAtualizacaoPonto,
    DadosPontoColeta,
    FiltrosDocumentosAdmin,
    FiltrosPontoColeta,
    ItemHorario,
)

MSG_CAMPO_OBRIGATORIO = "Campo(s) obrigatório(s) não preenchido(s)"
MSG_INCORRETO_PREFIXO = "Campo preenchido incorretamente"
OPCOES_UF = (("", "UF"), *UFS_BRASIL)


class _ResumoErrosMixin:
    def mensagens_resumo_erros(self) -> list[str]:
        mensagens: list[str] = []
        vistos: set[str] = set()
        for erro in self.non_field_errors():
            if erro not in vistos:
                mensagens.append(erro)
                vistos.add(erro)
        for campo in self:
            for erro in campo.errors:
                texto = f"{campo.label}: {erro}" if campo.label else erro
                if texto not in vistos:
                    mensagens.append(texto)
                    vistos.add(texto)
        return mensagens


class _BasePontoColetaForm(_ResumoErrosMixin, forms.Form):
    razao_social = forms.CharField(
        label="Razão social",
        required=True,
        max_length=150,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Razão social da instituição"}
        ),
    )
    nome_fantasia = forms.CharField(
        label="Nome fantasia",
        required=True,
        max_length=150,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Nome conhecido pelo público"}
        ),
    )
    tipo_estabelecimento = forms.ChoiceField(
        label="Tipo de estabelecimento",
        required=True,
        choices=(),
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    email = forms.EmailField(
        label="E-mail institucional",
        required=True,
        max_length=254,
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "invalid": f"{MSG_INCORRETO_PREFIXO}. Informe um e-mail válido.",
        },
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "contato@instituicao.com.br"}
        ),
    )
    telefone = forms.CharField(
        label="Telefone",
        required=True,
        max_length=20,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "(00) 00000-0000",
                "inputmode": "tel",
                "maxlength": "15",
                "data-mascara": "celular",
            }
        ),
    )
    cep = forms.CharField(
        label="CEP",
        required=True,
        max_length=9,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "00000-000",
                "inputmode": "numeric",
                "maxlength": "9",
                "data-mascara": "cep",
            }
        ),
    )
    logradouro = forms.CharField(
        label="Logradouro",
        required=True,
        max_length=150,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Preenchido pelo CEP"}
        ),
    )
    numero = forms.CharField(
        label="Número",
        required=True,
        max_length=20,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: 123"}),
    )
    bairro = forms.CharField(
        label="Bairro",
        required=True,
        max_length=100,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Preenchido pelo CEP"}
        ),
    )
    municipio = forms.CharField(
        label="Município",
        required=True,
        max_length=100,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Preenchido pelo CEP"}
        ),
    )
    estado = forms.ChoiceField(
        label="Estado",
        required=True,
        choices=OPCOES_UF,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    complemento = forms.CharField(
        label="Complemento (opcional)",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Apartamento, bloco, sala ou referência"}
        ),
    )
    possui_refrigeracao = forms.ChoiceField(
        label="Possui refrigeração para medicamentos?",
        required=True,
        choices=(("sim", "Sim"), ("nao", "Não")),
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    observacoes = forms.CharField(
        label="Observações (opcional)",
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Informe detalhes ou orientações sobre o ponto de coleta",
            }
        ),
    )

    def __init__(self, *args, tipos_estabelecimento=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_estabelecimento"].choices = [
            ("", "Selecione o tipo de estabelecimento"),
            *((str(t.pk), t.nome) for t in tipos_estabelecimento),
        ]

    def clean_email(self) -> str:
        return normalizar_email(self.cleaned_data.get("email", ""))

    def clean_telefone(self) -> str:
        try:
            return validar_telefone(self.cleaned_data.get("telefone", ""))
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro

    def clean_cep(self) -> str:
        try:
            return validar_cep(self.cleaned_data.get("cep", ""))
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro

    def clean_estado(self) -> str:
        try:
            return validar_uf(self.cleaned_data.get("estado", ""))
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro


class PontoColetaCadastroForm(_BasePontoColetaForm):
    """Formulário de cadastro inicial de ponto de coleta (RF005 — Passo 1)."""

    cnpj = forms.CharField(
        label="CNPJ",
        required=True,
        max_length=18,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "00.000.000/0000-00",
                "inputmode": "numeric",
                "maxlength": "18",
                "data-mascara": "cnpj",
            }
        ),
    )
    convidar_responsavel = forms.CharField(
        label="Convidar outro responsável (opcional)",
        required=False,
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "E-mail ou CPF de uma conta ReMed já cadastrada",
            }
        ),
    )

    def clean_cnpj(self) -> str:
        try:
            return validar_cnpj(self.cleaned_data.get("cnpj", ""))
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro

    def para_dados(self) -> DadosPontoColeta:
        return DadosPontoColeta(
            cnpj=self.cleaned_data["cnpj"],
            razao_social=self.cleaned_data["razao_social"],
            nome_fantasia=self.cleaned_data["nome_fantasia"],
            tipo_estabelecimento_id=int(self.cleaned_data["tipo_estabelecimento"]),
            email=self.cleaned_data["email"],
            telefone=self.cleaned_data["telefone"],
            possui_refrigeracao=self.cleaned_data["possui_refrigeracao"] == "sim",
            observacoes=self.cleaned_data.get("observacoes", ""),
            cep=self.cleaned_data["cep"],
            logradouro=self.cleaned_data["logradouro"],
            numero=self.cleaned_data["numero"],
            bairro=self.cleaned_data["bairro"],
            municipio=self.cleaned_data["municipio"],
            estado=self.cleaned_data["estado"],
            complemento=self.cleaned_data.get("complemento", ""),
        )


class PontoColetaEditarForm(_BasePontoColetaForm):
    """Edição de ponto de coleta pelo responsável ativo (CNPJ e status excluídos — RN-05-08)."""

    def para_dados(self) -> DadosAtualizacaoPonto:
        return DadosAtualizacaoPonto(
            razao_social=self.cleaned_data["razao_social"],
            nome_fantasia=self.cleaned_data["nome_fantasia"],
            tipo_estabelecimento_id=int(self.cleaned_data["tipo_estabelecimento"]),
            email=self.cleaned_data["email"],
            telefone=self.cleaned_data["telefone"],
            possui_refrigeracao=self.cleaned_data["possui_refrigeracao"] == "sim",
            observacoes=self.cleaned_data.get("observacoes", ""),
            cep=self.cleaned_data["cep"],
            logradouro=self.cleaned_data["logradouro"],
            numero=self.cleaned_data["numero"],
            bairro=self.cleaned_data["bairro"],
            municipio=self.cleaned_data["municipio"],
            estado=self.cleaned_data["estado"],
            complemento=self.cleaned_data.get("complemento", ""),
        )


class HorarioBlocoForm(forms.Form):
    """Um bloco de dias (Seg..Dom) com horário de abertura e fechamento."""

    dias = forms.MultipleChoiceField(
        label="Dias de funcionamento para retirada",
        required=False,
        choices=tuple((str(v), r) for v, r in DIAS_SEMANA_CURTOS),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    hora_abertura = forms.TimeField(
        label="Abertura",
        required=False,
        input_formats=["%H:%M"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={"type": "time", "class": "form-control"},
        ),
    )
    hora_fechamento = forms.TimeField(
        label="Fechamento",
        required=False,
        input_formats=["%H:%M"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={"type": "time", "class": "form-control"},
        ),
    )

    def clean(self):
        cleaned = super().clean()
        dias = cleaned.get("dias") or []
        abertura: time | None = cleaned.get("hora_abertura")
        fechamento: time | None = cleaned.get("hora_fechamento")

        tem_algo = bool(dias) or abertura is not None or fechamento is not None
        if not tem_algo:
            return cleaned

        if not dias:
            self.add_error("dias", "Selecione ao menos um dia da semana neste bloco de horário.")
        if abertura is None:
            self.add_error("hora_abertura", MSG_CAMPO_OBRIGATORIO)
        if fechamento is None:
            self.add_error("hora_fechamento", MSG_CAMPO_OBRIGATORIO)
        if abertura is not None and fechamento is not None and abertura >= fechamento:
            self.add_error(
                "hora_fechamento",
                f"{MSG_INCORRETO_PREFIXO}. O fechamento deve ser posterior à abertura.",
            )
        return cleaned


class BaseHorarioBlocoFormSet(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        itens: list[ItemHorario] = []
        for form in self.forms:
            if not getattr(form, "cleaned_data", None):
                continue
            dias = form.cleaned_data.get("dias") or []
            abertura = form.cleaned_data.get("hora_abertura")
            fechamento = form.cleaned_data.get("hora_fechamento")
            if dias and abertura is not None and fechamento is not None:
                for dia in dias:
                    itens.append(
                        ItemHorario(
                            dia_semana=int(dia),
                            hora_abertura=abertura,
                            hora_fechamento=fechamento,
                        )
                    )
        if not itens:
            raise ValidationError(
                "Informe ao menos um bloco de dias e horários de funcionamento para retirada."
            )

        por_dia: dict[int, list[ItemHorario]] = {}
        for item in itens:
            por_dia.setdefault(item.dia_semana, []).append(item)
        for faixas in por_dia.values():
            ordenadas = sorted(faixas, key=lambda h: (h.hora_abertura, h.hora_fechamento))
            for i in range(1, len(ordenadas)):
                if ordenadas[i].hora_abertura < ordenadas[i - 1].hora_fechamento:
                    raise ValidationError(
                        f"{MSG_INCORRETO_PREFIXO}. Existem horários sobrepostos no mesmo dia."
                    )

    def para_itens(self) -> list[ItemHorario]:
        itens: list[ItemHorario] = []
        for form in self.forms:
            if not getattr(form, "cleaned_data", None):
                continue
            dias = form.cleaned_data.get("dias") or []
            abertura = form.cleaned_data.get("hora_abertura")
            fechamento = form.cleaned_data.get("hora_fechamento")
            if dias and abertura is not None and fechamento is not None:
                for dia in dias:
                    itens.append(
                        ItemHorario(
                            dia_semana=int(dia),
                            hora_abertura=abertura,
                            hora_fechamento=fechamento,
                        )
                    )
        return itens


HorarioFuncionamentoFormSet = formset_factory(
    HorarioBlocoForm,
    formset=BaseHorarioBlocoFormSet,
    extra=1,
    max_num=14,
)


def agrupar_horarios_para_blocos(horarios) -> list[dict]:
    """Agrupa HorarioFuncionamentoPonto por faixa (abertura, fechamento) para o formset."""
    por_faixa: dict[tuple[time, time], list[str]] = {}
    for h in horarios:
        chave = (h.hora_abertura, h.hora_fechamento)
        por_faixa.setdefault(chave, []).append(str(h.dia_semana))
    blocos = [
        {
            "dias": dias,
            "hora_abertura": abertura.strftime("%H:%M"),
            "hora_fechamento": fechamento.strftime("%H:%M"),
        }
        for (abertura, fechamento), dias in por_faixa.items()
    ]
    return blocos or [{}]


class ConvidarResponsavelForm(_ResumoErrosMixin, forms.Form):
    identificador = forms.CharField(
        label="E-mail ou CPF do convidado",
        required=True,
        max_length=254,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Digite o e-mail ou CPF cadastrado no ReMed",
            }
        ),
    )


class PontoColetaFiltroPublicoForm(forms.Form):
    termo = forms.CharField(
        label="Nome do estabelecimento",
        required=False,
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Nome fantasia do ponto de coleta"}
        ),
    )
    tipo_estabelecimento = forms.ChoiceField(
        label="Tipo de estabelecimento",
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    municipio = forms.CharField(
        label="Município",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Cidade"}),
    )

    def __init__(self, *args, tipos_estabelecimento=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_estabelecimento"].choices = [
            ("", "Todos os tipos"),
            *((str(t.pk), t.nome) for t in tipos_estabelecimento),
        ]

    def para_filtros(self) -> FiltrosPontoColeta:
        tipo_raw = self.cleaned_data.get("tipo_estabelecimento") or ""
        return FiltrosPontoColeta(
            termo=self.cleaned_data.get("termo", ""),
            tipo_estabelecimento_id=int(tipo_raw) if tipo_raw.isdigit() else None,
            municipio=self.cleaned_data.get("municipio", ""),
        )


class AdminPontoColetaFiltroForm(PontoColetaFiltroPublicoForm):
    cnpj = forms.CharField(
        label="CNPJ",
        required=False,
        max_length=18,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Dígitos do CNPJ",
                "data-mascara": "cnpj",
            }
        ),
    )
    status = forms.ChoiceField(
        label="Status",
        required=False,
        choices=(("", "Todos os status"), *StatusPontoColeta.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    revisao_vencida = forms.BooleanField(
        label="Apenas revisão periódica vencida",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def para_filtros(self) -> FiltrosPontoColeta:
        base = super().para_filtros()
        return FiltrosPontoColeta(
            termo=base.termo,
            cnpj=somente_digitos(self.cleaned_data.get("cnpj", "")),
            tipo_estabelecimento_id=base.tipo_estabelecimento_id,
            municipio=base.municipio,
            status=self.cleaned_data.get("status", ""),
            revisao_vencida=bool(self.cleaned_data.get("revisao_vencida")),
        )


class AdminAlterarCnpjForm(_ResumoErrosMixin, forms.Form):
    novo_cnpj = forms.CharField(
        label="Novo CNPJ",
        required=True,
        max_length=18,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "00.000.000/0000-00",
                "data-mascara": "cnpj",
            }
        ),
    )
    motivo = forms.CharField(
        label="Motivo da alteração do CNPJ",
        required=True,
        max_length=500,
        error_messages={"required": "Informe o motivo da alteração do CNPJ."},
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 2, "placeholder": "Justificativa objetiva"}
        ),
    )

    def clean_novo_cnpj(self) -> str:
        try:
            return validar_cnpj(self.cleaned_data.get("novo_cnpj", ""))
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro

    def clean_motivo(self) -> str:
        valor = (self.cleaned_data.get("motivo") or "").strip()
        if not valor:
            raise ValidationError("Informe o motivo da alteração do CNPJ.")
        return valor


class DocumentoPontoForm(_ResumoErrosMixin, forms.Form):
    """Upload de documento de ponto de coleta (RF006 / ADR 0016)."""

    tipo_documento = forms.ChoiceField(
        label="Tipo de documento",
        required=True,
        choices=(),
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    numero_documento = forms.CharField(
        label="Número do documento",
        required=True,
        max_length=80,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Ex.: ALV-2026-00412"}
        ),
    )
    data_validade = forms.DateField(
        label="Data de validade",
        required=True,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "invalid": f"{MSG_INCORRETO_PREFIXO}. Informe uma data válida (dd/mm/aaaa).",
        },
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "class": "form-control"},
        ),
    )
    arquivo = forms.FileField(
        label="Arquivo (PDF, JPG ou PNG · máx. 5 MB)",
        required=True,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png"}
        ),
    )

    def __init__(self, *args, tipos_documento=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_documento"].choices = [
            ("", "Selecione o tipo de documento"),
            *((str(t.pk), t.nome) for t in tipos_documento),
        ]


class AdminDocumentoFiltroForm(forms.Form):
    ponto_coleta = forms.IntegerField(
        label="ID do ponto",
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ex.: 1"}),
    )
    tipo_documento = forms.ChoiceField(
        label="Tipo de documento",
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    status = forms.ChoiceField(
        label="Status",
        required=False,
        choices=(("", "Todos os status"), *StatusDocumentoPonto.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    validade_ate = forms.DateField(
        label="Validade até",
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}),
    )

    def __init__(self, *args, tipos_documento=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_documento"].choices = [
            ("", "Todos os tipos"),
            *((str(t.pk), t.nome) for t in tipos_documento),
        ]

    def para_filtros(self) -> FiltrosDocumentosAdmin:
        tipo_raw = self.cleaned_data.get("tipo_documento") or ""
        return FiltrosDocumentosAdmin(
            ponto_coleta_id=self.cleaned_data.get("ponto_coleta"),
            tipo_documento_id=int(tipo_raw) if tipo_raw.isdigit() else None,
            status=self.cleaned_data.get("status", ""),
            validade_ate=self.cleaned_data.get("validade_ate"),
        )


class AdminAnalisePontoForm(_ResumoErrosMixin, forms.Form):
    resultado = forms.ChoiceField(
        label="Resultado da análise",
        required=True,
        choices=ResultadoAnalisePonto.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    motivo = forms.CharField(
        label="Motivo / observação",
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Obrigatório em reprovação ou pendência de documentação.",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        resultado = cleaned.get("resultado")
        motivo = (cleaned.get("motivo") or "").strip()
        if (
            resultado
            in {
                ResultadoAnalisePonto.REPROVADO,
                ResultadoAnalisePonto.PENDENTE_DOCUMENTACAO,
            }
            and not motivo
        ):
            self.add_error(
                "motivo",
                ValidationError("Informe o motivo da reprovação ou da suspensão", code="required"),
            )
        cleaned["motivo"] = motivo
        return cleaned


class AdminSituacaoPontoForm(_ResumoErrosMixin, forms.Form):
    novo_status = forms.ChoiceField(
        label="Nova situação",
        required=True,
        choices=(
            (StatusPontoColeta.ATIVO, "Ativo (reativar)"),
            (StatusPontoColeta.SUSPENSO, "Suspenso"),
            (StatusPontoColeta.INATIVO, "Inativo"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    motivo = forms.CharField(
        label="Motivo",
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Descreva o motivo da suspensão, inativação ou reativação.",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        motivo = (cleaned.get("motivo") or "").strip()
        if not motivo:
            self.add_error(
                "motivo",
                ValidationError("Informe o motivo da reprovação ou da suspensão", code="required"),
            )
        cleaned["motivo"] = motivo
        return cleaned


class AdminRevisaoPontoForm(_ResumoErrosMixin, forms.Form):
    motivo = forms.CharField(
        label="Observação da revisão periódica (opcional)",
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Ex.: Documentação e funcionamento conferidos em revisão periódica.",
            }
        ),
    )
