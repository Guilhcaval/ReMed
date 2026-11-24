"""Formulários de validação de formato do app medicamentos (Specs 08, 09, 10, 11 e 14)."""

from decimal import Decimal, InvalidOperation

from django import forms
from django.conf import settings

from medicamentos.models import (
    CondicaoConservacao,
    ResultadoConferenciaDoacao,
    StatusDoacao,
)
from nucleo.validators import validar_cep

OPCOES_SIM_NAO = (
    ("sim", "Sim"),
    ("nao", "Não"),
)


def _validar_arquivo_foto_formato(arquivo):
    if arquivo is None:
        return None
    nome = getattr(arquivo, "name", "") or ""
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in {"jpg", "jpeg", "png"}:
        raise forms.ValidationError("Envie a foto da embalagem em JPG ou PNG")
    if arquivo.size > settings.REMED_ARQUIVO_TAMANHO_MAX_BYTES:
        raise forms.ValidationError("O arquivo deve ter no máximo 5 MB")
    return arquivo


class DoacaoBaseForm(forms.Form):
    """Campos comuns do cadastro e edição de doação (RF008 + RF010), sem campos do sistema."""

    nome_medicamento = forms.CharField(
        label="Nome do medicamento (comercial ou genérico)",
        max_length=150,
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Ex.: Losartana potássica"}
        ),
    )
    principio_ativo = forms.CharField(
        label="Princípio ativo",
        max_length=150,
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Ex.: Losartana potássica"}
        ),
    )
    concentracao_dosagem = forms.CharField(
        label="Concentração / dosagem",
        max_length=80,
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: 50 mg"}),
    )
    forma_farmaceutica = forms.ChoiceField(
        label="Forma farmacêutica",
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    quantidade = forms.IntegerField(
        label="Quantidade (unidades)",
        min_value=1,
        error_messages={
            "required": "Campo(s) obrigatório(s) não preenchido(s)",
            "min_value": "A quantidade deve ser maior que zero.",
            "invalid": "Informe uma quantidade numérica válida.",
        },
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": "1", "placeholder": "Ex.: 30"}
        ),
    )
    fabricante = forms.CharField(
        label="Fabricante / laboratório",
        max_length=120,
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: EMS"}),
    )
    lote = forms.CharField(
        label="Lote",
        max_length=60,
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: L2026A01"}),
    )
    data_validade = forms.DateField(
        label="Data de validade",
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        error_messages={
            "required": "Campo(s) obrigatório(s) não preenchido(s)",
            "invalid": "Informe uma data de validade válida.",
        },
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    embalagem_integra = forms.ChoiceField(
        label="A embalagem está íntegra (sem violação ou uso parcial)?",
        choices=OPCOES_SIM_NAO,
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.RadioSelect(),
    )
    controle_especial = forms.ChoiceField(
        label="É medicamento de controle especial (receita retida / Portaria SVS/MS nº 344/1998)?",
        choices=OPCOES_SIM_NAO,
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.RadioSelect(),
    )
    condicao_conservacao = forms.ChoiceField(
        label="Condição de conservação",
        choices=CondicaoConservacao.choices,
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.Select(attrs={"class": "form-select", "data-conservacao-select": "true"}),
    )
    faixa_temperatura_bula = forms.CharField(
        label="Faixa de temperatura indicada na bula",
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ex.: 2 °C a 8 °C (conforme a bula)",
            }
        ),
    )
    declaracao_doador_conservacao = forms.BooleanField(
        label=(
            "Declaro que o medicamento foi mantido refrigerado conforme a bula até o cadastro "
            "e será mantido refrigerado até o momento da retirada."
        ),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    sujeito_receita = forms.ChoiceField(
        label="Medicamento sujeito a receita médica?",
        choices=OPCOES_SIM_NAO,
        error_messages={"required": "Campo(s) obrigatório(s) não preenchido(s)"},
        widget=forms.RadioSelect(),
    )
    ponto_coleta = forms.ChoiceField(
        label="Ponto de coleta preferencial para retirada (opcional)",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "data-ponto-coleta-select": "true"}),
    )
    observacoes = forms.CharField(
        label="Observações (opcional)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Informações adicionais sobre a embalagem ou disponibilidade.",
            }
        ),
    )

    def __init__(self, *args, formas_farmaceuticas=(), pontos_coleta=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["forma_farmaceutica"].choices = [("", "Selecione...")] + [
            (str(f.pk), f.nome) for f in formas_farmaceuticas
        ]
        opcoes_pontos = [("", "Sem ponto pré-definido (combinar local seguro no agendamento)")]
        for ponto in pontos_coleta:
            sufixo = " · Com refrigeração" if ponto.possui_refrigeracao else ""
            rotulo = (
                f"{ponto.nome_fantasia} — {ponto.bairro}, {ponto.municipio}/{ponto.estado}{sufixo}"
            )
            opcoes_pontos.append((str(ponto.pk), rotulo))
        self.fields["ponto_coleta"].choices = opcoes_pontos

    def mensagens_resumo_erros(self) -> list[str]:
        mensagens: list[str] = []
        for erros in self.errors.values():
            for msg in erros:
                if msg not in mensagens:
                    mensagens.append(str(msg))
        return mensagens


class DoacaoCadastroForm(DoacaoBaseForm):
    foto_1 = forms.FileField(
        label="Foto 1 da embalagem (obrigatória — frente / nome e validade)",
        error_messages={"required": "Envie ao menos uma foto da embalagem em JPG ou PNG."},
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": ".jpg,.jpeg,.png,image/jpeg,image/png"}
        ),
    )
    foto_2 = forms.FileField(
        label="Foto 2 da embalagem (opcional — lote e validade)",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": ".jpg,.jpeg,.png,image/jpeg,image/png"}
        ),
    )
    ia_sugestao_utilizada = forms.CharField(
        required=False,
        initial="nao",
        widget=forms.HiddenInput(),
    )
    ia_validade_sugerida = forms.CharField(
        required=False,
        initial="nao",
        widget=forms.HiddenInput(),
    )
    ia_campos_baixa_confianca = forms.CharField(
        required=False,
        initial="",
        widget=forms.HiddenInput(),
    )
    confirmar_validade_ia = forms.BooleanField(
        label="Confirmo que conferi a data de validade sugerida pela IA diretamente na embalagem.",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    confirmar_baixa_confianca_ia = forms.BooleanField(
        label="Confirmo que revisei manualmente os campos destacados com baixa confiança da IA.",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_foto_1(self):
        return _validar_arquivo_foto_formato(self.cleaned_data.get("foto_1"))

    def clean_foto_2(self):
        return _validar_arquivo_foto_formato(self.cleaned_data.get("foto_2"))

    def clean(self):
        cleaned = super().clean()
        validade_sugerida = (cleaned.get("ia_validade_sugerida") or "").strip().lower() == "sim"
        campos_baixa = [
            c.strip()
            for c in (cleaned.get("ia_campos_baixa_confianca") or "").split(",")
            if c.strip()
        ]
        if validade_sugerida and not cleaned.get("confirmar_validade_ia"):
            self.add_error(
                "confirmar_validade_ia",
                "Confirme explicitamente a data de validade sugerida pela IA antes de salvar.",
            )
        if campos_baixa and not cleaned.get("confirmar_baixa_confianca_ia"):
            self.add_error(
                "confirmar_baixa_confianca_ia",
                "Revise e confirme os campos destacados com baixa confiança da IA antes de salvar.",
            )
        return cleaned


class DoacaoEditarForm(DoacaoBaseForm):
    foto_1 = forms.FileField(
        label="Substituir foto 1 da embalagem (opcional)",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": ".jpg,.jpeg,.png,image/jpeg,image/png"}
        ),
    )
    foto_2 = forms.FileField(
        label="Adicionar ou substituir foto 2 da embalagem (opcional)",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": ".jpg,.jpeg,.png,image/jpeg,image/png"}
        ),
    )

    def clean_foto_1(self):
        return _validar_arquivo_foto_formato(self.cleaned_data.get("foto_1"))

    def clean_foto_2(self):
        return _validar_arquivo_foto_formato(self.cleaned_data.get("foto_2"))


class MinhasDoacoesFiltroForm(forms.Form):
    termo = forms.CharField(
        label="Medicamento ou princípio ativo",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Nome ou princípio ativo"}
        ),
    )
    status = forms.ChoiceField(
        label="Status",
        required=False,
        choices=[("", "Todos")] + list(StatusDoacao.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    data_inicio = forms.DateField(
        label="Cadastrado de",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    data_fim = forms.DateField(
        label="Até",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )


class AdminConferenciaFiltroForm(forms.Form):
    termo = forms.CharField(
        label="Medicamento ou princípio ativo",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Buscar na fila..."}),
    )
    condicao_conservacao = forms.ChoiceField(
        label="Conservação",
        required=False,
        choices=[("", "Todas")] + list(CondicaoConservacao.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    sujeito_receita = forms.ChoiceField(
        label="Receita",
        required=False,
        choices=[("", "Todas"), ("sim", "Exige receita"), ("nao", "Sem receita")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    data_inicio = forms.DateField(
        label="Cadastrado de",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    data_fim = forms.DateField(
        label="Até",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )


class ConferenciaDoacaoForm(forms.Form):
    resultado = forms.ChoiceField(
        label="Resultado da conferência",
        choices=ResultadoConferenciaDoacao.choices,
        widget=forms.RadioSelect(),
    )
    motivo = forms.CharField(
        label="Motivo (obrigatório em caso de reprovação)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Informe o motivo claro para orientação ao doador.",
            }
        ),
    )


class ParametroVencimentoForm(forms.Form):
    validade_minima_restante_dias = forms.IntegerField(
        label="Validade mínima restante (dias)",
        min_value=0,
        max_value=3650,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "3650"}),
    )
    antecedencia_aviso_dias = forms.IntegerField(
        label="Antecedência do aviso de vencimento (dias)",
        min_value=1,
        max_value=365,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "365"}),
    )


class MedicamentoBuscaForm(forms.Form):
    termo = forms.CharField(
        label="Medicamento ou princípio ativo",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Ex.: Losartana, Dipirona, Insulina"}
        ),
    )
    forma_farmaceutica = forms.ChoiceField(
        label="Forma farmacêutica",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    concentracao = forms.CharField(
        label="Concentração / dosagem",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: 500 mg"}),
    )
    distancia_max_km = forms.IntegerField(
        label="Distância máxima (km)",
        required=False,
        min_value=1,
        max_value=500,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": "1", "placeholder": "Ex.: 10"}
        ),
    )
    validade_minima = forms.DateField(
        label="Válido pelo menos até",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    condicao_conservacao = forms.ChoiceField(
        label="Conservação",
        required=False,
        choices=[("", "Todas")] + list(CondicaoConservacao.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, formas_farmaceuticas=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["forma_farmaceutica"].choices = [("", "Todas")] + [
            (str(f.pk), f.nome) for f in formas_farmaceuticas
        ]


class DefinirLocalizacaoBuscaForm(forms.Form):
    cep = forms.CharField(
        label="CEP",
        required=False,
        max_length=9,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "00000-000", "inputmode": "numeric"}
        ),
    )
    latitude = forms.CharField(required=False, widget=forms.HiddenInput())
    longitude = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean(self):
        cleaned = super().clean()
        cep_bruto = (cleaned.get("cep") or "").strip()
        lat_bruta = (cleaned.get("latitude") or "").strip()
        lon_bruta = (cleaned.get("longitude") or "").strip()

        if cep_bruto:
            try:
                cleaned["cep_limpo"] = validar_cep(cep_bruto)
            except ValueError as erro:
                raise forms.ValidationError(str(erro)) from erro
            cleaned["modo"] = "cep"
            return cleaned

        if lat_bruta and lon_bruta:
            try:
                lat = Decimal(lat_bruta)
                lon = Decimal(lon_bruta)
            except InvalidOperation as erro:
                raise forms.ValidationError("Coordenadas de localização inválidas.") from erro
            if (
                lat < Decimal("-90")
                or lat > Decimal("90")
                or lon < Decimal("-180")
                or lon > Decimal("180")
            ):
                raise forms.ValidationError("Coordenadas de localização fora dos limites válidos.")
            cleaned["lat_decimal"] = lat
            cleaned["lon_decimal"] = lon
            cleaned["modo"] = "gps"
            return cleaned

        raise forms.ValidationError(
            "Informe um CEP válido ou autorize o uso da sua localização atual."
        )
