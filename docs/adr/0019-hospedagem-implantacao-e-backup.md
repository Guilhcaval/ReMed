# 0019. Definir modelo de hospedagem, implantação, CI/CD e backup

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF05, RNF08, RNF04, RNF11, RNF15, RS005, RS014

## Contexto

Os requisitos de infraestrutura e operação e várias ADRs já aceitas convergem na estratégia de hospedagem, implantação e backup:

- **RNF05 (Importante):** disponibilidade mínima de **99% ao mês**, **backup diário automático** com **retenção mínima de 30 dias** e **restauração testada periodicamente**.
- **RNF08 (Importante):** hospedagem em nuvem com **escalabilidade horizontal**, mínimo de **2 vCPU, 4 GB de RAM e 50 GB SSD** no ambiente inicial; fotos e receitas em armazenamento criptografado.
- **RNF04 (Importante):** páginas públicas e buscas em até 3 segundos (p95) com até 500 usuários simultâneos.
- **RS005 e RS014:** toda comunicação em **TLS 1.2 ou superior**; e-mails enviados exclusivamente do **domínio oficial** (com SPF, DKIM e DMARC).
- **RNF11 (Essencial — Questão 3 do PRD):** a viabilidade jurídica da redistribuição entre particulares é pré-requisito para a **implantação em produção**, mas não impede desenvolvimento e homologação acadêmica.
- **Dependências vindas das ADRs já aceitas ou em proposta:**
  - **Python 3.14** (ADR 0003), **Django 6.1** (ADR 0001) e **PostgreSQL** (ADR 0002).
  - Benchmark e calibração dos parâmetros do **Argon2id** no ambiente-alvo de 2 vCPU / 4 GB RAM, partindo do piso OWASP `>= 19 MiB` e `time_cost >= 2` (ADR 0008).
  - Execução dos comandos `manage.py` das rotinas agendadas (incluindo despacho de e-mails a cada 1 minuto e vencimento diário) + monitoramento de *heartbeat* (ADR 0014).
  - Provedor **SMTP** transacional sob domínio oficial (ADR 0015).
  - **Object Storage S3-compatível** e serviço **ClamAV (`clamd`)** (ADR 0016).
  - Execução automatizada de `ruff`, `pip-audit` e `manage.py test` em CI/CD (ADR 0012).

*Nota sobre preços e planos:* valores comerciais e limites de planos gratuitos mudam frequentemente e ficam marcados como **a confirmar no momento da contratação**.

## Direcionadores da decisão

- Garantir **Python 3.14 exato** (ADR 0003) e reprodutibilidade entre desenvolvimento, homologação e produção (portabilidade via contêiner).
- Atender **escalabilidade horizontal** (RNF08), **99% de disponibilidade** e **backups diários com retenção de 30 dias** (RNF05) sem sobrecarregar uma equipe acadêmica pequena com administração manual de servidores.
- Suportar agendamento confiável de comandos `manage.py` (ADR 0014), TLS 1.2+ automático (RS005) e variáveis de ambiente seguras para segredos (sem credenciais no repositório).
- Evitar aprisionamento forte (*vendor lock-in*) a recursos proprietários de um único provedor.

## Opções consideradas

### 1. Contêiner Docker (`gunicorn` + `whitenoise`) em PaaS gerenciado com PostgreSQL gerenciado, Object Storage S3-compatível e CronJobs gerenciados (ex.: Render, Railway, Fly.io ou DigitalOcean App Platform — provedor exato a confirmar) (recomendada)

Empacotar a aplicação Django em uma imagem **Docker** baseada em Python 3.14, servida via **`gunicorn`** (WSGI) com **`whitenoise`** para arquivos estáticos (incluindo o Bootstrap local da ADR 0005), conectada a um PostgreSQL gerenciado (com backup diário e retenção de 30 dias), um bucket S3-compatível (ADR 0016), um provedor SMTP transacional (ADR 0015) e CronJobs gerenciados para os comandos `manage.py` da ADR 0014. Pipeline de CI em **GitHub Actions** executando `ruff`, `pip-audit` e `python manage.py test` contra PostgreSQL antes de implantar.

- **Prós:**
  - O `Dockerfile` garante exatamente Python 3.14 (ADR 0003) e portabilidade entre provedores sem *vendor lock-in*.
  - Escalabilidade horizontal simples por aumento de réplicas do contêiner web (RNF08), sem estado local em disco (sessões e filas no PostgreSQL, arquivos em S3).
  - Banco PostgreSQL gerenciado entrega backups diários automáticos com retenção de 30 dias (RNF05) e TLS gerenciado (RS005) com mínimo esforço operacional.
  - CronJobs gerenciados disparam as rotinas da ADR 0014 sem manter servidor dedicado de `cron`.
- **Contras:**
  - Custo mensal tende a ser maior que o de um VPS único para os mesmos 2 vCPU / 4 GB RAM + banco gerenciado + storage + eventual serviço `clamd` (preços a confirmar na contratação).
  - Exige configurar monitoramento externo de disponibilidade e de *heartbeat* das rotinas agendadas (confirmando execuções recentes em `ExecucaoRotina`).

### 2. VPS Linux (IaaS, ex.: Hetzner, DigitalOcean Droplet, AWS Lightsail) com Docker Compose (Nginx + `gunicorn` + PostgreSQL + ClamAV + `cron`/systemd) e backups para S3

- **Prós:**
  - Menor custo fixo para obter 2 vCPU, 4 GB de RAM e 50 GB SSD (RNF08) e controle total sobre sistema operacional, `cron`, `clamd` e benchmark do Argon2id.
- **Contras:**
  - **Não oferece escalabilidade horizontal pronta** (RNF08): escalar para várias instâncias exigirá separar o PostgreSQL e introduzir load balancer manualmente.
  - Toda operação de segurança (atualizações do SO, firewall, renovação TLS, monitoramento de 99% de disponibilidade e scripts/alertas de backup diário com retenção de 30 dias) fica sob responsabilidade direta da equipe.

### 3. Nuvem corporativa completa (AWS ECS/RDS/S3/SES ou GCP Cloud Run/Cloud SQL/Cloud Storage)

- **Prós:**
  - Máxima maturidade de SLA, escalabilidade horizontal, KMS, backups gerenciados de 30 dias e serviço de e-mail integrado (como AWS SES).
- **Contras:**
  - Alta complexidade de configuração (VPC, IAM, redes, pipelines) e risco de custos inesperados para um projeto acadêmico em fase de MVP.

## Decisão

**Opção 1** — aplicação empacotada em **Docker (Python 3.14)** com **`gunicorn`** + **`whitenoise`**, implantada em **PaaS gerenciado** com **PostgreSQL gerenciado**, **Object Storage S3-compatível**, **CronJobs gerenciados** (ADR 0014), **provedor SMTP transacional** sob domínio oficial (ADR 0015) e **GitHub Actions no CI** (ADR 0012).

Regras que passam a valer:

- **Fases de implantação (RNF11, Questão 3 do PRD):**
  - **Agora (fase acadêmica):** implantação voltada apenas para **ambiente de homologação/demonstração acadêmica**, utilizando o mesmo `Dockerfile` e configuração por variáveis de ambiente (`.env.example` versionado sem segredos reais).
  - **Produção real (somente após validação jurídica do RNF11):** contratação dos recursos mínimos de produção (2 vCPU, 4 GB RAM, 50 GB SSD com escalabilidade horizontal — RNF08), domínio oficial com **SPF, DKIM e DMARC** no provedor SMTP (RS014, ADR 0015), **backups diários automáticos com retenção mínima de 30 dias** (RNF05), ativação do daemon **ClamAV (`clamd`)** (ADR 0016) e **benchmark/calibração dos parâmetros do Argon2id** no ambiente-alvo (ADR 0008, partindo do piso OWASP `memory_cost >= 19 MiB` e `time_cost >= 2`).
- **Servidor WSGI e arquivos estáticos:** **`gunicorn`** como servidor WSGI e **`whitenoise`** servindo `static/` comprimido direto do contêiner (alinhado ao Bootstrap local da ADR 0005). Ambos entram no `requirements.txt` fixados por `==` apenas quando o empacotamento for implementado (ADR 0004).
- **CI via GitHub Actions (ADR 0012):** pipeline automatizado a cada push/PR executando `ruff check .`, `ruff format --check .`, `pip-audit -r requirements.txt` e `python manage.py test` contra um serviço PostgreSQL real, além de `python manage.py check --deploy` nas validações de implantação.
- **Procedimento de teste de restauração de backup (RNF05):** registrado como **procedimento operacional obrigatório de produção** (periodicidade mensal recomendada): restaurar o backup diário em banco isolado de verificação, validar integridade dos dados e registrar o resultado da checagem.
- **Monitoramento de *heartbeat* das rotinas (ADR 0014):** na produção, checagem operacional verifica execuções bem-sucedidas recentes em `ExecucaoRotina` (RF012 diário e outbox de e-mails a cada 1 minuto).

## Consequências

- Positivas:
  - Fecha os pontos pendentes das ADRs 0008 (benchmark), 0012 (CI), 0014 (agendador), 0015 (SMTP/domínio oficial) e 0016 (storage/ClamAV) sob uma arquitetura portável via Docker.
  - Respeita o bloqueio jurídico do RNF11 (Questão 3 do PRD), evitando gastos prematuros de produção durante a etapa acadêmica sem perder reprodutibilidade.
- Negativas e custos:
  - A escolha comercial exata do provedor de PaaS, do provedor SMTP e do orçamento fica para o momento da contratação (tanto na homologação quanto na produção pós-RNF11).
  - `gunicorn` e `whitenoise` entram no `requirements.txt` (fixados por `==`, ADR 0004) quando o empacotamento de implantação for criado.
- Impacto em specs e arquitetura:
  - O novo `docs/arquitetura.md` documentará a topologia de implantação, o fluxo de CI (GitHub Actions), as variáveis de ambiente obrigatórias e os procedimentos de produção (backup/restauração, benchmark do Argon2id, `clamd` e SPF/DKIM/DMARC).

## Como verificar

- `docker build` gera imagem reprodutível com Python 3.14 e `pip check` sem erros.
- Workflow do GitHub Actions executa `ruff`, `pip-audit` e `python manage.py test` contra PostgreSQL com sucesso.
- `python manage.py check --deploy` passa sem alertas críticos no ambiente de homologação/produção.
- Em produção (pós-RNF11): registro mensal do teste de restauração de backup (RNF05), verificação de SPF/DKIM/DMARC no domínio oficial (RS014) e relatório de benchmark do Argon2id (ADR 0008).

## Notas

- **ADRs integradas:** [ADR 0003](0003-python-3-14.md), [ADR 0004](0004-pip-venv-requirements-fixado.md), [ADR 0005](0005-bootstrap-hospedado-no-projeto.md), [ADR 0008](0008-hash-de-senha-argon2-ou-bcrypt.md) (benchmark Argon2id), [ADR 0012](0012-ferramentas-teste-formatacao-lint-e-seguranca.md) (CI), [ADR 0014](0014-rotinas-agendadas.md) (CronJobs e *heartbeat*), [ADR 0015](0015-notificacoes-email-e-plataforma.md) (SMTP/domínio oficial) e [ADR 0016](0016-armazenamento-seguro-de-arquivos.md) (S3 e `clamd`).
