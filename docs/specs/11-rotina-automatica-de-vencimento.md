# Spec 11 — Rotina Automática de Vencimento (RF012)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `11` — Rotina Automática de Vencimento (`RF012`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF012 (Essencial — MVP, HU12). **Não funcionais:** RNF01, RNF02, RNF03, RNF06 (Essencial), RNF11 (Essencial — orientação de descarte sanitário), RNF14 (Essencial), RNF15 (Importante — rotina agendada, registro e alerta em falha). **Segurança:** RS001, RS007, RS015. |
| **Apps envolvidos** | `medicamentos` (principal: `ParametroVencimento`, `ExecucaoVencimento`, `VencimentoService`, comando `manage.py verificar_vencimento_doacoes`), `nucleo` (`ExecucaoRotina`, lock `pg_try_advisory_lock` — ADR 0014), `correspondencias` (cancelamento de reservas e agendamentos, retorno de solicitações a `aberta`), `notificacoes` (`NotificacaoService` — `doacao_prestes_vencer`, `doacao_vencida`, alertas operacionais para `gestao_administradores`), `auditoria` (`AuditoriaService`). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008`)** e **[10-conferencia-e-aprovacao-de-validade.md](10-conferencia-e-aprovacao-de-validade.md) (`RF011` — rascunho)**. **Depende de specs ainda não escritas:** **[12-cadastro-de-solicitacao.md](12-cadastro-de-solicitacao.md) (`RF013` — solicitação volta a `aberta`)**, **[14-busca-e-geolocalizacao.md](14-busca-e-geolocalizacao.md) (`RF015` — doação vencida sai da busca)**, **RF016** (verificação de validade em tempo real na reserva e cancelamento de reserva), **RF018** (verificação em tempo real no agendamento e cancelamento de agendamento) e **RF022** (v1.1 — métrica de medicamentos vencidos antes da entrega). **Pendência com o professor:** Questão 4 do PRD (validade mínima restante definitiva — prazo vencido em 03/11/2026). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0014](../adr/0014-rotinas-agendadas.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md). |

---

## 2. Objetivo e escopo

Verificar automaticamente, todos os dias, a validade das doações em andamento (`em_analise`, `disponivel` e `reservado`), notificar previamente os doadores sobre doações prestes a vencer, retirar automaticamente da plataforma as doações vencidas ou abaixo da validade mínima restante (cancelando reservas/agendamentos, devolvendo solicitações a `aberta` e orientando descarte conforme a legislação sanitária), além de oferecer conferência de validade em tempo real na reserva/agendamento e tela administrativa para configurar os parâmetros da rotina e consultar o histórico de execuções.

### Inclui

- Tabela configurável `ParametroVencimento` no PostgreSQL ([ADR 0014](../adr/0014-rotinas-agendadas.md)) editável exclusivamente pelo Administrador com função **`metricas_e_parametros`** (+ 2FA), com histórico imutável (`AuditoriaService`):
  - `validade_minima_restante_dias` (valor inicial provisório: **30 dias**, *pendência com o professor* — Questão 4 do PRD);
  - `antecedencia_aviso_dias` (valor inicial: **15 dias**, editável no banco por `metricas_e_parametros`).
  *(Novos parâmetros salvos passam a valer na próxima execução diária automática da rotina.)*
- Comando agendado diário `manage.py verificar_vencimento_doacoes` (horário de menor uso, ex.: `03:00` no fuso da plataforma — [ADR 0014](../adr/0014-rotinas-agendadas.md)), protegido por `pg_try_advisory_lock` e idempotente.
- Em caso de falha da rotina: registro de resultado `falha`, **alerta operacional aos Administradores com `gestao_administradores`** (Spec `03` / ADR 0014) e **até 3 novas tentativas automáticas com intervalo de 15 minutos** ([ADR 0014](../adr/0014-rotinas-agendadas.md)).
- Registro imutável de cada execução (`ExecucaoVencimento` / `ExecucaoRotina`) com todos os campos do RF012: data/hora, doações verificadas, doações marcadas como vencidas, reservas e agendamentos cancelados, notificações enviadas e resultado (`sucesso`, `parcial` ou `falha`).
- Método reutilizável `VencimentoService.doacao_dentro_da_validade(doacao, referencia=hoje)` chamado em tempo real no cadastro (RF008), conferência (RF011), reserva (RF016) e agendamento (RF018), impedindo reserva de doação que venceu no mesmo dia.
- Bloqueio irreversível: doação `vencido` **nunca** pode retornar a `disponivel`.

### Não inclui

- Relatório consolidado de métricas de medicamentos vencidos antes da entrega (v1.1 — RF022, que consumirá os registros de `Doacao` com `status = vencido`).
- Botão de disparo manual da rotina pela interface administrativa (possível acréscimo futuro na v1.1; no MVP, alterações de parâmetros passam a valer na próxima execução diária automática).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Sistema (rotina diária agendada)** | Verificar doações `em_analise`, `disponivel` e `reservado`, enviar avisos de vencimento próximo, marcar vencidas/abaixo do mínimo, cancelar reservas/agendamentos e devolver solicitações a `aberta`. | Agendador do PaaS/OS configurado ([ADR 0014](../adr/0014-rotinas-agendadas.md)); `ParametroVencimento` inicializado por migração de dados. |
| **Administrador (`metricas_e_parametros`)** | Visualizar histórico de execuções da rotina e alterar `validade_minima_restante_dias` e `antecedencia_aviso_dias` (com registro de auditoria). | Conta ativa, função explícita `metricas_e_parametros` ([ADR 0010](../adr/0010-perfis-e-permissoes.md)) e sessão com 2FA TOTP concluído. |
| **Doador e Solicitante** | Receber notificações de vencimento próximo (`doacao_prestes_vencer`) e de vencimento/cancelamento (`doacao_vencida`) com orientação de descarte sanitário (RF017). | Envolvidos em doações/reservas alcançadas pela rotina. |

---

## 4. Fluxos

### 4.1 Fluxo principal — Execução diária da rotina (`manage.py verificar_vencimento_doacoes`)

1. O agendador invoca `manage.py verificar_vencimento_doacoes` uma vez por dia em horário de menor uso (ex.: `03:00`).
2. `VencimentoService.executar_rotina_diaria()` tenta adquirir `pg_try_advisory_lock`; se já houver execução ativa em outra réplica, encerra sem duplicar trabalho ([ADR 0014](../adr/0014-rotinas-agendadas.md)).
3. Carrega `ParametroVencimento` atual (`validade_minima_restante_dias`, `antecedencia_aviso_dias`) e calcula a **data de corte de vencimento** (`hoje + validade_minima_restante_dias`).
4. **Etapa A — Vencimento efetivo:** seleciona doações com `status` ∈ {`em_analise`, `disponivel`, `reservado`} e `data_validade < data_corte` (ou `data_validade < hoje`). Para cada doação, em transação isolada (`transaction.atomic()` com `select_for_update()` na ordem fixa `Doacao -> Solicitacao -> Correspondencia -> Agendamento` da [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md), evitando que um erro pontual aborte todo o lote — resultado `parcial`):
   - Altera `Doacao.status` para `vencido`;
   - Se houver correspondência/reserva ou agendamento em aberto vinculados: cancela a correspondência/reserva e o agendamento, **devolve a solicitação vinculada para `aberta`** (RF013/RF016) e incrementa `reservas_agendamentos_cancelados`;
   - Agenda via `NotificacaoService` (outbox) notificação `doacao_vencida` ao **doador** (com **orientação de descarte conforme a legislação sanitária — RNF11**) e ao **solicitante** (quando havia reserva/agendamento, informando que a solicitação voltou a `aberta`);
   - Registra `doacao.vencida_rotina` em `AuditoriaService`.
5. **Etapa B — Aviso prévio de vencimento:** seleciona doações `disponivel` ou `em_analise` ainda válidas cuja **data de corte** (`data_validade - validade_minima_restante_dias`) esteja dentro da janela de antecedência (`<= hoje + antecedencia_aviso_dias`) e com `aviso_vencimento_enviado_em IS NULL`. Marca `aviso_vencimento_enviado_em = agora` e enfileira notificação `doacao_prestes_vencer` ao doador (idempotente), informando claramente quando a doação deixará a plataforma.
6. Persiste o resumo completo em `ExecucaoVencimento` (`sucesso` se 0 falhas de item; `parcial` se houve falha em algum item mantendo os demais; `falha` se erro fatal na etapa de carregamento/conexão).
7. Em caso de `parcial` ou `falha`: enfileira alerta operacional aos Administradores com `gestao_administradores` (Spec `03`) e agenda/executa nova tentativa conforme política da [ADR 0014](../adr/0014-rotinas-agendadas.md) (**até 3 novas tentativas com intervalo de 15 minutos**).

### 4.2 Fluxos alternativos

- **FA-01 — Alteração de parâmetros pelo Administrador (`medicamentos:admin_vencimento_parametros`):** Administrador com `metricas_e_parametros` (+ 2FA) edita `validade_minima_restante_dias` (≥ 0) e/ou `antecedencia_aviso_dias` (≥ 1) via `POST` com CSRF; `VencimentoService.atualizar_parametros(...)` grava alteração em `ParametroVencimento` e registra quem alterou, valores anteriores/novos, data e hora via `AuditoriaService` (RNF14).
- **FA-02 — Conferência de validade em tempo real (RF016 e RF018):** antes de concluir uma reserva (RF016) ou agendamento (RF018), o service correspondente chama `VencimentoService.verificar_ou_vencer_doacao(doacao)` dentro da transação com `select_for_update()`. Se a doação venceu no mesmo dia (ou ficou abaixo da validade mínima), marca imediatamente como `vencido`, recusa a reserva/agendamento e notifica o doador.

### 4.3 Fluxos de exceção

- **FE-01 — Tentativa de reativar ou retornar doação `vencido` para `disponivel`:** bloqueada no service (`RegraNegocioViolada`) em qualquer fluxo (RF012 regra 6).
- **FE-02 — Parâmetros inválidos (ex.: dias negativos ou `antecedencia_aviso_dias <= 0`):** form e `CheckConstraint` no PostgreSQL rejeitam a alteração.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-11-01** | Doações em `em_analise`, `disponivel` ou `reservado` com validade expirada (`< hoje`) ou abaixo de `validade_minima_restante_dias` passam automaticamente para **`vencido`**. O valor inicial provisório de `validade_minima_restante_dias` é **30 dias** (*pendência com o professor* — Questão 4 do PRD). | RF012 (regra 1), RS001 • `medicamentos` |
| **RN-11-02** | O aviso `"doação prestes a vencer"` vai ao doador com antecedência configurável em `ParametroVencimento.antecedencia_aviso_dias` (**15 dias** inicialmente, editável por `metricas_e_parametros`), contado **antes da data de corte** (`data_validade - validade_minima_restante_dias`) e enviado uma única vez por doação (`aviso_vencimento_enviado_em`). | RF012 (regra 2), RF017 • `medicamentos`, `notificacoes` |
| **RN-11-03** | A rotina roda automaticamente **1 vez por dia** em horário de menor uso, com lock distribuído (`pg_try_advisory_lock`) e idempotência. A validade também é conferida em tempo real na reserva (RF016) e no agendamento (RF018). | RF012 (regra 3), RNF15, [ADR 0014](../adr/0014-rotinas-agendadas.md) • `medicamentos`, `correspondencias` |
| **RN-11-04** | Cada execução registra `sucesso`, `parcial` ou `falha` com todos os contadores do RF012. Em falha/parcial, alerta os Administradores (`gestao_administradores`) e executa até **3 novas tentativas com intervalo de 15 minutos**. | RF012 (regra 4), RNF15, [ADR 0014](../adr/0014-rotinas-agendadas.md) • `medicamentos`, `notificacoes` |
| **RN-11-05** | Ao passar a `vencido`, a doação sai da busca (RF015), tem reservas e agendamentos cancelados transacionalmente ([ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)), a solicitação vinculada volta a `aberta` e doador + solicitante são notificados (RF017) com **orientação de descarte conforme a legislação sanitária** (RNF11). | RF012 (regra 5), RNF06, RNF11, RS001, RS007 • `medicamentos`, `correspondencias`, `solicitacoes`, `notificacoes` |
| **RN-11-06** | Uma doação `vencido` **nunca pode voltar a `disponivel`**. A quantidade vencida permanece íntegra (`on_delete=PROTECT`) para o RF022 (v1.1). | RF012 (regra 6), RS001 • `medicamentos` |
| **RN-11-07** | Apenas Administradores com `metricas_e_parametros` (+ 2FA) podem alterar os parâmetros da rotina, sempre com registro imutável de quem alterou, valores anterior/novo, data e hora (`AuditoriaService`). | RF012 (Alteração), RNF14, [ADR 0010](../adr/0010-perfis-e-permissoes.md), [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `medicamentos`, `auditoria` |

---

## 6. Modelo de dados lógico

#### `ParametroVencimento` (app `medicamentos` — registro único/singleton inicializado por migração de dados)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK = 1) | Sim | `CheckConstraint(id = 1)` garantindo registro único de configuração. |
| `validade_minima_restante_dias` | PositiveInteger | Sim | Padrão provisório: `30` (*pendência com o professor*). `CheckConstraint(>= 0)`. |
| `antecedencia_aviso_dias` | PositiveInteger | Sim | Padrão sugerido: `15`. `CheckConstraint(>= 1)`. |
| `atualizado_por` | FK (`Usuario`, `PROTECT`, anulável) | Não | Último Administrador que alterou. |
| `atualizado_em` | Datetime | Sim | |

#### `ExecucaoVencimento` (app `medicamentos` — `append-only`, vinculada a `ExecucaoRotina` da ADR 0014)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `execucao_rotina` | OneToOne (`ExecucaoRotina`, `PROTECT`) | Sim | Rastreia lock, tentativa (`1..4`) e duração (ADR 0014). |
| `executado_em` | Datetime (indexado) | Sim | Data e hora UTC da execução. |
| `doacoes_verificadas` | PositiveInteger | Sim | |
| `doacoes_marcadas_vencidas` | PositiveInteger | Sim | |
| `reservas_agendamentos_cancelados` | PositiveInteger | Sim | |
| `notificacoes_enviadas` | PositiveInteger | Sim | |
| `resultado` | TextChoices | Sim | `sucesso`, `parcial`, `falha`. |
| `resumo_erro` | Text | Não | Sanitizado (sem dados pessoais). |

*(Adiciona em `Doacao` o campo `aviso_vencimento_enviado_em` — Datetime anulável — para idempotência do aviso `doacao_prestes_vencer`.)*

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Comando:** `medicamentos/management/commands/verificar_vencimento_doacoes.py` (chama `VencimentoService.executar_rotina_diaria()`).
- **Views/Forms (`medicamentos`, restritas a `metricas_e_parametros` + 2FA):** `AdminVencimentoParametrosView` + `ParametroVencimentoForm` (`GET`/`POST`), `AdminVencimentoExecucoesView` (`GET` paginado).
- **Services (`VencimentoService`):** `obter_parametros()`, `atualizar_parametros(ator, validade_minima, antecedencia_aviso)`, `doacao_dentro_da_validade(doacao, referencia)`, `verificar_ou_vencer_doacao(doacao)` e `executar_rotina_diaria(referencia=None)`.
- **Templates:** `templates/medicamentos/admin_vencimento_parametros.html` e `templates/medicamentos/admin_vencimento_execucoes.html`.
- **Rotas:** `medicamentos:admin_vencimento_parametros` (`/admin-remed/vencimento/parametros/`), `medicamentos:admin_vencimento_execucoes` (`/admin-remed/vencimento/execucoes/`).

---

## 8. Mensagens e validações

- Notificação `doacao_vencida` ao doador inclui explicitamente a orientação de **descarte seguro conforme a legislação sanitária** (RNF11), ex.: *"Sua doação expirou ou ficou abaixo do prazo mínimo de validade e foi retirada da plataforma. Descarte medicamentos vencidos em pontos de coleta de descarte farmacêutico, conforme a legislação sanitária."*
- Alteração de parâmetros bem-sucedida: `"Parâmetros de vencimento atualizados com sucesso"`.
- Tentativa de reservar doação que venceu no mesmo dia: `"Esta doação atingiu o limite de validade e não está mais disponível"`.

---

## 9. Segurança e privacidade

- **RS001 (OWASP A06):** impede que medicamentos vencidos ou abaixo da validade mínima sejam exibidos, reservados ou entregues (rotina diária + validação em tempo real + bloqueio irreversível de retorno a `disponivel`).
- **RS007 (OWASP A06):** cancelamento transacional com `select_for_update()` na ordem fixa da ADR 0013 evita corrida entre a rotina diária e uma reserva/entrega simultânea.
- **RS015 (OWASP A01/A07/A09):** alteração de parâmetros restrita a `metricas_e_parametros` + 2FA com auditoria imutável.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF06:** transações atômicas por doação ao cancelar reservas/agendamentos e reabrir solicitações.
- **RNF11:** orientação explícita de descarte sanitário em toda notificação de vencimento.
- **RNF14 & RNF15:** histórico imutável de parâmetros e execuções; rotina diária com lock, alerta em falha e até 3 novas tentativas a cada 15 min.

---

## 11. Critérios de aceite

1. **CA-11-01 (Vencimento automático e cancelamento em cadeia — RN-11-01, RN-11-05):** Dada uma doação `reservado` com `data_validade` abaixo de `hoje + validade_minima_restante_dias`, quando `verificar_vencimento_doacoes` executa, então a doação muda para `vencido`, a reserva e o agendamento são cancelados, a solicitação vinculada volta a `aberta`, doador (com orientação sanitária RNF11) e solicitante são notificados e `ExecucaoVencimento` registra os contadores corretos com `resultado = sucesso`.
2. **CA-11-02 (Idempotência e lock — RN-11-02, RN-11-03):** Executando a rotina duas vezes no mesmo dia, o aviso `doacao_prestes_vencer` é enviado uma única vez por doação e não há duplicação de cancelamentos ou notificações.
3. **CA-11-03 (Validação em tempo real — RN-11-03):** Dada uma doação que venceu hoje antes da próxima rotina, quando `verificar_ou_vencer_doacao` é chamado na reserva (RF016) ou agendamento (RF018), a reserva é recusada e a doação muda imediatamente para `vencido`.
4. **CA-11-04 (Irreversibilidade e falha com alerta — RN-11-04, RN-11-06):** Tentativa de mudar doação `vencido` para `disponivel` é bloqueada; falha simulada na rotina grava `falha`, dispara alerta para `gestao_administradores` e aciona retry (até 3 tentativas de 15 min).
5. **CA-11-05 (Permissão de parâmetros — RN-11-07):** Apenas `metricas_e_parametros` (+ 2FA) consegue alterar `ParametroVencimento`, gravando auditoria com valores anterior e novo; demais perfis recebem 403.

---

## 12. Plano de testes

- **Unidade (`VencimentoService`, `ParametroVencimento`):** execução com relógio controlado cobrindo doações `em_analise`, `disponivel`, `reservado` e `entregue` (não afetada); cálculo da data de corte; idempotência do aviso prévio; transação por item gerando `parcial` quando um item falha; política de alerta + 3 retries; bloqueio de retorno `vencido -> disponivel`; conferência em tempo real.
- **Integração (Comando e Views):** execução de `call_command("verificar_vencimento_doacoes")`, concorrência de `pg_try_advisory_lock`, acesso à tela de parâmetros/execuções restrito a `metricas_e_parametros` + 2FA e registro em `RegistroAuditoria`.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Validade mínima restante definitiva (Questão 4 do PRD — prazo vencido em 03/11/2026):** confirmar com o professor/cliente o número definitivo de dias. | **Pendência com o professor** (Cliente / Ata) | Não bloqueia o MVP; inicializado com **30 dias provisórios** na tabela `ParametroVencimento`, ajustável pela tela de `metricas_e_parametros` sem mudança de código. |
