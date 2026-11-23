# 0002. Usar PostgreSQL como banco de dados

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF09, RNF06, RS007, RNF14, RNF05, RF015

## Contexto

O RNF09 pede um banco de dados relacional. Reserva, agendamento e entrega precisam ser transacionais, sem permitir que o mesmo medicamento seja reservado para duas solicitações (RNF06, RS007). Toda alteração gera um histórico imutável (RNF14). O RNF05 pede backup diário automático, com retenção mínima de 30 dias e restauração testada. Além disso, a busca de medicamentos (RF015) exige ordenação por proximidade geográfica, com cálculo de distância no servidor (RS010).

O `requirements.txt` inclui o driver `psycopg` 3.3.9.

## Direcionadores da decisão

- Banco relacional (RNF09).
- Transações e bloqueio de linha para impedir reserva dupla (RNF06, RS007).
- Constraints no banco para unicidade de CPF, CNPJ e e-mail (RF001, RF005) e para quantidades não negativas.
- Bom suporte no Django.

## Opções consideradas

1. PostgreSQL.
2. MySQL ou MariaDB.
3. SQLite.

## Decisão

Opção 1. O banco de dados do projeto é o PostgreSQL, acessado pelo Django com o driver `psycopg`, conforme o `requirements.txt`. As credenciais de acesso vêm de variáveis de ambiente, nunca do repositório.

## Consequências

- Positivas:
  - Transações e `SELECT ... FOR UPDATE` (no Django, `select_for_update()`) atendem a reserva transacional (RNF06, RS007).
  - As constraints de unicidade e de verificação ficam garantidas no banco, além da validação nos forms.
  - Caso o projeto opte por consultas espaciais no banco para a busca por proximidade (RF015, RS010), o PostgreSQL oferece a extensão PostGIS (recomendada pela documentação do GeoDjango), sem que esta ADR decida pelo seu uso.
- Negativas e custos:
  - Cada ambiente de desenvolvimento precisa de um servidor PostgreSQL. O SQLite padrão do Django não serve.
  - Os testes de concorrência (RNF06) só têm valor se rodarem em PostgreSQL, porque o comportamento de bloqueio depende do banco.
  - Backup, retenção e restauração (RNF05) dependem da hospedagem, ainda não decidida.
- Impacto em specs e arquitetura:
  - As specs podem exigir constraints e bloqueio de linha nas operações de reserva, agendamento e entrega.
  - A forma de calcular a distância na busca (RF015, RS010) pode usar recursos do PostgreSQL, mas isso será decidido na ADR de geolocalização.

## Como verificar

- `DATABASES` em `settings` usa `django.db.backends.postgresql`, com credenciais lidas do ambiente.
- Os testes, inclusive os de concorrência, rodam em PostgreSQL.
- Não há credenciais de banco versionadas.

## Notas

- Versão do PostgreSQL: a confirmar ao definir a hospedagem.
- Pendentes: as ADRs de hospedagem e backup (RNF05, RNF08), de geolocalização (RF015, RS010) e de reserva transacional (RNF06, RS007).
