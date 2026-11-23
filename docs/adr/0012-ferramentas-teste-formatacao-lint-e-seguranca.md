# 0012. Definir ferramentas de teste, formatação, lint e verificação de vulnerabilidades

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF09, RNF06, RS005

## Contexto

O projeto precisa padronizar suas ferramentas de qualidade antes da escrita do primeiro código de aplicação:

- **RNF09 (Desejável):** desenvolvimento com controle de versão (Git), banco de dados relacional e manutenção da rastreabilidade e da documentação técnica atualizada.
- **RNF06 (Essencial):** reserva, agendamento e entrega precisam ser testados com transações reais no PostgreSQL (ADR 0002), onde o comportamento de bloqueio de linha depende do banco de dados.
- **RS005:** exige proteção contra o OWASP Top 10 (cuja edição de 2025 inclui A03 — falhas na cadeia de suprimentos de software), reforçando a necessidade de checagem periódica de vulnerabilidades conhecidas nas dependências.
- **ADR 0003 e ADR 0004:** todas as ferramentas precisam ser compatíveis com **Python 3.14** e **Django 6.1.3**, e as dependências precisam ter versões fixadas por `==`, evitando misturar ferramentas de desenvolvimento com as de produção.

## Direcionadores da decisão

- Compatibilidade comprovada com Python 3.14 (ADR 0003) e Django 6.1 (ADR 0001).
- Suporte confiável a testes de service (sem `request`), testes de view (por perfil) e testes de concorrência com transações reais no PostgreSQL (RNF06).
- Poucas ferramentas para instalar, configurar e manter (ADR 0004).
- Checagem automatizável de estilo, problemas comuns, padrões inseguros de código e vulnerabilidades conhecidas em dependências (RS005).
- Separação clara entre dependências de produção e dependências de desenvolvimento.

## Opções consideradas

### Parte A — Executor de testes

#### T1. Runner nativo do Django (`python manage.py test` com `TestCase` e `TransactionTestCase`) (recomendada)

Usar o arcabouço `unittest` integrado ao Django (`django.test.TestCase` e `TransactionTestCase` para testes de concorrência no PostgreSQL).

- **Prós:**
  - Zero dependência externa adicional (ADR 0004) e compatibilidade imediata com o Django 6.1.3 e Python 3.14.
  - Alinhado diretamente às práticas de `TestCase` / `TransactionTestCase` e ao cliente de teste do Django.
  - Menor curva de aprendizado para toda a equipe.
- **Contras:**
  - Mais verboso para parametrização de casos de teste e reutilização de fixtures complexas do que o `pytest`.
  - Saída de falhas menos concisa do que a reescrita de `assert` do `pytest`.

#### T2. `pytest` + `pytest-django`

Usar `pytest` com o plugin `pytest-django` (suporte oficial a Python 3.14 e Django 6.0+ a partir da versão 4.12.0; validação com Django 6.1.3 no `.venv`).

- **Prós:**
  - Sintaxe enxuta (`assert`), fixtures composáveis e `@pytest.mark.parametrize`, muito úteis para matrizes de perfis e regras numeradas do ReMed.
  - Seleção rápida de testes por palavra-chave ou marcador.
- **Contras:**
  - Adiciona pacotes extras de desenvolvimento para fixar e manter.
  - Exige disciplina para não misturar convenções (`TestCase` vs. fixtures `db`/`transactional_db`).

---

### Parte B — Formatação e lint (incluindo checagem estática de segurança)

#### L1. `ruff` (`ruff check` + `ruff format`) (recomendada)

Usar o `ruff` (v0.14+, que suporta oficialmente Python 3.14 e `target-version = "py314"`) configurado em `pyproject.toml`, habilitando regras de estilo, imports, erros comuns e regras de segurança (`S`, equivalentes ao Bandit).

- **Prós:**
  - Uma única ferramenta muito rápida que substitui `black`, `isort`, `flake8` e grande parte do `bandit`.
  - Suporte oficial ao Python 3.14 e configuração unificada em `pyproject.toml`.
- **Contras:**
  - Não formata nem faz lint de templates HTML/Django (se desejado no futuro, exige ferramenta separada como `djlint`).

#### L2. Conjunto separado (`black` + `flake8` + `isort` + `bandit`)

- **Prós:**
  - Ferramentas tradicionais e bem documentadas no ecossistema Python.
- **Contras:**
  - Quatro dependências distintas para instalar, fixar, configurar sem conflitos entre si e manter atualizadas, com execução mais lenta.

---

### Parte C — Verificação de vulnerabilidades em dependências (OWASP A03)

#### S1. `pip-audit` (recomendada)

Usar `pip-audit` (suporte oficial a Python 3.14) para auditar `requirements.txt` e `requirements-dev.txt` contra vulnerabilidades conhecidas (PyPI/OSV).

- **Prós:**
  - Ferramenta mantida pela comunidade PyPA, executável localmente e em CI, retornando código de erro ao detectar vulnerabilidades conhecidas.
  - Complementa diretamente a ADR 0004 e o RS005.
- **Contras:**
  - Depende de acesso à rede para consultar a base de vulnerabilidades durante a execução da auditoria.

#### S2. Apenas alertas da plataforma Git (ex.: Dependabot) / revisão manual

- **Prós:**
  - Nenhuma ferramenta adicional no ambiente local.
- **Contras:**
  - Não permite auditar localmente antes de adicionar uma dependência nova ao `requirements.txt` e fica acoplado ao provedor Git.

---

### Parte D — Organização das dependências de desenvolvimento

#### D1. Arquivo separado `requirements-dev.txt` com `-r requirements.txt` e versões fixadas por `==` (recomendada)

- **Prós:**
  - Mantém `requirements.txt` limpo somente com pacotes de produção (reduzindo superfície de ataque e tamanho da imagem em produção), preservando todas as regras da ADR 0004.
- **Contras:**
  - Dois arquivos de dependências para manter sincronizados.

#### D2. Tudo em um único `requirements.txt`

- **Prós:**
  - Apenas um arquivo para instalar em qualquer ambiente.
- **Contras:**
  - Instala ferramentas de lint, auditoria e testes em produção sem necessidade.

## Decisão

Adotadas as opções **T1**, **L1**, **S1** e **D1**, com as seguintes regras que passam a valer:

- **Testes (T1):** runner nativo do Django (`python manage.py test`), rodando contra PostgreSQL (ADR 0002) para garantir fidelidade nos testes de constraints e concorrência (`TransactionTestCase`, RNF06).
- **Cobertura e templates:** uso de **`coverage` sem meta mínima obrigatória** (como ferramenta de apoio para identificar lacunas de teste); linter de templates (`djlint`) **fora do MVP**.
- **Formatação e lint (L1):** **`ruff`** (`ruff check` com regras de qualidade e segurança `S`, e `ruff format`), configurado em `pyproject.toml` com `target-version = "py314"`.
- **Vulnerabilidades em dependências (S1):** **`pip-audit`** executado ao adicionar/atualizar dependências e antes de entregas.
- **Separação de dependências (D1):** arquivo separado **`requirements-dev.txt`** (incluindo `-r requirements.txt` e fixando `ruff`, `pip-audit`, `coverage` e suas dependências indiretas com `==`), mantendo `requirements.txt` exclusivo de produção. Conforme a ADR 0004, essas ferramentas só entram no repositório quando o desenvolvimento de código começar.

## Consequências

- Positivas:
  - Apenas três ferramentas externas de desenvolvimento (`ruff`, `pip-audit` e `coverage`), mantendo o conjunto enxuto e compatível com Python 3.14.
  - Verificação local rápida de estilo, padrões inseguros, cobertura e vulnerabilidades antes de cada entrega.
  - Ambiente de produção livre de dependências de desenvolvimento.
- Negativas e custos:
  - Sem linter específico para templates HTML/Django no MVP (`djlint` fora do MVP).
  - A execução automática em pipeline de CI/CD dependerá da definição na ADR de hospedagem e implantação (ADR 0019).
- Impacto em specs e arquitetura:
  - Todas as specs passam a prever testes executáveis por `python manage.py test` e verificação com `ruff` e `pip-audit` antes de concluir cada entrega.

## Como verificar

- `python manage.py test` (e `coverage run manage.py test` + `coverage report`) executam toda a suíte de testes contra PostgreSQL sem falhas.
- `ruff check .` e `ruff format --check .` passam sem erros.
- `pip-audit -r requirements.txt` passa sem vulnerabilidades conhecidas não tratadas.
- `requirements.txt` não contém ferramentas exclusivas de desenvolvimento; todas as linhas de `requirements.txt` e `requirements-dev.txt` estão fixadas com `==`.

## Notas

- **Dependência de outras ADRs:** a automação dos comandos em pipeline (CI/CD) será integrada junto com a [ADR 0019](0019-hospedagem-implantacao-e-backup.md).
- **ADRs relacionadas:** [ADR 0002](0002-postgresql-como-banco-de-dados.md), [ADR 0003](0003-python-3-14.md), [ADR 0004](0004-pip-venv-requirements-fixado.md) e [ADR 0013](0013-reserva-transacional-e-concorrencia.md).
