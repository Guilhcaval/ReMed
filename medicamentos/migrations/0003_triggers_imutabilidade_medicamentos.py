# Migração SQL: triggers append-only BEFORE UPDATE OR DELETE em
# medicamentos_conferenciadoacao (Spec 10 / RF011) e medicamentos_execucaovencimento (Spec 11 / RF012).

from django.db import migrations

SQL_CRIAR_TRIGGERS = """
CREATE OR REPLACE FUNCTION remed_bloquear_mutacao_conferencia_doacao()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Conferencias de doacoes sao imutaveis (Spec 10 / ADR 0011 / RNF14).';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_medicamentos_conferenciadoacao_imutavel
    ON medicamentos_conferenciadoacao;

CREATE TRIGGER trg_medicamentos_conferenciadoacao_imutavel
BEFORE UPDATE OR DELETE ON medicamentos_conferenciadoacao
FOR EACH ROW
EXECUTE FUNCTION remed_bloquear_mutacao_conferencia_doacao();

CREATE OR REPLACE FUNCTION remed_bloquear_mutacao_execucao_vencimento()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Execucoes de vencimento sao imutaveis (Spec 11 / ADR 0014 / RNF14).';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_medicamentos_execucaovencimento_imutavel
    ON medicamentos_execucaovencimento;

CREATE TRIGGER trg_medicamentos_execucaovencimento_imutavel
BEFORE UPDATE OR DELETE ON medicamentos_execucaovencimento
FOR EACH ROW
EXECUTE FUNCTION remed_bloquear_mutacao_execucao_vencimento();
"""

SQL_REMOVER_TRIGGERS = """
DROP TRIGGER IF EXISTS trg_medicamentos_conferenciadoacao_imutavel
    ON medicamentos_conferenciadoacao;
DROP FUNCTION IF EXISTS remed_bloquear_mutacao_conferencia_doacao();

DROP TRIGGER IF EXISTS trg_medicamentos_execucaovencimento_imutavel
    ON medicamentos_execucaovencimento;
DROP FUNCTION IF EXISTS remed_bloquear_mutacao_execucao_vencimento();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("medicamentos", "0002_dados_iniciais_parametro_vencimento"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_CRIAR_TRIGGERS,
            reverse_sql=SQL_REMOVER_TRIGGERS,
        ),
    ]
