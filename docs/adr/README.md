# ADRs — ReMed

Registros de decisão de arquitetura. Cada arquivo registra uma decisão. A numeração é sequencial e nunca é reutilizada. Uma ADR `aceita` não é reescrita: para mudar a decisão, cria-se uma nova ADR e a antiga passa a "substituída por NNNN".

Requisitos: [PRD](../prd/01-remed.md) e [catálogo](../prd/02-catalogo-requisitos.md).

## Registradas

| ADR | Decisão | Status | Requisitos |
| --- | --- | --- | --- |
| [0001](0001-django-mvt-com-camada-de-service.md) | Django no padrão MVT, com camada de service e templates renderizados no servidor | aceita | RNF07, RNF08, RNF06, RNF14, RNF09, RS005 |
| [0002](0002-postgresql-como-banco-de-dados.md) | PostgreSQL como banco de dados | aceita | RNF09, RNF06, RS007, RNF14, RNF05, RF015 |
| [0003](0003-python-3-14.md) | Python 3.14 | aceita | RNF09 |
| [0004](0004-pip-venv-requirements-fixado.md) | pip, `.venv` e `requirements.txt` com versões fixadas | aceita | RNF09, RS005 |
| [0005](0005-bootstrap-hospedado-no-projeto.md) | Bootstrap como base de CSS, hospedado no projeto | aceita | RNF07, RNF08, RNF01, RNF03 |
| [0006](0006-javascript-simples-sem-framework.md) | JavaScript simples, sem framework de front-end | aceita | RNF07, RNF08, RNF04, RNF03 |
| [0007](0007-modelo-de-usuario-customizado.md) | Modelo de usuário customizado (`AbstractBaseUser` + `PermissionsMixin`) | aceita | RF001, RF002, RF004, RF005, RNF10, RNF14, RS002, RS005, RS006, RS015 |
| [0008](0008-hash-de-senha-argon2-ou-bcrypt.md) | Hash de senha (`Argon2id` — `Argon2PasswordHasher`) | aceita | RS005, RF001, RF002, RF003, RNF04, RNF08 |
| [0009](0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) | Sessão, bloqueio por tentativas e dois fatores do Administrador (PostgreSQL, service próprio, TOTP com `pyotp`) | aceita | RF002, RF003, RF004, RS005, RS015, RNF08, RNF14 |
| [0010](0010-perfis-e-permissoes.md) | Perfis de usuário final e permissões administrativas separadas por função (8 funções, incluindo `auditoria`, proibição de acúmulo com receitas) | aceita | RF001, RF002, RF004, RF005, RF006, RF007, RF011, RF014, RF021, RF022, RS002, RS015, RNF14 |
| [0011](0011-historico-imutavel-e-auditoria.md) | Histórico imutável e auditoria (service dedicado, tabela append-only com trigger no PostgreSQL e 8ª função `auditoria`) | aceita | RNF14, RF001, RF002, RF004, RF007, RF011, RF020, RF021, RNF10, RS013, RS015 |
| [0012](0012-ferramentas-teste-formatacao-lint-e-seguranca.md) | Ferramentas de teste (`manage.py test`), lint/formatação (`ruff`), `pip-audit`, `coverage` e `requirements-dev.txt` | aceita | RNF09, RNF06, RS005 |
| [0013](0013-reserva-transacional-e-concorrencia.md) | Reserva transacional e controle de concorrência (`select_for_update()`, 1 reserva ativa por doação, prazo inicial 48 h) | aceita | RNF06, RS007, RF008, RF012, RF016, RF018, RF020 |
| [0014](0014-rotinas-agendadas.md) | Rotinas agendadas no MVP via comandos `manage.py`, advisory lock no PostgreSQL e tabela `ExecucaoRotina` | aceita | RNF15, RF006, RF007, RF012, RF013, RF016, RF017, RF018, RS001, RS007, RNF08 |
| [0015](0015-notificacoes-email-e-plataforma.md) | Notificações na plataforma e por e-mail com *Transactional Outbox* (1 min) e SMTP nativo do Django | aceita | RF017, RNF15, RS002, RS014, RNF10, RNF12 |
| [0016](0016-armazenamento-seguro-de-arquivos.md) | Armazenamento seguro de arquivos (S3-compatível, SSE, Pillow, interface antimalware/`clamd` na implantação, URL pré-assinada 60 s) | aceita | RNF08, RNF16, RS013, RS002, RNF10, RF006, RF008, RF013, RF014 |
| [0017](0017-geolocalizacao-e-calculo-de-distancia.md) | Geolocalização aproximada (bounding box + Haversine, BrasilAPI + Nominatim com cache, última localização na sessão) | aceita | RF015, RF016, RF001, RF005, RS002, RS010, RNF04, RNF12 |
| [0018](0018-consulta-de-cep.md) | Consulta de CEP via proxy no servidor com cache no PostgreSQL (BrasilAPI + ViaCEP, `urllib.request`) | aceita | RF001, RF005, RF015, RNF12, RNF04, RS002, RS005 |
| [0019](0019-hospedagem-implantacao-e-backup.md) | Hospedagem, implantação, CI/CD e backup (PaaS Docker, `gunicorn` + `whitenoise`, GitHub Actions, homologação agora / produção pós-RNF11) | aceita | RNF05, RNF08, RNF04, RNF11, RNF15, RS005, RS014 |
| [0020](0020-configuracao-variaveis-ambiente-python-dotenv.md) | Configuração por variáveis de ambiente com `python-dotenv` e `.env.example` | aceita | RS005, RNF09, RNF08 |
| [0021](0021-provedor-ia-multimodal-leitura-embalagem.md) | Integração da leitura da embalagem por IA multimodal via protocolo interno e `urllib.request` (`gemini` e `openai_compat`, sem novas dependências) | aceita | RF009, RNF04, RNF10, RNF12, RNF13, RS009, RS013 |

Todas as ADRs necessárias para o MVP, a v1.1 e o RF009 (0001 a 0021) estão `aceita`. Resta como candidata apenas a decisão da v2.0 abaixo.

## Candidatas (ainda sem ADR)

Uma decisão candidata só pode ser implementada depois de ter uma ADR `aceita`.

| # | Tema | Requisitos | Por que decidir | Quando |
| --- | --- | --- | --- | --- |
| 1 | API REST | RNF09 | O RNF09 pede uma API e a ADR 0001 escolheu renderização no servidor | v2.0 |
