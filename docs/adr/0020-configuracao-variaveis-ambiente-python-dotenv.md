# 0020. Gerenciar configuração por variáveis de ambiente com `python-dotenv` e `.env.example`

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RS005, RNF09, RNF08

## Contexto

O projeto precisa separar segredos e configurações por ambiente (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, credenciais do PostgreSQL, credenciais SMTP, credenciais S3 e parâmetros operacionais) do código versionado no Git, atendendo às boas práticas de configuração segura (RS005 — OWASP Top 10:2025 A02) e à portabilidade entre desenvolvimento local (Windows/PowerShell), CI (GitHub Actions) e contêineres Docker em PaaS ([ADR 0019](0019-hospedagem-implantacao-e-backup.md)).

O repositório já possui `.env` listado no `.gitignore` e o pacote `python-dotenv==1.2.4` fixado no `requirements.txt` desde o commit inicial, mas essa escolha ainda não tinha uma ADR própria explicando os motivos e as regras de uso.

## Direcionadores da decisão

- Nenhum segredo versionado no Git (OWASP A02, RS005).
- Facilidade de configuração no ambiente local (Windows/PowerShell) sem exigir exportação manual de variáveis em cada terminal.
- Precedência garantida para variáveis de ambiente reais do sistema operacional/contêiner/PaaS em homologação e produção (sem que um arquivo `.env` sobrescreva variáveis do ambiente).
- Compatibilidade oficial com Python 3.14 ([ADR 0003](0003-python-3-14.md)) e parcimônia em novas dependências ([ADR 0004](0004-pip-venv-requirements-fixado.md)).

## Opções consideradas

### 1. `python-dotenv` + leitura via `os.environ` + `.env.example` versionado (recomendada)

Manter `python-dotenv` (já fixado em `requirements.txt` com suporte oficial ao Python 3.14) chamado em `core/settings.py` com `load_dotenv(override=False)`, ler valores via `os.environ` com pequenas funções auxiliares explícitas para conversão de tipos (`bool`, `int`, listas) e manter `.env.example` versionado sem valores reais.

- **Prós:**
  - Já está presente e validado no `requirements.txt` (`python-dotenv==1.2.4`, Python puro, zero dependências externas, suporte oficial ao Python 3.14).
  - `load_dotenv(override=False)` garante que variáveis injetadas por Docker, PaaS ou GitHub Actions sempre prevaleçam sobre um arquivo `.env` local.
  - Leitura direta com `os.environ` mantém `core/settings.py` transparente e sem DSL proprietária.
- **Contras:**
  - Conversões de tipo (`bool`, `int`, lista de `ALLOWED_HOSTS`) e parsing de URL de banco precisam de pequenos helpers explícitos no `settings.py` (em vez de virem prontos como no `django-environ`).

### 2. `django-environ`

Substituir `python-dotenv` por `django-environ`, utilizando `environ.Env()` com conversores prontos (`env.bool()`, `env.list()`, `env.db()` para `DATABASE_URL`).

- **Prós:**
  - Helpers prontos para padrões comuns do Django (incluindo parsing de `DATABASE_URL` em PaaS) e suporte a Python 3.14/Django 6.
- **Contras:**
  - Introduz troca de dependência já instalada (`python-dotenv` -> `django-environ`) e adiciona uma camada de DSL de configuração para um conjunto pequeno de variáveis que poucos helpers em Python resolvem com clareza.

### 3. `os.environ` puro (removendo `python-dotenv`)

Ler apenas variáveis de ambiente do sistema operacional sem suporte a arquivo `.env`.

- **Prós:**
  - Menos um pacote no `requirements.txt`.
- **Contras:**
  - Exige que cada desenvolvedor exporte manualmente todas as variáveis no shell (especialmente trabalhoso no Windows/PowerShell e em múltiplas sessões de terminal), aumentando atrito no desenvolvimento local e o risco de alguém colocar valores padrão inseguros no `settings.py`.

## Decisão

**Opção 1 (`python-dotenv` + `os.environ` + `.env.example`)**.

Regras que passam a valer:

- `core/settings.py` carrega `.env` com `load_dotenv(override=False)` (nunca sobrescrevendo variáveis já definidas pelo sistema/contêiner/CI).
- O arquivo `.env` (e variações `.env.*.local`) permanece estritamente fora do Git (`.gitignore`); o repositório mantém `.env.example` atualizado com todos os nomes de variáveis obrigatórias e valores fictícios/vazios.
- Variáveis críticas (`SECRET_KEY`, credenciais de banco, `ALLOWED_HOSTS` quando `DEBUG=False`) falham explicitamente na inicialização se ausentes — nunca usar chave secreta padrão em produção (OWASP A02).
- Valores de regra de negócio configuráveis (prazos, limites das ADRs 0009, 0013, 0014, 0015, 0016, 0018) ficam como constantes nomeadas em `settings`, podendo ser ajustadas por variável de ambiente sem espalhar literais no código.

## Consequências

- Positivas:
  - Formaliza a dependência `python-dotenv` já presente no `requirements.txt`, eliminando lacuna de rastreabilidade na tabela de dependências.
  - Fluxo uniforme entre Windows local, GitHub Actions e contêiner Docker em PaaS.
- Negativas e custos:
  - Exige manter `.env.example` sincronizado sempre que uma nova variável for adicionada em `core/settings.py` e escrever pequenos helpers de tipagem (`bool`/`int`/lista) no `settings.py`.
- Impacto em specs e arquitetura:
  - Atualiza a referência do `python-dotenv` na tabela de dependências de `docs/arquitetura.md`.

## Como verificar

- `.env` não está rastreado no Git (`git ls-files .env` vazio) e `.env.example` existe sem segredos reais.
- `load_dotenv(override=False)` (ou comportamento padrão sem `override=True`) é usado em `core/settings.py`.
- Teste de configuração confirma que `DEBUG=False` sem `SECRET_KEY` ou `ALLOWED_HOSTS` falha ao inicializar e que `python manage.py check --deploy` passa com variáveis de produção.

## Notas

- **ADRs relacionadas:** [ADR 0003](0003-python-3-14.md), [ADR 0004](0004-pip-venv-requirements-fixado.md) e [ADR 0019](0019-hospedagem-implantacao-e-backup.md).
