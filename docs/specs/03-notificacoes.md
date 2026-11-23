# Spec 03 — Notificações (RF017)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `03` — Notificações (`RF017`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF017 (Essencial — MVP, HU17). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF08, RNF10 (Essencial), RNF12, RNF14 (Essencial), RNF15 (Importante — antecipado ao MVP pela ADR 0014/0015). **Segurança:** RS002, RS014. |
| **Apps envolvidos** | `notificacoes` (principal), `nucleo` (`ExecucaoRotina`, lock PostgreSQL `pg_try_advisory_lock`, mixins de acesso), `auditoria` (`AuditoriaService` para alertas/eventos críticos), `contas` (destinatários e funções administrativas). |
| **Dependências de outras specs** | **[01-cadastro-de-usuario.md](01-cadastro-de-usuario.md) (`RF001`)** (cria `Usuario` e o *Transactional Outbox* mínimo `OutboxEmail` + despacho de confirmação de e-mail) e **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)** (mixins de autenticação/permissão). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0004](../adr/0004-pip-venv-requirements-fixado.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0014](../adr/0014-rotinas-agendadas.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0019](../adr/0019-hospedagem-implantacao-e-backup.md). |

---

## 2. Objetivo e escopo

Entregar o módulo completo de notificações do ReMed para todos os perfis autenticados, expandindo o *Transactional Outbox* mínimo criado na Spec 01 para cobrir:

### Inclui

- **Notificações na plataforma** (`Notificacao` persistida no PostgreSQL na mesma transação do evento de negócio), com lista paginada (**20 itens por página** — *acréscimo da especificação, não consta no RF017*) para o usuário autenticado indicando **lida / não lida**, contador de não lidas na barra de navegação, marcação individual como lida (registrando `data_hora_leitura`), botão **"Marcar todas como lidas"** via `POST` com CSRF (*acréscimo da especificação, não consta no RF017*) e **pesquisa/filtros por tipo, status e período** (RF017).
- **Catálogo completo de tipos de evento e templates padronizados seguros** no `NotificacaoService`, cobrindo todos os grupos da regra 1 do RF017 (correspondência/aceite/agendamento, lembrete 24 h, doação prestes a vencer e vencida, nova mensagem, análise de ponto de coleta e documento prestes a vencer, solicitação prestes a expirar, resultado de denúncia na v1.1, segurança da conta e confirmação de e-mail/alertas operacionais enviados apenas para **`gestao_administradores`**), **sem nunca incluir dados pessoais, motivo de saúde nem conteúdo das mensagens trocadas** (RS002, RS014).
- **Consolidação do *Transactional Outbox* de e-mails (`OutboxEmail`)** ([ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)):
  - Criação atômica na mesma transação da operação chamadora;
  - Despacho assíncrono a cada **1 minuto** pelo comando `manage.py despachar_emails` (com `pg_try_advisory_lock`, `select_for_update(skip_locked=True)` e registro em `ExecucaoRotina` — [ADR 0014](../adr/0014-rotinas-agendadas.md)), usando o **backend SMTP nativo do Django** (`django.core.mail`), atendendo ao SLA de até **5 minutos** (RNF15);
  - **Até 3 novas tentativas** com **backoff fixo de 1 minuto** em caso de falha SMTP antes de marcar `falha`, **sem bloquear a operação do usuário nem impedir a notificação na plataforma** (RF017 regra 4, RNF15);
  - **Limite de envio de e-mails não críticos por usuário:** **20 e-mails por hora por usuário**, configurável em `settings`, **suprimindo apenas e-mails não críticos**, mantendo sempre a notificação na plataforma e **nunca suprimindo notificações de segurança da conta** (RS014, RF017 regra 5, [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)).
- Registro completo de status (`pendente`, `enviada`, `lida`, `falha`) e timestamps de envio e leitura.

### Não inclui

- Canais desejáveis (**SMS** ou **aplicativo de mensagens** — RF017 regra 2; o modelo apenas mantém `canal` extensível).
- Tela de **preferências / desativação de tipos de notificação** pelo usuário (fica para a **v1.1** conforme [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md); no MVP, todas são enviadas por padrão e as de segurança já nascem marcadas como não desativáveis).
- Contratação do provedor SMTP de produção e configuração DNS (SPF, DKIM, DMARC) do domínio oficial (cobertas na implantação pós-RNF11 — [ADR 0019](../adr/0019-hospedagem-implantacao-e-backup.md)).
- Lógica de negócio dos eventos de origem (por exemplo, quando vence uma doação ou quando ocorre um agendamento — cada RF apenas invoca `NotificacaoService.registrar_evento(...)`).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Sistema (emissor)** | Registrar notificações na plataforma e enfileirar e-mails no outbox quando ocorre um evento relevante em outro RF; executar o comando `despachar_emails` a cada 1 minuto para envio SMTP e até 3 retentativas. | Evento relevante disparado em um service de domínio; usuário destinatário existente e não anonimizado. |
| **Qualquer usuário autenticado** (Doador, Solicitante, Cuidador/Familiar, Representante de instituição, Administrador) | Consultar sua lista de notificações na plataforma, filtrar por tipo/status/período, abrir/marcar como lida e receber os e-mails correspondentes. | Sessão autenticada válida (`status = ativo`, e-mail confirmado — RF002). |
| **Administrador (`gestao_administradores`)** | Receber alertas operacionais de falha de rotinas agendadas (RF012, RNF15) e de taxa anormal de falhas de envio SMTP. | Conta administrativa ativa com 2FA e função explícita `gestao_administradores` ([ADR 0010](../adr/0010-perfis-e-permissoes.md)). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Registro de evento de notificação (chamado por outros services)

1. Um service de domínio (ex.: `CorrespondenciaService`, `AgendamentoService`, `DoacaoService`, `UsuarioService`) conclui uma ação dentro de `transaction.atomic()` e chama `NotificacaoService.registrar_evento(destinatario, tipo, contexto_seguro, canais=...)`.
2. `NotificacaoService.registrar_evento(...)`:
   - Valida o `tipo` contra o catálogo fechado de tipos do RF017 e monta `assunto` e `mensagem` a partir do template padronizado daquele tipo (rejeitando qualquer campo proibido — sem nome completo de terceiros, CPF, telefone, endereço de usuário, motivo de saúde nem texto de mensagem do RF019; o endereço de retirada só é aceito para tipos pós-confirmação do agendamento RF018);
   - Cria o registro **`Notificacao`** para o canal `plataforma` com `status = enviada` e `enviada_em = agora` (imediatamente visível ao usuário);
   - Para o canal `email`, verifica se o destinatário possui e-mail válido (não anonimizado) e, se não for evento de segurança da conta (nem confirmação de cadastro/recuperação), verifica o **limite de envio de e-mails por usuário**; caso dentro do limite (ou se for segurança da conta), grava o registro **`OutboxEmail`** (e vincula o status do canal e-mail como `pendente`, `tentativas = 0`, `proxima_tentativa_em = agora`). Se o limite for atingido para e-mail não crítico, registra a supressão sem afetar a notificação na plataforma.
3. Se a transação chamadora confirmar (*commit*), ambos os registros ficam persistidos; se sofrer *rollback*, nenhum registro fica órfão ([ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md), [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)).

### 4.2 Fluxo principal — Despacho assíncrono do outbox de e-mails (rotina de 1 minuto)

1. O agendador externo (ou execução manual em desenvolvimento/testes) dispara `python manage.py despachar_emails` a cada 1 minuto ([ADR 0014](../adr/0014-rotinas-agendadas.md), [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)).
2. O comando adquire o lock exclusivo no PostgreSQL (`pg_try_advisory_lock`) — se outra instância já estiver executando, encerra silenciosamente sem duplicar envios — e abre um registro em `ExecucaoRotina`.
3. `NotificacaoService.despachar_outbox_pendentes(limite_lote=...)` seleciona em lotes os registros `OutboxEmail` com `status = pendente` e `proxima_tentativa_em <= agora` usando `select_for_update(skip_locked=True)`.
4. Para cada item, envia via `django.core.mail` usando o remetente oficial configurado em variável de ambiente (`DEFAULT_FROM_EMAIL` — RS014):
   - **Sucesso:** marca `OutboxEmail.status = enviada`, `enviado_em = agora` e atualiza o status correspondente.
   - **Falha SMTP:** incrementa `tentativas` (até 3 novas tentativas após a primeira falha — total de até 4 envios: tentativa inicial + 3 novas tentativas), registra `erro_ultimo` (sem dados pessoais/conteúdo sensível) e agenda `proxima_tentativa_em` conforme o *backoff* configurado; esgotadas as 3 novas tentativas, marca `status = falha`.
5. Ao final, fecha `ExecucaoRotina` com resultado `sucesso`, `parcial` (se houve falhas pontuais) ou `falha` (se houve erro sistêmico de conexão SMTP), disparando alerta operacional se houver falha sistêmica ou taxa anormal de falhas.

### 4.3 Fluxo principal — Consulta e leitura na plataforma

1. O usuário autenticado acessa `notificacoes:lista`.
2. A view lê filtros opcionais (`tipo`, `status` — lida/não lida — `data_inicio`, `data_fim`, `pagina`) e chama `NotificacaoService.listar_do_usuario(request.user.id, filtros)`.
3. A tela exibe a lista ordenada da mais recente para a mais antiga, destacando visualmente (com texto e estilo, nunca só cor — WCAG 2.1 AA) as não lidas, com botão para marcar como lida (`POST` em `notificacoes:marcar_lida`).
4. Ao marcar como lida, `NotificacaoService.marcar_como_lida(notificacao_id, usuario_id)` filtra pelo dono na própria consulta (OWASP A01 — devolvendo `RecursoNaoEncontrado`/404 se pertencer a outro usuário), grava `status = lida` e `lida_em = agora` (idempotente se já estiver lida) e redireciona (PRG).

### 4.4 Fluxos de exceção

- **FE-01 — Provedor SMTP indisponível ou lento:** a operação principal do usuário e a gravação da notificação na plataforma **não** são afetadas nem bloqueadas (RF017 regra 4, RNF15); o e-mail permanece na fila para até 3 novas tentativas.
- **FE-02 — Usuário tenta ler ou marcar notificação de terceiro:** `NotificacaoService` filtra sempre por `destinatario_id = usuario_id` e lança `RecursoNaoEncontrado` (HTTP 404), sem revelar a existência do registro (OWASP A01).
- **FE-03 — Tentativa de criar notificação com conteúdo fora do template permitido:** `NotificacaoService` exige sempre um `Tipo` válido e parâmetros explícitos de template (nunca texto livre arbitrário de usuário), impedindo vazamento acidental de PII ou mensagens do RF019.
- **FE-04 — Limite de envio de e-mails por usuário atingido:** e-mails não críticos são suprimidos com registro de motivo interno, mantendo a notificação na plataforma; e-mails de segurança da conta (RF003, RF004, 2FA) e confirmação de e-mail (RF001) ignoram o limite e sempre são enviados.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-03-01** | O sistema suporta todos os tipos de notificação definidos no RF017 regra 1: (1) correspondência, aceite e agendamento confirmado/alterado/cancelado (RF016, RF018); (2) lembrete 24 h antes da retirada (RF018); (3) doação prestes a vencer e doação vencida (RF012); (4) nova mensagem (RF019); (5) resultado da análise do ponto de coleta e documento prestes a vencer (RF007, RF006); (6) solicitação prestes a expirar (RF013); (7) resultado de denúncia (RF021 — v1.1); (8) segurança da conta — senha alterada, suspensão, bloqueio, reset de 2FA (RF003, RF004, ADR 0009); além de confirmação de e-mail (RF001) e alertas operacionais de falha de rotina (RF012, RNF15). | RF017 (regra 1), RNF15 • `notificacoes` |
| **RN-03-02** | Os canais **e-mail** e **notificação na plataforma** são obrigatórios. SMS e aplicativo de mensagens são desejáveis e ficam fora do MVP (modelo preparado com `canal` extensível). | RF017 (regra 2), [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md) • `notificacoes` |
| **RN-03-03** | Nenhuma notificação (na plataforma ou por e-mail) pode conter **dados pessoais** (CPF, nome completo de terceiros, telefone, e-mail ou endereço de usuário), **motivo da necessidade de saúde** nem o **texto das mensagens trocadas** (RF019). O endereço do local de retirada só pode constar após a **confirmação do agendamento** (RF018). | RF017 (regra 3), RS002, RS014 • `notificacoes` |
| **RN-03-04** | Todos os e-mails são enviados exclusivamente a partir do **domínio oficial** configurado em `settings` (com SPF, DKIM e DMARC na produção — [ADR 0019](../adr/0019-hospedagem-implantacao-e-backup.md)), por meio do **Transactional Outbox** no PostgreSQL despachado a cada **1 minuto** via SMTP nativo do Django, atendendo ao SLA de até **5 minutos** (RNF15). **Cálculo do SLA com backoff fixo de 1 minuto:** evento gravado em `t = 0`; tentativa inicial no próximo ciclo (`t <= 1 min`); 1ª nova tentativa em `t <= 2 min`; 2ª nova tentativa em `t <= 3 min`; 3ª nova tentativa em `t <= 4 min` — todas dentro da janela de **5 minutos** do RNF15. | RNF15, RS014 (solução 4), [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md) • `notificacoes` |
| **RN-03-05** | Os status de envio são `pendente`, `enviada`, `lida` e `falha`. Em caso de falha no envio de e-mail, são realizadas **até 3 novas tentativas** (intervalo fixo de **1 minuto** entre tentativas) antes de marcar `falha`, **sem bloquear a operação do usuário nem impedir a notificação na plataforma**. Todos os registros de envio são preservados no banco. Alertas operacionais de falha de rotina (RF012, RNF15) e falhas anormais de SMTP são enviados **somente para contas ativas com `gestao_administradores`**. | RF017 (regra 4), RNF15, [ADR 0010](../adr/0010-perfis-e-permissoes.md), [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md) • `notificacoes` |
| **RN-03-06** | O **limite de envio de e-mails não críticos por usuário** é de **20 por hora por usuário**, configurável em `settings`. Ao atingi-lo, suprimem-se **apenas e-mails não críticos**, preservando sempre a notificação na plataforma e **nunca suprimindo notificações de segurança da conta**. | RS014 (solução 4), [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md) • `notificacoes` |
| **RN-03-07** | As notificações na plataforma ficam disponíveis em lista paginada (**20 por página** — *acréscimo da especificação, não consta no RF017*) com indicação clara de **lida** ou **não lida**, data/hora de leitura registrada, botão **"Marcar todas como lidas"** via `POST` com CSRF (*acréscimo da especificação, não consta no RF017*) e filtros por **tipo, status e período**, mantidas pelo prazo da política de privacidade (RNF10). Notificações de segurança da conta são marcadas como obrigatórias (`obrigatoria = True`) e **nunca podem ser desativadas** (tela de preferências fica para a v1.1 — [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)). | RF017 (regra 5, Pesquisa), RNF10, [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md) • `notificacoes` |
| **RN-03-08** | Cada usuário visualiza e marca como lidas **exclusivamente as próprias notificações**; nenhum usuário acessa notificações de terceiros. | RS002, OWASP A01 • `notificacoes` |

---

## 6. Modelo de dados lógico

*(Nível lógico — sem código de models. Todas as datas/horas usam fuso horário com `USE_TZ = True`.)*

### 6.1 Entidades e campos

#### `Notificacao` (app `notificacoes` — lista na plataforma e registro consolidado)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `destinatario` | FK (`Usuario`, `PROTECT`, indexado) | Sim | Dono da notificação (anonimizado se a conta encerrar). |
| `tipo` | TextChoices (indexado) | Sim | Enumeração fechada de todos os eventos da `RN-03-01` (ex.: `nova_correspondencia`, `correspondencia_aceita`, `agendamento_confirmado`, `agendamento_alterado`, `agendamento_cancelado`, `lembrete_retirada_24h`, `doacao_prestes_vencer`, `doacao_vencida`, `nova_mensagem`, `ponto_analisado`, `documento_prestes_vencer`, `solicitacao_prestes_expirar`, `denuncia_resultado`, `seguranca_conta`, `confirmacao_email`, `alerta_operacional`). |
| `canal` | TextChoices | Sim | `plataforma` ou `email` (extensível no futuro para `sms` / `mensagens`). |
| `obrigatoria` | Boolean | Sim | `True` para eventos de segurança da conta (nunca desativável — RF017 regra 5). |
| `titulo` | String (140) | Sim | Resumo curto sem PII. |
| `mensagem` | Text | Sim | Gerada apenas por template seguro do tipo (`RN-03-03`). |
| `url_destino` | String (255) | Não | Rota interna relativa opcional (ex.: `/correspondencias/12/`) para levar o usuário direto ao contexto. |
| `status` | TextChoices (indexado) | Sim | `pendente`, `enviada`, `lida`, `falha`. |
| `criada_em` | Datetime (indexado) | Sim | Data e hora da criação do evento. |
| `enviada_em` | Datetime, anulável | Não | Preenchida imediatamente em `plataforma` ou no envio SMTP em `email`. |
| `lida_em` | Datetime, anulável | Não | Preenchida ao marcar como lida na plataforma (`status = lida`). |

**Índices obrigatórios (`Notificacao`):** `(destinatario, canal, status, criada_em)` para listagem rápida, contagem de não lidas e filtros por tipo/status/período.

#### `OutboxEmail` (app `notificacoes` — estende o outbox mínimo criado na Spec 01)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `notificacao` | OneToOne (`Notificacao`, `CASCADE`, anulável) | Não | Vincula o disparo de e-mail ao registro `Notificacao(canal=email)` (nulo apenas se for e-mail pré-ativação sem exibição na plataforma, como confirmação inicial RF001). |
| `destinatario` | FK (`Usuario`, `SET_NULL`, anulável) | Não | Para controle de limite por usuário (`RN-03-06`). |
| `email_destino` | EmailField (254) | Sim | Endereço de destino no momento do evento. |
| `tipo` | TextChoices | Sim | Mesmo catálogo de tipos de `Notificacao`. |
| `critico_seguranca` | Boolean | Sim | `True` para segurança da conta e confirmação de e-mail (ignora supressão por limite). |
| `assunto` | String (160) | Sim | Assunto padronizado sem PII. |
| `corpo_texto` | Text | Sim | Corpo em texto plano padronizado (e opcionalmente HTML simples sem conteúdo de usuário). |
| `status` | TextChoices (indexado) | Sim | `pendente`, `enviada`, `falha`, `suprimida` *(controle interno quando limite de e-mail não crítico é atingido; na UI/relatório externo mantém-se a rastreabilidade)*. |
| `tentativas` | SmallInteger | Sim | Padrão `0`; máximo de **3 novas tentativas** após a tentativa inicial (`tentativas <= 4` envios no total). |
| `proxima_tentativa_em` | Datetime (indexado) | Sim | Controla agendamento imediato e *backoff* de retentativas. |
| `criado_em` | Datetime | Sim | |
| `enviado_em` | Datetime, anulável | Não | |
| `erro_ultimo` | String (255) | Não | Resumo técnico sanitizado da última falha SMTP (sem credenciais nem PII). |

#### `ExecucaoRotina` (app `nucleo` — [ADR 0014](../adr/0014-rotinas-agendadas.md))

Utilizada pelo comando `manage.py despachar_emails` para registrar cada execução (`nome_rotina`, `iniciada_em`, `finalizada_em`, `resultado`: `sucesso`/`parcial`/`falha`, `contadores` em JSON, `resumo_erro`).

### 6.2 Status e transições

| Entidade / Canal | Origem | Destino | Condição | Quem dispara |
| --- | --- | --- | --- | --- |
| `Notificacao` (`plataforma`) | *(novo)* | `enviada` | Evento criado na transação | `NotificacaoService` |
| `Notificacao` (`plataforma`) | `enviada` | `lida` | Usuário marca como lida | Próprio destinatário |
| `OutboxEmail` (`email`) | *(novo)* | `pendente` | Dentro do limite ou evento de segurança | `NotificacaoService` |
| `OutboxEmail` (`email`) | *(novo)* | `suprimida` | Limite por usuário excedido em evento não crítico | `NotificacaoService` |
| `OutboxEmail` (`email`) | `pendente` | `enviada` | Envio SMTP bem-sucedido | Comando `despachar_emails` |
| `OutboxEmail` (`email`) | `pendente` | `pendente` | Falha SMTP com `< 3` novas tentativas | Comando `despachar_emails` |
| `OutboxEmail` (`email`) | `pendente` | `falha` | Falha SMTP esgotando as 3 novas tentativas | Comando `despachar_emails` |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

### 7.1 Camada de entrada (Views, Forms e Comandos)

| Componente | App | Métodos / Disparo | Acesso | Responsabilidade |
| --- | --- | --- | --- | --- |
| `NotificacaoListaView` + `NotificacaoFiltroForm` | `notificacoes` | `GET` | Autenticado (`ativo`, confirmado) | Valida filtros (`tipo`, `status`, `data_inicio`, `data_fim`), chama `NotificacaoService.listar_do_usuario(...)` e renderiza lista paginada com contador de não lidas. |
| `NotificacaoMarcarLidaView` | `notificacoes` | `POST` | Autenticado (`ativo`, confirmado) | Valida CSRF, chama `NotificacaoService.marcar_como_lida(notificacao_id, request.user.id)`, traduz `RecursoNaoEncontrado` em 404 e redireciona (PRG ou `url_destino` validada como relativa/segura). |
| `NotificacaoMarcarTodasLidasView` *(acréscimo da especificação, não consta no RF017)* | `notificacoes` | `POST` | Autenticado (`ativo`, confirmado) | Valida CSRF, chama `NotificacaoService.marcar_todas_como_lidas(request.user.id)` e redireciona (PRG). |
| Comando `manage.py despachar_emails` | `notificacoes` | CLI / CronJob (1 min) | Sistema | Adquire `pg_try_advisory_lock`, chama `NotificacaoService.despachar_outbox_pendentes(...)` e registra o resultado em `ExecucaoRotina`. |

### 7.2 Camada de regra de negócio (Services)

| Service e método | App | Transacional? | Entradas / saídas e regras aplicadas |
| --- | --- | --- | --- |
| `NotificacaoService.registrar_evento(destinatario, tipo, contexto, url_destino="", enviar_plataforma=True, enviar_email=True)` | `notificacoes` | Participa da transação chamadora | Aplica `RN-03-01` a `RN-03-07`: renderiza template seguro do tipo (validando ausência de campos proibidos), grava `Notificacao` (`plataforma`), verifica limite de e-mails não críticos por usuário e enfileira `OutboxEmail` (ou suprime e-mail não crítico mantendo a plataforma). |
| `NotificacaoService.despachar_outbox_pendentes(limite_lote=50)` | `notificacoes` | Por item/lote (`select_for_update(skip_locked=True)`) | Envia e-mails pendentes via SMTP nativo do Django fora de transação longa de rede, atualiza `OutboxEmail` e `Notificacao(canal=email)` para `enviada`, agenda até 3 novas tentativas ou marca `falha` e retorna métricas para `ExecucaoRotina`. |
| `NotificacaoService.listar_do_usuario(usuario_id, filtros, pagina=1)` | `notificacoes` | Não (leitura) | Filtra exclusivamente por `destinatario_id = usuario_id` e `canal = plataforma`, aplica filtros por tipo, status (`enviada` = não lida / `lida`) e período, ordena por `criada_em DESC` e devolve página + contagem de não lidas. |
| `NotificacaoService.marcar_como_lida(notificacao_id, usuario_id)` | `notificacoes` | **Sim** | Filtra por `id` + `destinatario_id = usuario_id`; se não existir, lança `RecursoNaoEncontrado`; se ainda não lida, define `status = lida` e `lida_em = agora`. |
| `NotificacaoService.contar_nao_lidas(usuario_id)` | `notificacoes` | Não (leitura) | Retorna inteiro para exibição discreta no cabeçalho autenticado. |

### 7.3 Interface (Telas e templates)

- **`templates/notificacoes/notificacao_lista.html`:**
  - Barra de filtros simples: **Tipo**, **Status** (`Todas`, `Não lidas`, `Lidas`) e **Período** (data inicial e data final) + botão **Filtrar** e link **Limpar filtros**.
  - Ação secundária **"Marcar todas como lidas"** (*acréscimo da especificação, não consta no RF017*) via formulário `POST` com CSRF; paginação de **20 itens por página** (*acréscimo da especificação, não consta no RF017*).
  - Lista de cartões/itens exibindo: etiqueta com texto e cor (`Não lida` / `Lida`), título, mensagem segura, data e hora (`dd/mm/aaaa hh:mm`), botão **"Marcar como lida"** (`POST`) e link de ação quando houver `url_destino`.
  - Estado vazio amigável (ex.: `"Você não tem notificações no momento"` / `"Nenhuma notificação encontrada para os filtros selecionados"`).
- **Templates de e-mail (`templates/notificacoes/email/<tipo>.txt`):** texto simples, objetivo, remetente oficial do ReMed, sem dados pessoais de terceiros, sem motivo de saúde e sem texto das mensagens do RF019.
- **Indicador no layout base (`templates/base.html`):** link `"Notificações"` na navegação autenticada com etiqueta acessível de contagem de não lidas (via context processor fino que chama `NotificacaoService.contar_nao_lidas`, sem consultar o ORM no template).

### 7.4 Rotas

| Nome da URL | Caminho proposto | Propósito |
| --- | --- | --- |
| `notificacoes:lista` | `/notificacoes/` | Listar e pesquisar as notificações do usuário autenticado. |
| `notificacoes:marcar_lida` | `/notificacoes/<int:notificacao_id>/ler/` | Marcar uma notificação como lida (`POST`). |
| `notificacoes:marcar_todas_lidas` | `/notificacoes/ler-todas/` | Marcar todas as notificações não lidas do usuário como lidas (`POST` — *acréscimo da especificação, não consta no RF017*). |

---

## 8. Mensagens e validações

O catálogo do RF017 não define textos literais específicos de validação de tela (as mensagens seguem RNF01 e RNF02 — linguagem simples e clara):
- Período inválido no filtro (`data_inicio > data_fim`): `"A data inicial não pode ser posterior à data final"`.
- Lista vazia: `"Você ainda não possui notificações"` (sem filtros) ou `"Nenhuma notificação encontrada para os filtros informados"` (com filtros).
- Toda mensagem enviada em notificação/e-mail segue estritamente a `RN-03-03` (sem PII, sem motivo de saúde e sem texto de conversa).

---

## 9. Segurança e privacidade

| Requisito | Perigo resumido | Categoria OWASP 2025 | Controle aplicado nesta spec |
| --- | --- | --- | --- |
| **RS002** | Exposição de dados pessoais ou motivo de saúde em notificações/e-mails | A01, A04 | Templates fechados por tipo sem CPF, contato, endereço de usuário ou motivo de saúde; endereço do ponto/local só após confirmação do agendamento (RF018); isolamento estrito por `destinatario_id` (404 para terceiros). |
| **RS014** | Phishing, spam, vazamento de texto de mensagens ou links externos maliciosos | A05, A06, A09 | E-mails enviados exclusivamente do domínio oficial (SPF/DKIM/DMARC em produção); texto das mensagens do RF019 nunca entra na notificação; limite de envio de e-mails não críticos por usuário; `url_destino` validada como rota interna (contra *open redirect*); autoescape ativo nos templates. |

---

## 10. Requisitos não funcionais aplicáveis

| ID | Exigência aplicada a esta spec |
| --- | --- |
| **RNF01–RNF03** | Lista acessível (WCAG 2.1 AA), distinção de lida/não lida por texto + cor (nunca só cor), filtros claros e navegação por teclado. |
| **RNF04** | Lista paginada e indexada respondendo em até 3 s (p95); envio de e-mail fora da requisição HTTP. |
| **RNF07–RNF08** | Interface responsiva (*mobile first*) sem CDNs externas; outbox no PostgreSQL compatível com escalabilidade horizontal. |
| **RNF10** | Retenção das notificações conforme prazo futuro da política de privacidade (Questão 8 do PRD). |
| **RNF14** | Registro preservado de todos os envios (`Notificacao`, `OutboxEmail`, `ExecucaoRotina`), sem exclusão pelo usuário. |
| **RNF15** | Despacho em até **5 minutos** após o evento (comando rodando a cada 1 min), com **até 3 novas tentativas** em falha e alerta ao Administrador em caso de falha da rotina, sem bloquear o usuário. |

---

## 11. Critérios de aceite

1. **CA-03-01 (Criação atômica na plataforma e outbox — RN-03-01, RN-03-02, ADR 0015):** Dado um evento relevante disparado dentro de `transaction.atomic()`, quando a transação confirma, então a notificação na plataforma fica imediatamente visível como não lida (`status = enviada`) e um registro `pendente` é criado em `OutboxEmail`; se a transação sofrer *rollback*, nenhum dos dois registros é persistido.
2. **CA-03-02 (Envio assíncrono e 3 retentativas sem bloquear o usuário — RN-03-04, RN-03-05, RNF15):** Dado um `OutboxEmail` pendente quando o servidor SMTP falha, quando `despachar_emails` roda, então a operação original e a notificação na plataforma não são afetadas, o sistema executa até **3 novas tentativas** respeitando `proxima_tentativa_em` e só marca `status = falha` após esgotar as 3 novas tentativas.
3. **CA-03-03 (Conteúdo seguro — RN-03-03, RS002, RS014):** Para todos os templates de notificação e e-mail implementados, quando gerados para um evento, então nenhum contém CPF, telefone, e-mail de terceiros, endereço de usuário, motivo de saúde ou o texto de uma mensagem do RF019; o endereço do local de retirada aparece apenas no tipo pós-confirmação do agendamento.
4. **CA-03-04 (Limite por usuário preservando segurança da conta — RN-03-06, ADR 0015):** Dado um usuário que atingiu o limite configurável de e-mails por período, quando ocorre um evento não crítico, então a notificação na plataforma continua sendo criada e o e-mail é suprimido; quando ocorre um evento de segurança da conta (`obrigatoria = True`), tanto a notificação na plataforma quanto o e-mail são enviados normalmente.
5. **CA-03-05 (Consulta, filtros e leitura isolados por dono — RN-03-07, RN-03-08):** Dado um usuário autenticado com notificações lidas e não lidas de tipos e datas diferentes, quando filtra por tipo, status ou período em `notificacoes:lista`, então vê apenas suas notificações correspondentes; ao marcar uma como lida (`POST`), `status` passa a `lida` e `lida_em` é gravado; ao tentar marcar como lida uma notificação de outro usuário, recebe HTTP 404.
6. **CA-03-06 (Execução única sob concorrência — ADR 0014):** Dado o comando `despachar_emails` acionado concorrentemente em duas instâncias no PostgreSQL, então o `pg_try_advisory_lock` / `select_for_update(skip_locked=True)` impede o envio duplicado do mesmo e-mail e registra a execução em `ExecucaoRotina`.

---

## 12. Plano de testes

*(Executor: `python manage.py test` contra PostgreSQL — [ADR 0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md). Sem código de aplicação.)*

### 12.1 Testes de unidade (Services e comando — sem `request`)

- `NotificacaoService.registrar_evento`: criação atômica (`Notificacao` + `OutboxEmail`), *rollback* sem registros órfãos, validação de cada tipo do RF017, conferência de que nenhum template inclui PII/texto de mensagem do RF019, comportamento ao atingir limite por usuário (suprimindo só e-mail não crítico e mantendo segurança da conta).
- `NotificacaoService.despachar_outbox_pendentes` e comando `despachar_emails`: envio bem-sucedido (backend `locmem`, remetente oficial `DEFAULT_FROM_EMAIL`), 1ª/2ª/3ª nova tentativa após falhas simuladas de SMTP, transição para `falha` ao esgotar 3 novas tentativas, registro em `ExecucaoRotina` (`sucesso`, `parcial`, `falha`) e teste de concorrência (`TransactionTestCase` no PostgreSQL) garantindo que dois despachos simultâneos não enviam o mesmo e-mail duas vezes.
- `listar_do_usuario`, `marcar_como_lida` e `contar_nao_lidas`: filtros por tipo, status e período, idempotência ao marcar como lida duas vezes e recusa com `RecursoNaoEncontrado` para notificação de terceiro.

### 12.2 Testes de integração (Views, rotas e permissões)

- `notificacoes:lista`: visitante redirecionado para login; usuário autenticado vê apenas suas notificações, filtros funcionam, período invertido exibe erro amigável e paginação funciona.
- `notificacoes:marcar_lida` (e `marcar_todas_lidas`): `GET` retorna 405; `POST` com CSRF atualiza e redireciona; `POST` para ID de outro usuário retorna 404; redirecionamento rejeita URL externa.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Prazo de retenção/eliminação das notificações (RNF10):** mantidas pelo prazo da política de privacidade, ainda em pendência da ata. | Pendência externa (Questão 8 do PRD) | Não bloqueia o MVP; o expurgo futuro entrará quando a política de privacidade fixar o prazo. |
