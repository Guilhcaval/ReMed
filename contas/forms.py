"""Formulários de validação de formato do app contas (Spec 01 / RF001)."""

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from contas.models import FUNCOES_ADMINISTRATIVAS, StatusUsuario
from contas.services import (
    NOME_MAX_CARACTERES,
    NOME_MIN_CARACTERES,
    ROTULOS_FUNCOES_ADMIN,
    SENHA_MIN_CARACTERES,
    DadosAtualizacaoPerfil,
    DadosCadastroUsuario,
    DadosEndereco,
    FiltrosConsultaUsuarios,
)
from nucleo.validators import (
    UFS_BRASIL,
    normalizar_email,
    somente_digitos,
    validar_celular,
    validar_cep,
    validar_cpf,
    validar_maioridade,
    validar_uf,
)

MSG_OBRIGATORIO_RESUMO = "Campo(s) obrigatório(s) não preenchido(s)"
MSG_INCORRETO_PREFIXO = "Campo preenchido incorretamente"
MSG_CAMPO_OBRIGATORIO = "Este campo é obrigatório."

OPCOES_UF = (("", "UF"), *UFS_BRASIL)


class _ResumoErrosMixin:
    """Consolida as mensagens literais da Spec 01 para exibição no topo do formulário."""

    def mensagens_resumo_erros(self) -> list[str]:
        if not self.errors:
            return []

        tem_obrigatorio = False
        tem_incorreto = False
        mensagens_especificas: list[str] = []

        for campo, lista_erros in self.errors.as_data().items():
            for erro in lista_erros:
                if erro.code == "required":
                    tem_obrigatorio = True
                elif erro.code in {"cpf_duplicado", "email_duplicado", "regra_negocio"}:
                    texto = erro.message
                    if texto not in mensagens_especificas:
                        mensagens_especificas.append(texto)
                else:
                    tem_incorreto = True
                    if campo == "__all__" and erro.message not in mensagens_especificas:
                        mensagens_especificas.append(erro.message)

        resumo: list[str] = []
        if tem_obrigatorio:
            resumo.append(MSG_OBRIGATORIO_RESUMO)
        if tem_incorreto:
            resumo.append(MSG_INCORRETO_PREFIXO)
        resumo.extend(mensagens_especificas)
        return resumo


class _BaseDadosUsuarioForm(_ResumoErrosMixin, forms.Form):
    """Campos comuns entre cadastro e edição de perfil (sem campos de sistema)."""

    nome_completo = forms.CharField(
        label="Nome completo",
        required=True,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Digite seu nome completo",
                "autocomplete": "name",
                "maxlength": "120",
            }
        ),
    )
    data_nascimento = forms.DateField(
        label="Data de nascimento",
        required=True,
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "invalid": f"{MSG_INCORRETO_PREFIXO}. Informe a data no formato dd/mm/aaaa.",
        },
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={
                "class": "form-control",
                "placeholder": "dd/mm/aaaa",
                "inputmode": "numeric",
                "autocomplete": "bday",
                "maxlength": "10",
                "data-mascara": "data",
            },
        ),
    )
    email = forms.EmailField(
        label="E-mail",
        required=True,
        max_length=254,
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "invalid": f"{MSG_INCORRETO_PREFIXO}. Informe um e-mail válido.",
            "max_length": f"{MSG_INCORRETO_PREFIXO}. O e-mail excede o limite permitido.",
        },
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "seuemail@exemplo.com",
                "autocomplete": "email",
            }
        ),
    )
    celular = forms.CharField(
        label="Celular",
        required=True,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "(00) 00000-0000",
                "inputmode": "tel",
                "autocomplete": "tel-national",
                "maxlength": "15",
                "data-mascara": "celular",
            }
        ),
    )

    perfil_doador = forms.BooleanField(
        label="Doador",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    perfil_solicitante = forms.BooleanField(
        label="Solicitante",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    perfil_cuidador = forms.BooleanField(
        label="Cuidador/Familiar",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    cep = forms.CharField(
        label="CEP",
        required=True,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "00000-000",
                "inputmode": "numeric",
                "autocomplete": "postal-code",
                "maxlength": "9",
                "data-mascara": "cep",
            }
        ),
    )
    logradouro = forms.CharField(
        label="Logradouro",
        required=True,
        max_length=150,
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "max_length": f"{MSG_INCORRETO_PREFIXO}. Use no máximo 150 caracteres.",
        },
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Preenchido pelo CEP",
                "autocomplete": "street-address",
                "maxlength": "150",
            }
        ),
    )
    numero = forms.CharField(
        label="Número",
        required=True,
        max_length=20,
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "max_length": f"{MSG_INCORRETO_PREFIXO}. Use no máximo 20 caracteres.",
        },
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ex.: 123",
                "maxlength": "20",
            }
        ),
    )
    bairro = forms.CharField(
        label="Bairro",
        required=True,
        max_length=100,
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "max_length": f"{MSG_INCORRETO_PREFIXO}. Use no máximo 100 caracteres.",
        },
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Preenchido pelo CEP",
                "maxlength": "100",
            }
        ),
    )
    municipio = forms.CharField(
        label="Município",
        required=True,
        max_length=100,
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "max_length": f"{MSG_INCORRETO_PREFIXO}. Use no máximo 100 caracteres.",
        },
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Preenchido pelo CEP",
                "autocomplete": "address-level2",
                "maxlength": "100",
            }
        ),
    )
    estado = forms.ChoiceField(
        label="Estado",
        required=True,
        choices=OPCOES_UF,
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "invalid_choice": f"{MSG_INCORRETO_PREFIXO}. Selecione uma UF brasileira válida.",
        },
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "autocomplete": "address-level1",
            }
        ),
    )
    complemento = forms.CharField(
        label="Complemento (opcional)",
        required=False,
        max_length=100,
        error_messages={
            "max_length": f"{MSG_INCORRETO_PREFIXO}. Use no máximo 100 caracteres.",
        },
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Apartamento, bloco, sala ou referência",
                "maxlength": "100",
            }
        ),
    )

    def clean_nome_completo(self) -> str:
        valor = (self.cleaned_data.get("nome_completo") or "").strip()
        if not valor:
            raise ValidationError(MSG_CAMPO_OBRIGATORIO, code="required")
        if len(valor) < NOME_MIN_CARACTERES or len(valor) > NOME_MAX_CARACTERES:
            raise ValidationError(
                f"{MSG_INCORRETO_PREFIXO}. Informe entre 3 e 120 caracteres.",
                code="invalid",
            )
        return valor

    def clean_data_nascimento(self):
        data_nasc = self.cleaned_data.get("data_nascimento")
        if data_nasc is None:
            return data_nasc
        try:
            return validar_maioridade(data_nasc)
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro

    def clean_email(self) -> str:
        return normalizar_email(self.cleaned_data.get("email", ""))

    def clean_celular(self) -> str:
        valor = (self.cleaned_data.get("celular") or "").strip()
        try:
            return validar_celular(valor)
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro

    def clean_cep(self) -> str:
        valor = (self.cleaned_data.get("cep") or "").strip()
        try:
            return validar_cep(valor)
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro

    def clean_estado(self) -> str:
        valor = (self.cleaned_data.get("estado") or "").strip()
        try:
            return validar_uf(valor)
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro

    def clean(self):
        cleaned = super().clean()
        tem_perfil = any(
            [
                cleaned.get("perfil_doador"),
                cleaned.get("perfil_solicitante"),
                cleaned.get("perfil_cuidador"),
            ]
        )
        if not tem_perfil:
            self.add_error(
                "perfil_doador",
                ValidationError(
                    "Selecione ao menos um perfil de uso "
                    "(Doador, Solicitante ou Cuidador/Familiar).",
                    code="required",
                ),
            )
        return cleaned

    def _montar_endereco(self) -> DadosEndereco:
        return DadosEndereco(
            cep=self.cleaned_data["cep"],
            logradouro=self.cleaned_data["logradouro"].strip(),
            numero=self.cleaned_data["numero"].strip(),
            bairro=self.cleaned_data["bairro"].strip(),
            municipio=self.cleaned_data["municipio"].strip(),
            estado=self.cleaned_data["estado"],
            complemento=(self.cleaned_data.get("complemento") or "").strip(),
        )


class UsuarioCadastroForm(_BaseDadosUsuarioForm):
    """Formulário de cadastro de pessoa física (Spec 01 / RF001)."""

    cpf = forms.CharField(
        label="CPF",
        required=True,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "000.000.000-00",
                "inputmode": "numeric",
                "maxlength": "14",
                "data-mascara": "cpf",
            }
        ),
    )
    senha = forms.CharField(
        label="Senha",
        required=True,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "class": "form-control",
                "placeholder": "Crie sua senha",
                "autocomplete": "new-password",
            },
        ),
    )
    aceite_termos = forms.BooleanField(
        label="Li e aceito os Termos de Uso e a Política de Privacidade.",
        required=True,
        error_messages={
            "required": "É obrigatório aceitar os Termos de Uso e a Política de Privacidade."
        },
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_cpf(self) -> str:
        valor = (self.cleaned_data.get("cpf") or "").strip()
        try:
            return validar_cpf(valor)
        except ValueError as erro:
            raise ValidationError(f"{MSG_INCORRETO_PREFIXO}. {erro}", code="invalid") from erro

    def clean_senha(self) -> str:
        senha = self.cleaned_data.get("senha") or ""
        if len(senha) < SENHA_MIN_CARACTERES:
            raise ValidationError(
                f"{MSG_INCORRETO_PREFIXO}. Use no mínimo 8 caracteres.",
                code="invalid",
            )
        # Acréscimo da especificação (aprovado): aplica os validadores de senha em settings.
        try:
            validate_password(senha)
        except ValidationError as erro:
            orientacao = " ".join(erro.messages)
            raise ValidationError(
                f"{MSG_INCORRETO_PREFIXO}. {orientacao}", code="invalid"
            ) from erro
        return senha

    def para_dados(self) -> DadosCadastroUsuario:
        return DadosCadastroUsuario(
            nome_completo=self.cleaned_data["nome_completo"],
            cpf=self.cleaned_data["cpf"],
            data_nascimento=self.cleaned_data["data_nascimento"],
            email=self.cleaned_data["email"],
            celular=self.cleaned_data["celular"],
            senha=self.cleaned_data["senha"],
            perfil_doador=bool(self.cleaned_data["perfil_doador"]),
            perfil_solicitante=bool(self.cleaned_data["perfil_solicitante"]),
            perfil_cuidador=bool(self.cleaned_data["perfil_cuidador"]),
            aceite_termos=bool(self.cleaned_data["aceite_termos"]),
            endereco=self._montar_endereco(),
        )


class UsuarioPerfilEditarForm(_BaseDadosUsuarioForm):
    """Formulário de alteração dos próprios dados cadastrais (CPF excluído — RN-01-03)."""

    def para_dados(self) -> DadosAtualizacaoPerfil:
        return DadosAtualizacaoPerfil(
            nome_completo=self.cleaned_data["nome_completo"],
            data_nascimento=self.cleaned_data["data_nascimento"],
            email=self.cleaned_data["email"],
            celular=self.cleaned_data["celular"],
            perfil_doador=bool(self.cleaned_data["perfil_doador"]),
            perfil_solicitante=bool(self.cleaned_data["perfil_solicitante"]),
            perfil_cuidador=bool(self.cleaned_data["perfil_cuidador"]),
            endereco=self._montar_endereco(),
        )


class ReenviarConfirmacaoForm(_ResumoErrosMixin, forms.Form):
    email = forms.EmailField(
        label="E-mail cadastrado",
        required=True,
        max_length=254,
        error_messages={
            "required": MSG_CAMPO_OBRIGATORIO,
            "invalid": f"{MSG_INCORRETO_PREFIXO}. Informe um e-mail válido.",
        },
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "seuemail@exemplo.com",
                "autocomplete": "email",
            }
        ),
    )

    def clean_email(self) -> str:
        return normalizar_email(self.cleaned_data.get("email", ""))


class UsuarioEncerrarContaForm(_ResumoErrosMixin, forms.Form):
    senha_atual = forms.CharField(
        label="Confirme sua senha atual",
        required=True,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "class": "form-control",
                "placeholder": "Digite sua senha atual",
                "autocomplete": "current-password",
            },
        ),
    )
    confirmar_encerramento = forms.BooleanField(
        label=(
            "Entendo que esta ação é irreversível e que meus dados pessoais serão "
            "eliminados/anonimizados."
        ),
        required=True,
        error_messages={"required": "Confirme que compreende a irreversibilidade do encerramento."},
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class LoginForm(_ResumoErrosMixin, forms.Form):
    """Formulário de entrada por E-mail ou CPF (sem CNPJ — ADR 0007 / Spec 02)."""

    identificador = forms.CharField(
        label="E-mail ou CPF",
        required=True,
        max_length=254,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Digite seu e-mail ou CPF",
                "autocomplete": "username",
            }
        ),
    )
    senha = forms.CharField(
        label="Senha",
        required=True,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "class": "form-control",
                "placeholder": "Digite sua senha",
                "autocomplete": "current-password",
            },
        ),
    )


class TotpCodigoForm(_ResumoErrosMixin, forms.Form):
    """Formulário de código TOTP de 6 dígitos (pareamento, login 2FA e step-up)."""

    codigo = forms.CharField(
        label="Código do aplicativo autenticador",
        required=True,
        max_length=12,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "000000",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "maxlength": "12",
            }
        ),
    )


class TotpRecuperacaoForm(_ResumoErrosMixin, forms.Form):
    """Formulário de código de recuperação alfanumérico de uso único."""

    codigo_recuperacao = forms.CharField(
        label="Código de recuperação",
        required=True,
        max_length=20,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control text-uppercase",
                "placeholder": "XXXX-XXXX",
                "autocomplete": "off",
                "maxlength": "20",
            }
        ),
    )


OPCOES_PERFIL_CONSULTA = (
    ("", "Todos os perfis/funções"),
    ("doador", "Doador"),
    ("solicitante", "Solicitante"),
    ("cuidador", "Cuidador/Familiar"),
    *((nome, f"Admin: {ROTULOS_FUNCOES_ADMIN[nome]}") for nome in FUNCOES_ADMINISTRATIVAS),
)
OPCOES_STATUS_CONSULTA = (("", "Todos os status"), *StatusUsuario.choices)
OPCOES_FUNCOES_ADMIN = tuple(
    (nome, ROTULOS_FUNCOES_ADMIN[nome]) for nome in FUNCOES_ADMINISTRATIVAS
)


class AdminUsuarioConsultaForm(forms.Form):
    """Filtros de pesquisa administrativa de usuários (RF004 / RN-04-07)."""

    termo = forms.CharField(
        label="Nome ou CPF parcial",
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Nome ou ao menos 3 dígitos do CPF",
            }
        ),
    )
    email = forms.CharField(
        label="E-mail",
        required=False,
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Trecho do e-mail",
            }
        ),
    )
    perfil = forms.ChoiceField(
        label="Perfil / Função",
        required=False,
        choices=OPCOES_PERFIL_CONSULTA,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    status = forms.ChoiceField(
        label="Status",
        required=False,
        choices=OPCOES_STATUS_CONSULTA,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    data_inicio = forms.DateField(
        label="Cadastrado de",
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}),
    )
    data_fim = forms.DateField(
        label="Até",
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}),
    )

    def clean_termo(self) -> str:
        valor = (self.cleaned_data.get("termo") or "").strip()
        if valor:
            somente_chars_cpf = all(ch.isdigit() or ch in ".- " for ch in valor)
            digitos = somente_digitos(valor)
            if somente_chars_cpf and digitos and len(digitos) < 3:
                raise ValidationError("Informe ao menos 3 dígitos para pesquisar por CPF parcial.")
        return valor

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("data_inicio")
        fim = cleaned.get("data_fim")
        if inicio is not None and fim is not None and inicio > fim:
            raise ValidationError("A data inicial não pode ser posterior à data final")
        return cleaned

    def para_filtros(self) -> FiltrosConsultaUsuarios:
        return FiltrosConsultaUsuarios(
            termo=self.cleaned_data.get("termo", ""),
            email=self.cleaned_data.get("email", ""),
            perfil=self.cleaned_data.get("perfil", ""),
            status=self.cleaned_data.get("status", ""),
            data_inicio=self.cleaned_data.get("data_inicio"),
            data_fim=self.cleaned_data.get("data_fim"),
        )


class AdminAlterarStatusForm(_ResumoErrosMixin, forms.Form):
    """Formulário de alteração de status administrativo (RF004 / RN-04-02 / RN-04-03)."""

    novo_status = forms.ChoiceField(
        label="Novo status",
        required=True,
        choices=StatusUsuario.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    motivo = forms.CharField(
        label="Motivo",
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Descreva o motivo objetivo da ação administrativa.",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("novo_status")
        motivo = (cleaned.get("motivo") or "").strip()
        if not motivo:
            if status in {StatusUsuario.SUSPENSO, StatusUsuario.BLOQUEADO}:
                self.add_error(
                    "motivo",
                    ValidationError(
                        "Informe o motivo da suspensão ou do bloqueio",
                        code="regra_negocio",
                    ),
                )
            else:
                self.add_error(
                    "motivo",
                    ValidationError(
                        "Informe o motivo da alteração de status.",
                        code="regra_negocio",
                    ),
                )
        cleaned["motivo"] = motivo
        return cleaned


class AdminAlterarFuncoesForm(_ResumoErrosMixin, forms.Form):
    """Atribuição/remoção das 8 funções administrativas com step-up 2FA (RF004 / ADR 0010)."""

    funcoes = forms.MultipleChoiceField(
        label="Funções administrativas",
        required=False,
        choices=OPCOES_FUNCOES_ADMIN,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    motivo = forms.CharField(
        label="Motivo",
        required=True,
        max_length=500,
        error_messages={"required": "Informe o motivo da alteração de funções administrativas."},
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Justificativa para atribuição ou remoção das funções.",
            }
        ),
    )
    codigo_step_up = forms.CharField(
        label="Código TOTP atual (reconfirmação 2FA)",
        required=True,
        max_length=12,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "000000",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "maxlength": "12",
            }
        ),
    )

    def clean_motivo(self) -> str:
        valor = (self.cleaned_data.get("motivo") or "").strip()
        if not valor:
            raise ValidationError("Informe o motivo da alteração de funções administrativas.")
        return valor


class AdminResetar2faForm(_ResumoErrosMixin, forms.Form):
    """Reset de 2FA de outro Administrador mediante motivo e step-up 2FA (ADR 0009)."""

    motivo = forms.CharField(
        label="Motivo do reset de 2FA",
        required=True,
        max_length=500,
        error_messages={"required": "Informe o motivo do reset de 2FA."},
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Ex.: perda de dispositivo confirmada pela equipe.",
            }
        ),
    )
    codigo_step_up = forms.CharField(
        label="Seu código TOTP atual (reconfirmação 2FA)",
        required=True,
        max_length=12,
        error_messages={"required": MSG_CAMPO_OBRIGATORIO},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "000000",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "maxlength": "12",
            }
        ),
    )

    def clean_motivo(self) -> str:
        valor = (self.cleaned_data.get("motivo") or "").strip()
        if not valor:
            raise ValidationError("Informe o motivo do reset de 2FA.")
        return valor
