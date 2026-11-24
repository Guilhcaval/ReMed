# Migração de dados: popula as 11 formas farmacêuticas iniciais (Spec 08 / RN-08-01).

from django.db import migrations

FORMAS_FARMACEUTICAS_INICIAIS = (
    "Comprimido",
    "Cápsula",
    "Xarope",
    "Injetável",
    "Pomada",
    "Colírio",
    "Solução oral",
    "Suspensão",
    "Creme/Gel",
    "Aerossol/Spray",
    "Outros",
)


def popular_formas_farmaceuticas(apps, schema_editor):
    _ = schema_editor
    FormaFarmaceutica = apps.get_model("nucleo", "FormaFarmaceutica")
    for nome in FORMAS_FARMACEUTICAS_INICIAIS:
        FormaFarmaceutica.objects.get_or_create(nome=nome, defaults={"ativo": True})


class Migration(migrations.Migration):
    dependencies = [
        ("nucleo", "0004_formafarmaceutica"),
    ]

    operations = [
        # reverse_code=noop preserva integridade de FKs on_delete=PROTECT em reversão.
        migrations.RunPython(
            popular_formas_farmaceuticas,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
