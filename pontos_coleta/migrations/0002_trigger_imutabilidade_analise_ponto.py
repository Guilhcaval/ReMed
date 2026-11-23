# Migração SQL: trigger append-only BEFORE UPDATE OR DELETE em pontos_coleta_analisepontocoleta
# (Spec 07 / RN-07-05 / ADR 0011 / RNF14 — acréscimo da especificação aprovado).

from django.db import migrations

SQL_CRIAR_TRIGGER = """
CREATE OR REPLACE FUNCTION remed_bloquear_mutacao_analise_ponto()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Analises de pontos de coleta sao imutaveis (Spec 07 / ADR 0011 / RNF14).';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pontos_coleta_analisepontocoleta_imutavel
    ON pontos_coleta_analisepontocoleta;

CREATE TRIGGER trg_pontos_coleta_analisepontocoleta_imutavel
BEFORE UPDATE OR DELETE ON pontos_coleta_analisepontocoleta
FOR EACH ROW
EXECUTE FUNCTION remed_bloquear_mutacao_analise_ponto();
"""

SQL_REMOVER_TRIGGER = """
DROP TRIGGER IF EXISTS trg_pontos_coleta_analisepontocoleta_imutavel
    ON pontos_coleta_analisepontocoleta;
DROP FUNCTION IF EXISTS remed_bloquear_mutacao_analise_ponto();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("pontos_coleta", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_CRIAR_TRIGGER,
            reverse_sql=SQL_REMOVER_TRIGGER,
        ),
    ]
