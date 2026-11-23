# Migração SQL: trigger append-only BEFORE UPDATE OR DELETE em contas_registroacesso
# (ADR 0009 / ADR 0011 / RNF14).

from django.db import migrations

SQL_CRIAR_TRIGGER = """
CREATE OR REPLACE FUNCTION remed_bloquear_mutacao_registro_acesso()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Registros de acesso sao imutaveis (ADR 0009 / ADR 0011 / RNF14).';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contas_registroacesso_imutavel
    ON contas_registroacesso;

CREATE TRIGGER trg_contas_registroacesso_imutavel
BEFORE UPDATE OR DELETE ON contas_registroacesso
FOR EACH ROW
EXECUTE FUNCTION remed_bloquear_mutacao_registro_acesso();
"""

SQL_REMOVER_TRIGGER = """
DROP TRIGGER IF EXISTS trg_contas_registroacesso_imutavel
    ON contas_registroacesso;
DROP FUNCTION IF EXISTS remed_bloquear_mutacao_registro_acesso();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("contas", "0003_dispositivototp_codigorecuperacaototp_registroacesso_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_CRIAR_TRIGGER,
            reverse_sql=SQL_REMOVER_TRIGGER,
        ),
    ]
