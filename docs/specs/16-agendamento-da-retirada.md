# Spec 16 — Agendamento da Retirada (RF018)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `16` — Agendamento da Retirada (`RF018`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF018 (Essencial — MVP, HU18). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF06 (Essencial — agendamento transacional), RNF07, RNF14 (Essencial), RNF15 (Importante — lembretes 24 h e detecção de não comparecimento). **Segurança:** RS002, RS004, RS007, RS008. |
| **Apps envolvidos** | `correspondencias` (principal: `Agendamento`, `AgendamentoService`, comandos `manage.py enviar_lembretes_retirada` e `manage.py verificar_nao_comparecimento`), `pontos_coleta` (seleção prioritária de pontos `ativo` respeitando `HorarioFuncionamento` e `possui_refrigeracao`), `medicamentos` (`RefrigeracaoService` — RF010, `VencimentoService` — RF012), `nucleo` (`ExecucaoRotina`), `notificacoes` (`NotificacaoService`), `auditoria` (`AuditoriaService`). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[05-cadastro-de-ponto-de-coleta.md](05-cadastro-de-ponto-de-coleta.md) (`RF005`)**, **[07-aprovacao-ponto-de-coleta.md](07-aprovacao-ponto-de-coleta.md) (`RF007` — cancelamento de agendamentos futuros quando ponto é suspenso/inativado mantendo correspondência aceita e reiniciando prazo de 48 h)**, **[09-medicamentos-refrigerados.md](09-medicamentos-refrigerados.md) (`RF010` — janela curta de 2 h provisórias e ciência obrigatória de transporte térmico)**, **[11-rotina-automatica-de-vencimento.md](11-rotina-automatica-de-vencimento.md) (`RF012`)** e **[15-correspondencia-oferta-e-necessidade.md](15-correspondencia-oferta-e-necessidade.md) (`RF016` — rascunho)**. **Articula-se com specs em rascunho desta leva:** **[17-mensagens-na-plataforma.md](17-mensagens-na-plataforma.md) (`RF019`)** e **[18-confirmacao-de-retirada-e-entrega.md](18-confirmacao-de-retirada-e-entrega.md) (`RF020` — geração do código de confirmação ao confirmar)**. **Pendências externas:** Questão 5 do PRD (*pendência com o professor* — janela de 2 h provisórias de refrigerados), Questão 13 (limite sugerido de 2 h para reagendar/cancelar) e Questão 22 (status da solicitação/correspondência após `nao_compareceu`). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0014](../adr/0014-rotinas-agendadas.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md). |

---

## 2. Objetivo e escopo

Permitir que doador e solicitante (com correspondência aceita no RF016) proponham, confirmem, reagendem ou cancelem a retirada do medicamento em um **ponto de coleta ativo** (prioritariamente, respeitando seu horário de funcionamento) ou outro local seguro combinado, revelando o endereço do local apenas após a confirmação, gerando o código de retirada do RF020, enviando lembrete 24 horas antes e tratando automaticamente o não comparecimento após 24 horas.

### Inclui

- Proposta de agendamento iniciada pelo **Doador** (data, horário — ou janela curta de até **2 horas** no mesmo dia se `refrigerado`, Spec `09` — e seleção prioritária de **ponto de coleta `ativo`**, validando `HorarioFuncionamento`, ou descrição de outro local seguro combinado, nunca sugerindo a residência por padrão — RS008).
- Confirmação ou contraproposta de reagendamento pelo **Solicitante / Cuidador/Familiar** (exigindo, para refrigerados, a confirmação explícita de **ciência sobre transporte refrigerado** da Spec `09` antes de confirmar).
- Revelação do **endereço completo do local de retirada** às duas partes **somente após `Agendamento.status == confirmado`** (RS002, RF018 regra 3), junto à geração do **código de confirmação da entrega** do RF020 (exibido somente ao solicitante — RS008) e à atualização de `Solicitacao.status = agendada`.
- Reagendamento e cancelamento permitidos até **2 horas antes** do horário marcado (`AGENDAMENTO_LIMITE_ALTERACAO_HORAS = 2` em `settings`), com notificação à outra parte (RF017), diferenciando **`Reagendar`** (mantém correspondência `aceita` e propõe nova data/horário) de **`Cancelar retirada`** (encerra correspondência, devolve doação a `disponivel` e solicitação a `aberta`).
- Integração com RF005/RF006/RF007: método `AgendamentoService.cancelar_por_indisponibilidade_ponto(ponto_coleta, motivo)` chamado dentro da transação da suspensão/inativação/vencimento/mudança de endereço do ponto, cancelando agendamentos futuros, **mantendo a correspondência `aceita`**, **reiniciando `reservado_ate = agora + RESERVA_EXPIRACAO_HORAS` (48 h)** (Spec `07`) e notificando ambas as partes.
- Rotina horária `manage.py enviar_lembretes_retirada` (ADR 0014): envia lembrete idempotente **24 horas antes** do horário confirmado (RF017 regra 1).
- Rotina horária `manage.py verificar_nao_comparecimento` (ADR 0014): se **24 horas após o horário marcado** não houver confirmação de retirada (RF020), muda o agendamento para **`nao_compareceu`**, desfaz a reserva devolvendo a doação a `disponivel` (conferindo RF012), encerra a correspondência como **`expirada`**, devolve a solicitação para **`aberta`** (se não vencida no RF013) e notifica ambas as partes.

### Não inclui

- Logística própria de transporte/motoboy ou guarda temporária no ponto de coleta (fora de escopo — RF005, RF018).
- Troca de mensagens de texto (Spec `17` — RF019) e confirmação presencial de entrega (Spec `18` — RF020).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Doador** | Propor data, horário/janela e ponto de coleta (ou local seguro); aceitar contraproposta; reagendar ou cancelar até 2 h antes. | Correspondência `aceita` (RF016) onde é o doador. |
| **Solicitante / Cuidador/Familiar** | Confirmar proposta (confirmando ciência de transporte térmico se refrigerado — RF010), sugerir outra data/horário/local, reagendar ou cancelar até 2 h antes; visualizar `pessoa_retirada` e receber o código de confirmação após `confirmado`. | Correspondência `aceita` (RF016) onde é o solicitante. |
| **Sistema (rotinas agendadas)** | Enviar lembretes 24 h antes e marcar `nao_compareceu` após 24 h sem confirmação de retirada. | Agendamento `confirmado` e rotinas ativas (ADR 0014). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Proposta e confirmação de agendamento

1. Com a correspondência `aceita` (RF016), o **Doador** acessa `correspondencias:agendar` (podendo combinar preferências previamente pelo chat do RF019).
2. Seleciona preferencialmente um **ponto de coleta `ativo`** (se a doação for `refrigerado`, pontos com `possui_refrigeracao = True` aparecem primeiro e destacados — Spec `09`), ou informa outro local público/seguro combinado (sem pré-preencher endereço residencial — RS008), informa **Data da retirada** e **Horário** (para refrigerados: janela curta `janela_retirada_inicio`–`janela_retirada_fim` no mesmo dia ≤ **2 horas**, Spec `09`) e envia via `POST` com CSRF.
3. Sob `transaction.atomic()` + `select_for_update()` (ordem fixa da ADR 0013):
   - Valida validade em tempo real da doação (`VencimentoService.verificar_ou_vencer_doacao` — RF012);
   - Se `ponto_coleta` escolhido, valida que está `ativo` e que a data/horário cai dentro do `HorarioFuncionamento` daquele dia da semana (RF018 regra 3);
   - Se `refrigerado`, valida janela curta via `RefrigeracaoService.validar_janela_curta(...)` (RF010);
   - Cria `Agendamento` com `status = proposto`, `pessoa_retirada = solicitacao.pessoa_retirada`, grava `agendamento.proposto` na auditoria e notifica o solicitante (`agendamento_proposto`, RF017 — **ainda sem o endereço completo**).
4. O **Solicitante / Cuidador/Familiar** abre `correspondencias:agendamento_detalhe`:
   - Se `refrigerado`, lê as orientações de transporte térmico e marca a caixa obrigatória **Ciência sobre o transporte refrigerado** (Spec `09`);
   - Aciona **Confirmar agendamento** (`POST` com CSRF).
5. Sob `transaction.atomic()` + `select_for_update()` (ordem fixa ADR 0013):
   - Reconfere validade da doação (RF012), status `ativo` do ponto de coleta (se houver) e ciência de transporte (se refrigerado);
   - Muda `Agendamento.status = confirmado`, limpa `Correspondencia.reservado_ate` (reserva agora vinculada ao agendamento confirmado), muda `Solicitacao.status = agendada`, gera o **código de confirmação de retirada** (RF020 — exibido e notificado **apenas ao solicitante**), grava `agendamento.confirmado` na auditoria e notifica ambas as partes com o **endereço completo do local de retirada** (RF017, RF018 regra 3).

### 4.2 Fluxos alternativos

- **FA-01 — Contraproposta / Reagendamento (`correspondencias:agendamento_reagendar`):** permitida quando `proposto` (a qualquer momento pela outra parte) ou quando `confirmado` até **2 horas antes** do horário marcado (`AGENDAMENTO_LIMITE_ALTERACAO_HORAS = 2`). Mantém a correspondência `aceita`, atualiza data/horário/local, muda status para `reagendado` (aguardando aceite da outra parte para voltar a `confirmado`, regenerando o código de retirada se já confirmado), grava auditoria e notifica a outra parte (RF017).
- **FA-02 — Cancelamento voluntário da retirada por uma das partes (`correspondencias:agendamento_cancelar`):** permitido até **2 horas antes** do horário marcado; encerra a correspondência (`recusada`/`cancelada`), desfaz a reserva devolvendo a doação a `disponivel` (conferindo RF012) e a solicitação a `aberta` (se não vencida), encerra a conversa do RF019 em somente leitura, notifica a outra parte (RF017) e grava auditoria.
- **FA-03 — Lembrete 24 horas antes (`manage.py enviar_lembretes_retirada`):** rotina horária com `pg_try_advisory_lock` seleciona agendamentos `confirmado` previstos para as próximas 24 horas com `lembrete_24h_enviado_em IS NULL`, marca o timestamp e enfileira `lembrete_retirada_24h` para doador e solicitante (RF017).
- **FA-04 — Não comparecimento após 24 horas (`manage.py verificar_nao_comparecimento`):** rotina horária com `pg_try_advisory_lock` seleciona agendamentos `confirmado` cujo horário marcado ocorreu há mais de **24 horas** sem entrega confirmada (RF020). Em transação isolada por agendamento (`select_for_update` na ordem ADR 0013): muda `Agendamento -> nao_compareceu`, desfaz a reserva devolvendo `Doacao -> disponivel` (conferindo RF012; se vencida, `vencido`), marca `Correspondencia -> expirada`, devolve `Solicitacao -> aberta` (se não vencida no RF013), encerra a conversa do RF019 em somente leitura, notifica ambas as partes (RF017) e grava auditoria + `ExecucaoRotina`.

### 4.3 Fluxos de exceção

- **FE-01 — Horário fora do funcionamento do ponto de coleta escolhido:** bloqueia a proposta exibindo os horários de funcionamento do ponto (RF018 regra 3).
- **FE-02 — Tentativa de reagendar ou cancelar com menos de 2 horas para a retirada:** bloqueada com orientação clara.
- **FE-03 — Refrigerado sem ciência de transporte térmico ou janela > 2 horas:** bloqueada conforme Spec `09`.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-16-01** | O **doador propõe** data, horário e local; o **solicitante confirma ou sugere outra opção** (reagendamento). Detalhes são combinados via mensagens na plataforma (RF019), sem revelar telefone ou e-mail. | RF018 (regra 1), RS008 • `correspondencias` |
| **RN-16-02** | Status válidos do agendamento: `proposto`, `confirmado`, `reagendado`, `cancelado`, `retirado`, `nao_compareceu`, sempre com histórico imutável (`AuditoriaService`). | RF018 (regra 2), RNF14 • `correspondencias`, `auditoria` |
| **RN-16-03** | O **endereço completo do local de retirada só é liberado às duas partes após `status == confirmado`** (RS002). Pontos de coleta `ativo` têm prioridade, respeitando obrigatoriamente o `HorarioFuncionamento` cadastrado (RF005). A residência nunca é sugerida por padrão (RS008). | RF018 (regra 3), RF005, RS002, RS008 • `correspondencias`, `pontos_coleta` |
| **RN-16-04** | Reagendar e cancelar é permitido até **2 horas antes** do horário marcado (`AGENDAMENTO_LIMITE_ALTERACAO_HORAS = 2` em `settings`), com notificação à outra parte (RF017). **`Reagendar`** mantém a correspondência `aceita`; **`Cancelar retirada`** encerra a correspondência, desfaz a reserva devolvendo doação a `disponivel` e solicitação a `aberta`. | RF018 (regra 4), RF017 • `correspondencias`, `notificacoes` |
| **RN-16-05** | Sem confirmação de retirada **24 horas após o horário marcado**, o agendamento passa automaticamente para **`nao_compareceu`**, a reserva é desfeita, a doação volta a `disponivel` (se dentro da validade do RF012), a correspondência é encerrada como **`expirada`** e a solicitação volta a **`aberta`** (se não vencida no RF013), notificando ambas as partes. | RF018 (regra 5), RNF15, [ADR 0014](../adr/0014-rotinas-agendadas.md) • `correspondencias`, `medicamentos`, `solicitacoes` |
| **RN-16-06** | Para medicamentos `refrigerado`, aplicam-se obrigatoriamente a janela curta no mesmo dia (**2 horas provisórias**, *pendência com o professor* — Questão 5 do PRD), priorização de ponto com refrigeração e ciência prévia do solicitante (Spec `09`). | RF018 (regra 6), RF010, RS004 • `correspondencias`, `medicamentos` |
| **RN-16-07** | Suspensão, inativação ou retorno a `pendente_aprovacao` do ponto de coleta (RF005/RF006/RF007) cancela automaticamente agendamentos futuros nele, **mantendo a correspondência `aceita` e reiniciando o prazo de expiração da reserva de 48 h (ADR 0013)**, com aviso às duas partes. | RF007 (regra 3), Spec `07`, [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md) • `correspondencias`, `pontos_coleta` |

---

## 6. Modelo de dados lógico

#### `Agendamento` (app `correspondencias`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | Referenciado com `on_delete=PROTECT` por `EntregaConfirmacao` (RF020). |
| `correspondencia` | FK (`Correspondencia`, `PROTECT`, indexado) | Sim | `UniqueConstraint(fields=["correspondencia"], condition=Q(status__in=["proposto", "reagendado", "confirmado"]))`. |
| `data_retirada` | Date (indexado) | Sim | Não aceita data no passado. |
| `horario_retirada` | Time | Sim | Para refrigerados, corresponde a `janela_retirada_inicio`. |
| `janela_retirada_inicio` / `janela_retirada_fim` | Time, anulável | Condicional | Obrigatórios se `doacao.condicao_conservacao == refrigerado` (Spec `09`). |
| `ponto_coleta` | FK (`PontoColeta`, `PROTECT`, anulável) | Condicional | Exige `ponto_coleta` OU `local_combinado` (`CheckConstraint`). |
| `local_combinado` | String (250) | Condicional | Endereço/descrição de local público seguro quando não houver ponto próximo. |
| `pessoa_retirada` | String (150) | Sim | Copiada de `Solicitacao.pessoa_retirada` para conferência na entrega (RF014/RF020). |
| `proposto_por` | FK (`Usuario`, `PROTECT`) | Sim | Controla qual parte deve confirmar uma proposta ou contraproposta. |
| `ciencia_transporte_refrigerado` / `ciencia_transporte_em` | Boolean / Datetime, anulável | Condicional | Obrigatórios antes de `confirmado` quando `refrigerado` (Spec `09`). |
| `status` | TextChoices (indexado) | Sim | `proposto`, `confirmado`, `reagendado`, `cancelado`, `retirado`, `nao_compareceu`. |
| `lembrete_24h_enviado_em` | Datetime, anulável | Não | Idempotência do lembrete 24 h antes (RF017 / ADR 0014). |
| `criado_em` / `atualizado_em` | Datetime | Sim | |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`correspondencias`, restritas às duas partes da correspondência — 404 para terceiros):** `AgendamentoProporView` + `AgendamentoPropostaForm`, `AgendamentoDetalheView` (`GET`), `AgendamentoConfirmarView` + `AgendamentoConfirmarForm` (`POST`, inclui checkbox de ciência para refrigerados), `AgendamentoReagendarView` (`GET`/`POST`), `AgendamentoCancelarView` (`POST`).
- **Comandos:** `correspondencias/management/commands/enviar_lembretes_retirada.py` e `verificar_nao_comparecimento.py`.
- **Services (`AgendamentoService`):** `propor`, `confirmar`, `reagendar`, `cancelar`, `cancelar_por_indisponibilidade_ponto`, `enviar_lembretes_24h`, `processar_nao_comparecimentos`.
- **Templates:** `agendamento_form.html` (priorizando pontos ativos com horários visíveis; pontos refrigerados destacados se RF010) e `agendamento_detalhe.html` (esconde endereço completo enquanto `proposto`/`reagendado`; exibe endereço + código de retirada somente para o solicitante após `confirmado`).
- **Rotas:** `correspondencias:agendar`, `correspondencias:agendamento_detalhe`, `correspondencias:agendamento_confirmar`, `correspondencias:agendamento_reagendar`, `correspondencias:agendamento_cancelar`.

---

## 8. Mensagens e validações

- Fora do horário do ponto de coleta: `"O horário escolhido está fora do expediente do ponto de coleta selecionado"`;
- Alteração/cancelamento após o prazo: `"Reagendamentos e cancelamentos só são permitidos até 2 horas antes do horário marcado"`;
- Sucesso na confirmação: `"Agendamento confirmado! O endereço do local de retirada foi liberado"`.

---

## 9. Segurança e privacidade

- **RS002 (OWASP A01):** endereço completo do local ocultado na view e nas notificações até `status == confirmado`; checagem por objeto nas duas partes (404 para terceiros).
- **RS008 (OWASP A06):** priorização de pontos aprovados no expediente oficial, sem sugerir residência; código de entrega restrito ao solicitante; agendamento formal separado do chat (RF019).
- **RS004 & RS007:** janela curta + ciência de refrigerados e locks na ordem fixa da ADR 0013.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** exibição clara do status, horários do ponto e orientações térmicas (WCAG 2.1 AA).
- **RNF06, RNF07, RNF14, RNF15:** transações atômicas, *mobile first*, auditoria e rotinas horárias idempotentes.

---

## 11. Critérios de aceite

1. **CA-16-01 (Endereço oculto até confirmação e geração de código — RN-16-03):** Enquanto `Agendamento.status == proposto`, o HTML e a notificação não exibem o endereço completo do local; após `confirmado`, ambas as partes veem o endereço e **somente o solicitante** recebe o código de confirmação do RF020.
2. **CA-16-02 (Validação de expediente do ponto e janela refrigerada — RN-16-03, RN-16-06):** Proposta fora do `HorarioFuncionamento` do ponto é recusada; doação `refrigerado` exige janela ≤ 2 h no mesmo dia e ciência do solicitante antes de `confirmado`.
3. **CA-16-03 (Limite de 2 horas para reagendar/cancelar — RN-16-04):** Tentativa de reagendar ou cancelar com 1 h 59 min de antecedência é recusada; com ≥ 2 h é aceita e notifica a outra parte.
4. **CA-16-04 (Lembrete 24 h e não comparecimento 24 h depois — RN-16-05):** `enviar_lembretes_retirada` envia 1 lembrete 24 h antes; após 24 h do horário sem entrega confirmada, `verificar_nao_comparecimento` marca `nao_compareceu`, devolve doação a `disponivel` e notifica as partes.
5. **CA-16-05 (Indisponibilidade do ponto — RN-16-07):** Ao suspender/inativar ponto com agendamento futuro (RF007), o agendamento é cancelado, a correspondência permanece `aceita`, `reservado_ate` é reiniciado para `+48 h` e ambas as partes são notificadas.

---

## 12. Plano de testes

- **Unidade (`AgendamentoService`):** validação de horário contra `HorarioFuncionamento`, bloqueio de ponto inativo/suspenso, validação de refrigerados (`RefrigeracaoService`), limite exato de 2 h, lembrete 24 h idempotente, rotina de `nao_compareceu` (incluindo doação que venceu nesse intervalo), e `cancelar_por_indisponibilidade_ponto` reiniciando `reservado_ate`.
- **Integração (Views/Privacidade):** ocultação do endereço antes de `confirmado`, restrição de 404 para terceiros, exibição do código de confirmação **somente** para o solicitante e não para o doador.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Limite máximo da janela curta de refrigerados (Questão 5 do PRD — prazo vencido em 10/11/2026):** confirmar com o professor/cliente o valor definitivo. | **Pendência com o professor** (Cliente / Ata) | Adotadas **2 horas** provisórias (`REFRIGERADO_JANELA_MAX_MINUTOS = 120` em `settings`, Spec `09`). |
| 2 | **Validação final do limite de 2 horas para reagendar/cancelar (Questão 13 do PRD):** confirmar com o cliente o valor sugerido. | Pendência externa (Cliente / PO) | Configurável em `settings` (`AGENDAMENTO_LIMITE_ALTERACAO_HORAS = 2`). |
