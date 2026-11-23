# Spec 21 — Denúncia e Moderação (RF021 — v1.1)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `21` — Denúncia e Moderação (`RF021` — **v1.1**) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF021 (Importante — **v1.1**, HU21). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF10 (Essencial), RNF14 (Essencial). **Segurança:** RS001, RS002, RS006, RS008, RS011, RS014, RS015. |
| **Apps envolvidos** | `moderacao` (principal: `Denuncia`, `AnaliseDenuncia`, `ModeracaoService`), `contas` (suspensão/bloqueio via `GestaoUsuarioService` — RF004), `pontos_coleta` (suspensão de ponto via `AprovacaoPontoService` — RF007), `medicamentos` (retirada preventiva/definitiva de doação — RF008), `correspondencias` (consulta restrita de conversa/entrega ligada à denúncia — RF019/RF020), `notificacoes` (`NotificacaoService`), `auditoria` (`AuditoriaService`). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[04-gestao-de-usuarios-administrador.md](04-gestao-de-usuarios-administrador.md) (`RF004`)**, **[05-cadastro-de-ponto-de-coleta.md](05-cadastro-de-ponto-de-coleta.md) (`RF005`)**, **[07-aprovacao-ponto-de-coleta.md](07-aprovacao-ponto-de-coleta.md) (`RF007`)**, **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008`)**, **[10-conferencia-e-aprovacao-de-validade.md](10-conferencia-e-aprovacao-de-validade.md) (`RF011`)**, **[12-cadastro-de-solicitacao.md](12-cadastro-de-solicitacao.md) (`RF013`)**, **[17-mensagens-na-plataforma.md](17-mensagens-na-plataforma.md) (`RF019` — substitui placeholder `"Denunciar"`)** e **[18-confirmacao-de-retirada-e-entrega.md](18-confirmacao-de-retirada-e-entrega.md) (`RF020` — substitui placeholder `"Denunciar"`)**. **Pendências externas:** Questão 11 do PRD (limite de denúncias por usuário em período) e Questão 13 (prazo sugerido de 3 dias úteis para análise). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md). |

---

## 2. Objetivo e escopo

Permitir que usuários autenticados registrem denúncias contra usuários, doações, solicitações, conversas, pontos de coleta ou retiradas — substituindo os avisos provisórios do MVP (Specs `17` e `18`) — e que Administradores com a função **`moderacao_denuncias`** (+ 2FA) analisem com prioridade casos de risco à saúde, consultem evidências estritamente vinculadas à denúncia (sem revelar o denunciante) e apliquem decisões auditadas.

### Inclui

- Registro de denúncia acessível a partir das telas de **doação (RF008)**, **solicitação (RF013)**, **conversa (RF019)**, **ponto de coleta (RF005)** e **confirmação de retirada (RF020)**, além de objeto **usuário**.
- 7 motivos estruturados do RF021: `medicamento_divergente`, `golpe_ou_cobranca`, `assedio_ou_comportamento`, `perfil_falso`, `revenda_ou_acumulo`, `ponto_coleta_irregular`, `outros` + descrição obrigatória (máx. 500 caracteres).
- **Prioridade e proteção sanitária imediata (RS001):** denúncias com motivo de risco à saúde (`medicamento_divergente`, ex.: validade/embalagem adulterada) recebem prioridade alta e **retiram preventivamente a doação da busca** (`oculto_por_denuncia = True` — *acréscimo da especificação*) até a decisão do moderador.
- **Sigilo absoluto do denunciante:** a identidade do denunciante **nunca** é revelada ao denunciado em telas, mensagens ou notificações.
- **Limite de 5 denúncias a cada 24 horas por usuário** (`DENUNCIAS_MAX_POR_24H = 5` configurável em `settings` — RS006) para combater denúncias abusivas/de má-fé.
- Fila de moderação restrita a **`moderacao_denuncias`** (+ 2FA) com SLA configurável de **3 dias úteis** (`DENUNCIA_PRAZO_ANALISE_DIAS_UTEIS = 3` em `settings`), pesquisa por status, motivo, objeto e período, acesso auditado e limitado às evidências vinculadas (conversa do RF019, conferência do RF011 e entrega do RF020 — **nunca receitas médicas do RF014** — ADR 0010).
- Decisões: `arquivar`, `advertir_usuario`, `retirar_doacao`, `suspender_usuario`, `bloquear_usuario` (RF004) ou `suspender_ponto_coleta` (RF007), aplicadas diretamente via chamada interna transacional a `GestaoUsuarioService` / `AprovacaoPontoService` registrando `denuncia_id` e motivo obrigatório na auditoria; se julgada `improcedente`, eventual doação ocultada preventivamente tem a visibilidade restaurada automaticamente (conferindo RF012).
- Registro imutável (`on_delete=PROTECT` + `AuditoriaService`) e consulta das próprias denúncias pelo denunciante.

### Não inclui

- Relatório agregado de denúncias procedentes (coberto na Spec `22` — RF022).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Doador / Solicitante / Cuidador/Familiar / Representante (denunciante)** | Registrar denúncia sobre objeto com que teve contato/visualização e consultar o andamento das próprias denúncias. | Usuário autenticado (`ativo`, e-mail confirmado — RF002) dentro do limite de denúncias por período. |
| **Administrador (`moderacao_denuncias`)** | Pesquisar fila de denúncias, consultar evidências vinculadas (registrando leitura na auditoria), assumir análise (`em_analise`) e registrar decisão fundamentada. | Conta ativa com função explícita **`moderacao_denuncias`** ([ADR 0010](../adr/0010-perfis-e-permissoes.md)) e sessão com 2FA TOTP concluído. |

---

## 4. Fluxos

### 4.1 Fluxo principal — Registro e análise de denúncia

1. O usuário aciona `"Denunciar"` em uma das telas previstas (RF005, RF008, RF013, RF019, RF020), seleciona o **Motivo**, descreve o ocorrido (até 500 caracteres) e envia (`POST` com CSRF).
2. `ModeracaoService.registrar_denuncia(...)`:
   - Rejeita descrição vazia com mensagem literal **`"Descreva o motivo da denúncia"`**;
   - Verifica limite de **5 denúncias a cada 24 horas por usuário** (`DENUNCIAS_MAX_POR_24H = 5` em `settings`);
   - Dentro de `transaction.atomic()`, cria `Denuncia` (`status = aberta`, `prioritaria = True` quando `motivo == medicamento_divergente`), oculta preventivamente a doação da busca se risco à saúde (RS001), grava `denuncia.registrada` na auditoria e retorna;
   - View redireciona (PRG) exibindo literalmente **`"Denúncia registrada. Você será avisado do resultado"`**.
3. O moderador (`moderacao_denuncias` + 2FA) abre `moderacao:admin_lista` (prioritárias e com SLA próximo no topo), acessa `moderacao:admin_detalhe` — consultando, quando vinculadas à denúncia, conversa (RF019), conferência (RF011) e entrega (RF020) com registro de leitura em `AuditoriaService` (RNF10/RS015).
4. Seleciona o resultado (`procedente` ou `improcedente`), a **Decisão** (`arquivar`, `advertir_usuario`, `retirar_doacao`, `suspender_usuario`, `bloquear_usuario` ou `suspender_ponto_coleta`), preenche a **Justificativa** e envia (`POST` com CSRF).
5. Dentro de `transaction.atomic()`:
   - Atualiza `Denuncia.status`, grava `AnaliseDenuncia` (`append-only`), aplica o efeito da decisão: se `improcedente`, restaura automaticamente a visibilidade da doação ocultada preventivamente (se ainda `disponivel` e dentro da validade do RF012); se suspensão/bloqueio de usuário ou suspensão de ponto, executa diretamente via chamada interna transacional a `GestaoUsuarioService` / `AprovacaoPontoService` gravando `denuncia_id` e motivo na auditoria;
   - Notifica o denunciante sobre o resultado (`resultado_denuncia`, RF017) e, em caso de advertência/suspensão/bloqueio, notifica o denunciado com a justificativa **sem jamais revelar quem denunciou**;
   - Grava `denuncia.analisada` na auditoria.

### 4.2 Fluxos de exceção

- **FE-01 — Descrição vazia:** bloqueia exibindo `"Descreva o motivo da denúncia"`.
- **FE-02 — Limite de denúncias excedido no período:** bloqueia informando o limite (RS006).
- **FE-03 — Moderador tenta abrir conversa ou entrega NÃO vinculada a uma denúncia aberta/em análise:** negado (HTTP 403 — RNF10/RS002).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-21-01** | Objetos denunciáveis: `usuario`, `doacao`, `solicitacao`, `conversa`, `ponto_coleta` ou `retirada`, acionáveis a partir de RF005, RF008, RF013, RF019 e RF020. | RF021 (regra 1) • `moderacao` |
| **RN-21-02** | Motivos: `medicamento_divergente`, `golpe_ou_cobranca`, `assedio_ou_comportamento`, `perfil_falso`, `revenda_ou_acumulo`, `ponto_coleta_irregular` e `outros`. | RF021 (regra 2), RS006, RS008, RS011 • `moderacao` |
| **RN-21-03** | Status: `aberta`, `em_analise`, `procedente` ou `improcedente`. Prazo de análise configurável de **3 dias úteis** (`DENUNCIA_PRAZO_ANALISE_DIAS_UTEIS = 3` em `settings`). Denúncias de risco à saúde têm prioridade e ocultam a doação da busca preventivamente até a decisão (RS001); sendo julgadas `improcedente`, a visibilidade é restaurada automaticamente se ainda `disponivel` e válida (RF012). | RF021 (regra 3), RS001 • `moderacao`, `medicamentos` |
| **RN-21-04** | Decisões: `arquivar`, `advertir_usuario`, `retirar_doacao`, `suspender_usuario`, `bloquear_usuario` ou `suspender_ponto_coleta`. Suspensões/bloqueios são aplicados diretamente via chamada interna transacional a `GestaoUsuarioService`/`AprovacaoPontoService` gravando `denuncia_id` e justificativa obrigatória na auditoria e informando o envolvido (RF017). | RF021 (regra 4), RF004, RF007 • `moderacao` |
| **RN-21-05** | A identidade do denunciante **nunca é revelada ao denunciado**; o denunciante é avisado do resultado (RF017). | RF021 (regra 5), RS002 • `moderacao`, `notificacoes` |
| **RN-21-06** | O moderador consulta conversa (RF019), conferência (RF011) e entrega (RF020) **apenas quando ligadas à denúncia**, com auditoria de acesso, **nunca** receitas médicas (RF014). | RF021 (regra 6), RNF10, RS002, RS015, [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `moderacao`, `auditoria` |
| **RN-21-07** | Limite de **5 denúncias a cada 24 horas por usuário** (`DENUNCIAS_MAX_POR_24H = 5` em `settings`); denúncias não podem ser apagadas (`on_delete=PROTECT` + `RegistroAuditoria`). | RF021 (regras 7 e 8), RNF14, RS006 • `moderacao`, `auditoria` |

---

## 6. Modelo de dados lógico

#### `Denuncia` (app `moderacao` — `on_delete=PROTECT`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `denunciante` | FK (`Usuario`, `PROTECT`, indexado) | Sim | Oculto do denunciado em todas as visões. |
| `objeto_tipo` / `objeto_id` | TextChoices / String (64) | Sim | `usuario`, `doacao`, `solicitacao`, `conversa`, `ponto_coleta`, `retirada`. |
| `motivo` | TextChoices (indexado) | Sim | 7 motivos do RF021. |
| `descricao` | String (500) | Sim | `CheckConstraint(length(trim(descricao)) >= 1)`. |
| `prioritaria` | Boolean (indexado) | Sim | `True` para risco à saúde (`medicamento_divergente`). |
| `status` | TextChoices (indexado) | Sim | `aberta`, `em_analise`, `procedente`, `improcedente`. |
| `criado_em` | Datetime (indexado) | Sim | |

#### `AnaliseDenuncia` (app `moderacao` — `append-only`, `on_delete=PROTECT`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `denuncia` | OneToOne (`Denuncia`, `PROTECT`) | Sim | |
| `decisao` | TextChoices | Sim | `arquivar`, `advertir_usuario`, `retirar_doacao`, `suspender_usuario`, `bloquear_usuario`, `suspender_ponto_coleta`. |
| `justificativa` | Text | Sim | Obrigatória em toda decisão administrativa. |
| `responsavel` | FK (`Usuario`, `PROTECT`) | Sim | Moderador (`moderacao_denuncias`). |
| `analisada_em` | Datetime (indexado) | Sim | |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`moderacao`):** `DenunciaCriarView` + `DenunciaForm`, `MinhasDenunciasListaView`, `AdminModeracaoListaView` + `AdminModeracaoFiltroForm` (`moderacao_denuncias` + 2FA), `AdminModeracaoDetalheView`, `AdminModeracaoDecidirView` + `AnaliseDenunciaForm` (`POST`).
- **Services (`ModeracaoService`):** `registrar_denuncia`, `listar_do_denunciante`, `pesquisar_admin`, `obter_evidencias_vinculadas`, `decidir`.
- **Templates:** `denuncia_form.html`, `minhas_denuncias.html`, `admin_moderacao_lista.html`, `admin_moderacao_detalhe.html`.
- **Rotas:** `moderacao:denunciar`, `moderacao:minhas`, `moderacao:admin_lista`, `moderacao:admin_detalhe`, `moderacao:admin_decidir`.

---

## 8. Mensagens e validações

Textos literais exigidos pela fonte (RF021):
- Descrição vazia: `"Descreva o motivo da denúncia"`;
- Sucesso: `"Denúncia registrada. Você será avisado do resultado"`.

---

## 9. Segurança e privacidade

- **RS001, RS002, RS006, RS008, RS011, RS014, RS015:** retirada preventiva de doação sob risco sanitário; sigilo absoluto do denunciante; acesso a conversas/entregas restrito estritamente ao objeto da denúncia e auditado; zero acesso a receitas médicas; limite contra denúncias de má-fé; isolamento em `moderacao_denuncias` + 2FA.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF04, RNF07, RNF10, RNF14:** formulário simples, fila paginada em ≤ 3 s, LGPD e histórico imutável.

---

## 11. Critérios de aceite

1. **CA-21-01 (Registro e retirada preventiva — RN-21-03):** Denúncia de `medicamento_divergente` contra doação `disponivel` exibe `"Denúncia registrada. Você será avisado do resultado"` e oculta imediatamente a doação da busca do RF015 até decisão.
2. **CA-21-02 (Sigilo do denunciante — RN-21-05):** Notificação de suspensão/advertência ao denunciado e telas do denunciado nunca expõem quem registrou a denúncia.
3. **CA-21-03 (Escopo mínimo de evidências e permissão — RN-21-06):** `moderacao_denuncias` (+ 2FA) visualiza apenas a conversa/entrega vinculada à denúncia (gravando auditoria) e recebe 403 em conversas não denunciadas ou receitas médicas; outros perfis recebem 403 na fila.
4. **CA-21-04 (Imutabilidade e limite — RN-21-07):** Denúncias excedendo o limite por período são bloqueadas; `on_delete=PROTECT` impede exclusão física.

---

## 12. Plano de testes

- **Unidade (`ModeracaoService`):** criação nos 6 tipos de objeto, ocultação preventiva em risco à saúde, restauração ao julgar `improcedente`, limite por período, aplicação das 6 decisões, sigilo do denunciante nas notificações e auditoria.
- **Integração (Views/Permissões):** mensagens literais, acesso exclusivo a `moderacao_denuncias` + 2FA, bloqueio de acesso a conversa não denunciada e a receitas médicas.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Validação final do limite de 5 denúncias/24 h e SLA de 3 dias úteis (Questões 11 e 13 do PRD):** confirmar com o cliente na v1.1. | Pendência externa (Cliente / PO) | Ambos configuráveis em `settings`. |
