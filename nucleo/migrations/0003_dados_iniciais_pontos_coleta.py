# Migração de dados: popula os 6 tipos iniciais de estabelecimento (RN-05-02)
# e os 2 tipos obrigatórios de documento de ponto de coleta (RN-06-01).

from django.db import migrations

TIPOS_ESTABELECIMENTO_INICIAIS = (
    "Farmácia",
    "Posto/Unidade de Saúde",
    "Hospital",
    "Clínica",
    "ONG/Instituição Social",
    "Outros",
)

TIPOS_DOCUMENTO_INICIAIS = (
    ("Licença de funcionamento", True),
    ("Alvará sanitário", True),
)


def popular_cadastros_auxiliares(apps, schema_editor):
    _ = schema_editor
    TipoEstabelecimento = apps.get_model("nucleo", "TipoEstabelecimento")
    TipoDocumentoPonto = apps.get_model("nucleo", "TipoDocumentoPonto")

    for nome in TIPOS_ESTABELECIMENTO_INICIAIS:
        TipoEstabelecimento.objects.get_or_create(nome=nome, defaults={"ativo": True})

    for nome, obrigatorio in TIPOS_DOCUMENTO_INICIAIS:
        TipoDocumentoPonto.objects.get_or_create(
            nome=nome,
            defaults={"obrigatorio": obrigatorio, "ativo": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("nucleo", "0002_tipodocumentoponto_tipoestabelecimento"),
    ]

    operations = [
        # reverse_code=noop preserva integridade de FKs on_delete=PROTECT em reversão.
        migrations.RunPython(popular_cadastros_auxiliares, reverse_code=migrations.RunPython.noop),
    ]
