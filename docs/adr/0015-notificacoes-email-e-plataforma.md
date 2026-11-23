# 0015. Implementar notificações na plataforma e por e-mail com padrão Transactional Outbox

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RF017, RNF15, RS002, RS014, RNF10, RNF12, RF001, RF003, RF004, RF006, RF007, RF011, RF012, RF013, RF016, RF018, RF019, RF021

## Contexto

O **RF017 (Essencial)** exige notificar os usuários por **e-mail** e **na plataforma** sobre eventos relevantes de praticamente todos os fluxos do sistema (correspondência, aceite, agendamento, lembrete 24 h, vencimento, nova mensagem, ponto de coleta/documento, expiração de solicitação, resultado de denúncia e segurança da conta) e registrar todos os envios (`pendente`, `enviada`, `lida` ou `falha`). Além disso, o RF001 (confirmação de e-mail) e o RF003 (link de recuperação de senha válido por 1 hora) também dependem de envio de e-mail.

Requisitos de desempenho, confiabilidade e segurança que restringem o desenho:

- **RNF15 e RF017 regra 4:** notificações devem ser enviadas em **até 5 minutos após o evento**, com **até 3 novas tentativas** em caso de falha, **sem bloquear a operação do usuário** nem impedir a notificação na plataforma.
- **RS002 e RS014:** notificações **nunca** podem conter dados pessoais, o motivo da necessidade de saúde nem o texto das mensagens trocadas (o endereço do local de retirada só aparece após a confirmação do agendamento — RF018). E-mails devem ser enviados **apenas do domínio oficial do sistema**, com **limite de envio por usuário** (RS014 solução 4).
- **RF017 regra 5:** notificações na plataforma ficam em lista com indicação de lida/não lida e seguem o prazo de retenção da política de privacidade (RNF10); **notificações de segurança da conta não podem ser desativadas**.
- **RNF04 e RNF08:** requisições web devem responder rápido (até 3 s no p95) em ambiente mínimo de 2 vCPU e 4 GB de RAM.

## Direcionadores da decisão

- Desacoplar o envio de e-mail da requisição HTTP para não bloquear nem atrasar o usuário (RF017 regra 4, RNF15, RNF04).
- Garantir consistência transacional: uma notificação só existe se a operação de negócio que a originou for confirmada (sem avisos fantasmas após *rollback*, RNF06 / ADR 0013).
- Atender o SLA de **até 5 minutos** e **até 3 novas tentativas** com registro completo de status (`pendente`, `enviada`, `lida`, `falha`) exigido pelo RF017.
- Garantir que e-mails saiam exclusivamente do domínio oficial (SPF/DKIM/DMARC), sem vazar PII, motivo de saúde ou conteúdo de mensagens (RS002, RS014).
- Evitar infraestrutura extra (Redis/Celery) no MVP (alinhado à ADR 0014 e à ADR 0004).

## Opções consideradas

### 1. Padrão *Transactional Outbox* no PostgreSQL + despacho assíncrono por comando agendado (a cada 1 min) via `django.core.mail` (recomendada)

Na mesma transação (`transaction.atomic()`) da operação de domínio, o `NotificacaoService` grava:
1. O registro da **notificação na plataforma** (imediatamente visível na lista de lidas/não lidas do usuário); e
2. Um registro de **envio de e-mail** na tabela de outbox do PostgreSQL com status `pendente`, `tentativas = 0` e `proxima_tentativa_em`.

Um comando agendado pela [ADR 0014](0014-rotinas-agendadas.md) (executando a cada 1 minuto com `select_for_update(skip_locked=True)`) consome lotes pendentes, aplica a verificação de limite de envio por usuário (RS014, exceto segurança da conta), envia via `django.core.mail` (SMTP nativo em produção ou `django-anymail` caso se opte por API HTTP de provedor na ADR de hospedagem) e atualiza o status para `enviada` ou agenda até **3 novas tentativas** com intervalo crescente (*backoff*) antes de marcar `falha`.

- **Prós:**
  - **Atomicidade real:** se a transação de negócio sofrer *rollback*, nenhuma notificação é gravada ou enviada; se confirmar, o envio é durável mesmo que o servidor reinicie antes do SMTP responder.
  - **Não bloqueia o usuário** (cumpre RF017 regra 4 e RNF15) e mantém a notificação na plataforma disponível no mesmo instante.
  - Atende com folga o prazo de até 5 minutos (despacho a cada 1 minuto) e registra nativamente todos os campos e status do RF017.
  - Zero Redis/Celery no MVP e zero dependência externa obrigatória no `requirements.txt` ao usar o SMTP nativo do Django (ADR 0004).
  - Fácil de testar usando o backend `locmem` do Django e chamando o service de despacho diretamente.
- **Contras:**
  - Introduz latência de até ~1 minuto para o envio de e-mails (dentro do limite de 5 minutos do RNF15, mas merece atenção em e-mails interativos como confirmação de cadastro RF001 e recuperação de senha RF003).
  - Depende da rotina de 1 minuto da ADR 0014 estar ativa na hospedagem.

### 2. Fila dedicada (Celery + Redis) + `django-anymail`

Enfileirar tarefas de envio de e-mail no Redis em `transaction.on_commit(...)`, processadas em segundos por workers Celery usando `django-anymail` (compatível com Django 6 e Python 3.14) para integrar com API HTTP de provedor transacional.

- **Prós:**
  - Envio quase instantâneo (poucos segundos), ótimo para e-mails interativos (RF001, RF003).
  - Retentativas com *backoff* nativas do Celery e suporte do `django-anymail` a webhooks de bounce/entrega.
- **Contras:**
  - Exige provisionar e operar Redis + worker Celery dentro do servidor inicial de 2 vCPU / 4 GB RAM (RNF08), adicionando dezenas de dependências (ADR 0004).
  - Se o Redis falhar no momento do `on_commit`, o envio pode se perder a menos que ainda se mantenha uma tabela outbox no PostgreSQL para reprocessamento.

### 3. Envio síncrono na requisição HTTP (ou em thread em memória do processo web)

Chamar `send_mail()` diretamente na view/service durante a requisição ou disparar uma `threading.Thread` em segundo plano.

- **Prós:**
  - Simplicidade máxima, sem fila nem agendador.
- **Contras:**
  - Envio síncrono **bloqueia a requisição do usuário** e pode estourar os 3 segundos do RNF04 quando o provedor SMTP estiver lento ou fora do ar, **violando diretamente o RNF15 e o RF017 regra 4**.
  - Threads em memória perdem retentativas e registros pendentes quando o processo web é reiniciado ou reciclado pela nuvem.

## Decisão

**Opção 1** — padrão *Transactional Outbox* no PostgreSQL com `NotificacaoService`, consumido a cada **1 minuto** pelo mecanismo de rotinas da [ADR 0014](0014-rotinas-agendadas.md) (`select_for_update(skip_locked=True)`), com até **3 novas tentativas** em caso de falha e registro completo de status (`pendente`, `enviada`, `lida`, `falha`).

Regras que passam a valer:

- **Uniformidade do outbox (inclusive RF001 e RF003):** **todos os e-mails**, incluindo confirmação de cadastro (RF001) e recuperação de senha (RF003), passam pelo mesmo outbox de 1 minuto — mantendo simplicidade, atomicidade transacional e atendimento ao SLA de 5 minutos (RNF15).
- **Transporte em produção:** usar o **backend SMTP nativo do Django** (`django.core.mail`), sem dependências externas adicionais (ADR 0004). O provedor SMTP definitivo e a configuração DNS (SPF, DKIM, DMARC) do domínio oficial serão definidos na [ADR 0019](0019-hospedagem-implantacao-e-backup.md).
- **Limite de envio por usuário (RS014 solução 4, Questão 11 do PRD):** definido como **parâmetro configurável em `settings`**. Ao atingir o limite, **suprimem-se apenas e-mails não críticos**, mantendo sempre o registro na plataforma e **nunca suprimindo notificações de segurança da conta**.
- **Preferências de notificação (RF017 regra 5, Questão 27 do PRD):** no MVP, o sistema entrega apenas o envio padrão (com notificações de segurança da conta sempre marcadas como obrigatórias); a tela de preferências/desativação por tipo fica para a **v1.1**.
- **Separação de conteúdo seguro (RS002, RS014):** templates de notificação são padronizados por `Tipo` no código e **nunca** recebem nome completo de terceiros, contato, motivo de saúde nem o texto de mensagens do RF019. O endereço do local de retirada só entra após a confirmação do agendamento (RF018).
- **Retentativas e resiliência (RF017, RNF15):** falha no provedor de e-mail não afeta a operação principal nem a notificação na plataforma; até 3 novas tentativas com intervalo crescente antes de marcar `falha` (com alerta operacional em caso de taxa anormal de falhas).
- **Canais desejáveis (SMS/app de mensagens):** fora do MVP; a interface do `NotificacaoService` separa o canal no modelo para permitir extensão futura sem refatoração dos services de domínio.

## Consequências

- Positivas:
  - Cumpre integralmente RF017, RNF15, RS002 e RS014 sem adicionar Redis/Celery nem bibliotecas externas de e-mail no MVP.
  - Garante que nenhuma notificação seja enviada por uma transação que sofreu *rollback* nem perdida por queda temporária do provedor SMTP.
  - Mantém histórico consultável por tipo, status e período (RF017 — Pesquisa).
- Negativas e custos:
  - Latência de até ~1 minuto para todos os e-mails (incluindo confirmação de cadastro RF001 e recuperação de senha RF003), dentro do SLA de 5 minutos do RNF15.
  - Exige política de retenção e expurgo de notificações antigas conforme a política de privacidade (RNF10, Questão 8 do PRD).
- Impacto em specs e arquitetura:
  - Transversal a quase todas as specs do MVP (RF001, RF003, RF004, RF006, RF007, RF011, RF012, RF013, RF016, RF017, RF018, RF019, RF021): os services de domínio só chamam `NotificacaoService.registrar_evento(...)`, nunca `send_mail()` diretamente.

## Como verificar

- Testes de cada fluxo confirmam que a notificação na plataforma e o registro de envio na fila são criados na mesma transação (e desfeitos em caso de *rollback*).
- Testes simulando falha do servidor SMTP confirmam que a operação do usuário continua com sucesso, a notificação na plataforma é mantida e o despachante executa até 3 novas tentativas antes de marcar `falha`.
- Testes de conteúdo dos templates confirmam ausência de CPF, endereço de usuário, telefone, motivo de saúde e texto de mensagem do RF019 nos e-mails e notificações.
- Testes confirmam que o limite por usuário suprime apenas e-mails não críticos (mantendo a notificação na plataforma) e nunca suprime notificações de segurança da conta.

## Notas

- **ADRs relacionadas:** [ADR 0004](0004-pip-venv-requirements-fixado.md), [ADR 0013](0013-reserva-transacional-e-concorrencia.md), [ADR 0014](0014-rotinas-agendadas.md) (despacho a cada 1 minuto) e [ADR 0019](0019-hospedagem-implantacao-e-backup.md) (provedor SMTP e DNS SPF/DKIM/DMARC do domínio oficial).
