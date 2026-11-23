# Migração SQL: trigger append-only BEFORE UPDATE OR DELETE em contas_acaogestaousuario
# (Spec 04 / ADR 0011 / RNF14 — acréscimo da especificação aprovado).

from django.db import migrations

SQL_CRIAR_TRIGGER = """
CREATE OR REPLACE FUNCTION remed_bloquear_mutacao_acao_gestao()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Acoes de gestao de usuarios sao imutaveis (Spec 04 / ADR 0011 / RNF14).';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contas_acaogestaousuario_imutavel
    ON contas_acaogestaousuario;

CREATE TRIGGER trg_contas_acaogestaousuario_imutavel
BEFORE UPDATE OR DELETE ON contas_acaogestaousuario
FOR EACH ROW
EXECUTE FUNCTION remed_bloquear_mutacao_acao_gestao();
"""

SQL_REMOVER_TRIGGER = """
DROP TRIGGER IF EXISTS trg_contas_acaogestaousuario_imutavel
    ON contas_acaogestaousuario;
DROP FUNCTION IF EXISTS remed_bloquear_mutacao_acao_gestao();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("contas", "0005_acaogestaousuario"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_CRIAR_TRIGGER,
            reverse_sql=SQL_REMOVER_TRIGGER,
        ),
    ]
