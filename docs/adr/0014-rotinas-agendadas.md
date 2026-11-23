# 0014. Executar rotinas agendadas via comandos de gerenciamento do Django com lock no PostgreSQL

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF15, RF006, RF007, RF012, RF013, RF016, RF017, RF018, RS001, RS007, RS011, RNF08

## Contexto

Embora o **RNF15** tenha prioridade "Importante" na fonte, diversas rotinas automáticas sustentam requisitos **Essenciais** ou antecipados para o **MVP** (Questão 17 do PRD):

1. **Vencimento diário de doações e aviso de proximidade de vencimento (RF012 — MVP):** roda 1×/dia em horário de menor uso; marca doações vencidas ou abaixo da validade mínima, cancela reservas/agendamentos, devolve solicitações a `"aberta"`, notifica com orientação de descarte e envia aviso prévio (sugerido: 15 dias). Exige registro de contadores (`verificadas`, `vencidas`, `canceladas`, `notificacoes`) e resultado (`sucesso`, `parcial` ou `falha`). Em falha, **alerta o Administrador e roda de novo** (RF012 regra 4, RNF15).
2. **Expiração de solicitações sem correspondência (RF013 — MVP):** prazo configurável (sugerido: 30 dias), com aviso ao usuário.
3. **Expiração de prazos de aceite e reservas (RF016, RS007 — MVP):** aceite configurável (sugerido: 48 h) e expiração de reserva sem agendamento confirmado (Questão 12 do PRD).
4. **Lembrete 24 h antes da retirada (RF017, RF018 — MVP).**
5. **Marcação de `"não compareceu"` 24 h após o horário agendado sem confirmação (RF018 — MVP).**
6. **Aviso de documento prestes a vencer e retorno do ponto de coleta a pendente após vencimento (RF006, RF007 — MVP ⬆).**
7. **Limpeza de sessões expiradas (`clearsessions`, ADR 0009).**
8. **Envio e retentativa de notificações por e-mail em até 5 minutos (RF017, RNF15 — ADR 0015).**

O **RNF08** exige suporte a **escalabilidade horizontal** (múltiplas instâncias do servidor) em ambiente inicial de 2 vCPU e 4 GB de RAM. Por isso, o mecanismo de agendamento precisa evitar que a mesma rotina rode em duplicidade em duas instâncias simultaneamente, sem desperdiçar RAM com infraestrutura pesada no MVP.

## Direcionadores da decisão

- Garantir execução **idempotente** e **única** (sem duplicidade mesmo com múltiplas instâncias, RNF08).
- Registrar cada execução no banco (`sucesso`, `parcial` ou `falha` e métricas do RF012) e alertar o Administrador em caso de falha (RNF15, RF012 regra 4).
- Manter toda regra de negócio das rotinas na camada de service (ADR 0001), desacoplada do agendador escolhido.
- Preservar memória e simplicidade operacional no ambiente mínimo de 2 vCPU / 4 GB RAM (RNF08) e parcimônia em novas dependências (ADR 0004).
- Compatibilidade com Python 3.14 (ADR 0003) e Django 6.1 (ADR 0001).

## Opções consideradas

### 1. Services idempotentes + comandos `manage.py` + advisory lock no PostgreSQL + tabela `ExecucaoRotina` + agendador nativo do ambiente (`cron`/CronJob da nuvem) (recomendada)

Implementar cada rotina como um **service idempotente** (ADR 0001) exposto por um comando de gerenciamento fino (`python manage.py <nome_rotina>`). Ao iniciar, o comando adquire um lock exclusivo no PostgreSQL (`pg_try_advisory_lock`) para impedir execuções simultâneas em múltiplas instâncias (RNF08) e grava um registro na tabela `ExecucaoRotina` (início, fim, contadores, resultado `sucesso`/`parcial`/`falha` e resumo de erro). Em caso de falha, dispara alerta ao Administrador e permite reexecução automática. O disparo periódico fica a cargo do agendador nativo da hospedagem (`cron`, `systemd timer` ou CronJob gerenciado).

- **Prós:**
  - Zero infraestrutura extra no MVP (sem Redis, sem broker e sem workers permanentes consumindo os 4 GB de RAM do RNF08).
  - Zero dependência externa adicional no `requirements.txt` (ADR 0004) e 100% compatível com Python 3.14 e Django 6.1.3.
  - Facilita testes automatizados (basta testar o service diretamente ou via `call_command`).
  - Desacopla totalmente a lógica do disparador: se o volume futuro exigir migrar para Celery/worker dedicado, os services e comandos permanecem intactos.
- **Contras:**
  - Depende do agendador externo da hospedagem (se o `cron`/CronJob parar silenciosamente, é preciso monitoramento de *heartbeat* para perceber ausência de execução).
  - Granularidade típica mínima de 1 minuto (suficiente para todas as rotinas do ReMed, incluindo o SLA de 5 minutos do RNF15).

### 2. Celery + Celery Beat + Redis (ou RabbitMQ)

Executar tarefas agendadas e assíncronas com Celery (`5.6+` com suporte inicial a Python 3.14) e `django-celery-beat` (suporte a Django 6.0+ e Python 3.14), usando Redis como broker.

- **Prós:**
  - Solução consagrada para filas de alta vazão, com retentativas com *backoff*, agendamento centralizado e execução em segundos.
- **Contras:**
  - Exige provisionar, monitorar e manter três componentes adicionais (broker Redis + processo worker + processo beat) dentro de um servidor mínimo de 2 vCPU / 4 GB RAM (RNF08).
  - Introduz dezenas de dependências transitivas no `requirements.txt` (ADR 0004), com suporte ainda recente do Celery ao Python 3.14.
  - Complexidade operacional desproporcional à escala inicial do ReMed (até 500 usuários simultâneos — RNF04).

### 3. Fila/agendador apoiado no PostgreSQL (ex.: `django-q2` ou backend externo para `django.tasks`)

Adotar uma biblioteca com worker contínuo usando o próprio PostgreSQL como broker (já que o `django.tasks` nativo do Django 6.1.3 oferece apenas `ImmediateBackend` e `DummyBackend`, sem worker de produção nem agendador embutido no núcleo — verificado por inspeção direta do módulo `django.tasks.backends` no Django 6.1.3 instalado no `.venv` e confirmado pela documentação oficial do Django 6, *Tasks framework* em `docs.djangoproject.com`).

- **Prós:**
  - Dispensa Redis reutilizando o PostgreSQL (ADR 0002) e oferece worker contínuo em Python.
- **Contras:**
  - Ainda exige manter e monitorar um processo worker separado em produção.
  - Adiciona dependência externa cuja compatibilidade com Django 6.1 e Python 3.14 precisa ser acompanhada continuamente.

## Decisão

**Opção 1** — services idempotentes chamados por comandos `manage.py`, protegidos por *advisory lock* no PostgreSQL (`pg_try_advisory_lock`), com registro em tabela `ExecucaoRotina` e disparados pelo agendador nativo do ambiente de hospedagem (`cron` / CronJob gerenciado, fechado na [ADR 0019](0019-hospedagem-implantacao-e-backup.md)).

Regras que passam a valer:

- **Escopo no MVP (Questão 17 do PRD):** embora o RNF15 tenha prioridade "Importante" na fonte, esta base de rotinas agendadas **entra no MVP** para sustentar o RF012 (Essencial) e os fluxos do MVP (RF006, RF013, RF016, RF017, RF018, `clearsessions` da ADR 0009 e despacho do outbox de e-mails da ADR 0015).
- **Idempotência obrigatória:** rodar qualquer rotina duas vezes seguidas não pode duplicar notificações, cancelar duas vezes nem corromper contadores.
- **Concorrência segura:** cada atualização de doação, solicitação, reserva ou agendamento feita pela rotina usa o mesmo bloqueio transacional da [ADR 0013](0013-reserva-transacional-e-concorrencia.md) (`select_for_update()`), evitando disputa com ações simultâneas dos usuários.
- **Registro, alerta e reexecução em falha (RF012 regra 4, RNF15):** toda execução grava em `ExecucaoRotina` (com `sucesso`, `parcial` ou `falha` e os contadores do RF012). Em caso de `falha` na rotina diária de vencimento (RF012), o sistema **alerta o Administrador** (via ADR 0015 e log estruturado) e executa **até 3 tentativas automáticas com intervalo de 15 minutos**.
- **Armazenamento dos parâmetros de prazo:**
  - Os parâmetros editáveis pelo Administrador no **RF012** (*validade mínima restante* e *antecedência do aviso de vencimento*) ficam em **tabela de configuração no banco de dados**, editáveis pela função `metricas_e_parametros` (ADR 0010) com histórico imutável (ADR 0011).
  - Os demais prazos (Questões 12 e 13 do PRD: 30 dias de expiração de solicitação, 48 h de aceite, 48 h de reserva sem agendamento, 24 h de lembrete e não comparecimento) ficam como **parâmetros nomeados em `settings`**.

## Consequências

- Positivas:
  - Atende ao RF012, RNF15 e demais rotinas do MVP sem adicionar Redis, RabbitMQ nem novas dependências Python.
  - Mantém o código 100% aderente à camada de service (ADR 0001) e fácil de migrar para um worker dedicado caso o volume cresça.
- Negativas e custos:
  - A definição concreta do disparador (`cron`, `systemd timer`, CronJob de container ou serviço gerenciado) e do alerta de *heartbeat* fica condicionada à [ADR 0019](0019-hospedagem-implantacao-e-backup.md).
  - Exige cuidado com `pg_try_advisory_lock` em ambientes com *connection pooling* em modo transação (usar lock por transação ou conexão dedicada ao comando).
- Impacto em specs e arquitetura:
  - Condiciona as specs de **RF006**, **RF007**, **RF012**, **RF013**, **RF016**, **RF017** e **RF018**, além da rotina de limpeza `clearsessions` da ADR 0009.

## Como verificar

- Testes unitários e de integração dos services de cada rotina (com relógio controlado) confirmam transições corretas, gravação em `ExecucaoRotina` e **idempotência** ao rodar duas vezes seguidas.
- Teste com duas execuções concorrentes da mesma rotina no PostgreSQL confirma que o *advisory lock* impede processamento duplicado.
- Teste com falha simulada no RF012 confirma gravação do status `falha`, disparo do alerta ao Administrador e respeito ao limite de 3 tentativas com intervalo de 15 minutos.
- Teste confirma que alterar os parâmetros do RF012 exige a função `metricas_e_parametros` e gera registro de auditoria (ADR 0011).

## Notas

- **Fonte sobre `django.tasks` no Django 6.1.3:** verificado por inspeção direta do pacote `django.tasks.backends` no Django 6.1.3 instalado no `.venv` (contendo apenas `base`, `dummy` e `immediate`) e pela documentação oficial do Django 6 (*Tasks framework*, `docs.djangoproject.com`), que confirma que o núcleo inclui apenas `ImmediateBackend` e `DummyBackend`, exigindo infraestrutura ou backend externo para execução assíncrona em produção.
- **ADRs relacionadas:** [ADR 0009](0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) (`clearsessions`), [ADR 0010](0010-perfis-e-permissoes.md) (`metricas_e_parametros`), [ADR 0011](0011-historico-imutavel-e-auditoria.md), [ADR 0013](0013-reserva-transacional-e-concorrencia.md), [ADR 0015](0015-notificacoes-email-e-plataforma.md) e [ADR 0019](0019-hospedagem-implantacao-e-backup.md).
