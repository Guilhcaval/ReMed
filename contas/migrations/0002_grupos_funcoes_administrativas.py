# Migração de dados idempotente: 8 funções administrativas da ADR 0010 e ADR 0011.

from django.db import migrations

FUNCOES_ADMINISTRATIVAS = (
    "gestao_usuarios",
    "aprovacao_pontos_coleta",
    "conferencia_doacoes",
    "verificacao_receitas",
    "moderacao_denuncias",
    "metricas_e_parametros",
    "gestao_administradores",
    "auditoria",
)


def criar_grupos_administrativos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for nome in FUNCOES_ADMINISTRATIVAS:
        Group.objects.get_or_create(name=nome)


def remover_grupos_administrativos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=FUNCOES_ADMINISTRATIVAS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contas", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            criar_grupos_administrativos,
            reverse_code=remover_grupos_administrativos,
        ),
    ]
