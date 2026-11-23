"""Formulários de validação de formato do app contas (Spec 01 / RF001)."""

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from contas.services import (
    NOME_MAX_CARACTERES,
    NOME_MIN_CARACTERES,
    SENHA_MIN_CARACTERES,
    DadosAtualizacaoPerfil,
    DadosCadastroUsuario,
    DadosEndereco,
)
from nucleo.validators import (
    UFS_BRASIL,
    normalizar_email,
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
