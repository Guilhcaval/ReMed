# Spec 04 — Gestão de Usuários pelo Administrador (RF004)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `04` — Gestão de Usuários pelo Administrador (`RF004`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF004 (Importante — **MVP ⬆**, HU04). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF06 (Essencial — cancelamento transacional de reservas/agendamentos), RNF07, RNF08, RNF10 (Essencial), RNF14 (Essencial). **Segurança:** RS002, RS005, RS006, RS015. |
| **Apps envolvidos** | `contas` (principal: consulta administrativa de usuários, alteração de status, gestão das 8 funções administrativas e interface de reset de 2FA), `auditoria` (`AuditoriaService` — histórico imutável), `notificacoes` (`NotificacaoService` — avisos obrigatórios de `seguranca_conta` e avisos à outra parte em cancelamentos), `nucleo` (mixins de função administrativa + 2FA), `medicamentos` e `correspondencias` (cancelamento/ocultação transacional de doações, reservas e agendamentos em aberto). |
| **Dependências de outras specs** | **[01-cadastro-de-usuario.md](01-cadastro-de-usuario.md) (`RF001`)**, **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)** (2FA TOTP, *step-up*, reset de 2FA, `SessaoService` e os 8 grupos administrativos) e **[03-notificacoes.md](03-notificacoes.md) (`RF017`)** (avisos `seguranca_conta` e avisos à outra parte). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0007](../adr/0007-modelo-de-usuario-customizado.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md). |

---

## 2. Objetivo e escopo

Permitir que contas administrativas autorizadas (sempre autenticadas com 2FA TOTP) consultem usuários com visibilidade estritamente minimizada, alterem o status das contas (ativar, inativar, suspender, bloquear e desbloquear) com motivo registrado e impacto transacional nas operações abertas, atribuam ou removam as **8 funções administrativas separadas** (com proibição técnica de acúmulo e *step-up* de 2FA) e executem o reset de 2FA de outro Administrador quando necessário.

### Inclui

- **Consulta e pesquisa de usuários** restrita à função `gestao_usuarios` (ou `gestao_administradores` para seleção de contas na gestão de funções), com filtros por **nome ou CPF parcial** (mínimo de **3 dígitos** quando filtrado por CPF — viabilizado pela [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)), **e-mail**, **perfil de uso**, **status** e **período de cadastro**.
- **Visualização minimizada dos dados do usuário (RF004 regra 5, RS002):** exibe apenas nome, **CPF parcialmente oculto no formato `123.***.***-01`** (3 primeiros e 2 últimos dígitos), e-mail, perfis de uso, funções administrativas, status, data de cadastro e histórico resumido de ações administrativas sobre aquela conta — **nunca** exibe receitas (RF014), endereço do usuário nem dados de saúde.
- **Alteração de status** (`ativar`, `inativar`, `suspender`, `bloquear`, `desbloquear`) restrita à função `gestao_usuarios`:
  - **Motivo obrigatório** (texto livre curto) em **todas as ações administrativas** (em suspensão e bloqueio, exige a mensagem literal `"Informe o motivo da suspensão ou do bloqueio"` e informa o motivo ao usuário via `NotificacaoService` — `seguranca_conta`, nunca limitada; nas demais ações, *acréscimo da especificação, além do mínimo do RF004*);
  - Encerramento imediato de todas as sessões ativas do usuário (`SessaoService.encerrar_todas_sessoes`) ao `inativar`, `suspender` ou `bloquear`;
  - Ao `suspender` ou `bloquear`, **doações `"disponíveis"` ficam ocultas dinamicamente** da busca e da correspondência enquanto durar a suspensão ou o bloqueio (filtrando `doador.status == ativo`, voltando a aparecer se o usuário for reativado e a doação continuar válida), e **reservas e agendamentos em aberto são sempre cancelados transacionalmente** sob `select_for_update()` ([ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)), com aviso à outra parte (RF017);
  - Impossibilidade de reativar conta **anonimizada** (`anonimizado_em != NULL` — [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)) e impossibilidade de `inativar`/`suspender`/`bloquear` o último Administrador ativo com `gestao_administradores` (RS015).
- **Atribuição e remoção das 8 funções administrativas** (`gestao_usuarios`, `aprovacao_pontos_coleta`, `conferencia_doacoes`, `verificacao_receitas`, `moderacao_denuncias`, `metricas_e_parametros`, `gestao_administradores`, `auditoria`) restrita à função `gestao_administradores`:
  - Proibição de alterar as próprias funções administrativas (nunca dar ou ampliar privilégio a si mesmo — RF004 regra 4);
  - Exigência de **reconfirmação imediata (*step-up*) do código 2FA** ([ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md)) e **motivo obrigatório** (texto livre curto);
  - Ao conceder a **primeira função administrativa** a um usuário sem 2FA ainda, **encerrar todas as sessões sem 2FA** da conta-alvo, forçar o pareamento TOTP no próximo acesso (Spec `02`) e enviar notificação `seguranca_conta`;
  - **Proibição técnica de acumular `gestao_usuarios` e `verificacao_receitas`** na mesma conta ([ADR 0010](../adr/0010-perfis-e-permissoes.md));
  - Trava impedindo remover `gestao_administradores` do último Administrador ativo (`"Não é possível remover o último Administrador ativo"` — RF004 regra 4, RS015).
- **Interface para reset de 2FA de outro Administrador ativo** (restrita a `gestao_administradores`, exigindo ≥ 2 Administradores ativos com `gestao_administradores`, nunca auto-reset, motivo obrigatório e *step-up* 2FA — [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md)).
- Registro imutável de todas as ações em `RegistroAuditoria` (`AuditoriaService` — RNF14, [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)).

### Não inclui

- Alteração de dados pessoais do usuário (nome, CPF, data de nascimento, e-mail, celular, endereço — vedada ao Administrador pelo RF004 regra 1).
- Exclusão física ou encerramento voluntário de conta pelo Administrador (vedada pelo RF004 — Exclusão; encerramento só pelo próprio usuário no RF001).
- Acesso a receitas médicas (RF014) ou conversas privadas (RF019 — acessíveis apenas na análise de denúncia por `moderacao_denuncias` no RF021).
- Fluxo de denúncia e moderação que pode originar uma suspensão (v1.1 — RF021).
- Tela global somente leitura de revisão de `RegistroAuditoria` pela 8ª função `auditoria` — será especificada em **spec transversal curta marcada como `NOVO`** (sem RF na fonte), escrita **depois da spec do RF020**.

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Administrador com `gestao_usuarios`** | Consultar usuários (filtros e CPF parcialmente oculto) e alterar status (`ativar`, `inativar`, `suspender`, `bloquear`, `desbloquear`). | Conta ativa, e-mail confirmado, função explícita `gestao_usuarios`, sessão com 2FA TOTP concluído ([ADRs 0009 e 0010](../adr/0010-perfis-e-permissoes.md)). Nunca possui `verificacao_receitas`. |
| **Administrador com `gestao_administradores`** | Consultar contas para atribuição, atribuir/remover qualquer uma das 8 funções administrativas em **outras** contas e executar reset de 2FA de outro Administrador. | Conta ativa, e-mail confirmado, função explícita `gestao_administradores`, sessão com 2FA concluído e **reconfirmação imediata (*step-up*) do código TOTP** na submissão da ação ([ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md)). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Consulta de usuários

1. O Administrador (`gestao_usuarios` ou `gestao_administradores`) acessa `contas:admin_usuario_lista`.
2. Informa filtros opcionais: **Nome ou CPF parcial**, **E-mail**, **Perfil de uso**, **Status** e **Período de cadastro (início e fim)**.
3. `GestaoUsuariosService.consultar(...)` aplica os filtros no PostgreSQL (buscando CPF sem máscara via correspondência parcial conforme [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)), exclui dados proibidos do retorno e devolve lista paginada com **CPF mascarado**, nome, e-mail, perfis/funções, status e data de cadastro.
4. Ao abrir o detalhe de um usuário (`contas:admin_usuario_detalhe`), o sistema mostra somente os campos permitidos (RF004 regra 5) e as ações permitidas para as funções do ator (alterar status para `gestao_usuarios`; gerir funções administrativas e reset de 2FA para `gestao_administradores`).

### 4.2 Fluxo principal — Alteração de status (ativar, inativar, suspender, bloquear, desbloquear)

1. Na tela de detalhe do usuário, o Administrador com `gestao_usuarios` escolhe o **Novo status** (`ativo`, `inativo`, `suspenso` ou `bloqueado`), informa o **Motivo** (obrigatório para `suspenso` ou `bloqueado`) e confirma via `POST` com CSRF.
2. Dentro de `transaction.atomic()` com `select_for_update()` no `Usuario` alvo (e, quando aplicável, na ordem fixa `Doacao -> Solicitacao -> Correspondencia -> Agendamento` da [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)), `GestaoUsuariosService.alterar_status(ator, usuario_alvo_id, novo_status, motivo)`:
   - Valida que `ator` possui `gestao_usuarios` e não está alterando a si mesmo para status restritivo (`inativo`/`suspenso`/`bloqueado`);
   - Rejeita alteração de conta anonimizada (`anonimizado_em != NULL`);
   - Exige motivo não vazio para `suspenso` ou `bloqueado` (`"Informe o motivo da suspensão ou do bloqueio"`);
   - Se o alvo possui `gestao_administradores` e o novo status não é `ativo`, verifica sob bloqueio que restará ao menos outro Administrador ativo com `gestao_administradores` (caso contrário, lança erro com `"Não é possível remover o último Administrador ativo"`);
   - Atualiza `usuario.status`, grava `AcaoGestaoUsuario` (histórico de gestão) e `RegistroAuditoria` (`usuario.status_alterado`, com status anterior, novo status e motivo — sem PII bruto);
   - Se `novo_status` ∈ {`inativo`, `suspenso`, `bloqueado`}: chama `SessaoService.encerrar_todas_sessoes(usuario_alvo.id)`;
   - Se `novo_status` ∈ {`suspenso`, `bloqueado`}: retira doações `"disponíveis"` da busca, cancela reservas e agendamentos em aberto notificando a outra parte via `NotificacaoService` (RF017) e envia notificação `seguranca_conta` ao usuário alvo contendo o motivo (RF004 regra 3, RF017);
   - Se reativado/desbloqueado (`ativo`): envia notificação `seguranca_conta` ao usuário alvo.
3. A view redireciona (PRG) exibindo `"Status do usuário alterado com sucesso"`.

### 4.3 Fluxo principal — Atribuição ou remoção de funções administrativas

1. Na tela de detalhe de **outro** usuário (`ator.id != usuario_alvo.id`), o Administrador com `gestao_administradores` seleciona o conjunto desejado dentre as **8 funções administrativas**, informa o **código TOTP atual (*step-up*)** (e motivo opcional) e confirma via `POST` com CSRF.
2. Dentro de `transaction.atomic()`, `GestaoUsuariosService.atualizar_funcoes_administrativas(ator, usuario_alvo_id, funcoes, codigo_step_up, motivo, ip)`:
   - Valida `ator` com `gestao_administradores` e `ator.id != usuario_alvo_id` (proíbe auto-atribuição ou auto-alteração — RF004 regra 4);
   - Rejeita se `usuario_alvo` estiver anonimizado ou não tiver status `ativo` com e-mail confirmado;
   - Valida *step-up* 2FA via `TotpService.verificar_codigo(ator, codigo_step_up, ip, etapa="step_up")` ([ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md));
   - Aplica a **proibição técnica de acúmulo ([ADR 0010](../adr/0010-perfis-e-permissoes.md)):** rejeita se o conjunto resultante contiver simultaneamente `gestao_usuarios` e `verificacao_receitas`;
   - Se `gestao_administradores` estiver sendo removida do alvo, verifica sob bloqueio se restará ao menos outro Administrador ativo com `gestao_administradores`; caso contrário, rejeita com `"Não é possível remover o último Administrador ativo"`;
   - Atualiza os grupos do usuário alvo, grava `AcaoGestaoUsuario` e `RegistroAuditoria` (`usuario.funcoes_admin_alteradas`, com funções adicionadas/removidas e motivo), notifica o usuário alvo (`seguranca_conta`) e, se todas as funções administrativas forem removidas ou se novas funções exigirem 2FA, encerra sessões não verificadas com 2FA do alvo.

### 4.4 Fluxo alternativo — Reset de 2FA de outro Administrador

1. Na tela de detalhe de outro Administrador com TOTP ativo, o ator com `gestao_administradores` aciona **"Resetar 2FA"**, informa seu próprio código TOTP (*step-up*) e motivo, e confirma via `POST` com CSRF.
2. Chama `TotpService.resetar_por_administrador(...)` (Spec `02`), que exige ≥ 2 Administradores ativos com `gestao_administradores`, invalida o TOTP e códigos de recuperação do alvo, encerra suas sessões, notifica o alvo (`seguranca_conta`) e registra `usuario.totp_resetado` na auditoria.

### 4.5 Fluxos de exceção

- **FE-01 — Motivo vazio em suspensão ou bloqueio:** bloqueia a operação exibindo `"Informe o motivo da suspensão ou do bloqueio"`.
- **FE-02 — Tentativa de remover ou desativar o último Administrador ativo com `gestao_administradores`:** bloqueia exibindo `"Não é possível remover o último Administrador ativo"`.
- **FE-03 — Tentativa de acumular `gestao_usuarios` e `verificacao_receitas`:** `GestaoUsuariosService` lança `AcumuloFuncoesProibido` e exibe mensagem clara explicando a segregação de funções (RF004 regra 5, RS015, [ADR 0010](../adr/0010-perfis-e-permissoes.md)).
- **FE-04 — Auto-atribuição de função administrativa ou *step-up* 2FA inválido:** bloqueia com `PermissaoNegada` / erro de validação sem alterar privilégios.
- **FE-05 — Tentativa de alterar dados pessoais (CPF, nome, e-mail) ou excluir usuário:** não há formulário nem endpoint para edição de dados pessoais ou exclusão de usuário pelo Administrador (RF004 regra 1 e Exclusão).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-04-01** | As ações administrativas permitidas sobre usuários são: consultar cadastro, alterar status (`ativar`, `inativar`, `suspender`, `bloquear`, `desbloquear`), atribuir/remover funções administrativas e resetar 2FA de outro Administrador. O Administrador **não altera dados pessoais nem CPF** e **não exclui usuários**. | RF004 (regra 1, Exclusão), [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) • `contas` |
| **RN-04-02** | Os status válidos seguem o RF001 (`ativo`, `inativo`, `suspenso`, `bloqueado`). Contas anonimizadas (`anonimizado_em != NULL`) não podem ser reativadas. Usuário `suspenso` ou `bloqueado` não consegue autenticar (RF002), tem sessões ativas encerradas, suas doações `"disponíveis"` ficam **ocultas dinamicamente** da busca e da correspondência enquanto durar a suspensão/bloqueio (voltando a aparecer se reativado e dentro da validade) e suas **reservas e agendamentos em aberto são sempre cancelados** transacionalmente ([ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)), com aviso à outra parte (RF017). | RF004 (regra 2), [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md), [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md) • `contas`, `medicamentos`, `correspondencias`, `notificacoes` |
| **RN-04-03** | O **motivo é obrigatório** (texto livre curto) em **todas as ações administrativas** desta spec (`suspender`, `bloquear`, `inativar`, `ativar`/`desbloquear`, alterar funções administrativas e resetar 2FA — sendo *acréscimo da especificação* para as ações além de suspensão/bloqueio). Em suspensão ou bloqueio sem motivo, exibe-se literalmente `"Informe o motivo da suspensão ou do bloqueio"`. O motivo da suspensão ou bloqueio é **informado ao usuário** por notificação de `seguranca_conta` (RF017). | RF004 (regra 3, Mensagens), RS015 (solução 4), [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md) • `contas`, `notificacoes` |
| **RN-04-04** | Funções administrativas só podem ser atribuídas ou removidas por **outro** Administrador com `gestao_administradores` (**nunca a si mesmo**), exigindo **reconfirmação imediata (*step-up*) do código 2FA** e motivo obrigatório. Ao atribuir a primeira função administrativa a um usuário sem 2FA ainda, todas as sessões sem 2FA da conta-alvo são encerradas para forçar o pareamento TOTP no próximo acesso, enviando notificação `seguranca_conta`. | RF004 (regra 4), RS015, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `contas`, `notificacoes` |
| **RN-04-05** | **Segregação técnica de funções:** é proibido que uma mesma conta acumule `gestao_usuarios` e `verificacao_receitas`. | RF004 (regra 5), RS015 (solução 2), [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `contas` |
| **RN-04-06** | **Último Administrador ativo:** deve existir sempre ao menos um Administrador `ativo` (com 2FA e função `gestao_administradores`). Qualquer tentativa de remover `gestao_administradores` ou de `inativar`/`suspender`/`bloquear` o último Administrador ativo é bloqueada com `"Não é possível remover o último Administrador ativo"`. | RF004 (regra 4, Mensagens), RS015, [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `contas` |
| **RN-04-07** | **Visibilidade minimizada:** o Administrador visualiza apenas nome, **CPF parcialmente oculto no formato `123.***.***-01`** (3 primeiros e 2 últimos dígitos), e-mail, perfis/funções, status e data de cadastro — **nunca** receitas (RF014), endereço do usuário nem dados de saúde. A busca por CPF parcial exige **mínimo de 3 dígitos**. | RF004 (regra 5), RS002 • `contas` |
| **RN-04-08** | Toda alteração de status, alteração de funções administrativas ou reset de 2FA gera registro imutável (quem, o quê, motivo, data e hora) em `RegistroAuditoria` (RNF14, [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)). | RF004 (Alteração), RNF14, RS015 • `contas`, `auditoria` |

---

## 6. Modelo de dados lógico

*(Nível lógico — sem código de models. Reaproveita `Usuario`, `Group`/`Permission`, `RegistroAuditoria` e `Notificacao` das specs anteriores.)*

#### `AcaoGestaoUsuario` (app `contas` — registro estruturado dos campos de gestão do RF004, `append-only` / `on_delete=PROTECT`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `usuario_alvo` | FK (`Usuario`, `PROTECT`, indexado) | Sim | Usuário sobre o qual a ação foi aplicada. |
| `responsavel` | FK (`Usuario`, `PROTECT`, indexado) | Sim | Administrador que executou a ação. |
| `acao` | TextChoices | Sim | `ativar`, `inativar`, `suspender`, `bloquear`, `desbloquear`, `alterar_funcoes_admin`, `resetar_2fa`. |
| `status_anterior` / `status_novo` | TextChoices (anulável) | Não | Preenchidos em mudanças de status. |
| `funcoes_anteriores` / `funcoes_novas` | JSONField (lista de strings, anulável) | Não | Preenchidos em alterações de funções administrativas. |
| `motivo` | Text | Sim | Obrigatório em **todas as ações administrativas** (texto livre curto; `CheckConstraint` no PostgreSQL exigindo `motivo != ""`). |
| `criado_em` | Datetime (indexado) | Sim | Data e hora UTC da ação. |

*(Toda gravação em `AcaoGestaoUsuario` é acompanhada na mesma transação pelo evento correspondente em `RegistroAuditoria` — `usuario.status_alterado`, `usuario.funcoes_admin_alteradas`, `usuario.totp_resetado`.)*

### Transições de status administrativas

| Origem | Destino | Condição |
| --- | --- | --- |
| `ativo` | `inativo` | Não é o último Admin ativo com `gestao_administradores`; encerra sessões. |
| `ativo` / `inativo` | `suspenso` / `bloqueado` | Motivo obrigatório; não é o último Admin ativo; encerra sessões; cancela reservas/agendamentos e oculta/cancela doações disponíveis com aviso às partes e ao usuário. |
| `inativo` / `suspenso` / `bloqueado` | `ativo` | Conta **não** anonimizada (`anonimizado_em IS NULL`); notifica usuário (`seguranca_conta`). |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

### 7.1 Camada de entrada (Views e Forms)

| Componente | App | Métodos | Acesso | Responsabilidade |
| --- | --- | --- | --- | --- |
| `AdminUsuarioListaView` + `AdminUsuarioConsultaForm` | `contas` | `GET` | `gestao_usuarios` ou `gestao_administradores` (+ 2FA) | Valida filtros (nome/CPF parcial, e-mail, perfil, status, período), chama `GestaoUsuariosService.consultar(...)` e renderiza tabela paginada com CPF mascarado. |
| `AdminUsuarioDetalheView` | `contas` | `GET` | `gestao_usuarios` ou `gestao_administradores` (+ 2FA) | Carrega visão minimizada via `GestaoUsuariosService.obter_resumo_gestao(usuario_id)` e exibe somente as seções permitidas às funções do ator. |
| `AdminUsuarioAlterarStatusView` + `AdminAlterarStatusForm` | `contas` | `POST` | `gestao_usuarios` (+ 2FA) | Valida formato, chama `GestaoUsuariosService.alterar_status(...)`, traduz exceções nas mensagens literais e redireciona (PRG) com `"Status do usuário alterado com sucesso"`. |
| `AdminUsuarioFuncoesView` + `AdminAlterarFuncoesForm` | `contas` | `POST` | `gestao_administradores` (+ 2FA + *step-up*) | Valida campos e código TOTP *step-up*, chama `GestaoUsuariosService.atualizar_funcoes_administrativas(...)`, traduz exceções (`AcumuloFuncoesProibido`, `UltimoAdministradorAtivo`, `PermissaoNegada`) e redireciona (PRG). |
| `AdminUsuarioResetar2faView` + `AdminResetar2faForm` | `contas` | `POST` | `gestao_administradores` (+ 2FA + *step-up*) | Valida *step-up* TOTP, chama `TotpService.resetar_por_administrador(...)` e redireciona (PRG). |

### 7.2 Camada de regra de negócio (Services)

| Service e método | App | Transacional? | Entradas / saídas e regras aplicadas |
| --- | --- | --- | --- |
| `GestaoUsuariosService.consultar(ator, filtros, pagina=1)` | `contas` | Não (leitura) | Aplica `RN-04-07`: filtra por nome/CPF parcial (sem máscara), e-mail, perfil/função, status e período de cadastro; projeta apenas campos permitidos com CPF mascarado. |
| `GestaoUsuariosService.obter_resumo_gestao(ator, usuario_id)` | `contas` | Não (leitura) | Retorna dados mínimos do alvo (CPF mascarado, sem endereço nem receitas) + histórico de `AcaoGestaoUsuario`. |
| `GestaoUsuariosService.alterar_status(ator, usuario_alvo_id, novo_status, motivo)` | `contas` | **Sim** (`transaction.atomic` + `select_for_update`) | Aplica `RN-04-01` a `RN-04-03`, `RN-04-06` e `RN-04-08`: valida função `gestao_usuarios`, recusa conta anonimizada, exige motivo em suspensão/bloqueio, protege último Admin ativo, encerra sessões, cancela operações abertas (via services de `medicamentos`/`correspondencias`), registra `AcaoGestaoUsuario` + `RegistroAuditoria` e enfileira notificações (`NotificacaoService`). |
| `GestaoUsuariosService.atualizar_funcoes_administrativas(ator, usuario_alvo_id, funcoes, codigo_step_up, motivo, ip)` | `contas` | **Sim** (`transaction.atomic` + `select_for_update`) | Aplica `RN-04-04`, `RN-04-05`, `RN-04-06` e `RN-04-08`: exige `gestao_administradores`, bloqueia auto-alteração, valida *step-up* 2FA, bloqueia acúmulo `gestao_usuarios` + `verificacao_receitas`, protege último Admin ativo, atualiza grupos, registra histórico e notifica o alvo. |

### 7.3 Interface (Templates)

- `templates/contas/admin_usuario_lista.html`: filtros claros (Nome ou CPF parcial, E-mail, Perfil de uso, Status, Período de cadastro), tabela responsiva com etiquetas de status (texto + cor — WCAG 2.1 AA), CPF parcialmente oculto e paginação.
- `templates/contas/admin_usuario_detalhe.html`: cabeçalho com dados mínimos permitidos (nunca endereço nem receitas), cartão de **Alterar status** (visível apenas para `gestao_usuarios`, com campo Motivo destacado como obrigatório em suspensão/bloqueio), cartão de **Funções administrativas** (visível apenas para `gestao_administradores` em contas de terceiros, listando as 8 funções com aviso claro da incompatibilidade `gestao_usuarios` × `verificacao_receitas` e campo de código TOTP *step-up*), ação **Resetar 2FA** (quando aplicável e houver ≥ 2 Admins ativos) e linha do tempo de `AcaoGestaoUsuario`.

### 7.4 Rotas

| Nome da URL | Caminho proposto | Propósito |
| --- | --- | --- |
| `contas:admin_usuario_lista` | `/admin-remed/usuarios/` | Consultar e filtrar usuários. |
| `contas:admin_usuario_detalhe` | `/admin-remed/usuarios/<int:usuario_id>/` | Exibir dados mínimos permitidos e ações administrativas sobre o usuário. |
| `contas:admin_usuario_status` | `/admin-remed/usuarios/<int:usuario_id>/status/` | Processar alteração de status (`POST`). |
| `contas:admin_usuario_funcoes` | `/admin-remed/usuarios/<int:usuario_id>/funcoes/` | Processar atribuição/remoção das 8 funções administrativas com *step-up* (`POST`). |
| `contas:admin_usuario_resetar_2fa` | `/admin-remed/usuarios/<int:usuario_id>/resetar-2fa/` | Resetar 2FA de outro Administrador com *step-up* (`POST`). |

---

## 8. Mensagens e validações

Textos literais exigidos pela fonte (RF004):

| Condição | Mensagem literal |
| --- | --- |
| Suspensão ou bloqueio sem motivo informado | `"Informe o motivo da suspensão ou do bloqueio"` |
| Tentativa de remover `gestao_administradores` (ou desativar/suspender/bloquear) do último Administrador ativo | `"Não é possível remover o último Administrador ativo"` |
| Alteração de status concluída com sucesso | `"Status do usuário alterado com sucesso"` |

---

## 9. Segurança e privacidade

| Requisito | Perigo resumido | Categoria OWASP 2025 | Controle aplicado nesta spec |
| --- | --- | --- | --- |
| **RS002** | Exposição de CPF completo, endereço ou receitas ao Administrador | A01, A04 | Projeção mínima de campos, CPF sempre parcialmente oculto na interface, proibição de exibir receitas/endereço e proibição técnica de acumular `gestao_usuarios` + `verificacao_receitas`. |
| **RS015** | Abuso ou invasão de conta de Administrador | A01, A07, A09 | 2FA obrigatório em todas as rotas; *step-up* 2FA em alteração de funções e reset de 2FA; proibição de auto-atribuição; trava do último Administrador ativo; motivo obrigatório em suspensões/bloqueios; registro imutável (`RegistroAuditoria`); sem atalho por `is_superuser`. |
| **RS006** | Contorno de suspensão ou bloqueio | A06, A07 | Encerramento imediato de sessões ativas, bloqueio de login (RF002) e bloqueio de encerramento voluntário de conta (RF001 / ADR 0007). |

---

## 10. Requisitos não funcionais aplicáveis

| ID | Exigência aplicada a esta spec |
| --- | --- |
| **RNF01–RNF03** | Telas administrativas claras, mensagens literais e conformidade WCAG 2.1 AA (etiquetas de status com texto + cor, foco visível, resumo de erros acessível). |
| **RNF04** | Consulta paginada e indexada respondendo em até 3 s (p95). |
| **RNF06** | Cancelamento de reservas/agendamentos em suspensão/bloqueio executado na mesma transação sob `select_for_update()` ([ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)). |
| **RNF07–RNF08** | Interface responsiva com Bootstrap local. |
| **RNF10** | Minimização de dados pessoais na visualização administrativa; preservação de contas anonimizadas sem reativação. |
| **RNF14** | Histórico imutável de toda alteração de status, função administrativa e reset de 2FA em `RegistroAuditoria` ([ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)). |

---

## 11. Critérios de aceite

1. **CA-04-01 (Pesquisa com CPF parcial e exibição mascarada — RN-04-07):** Dado um Administrador com `gestao_usuarios` (+ 2FA), quando pesquisa por trecho de CPF, nome, e-mail, perfil, status ou período de cadastro, então vê os usuários correspondentes com CPF parcialmente oculto e sem exibição de endereço completo ou receitas.
2. **CA-04-02 (Suspensão/bloqueio exigindo motivo e efeito em cadeia — RN-04-02, RN-04-03):** Dado um usuário `ativo` com sessão aberta, doação `"disponível"` e agendamento em aberto, quando um Administrador com `gestao_usuarios` tenta suspender sem motivo, então recebe `"Informe o motivo da suspensão ou do bloqueio"`; quando informa o motivo, então o status muda com `"Status do usuário alterado com sucesso"`, as sessões do alvo são encerradas, a doação sai da busca, o agendamento é cancelado com notificação à outra parte, o usuário alvo recebe notificação `seguranca_conta` com o motivo e `RegistroAuditoria` grava o evento.
3. **CA-04-03 (Proibição de alterar dados pessoais, CPF ou excluir usuário — RN-04-01):** Dado um Administrador com `gestao_usuarios`, quando acessa as rotas do RF004, então não existe ação nem parâmetro aceito para modificar CPF, nome, e-mail, endereço ou excluir fisicamente um usuário; contas anonimizadas não podem ser reativadas.
4. **CA-04-04 (Atribuição de funções com *step-up* e proibição de auto-atribuição — RN-04-04):** Dado um Administrador com `gestao_administradores`, quando tenta alterar as próprias funções, então é bloqueado (HTTP 403 / `PermissaoNegada`); quando altera funções de outro usuário com código TOTP *step-up* inválido, é recusado; com código válido, as funções são atualizadas e registradas na auditoria.
5. **CA-04-05 (Proibição técnica de acumular `gestao_usuarios` e `verificacao_receitas` — RN-04-05, ADR 0010):** Dado um Administrador com `gestao_administradores` tentando atribuir simultaneamente `gestao_usuarios` e `verificacao_receitas` à mesma conta (ou adicionar uma delas a uma conta que já tem a outra), quando submete, então o service rejeita a operação com `AcumuloFuncoesProibido`.
6. **CA-04-06 (Trava do último Administrador ativo — RN-04-06):** Dado um único Administrador `ativo` com `gestao_administradores` no sistema, quando há tentativa de remover essa função ou de alterar seu status para `inativo`, `suspenso` ou `bloqueado`, então o sistema bloqueia exibindo `"Não é possível remover o último Administrador ativo"`.
7. **CA-04-07 (Controle de acesso estrito — ADR 0010):** Dado um visitante, cidadão comum, Administrador sem 2FA, Administrador com apenas `conferencia_doacoes` ou `is_superuser` sem função explícita, quando tenta acessar qualquer rota do RF004, então o acesso é negado (redirect para login/2FA ou HTTP 403).

---

## 12. Plano de testes

*(Executor: `python manage.py test` contra PostgreSQL — [ADR 0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md). Sem código de aplicação.)*

### 12.1 Testes de unidade (Services e constraints — sem `request`)

- `GestaoUsuariosService.consultar` e `obter_resumo_gestao`: filtros por nome, CPF parcial, e-mail, perfil, status e período; verificação de que CPF retornado está mascarado e que endereço/receitas não fazem parte do retorno.
- `GestaoUsuariosService.alterar_status`: motivo obrigatório em `suspender`/`bloquear` (inclusive `CheckConstraint` no banco); recusa em conta anonimizada; trava do último Administrador ativo com `gestao_administradores`; encerramento de sessões ativas; cancelamento/ocultação transacional de doações/reservas/agendamentos (testado em integração com `medicamentos`/`correspondencias` à medida que forem implementados); criação de `AcaoGestaoUsuario`, `RegistroAuditoria` e notificações `seguranca_conta`.
- `GestaoUsuariosService.atualizar_funcoes_administrativas`: bloqueio de auto-atribuição; validação de *step-up* 2FA; proibição de acúmulo `gestao_usuarios` + `verificacao_receitas` em ambos os sentidos; trava do último Administrador ativo (inclusive teste concorrente `TransactionTestCase` com duas remoções simultâneas deixando sempre ao menos 1 ativo); auditoria e notificação.

### 12.2 Testes de integração (Views, rotas e permissões)

- Matriz de permissões em todas as 5 rotas do RF004: visitante, cidadão comum, Admin sem 2FA, Admin com `conferencia_doacoes`, Admin com apenas `gestao_usuarios` (consegue alterar status mas recebe 403 em `funcoes` e `resetar_2fa`), Admin com apenas `gestao_administradores` (consegue gerir funções/reset 2FA mas recebe 403 em `status`), `is_superuser` sem função explícita (403).
- Verificação em HTML renderizado de que o CPF completo, o endereço do usuário e receitas nunca aparecem no DOM da lista nem do detalhe.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Quem exerce a função `verificacao_receitas`:** pendência da ata no RF014 (prazo vencido em 10/11/2026). | Pendência externa com o professor (Questões 6 e 7 do PRD, [ADR 0010](../adr/0010-perfis-e-permissoes.md)) | Não bloqueia esta spec (a função isolada já existe e está proibida de acumular com `gestao_usuarios`). |
