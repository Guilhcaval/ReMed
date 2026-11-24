# Migração de dados: inicializa o singleton ParametroVencimento (id=1) com valores iniciais
# (validade_minima_restante_dias=30 provisório da Questão 4 do PRD; antecedencia_aviso_dias=15).

from django.db import migrations


def inicializar_parametro_vencimento(apps, schema_editor):
    _ = schema_editor
    ParametroVencimento = apps.get_model("medicamentos", "ParametroVencimento")
    ParametroVencimento.objects.get_or_create(
        id=1,
        defaults={
            "validade_minima_restante_dias": 30,
            "antecedencia_aviso_dias": 15,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("medicamentos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            inicializar_parametro_vencimento,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
