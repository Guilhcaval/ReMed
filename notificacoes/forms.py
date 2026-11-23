"""Formulários de filtro do app notificacoes (Spec 03 / RF017)."""

from django import forms
from django.core.exceptions import ValidationError

from notificacoes.models import TipoNotificacao
from notificacoes.services import FiltrosNotificacao

OPCOES_TIPO_FILTRO = (("", "Todos os tipos"), *TipoNotificacao.choices)
OPCOES_STATUS_FILTRO = (
    ("", "Todas"),
    ("nao_lida", "Não lidas"),
    ("lida", "Lidas"),
)


class NotificacaoFiltroForm(forms.Form):
    tipo = forms.ChoiceField(
        label="Tipo",
        required=False,
        choices=OPCOES_TIPO_FILTRO,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    status = forms.ChoiceField(
        label="Status",
        required=False,
        choices=OPCOES_STATUS_FILTRO,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    data_inicio = forms.DateField(
        label="Data inicial",
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "class": "form-control"},
        ),
    )
    data_fim = forms.DateField(
        label="Data final",
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "class": "form-control"},
        ),
    )

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("data_inicio")
        fim = cleaned.get("data_fim")
        if inicio is not None and fim is not None and inicio > fim:
            raise ValidationError("A data inicial não pode ser posterior à data final")
        return cleaned

    def para_filtros(self) -> FiltrosNotificacao:
        return FiltrosNotificacao(
            tipo=self.cleaned_data.get("tipo", ""),
            status=self.cleaned_data.get("status", ""),
            data_inicio=self.cleaned_data.get("data_inicio"),
            data_fim=self.cleaned_data.get("data_fim"),
        )
