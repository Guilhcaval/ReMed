# Migração SQL: trigger append-only BEFORE UPDATE OR DELETE em auditoria_registroauditoria (ADR 0011).

from django.db import migrations

SQL_CRIAR_TRIGGER = """
CREATE OR REPLACE FUNCTION remed_bloquear_mutacao_auditoria()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Registros de auditoria sao imutaveis (ADR 0011 / RNF14).';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auditoria_registroauditoria_imutavel
    ON auditoria_registroauditoria;

CREATE TRIGGER trg_auditoria_registroauditoria_imutavel
BEFORE UPDATE OR DELETE ON auditoria_registroauditoria
FOR EACH ROW
EXECUTE FUNCTION remed_bloquear_mutacao_auditoria();
"""

SQL_REMOVER_TRIGGER = """
DROP TRIGGER IF EXISTS trg_auditoria_registroauditoria_imutavel
    ON auditoria_registroauditoria;
DROP FUNCTION IF EXISTS remed_bloquear_mutacao_auditoria();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("auditoria", "0002_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_CRIAR_TRIGGER,
            reverse_sql=SQL_REMOVER_TRIGGER,
        ),
    ]
