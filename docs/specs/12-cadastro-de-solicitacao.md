# Spec 12 — Cadastro de Solicitação de Medicamento (RF013)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `12` — Cadastro de Solicitação de Medicamento (`RF013`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF013 (Essencial — MVP, HU13). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF06 (Essencial), RNF07, RNF08, RNF10 (Essencial — LGPD/dados sensíveis), RNF13 (Essencial — aviso médico/farmacêutico), RNF14 (Essencial), RNF16. **Segurança:** RS002, RS006, RS013. |
| **Apps envolvidos** | `solicitacoes` (principal: `Solicitacao`, `SolicitacaoService`, comando `manage.py expirar_solicitacoes`), `nucleo` (`FormaFarmaceutica`, `ArquivoService` da ADR 0016, `ExecucaoRotina` da ADR 0014, mixins de perfil), `auditoria` (`AuditoriaService`), `notificacoes` (`NotificacaoService`), `correspondencias` (cancelamento de correspondência se o solicitante editar/cancelar em `correspondida` — RF016). |
| **Dependências de outras specs** | **[01-cadastro-de-usuario.md](01-cadastro-de-usuario.md) (`RF001`)**, **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[06-envio-documentos-ponto-de-coleta.md](06-envio-documentos-ponto-de-coleta.md) (`RF006` — `ArquivoService`)** e **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008` — `FormaFarmaceutica`)**. **Articula-se com specs em rascunho ou ainda não escritas:** **[13-fluxo-medicamentos-sujeitos-a-receita.md](13-fluxo-medicamentos-sujeitos-a-receita.md) (`RF014` — verificação de receita)**, **[14-busca-e-geolocalizacao.md](14-busca-e-geolocalizacao.md) (`RF015` — atalho quando a busca não encontra resultado)** e **RF016** (cruzamento automático e correspondência). **Pendências externas:** Questão 11 do PRD (limite de solicitações abertas por usuário — RS006) e Questão 13 do PRD (prazo sugerido de expiração de 30 dias). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0014](../adr/0014-rotinas-agendadas.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0016](../adr/0016-armazenamento-seguro-de-arquivos.md). |

---

## 2. Objetivo e escopo

Permitir que usuários autenticados com perfil **`Solicitante`** ou **`Cuidador/Familiar`** cadastrem sua necessidade de um medicamento (em nome próprio ou de terceiro, coletando apenas o mínimo necessário e **nunca** o motivo de saúde), consultem suas solicitações, editem ou cancelem enquanto ainda não agendadas, e recebam aviso quando uma solicitação sem correspondência expirar.

### Inclui

- Cadastro de solicitação com todos os campos do RF013: medicamento (nome comercial ou princípio ativo), concentração/dosagem, **forma farmacêutica obrigatória** (*acréscimo da especificação* para viabilizar o cruzamento do RF016), quantidade necessária, `pedido_em_nome_terceiro` (`Boolean`), `pessoa_retirada` (obrigatório quando pedido por cuidador/familiar ou em nome de terceiro), **`sujeito_receita`** (*acréscimo da especificação* para disparar o RF014) + upload de receita (`JPG`, `PNG` ou `PDF`, máx. 5 MB via `ArquivoService` — ADR 0016 / RF014), raio de busca para retirada (`km`) e disponibilidade de dias e horários.
- Garantia estrutural de **minimização de dados (LGPD / RS002)**: a tela e o modelo de dados **não possuem campo** para motivo da necessidade de saúde, diagnóstico ou dados clínicos do beneficiário.
- Limite configurável de **5 solicitações abertas simultâneas por usuário** (`SOLICITACOES_ABERTAS_MAX_POR_USUARIO = 5` em `settings` — RS006).
- Exibição obrigatória do aviso de que **a plataforma não substitui avaliação médica ou farmacêutica** (RNF13).
- Alteração e cancelamento pelo próprio solicitante enquanto `status` ∈ {`aberta`, `correspondida`} (sem exclusão física — `on_delete=PROTECT`); alterações de medicamento, concentração, forma ou quantidade em `correspondida` cancelam automaticamente a correspondência pendente com aviso ao doador.
- Rotina diária agendada (`manage.py expirar_solicitacoes`, [ADR 0014](../adr/0014-rotinas-agendadas.md)) que avisa **3 dias antes** e expira solicitações `aberta` sem correspondência após **30 dias** (`SOLICITACAO_EXPIRACAO_DIAS = 30` em `settings`), oferecendo botão **`"Renovar solicitação"`** (*acréscimo da especificação*) que reabre por mais 30 dias com auditoria.
- Pesquisa das próprias solicitações por **medicamento, status e período**.

### Não inclui

- Verificação da receita médica pelo verificador (Spec `13` — RF014).
- Cruzamento automático oferta × necessidade (Spec do RF016).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Solicitante** | Cadastrar solicitação em nome próprio, listar/pesquisar suas solicitações, editar/cancelar em `aberta` ou `correspondida` e renovar solicitação expirada. | Usuário autenticado (`status = ativo`, e-mail confirmado — RF002) com perfil **`Solicitante`** ativo (RF001). |
| **Cuidador/Familiar** | Mesmas ações acima, podendo cadastrar pedido em nome de terceiro informando quem fará a retirada (sem coletar motivo de saúde). | Usuário autenticado (`status = ativo`, e-mail confirmado) com perfil **`Cuidador/Familiar`** ativo (RF001). |
| **Sistema (rotina diária)** | Expirar solicitações `aberta` vencidas e notificar o solicitante (RF017). | Agendador configurado ([ADR 0014](../adr/0014-rotinas-agendadas.md)). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Cadastro de solicitação

1. O usuário (`Solicitante` ou `Cuidador/Familiar`) acessa `solicitacoes:criar` (diretamente ou pelo atalho `"Cadastrar solicitação"` da busca vazia no RF015).
2. Preenche medicamento (nome comercial ou princípio ativo), concentração/dosagem, forma farmacêutica obrigatória (*acréscimo da especificação*), quantidade necessária (inteiro ≥ 1), raio de busca (`km`, ≥ 1) e disponibilidade de dias e horários.
3. Se for `Cuidador/Familiar` (ou marcar `Pedido em nome de terceiro = Sim`), informa obrigatoriamente o **nome da pessoa que fará a retirada** (coletado estritamente para conferência na entrega — RF014 regra 5 / RF020).
4. Informa se o medicamento é **Sujeito a receita** (*acréscimo da especificação*); se `Sim`, anexa o arquivo da **Receita** (`JPG`, `PNG` ou `PDF`, máx. 5 MB) e informa a data de emissão (RF014 — Spec `13`).
5. Aciona **Cadastrar solicitação** (`POST` com CSRF e `multipart/form-data`).
6. Dentro de `transaction.atomic()`, `SolicitacaoService.cadastrar(...)`:
   - Valida perfil (`Solicitante` ou `Cuidador/Familiar`) e **limite de 5 solicitações abertas por usuário** (`SOLICITACOES_ABERTAS_MAX_POR_USUARIO = 5` em `settings` — RS006);
   - Valida `pessoa_retirada` obrigatória quando `pedido_em_nome_terceiro == True` (ou usuário tem perfil `Cuidador/Familiar` sem ser o próprio beneficiário);
   - Se houver receita anexada, delega o armazenamento privado e a criação da `ReceitaMedica` (`status = pendente`) ao `ReceitaService` (Spec `13` — RF014);
   - Cria `Solicitacao` com `status = aberta`, `expira_em = hoje + SOLICITACAO_EXPIRACAO_DIAS` (30 dias) e registra `solicitacao.cadastrada` via `AuditoriaService` (sem jamais incluir dados de receita ou informações de saúde em `detalhes` — ADR 0011);
   - Se a solicitação **não** depender de verificação pendente de receita, aciona o gancho de cruzamento de correspondência (RF016).
7. Redireciona (PRG) exibindo confirmação + **aviso obrigatório (RNF13)** de que a plataforma não substitui avaliação médica ou farmacêutica.

### 4.2 Fluxos alternativos

- **FA-01 — Alteração pelo solicitante (`solicitacoes:editar`):** permitida apenas ao autor enquanto `status` ∈ {`aberta`, `correspondida`}. Se estiver `correspondida` e mudarem medicamento, concentração, forma farmacêutica ou quantidade, cancela automaticamente a correspondência pendente (devolvendo a doação a `disponivel`, a solicitação a `aberta` e notificando o doador — RF016/RF017). Grava `solicitacao.alterada` na auditoria.
- **FA-02 — Cancelamento pelo solicitante (`solicitacoes:cancelar`):** via `POST` com CSRF enquanto `status` ∈ {`aberta`, `correspondida`}. Sob `transaction.atomic()` + `select_for_update()` (ordem fixa da ADR 0013), muda `status = cancelada`, libera eventual correspondência pendente notificando o doador (RF016/RF017) e grava `solicitacao.cancelada` na auditoria.
- **FA-03 — Rotina diária de expiração (`manage.py expirar_solicitacoes`):** adquirindo `pg_try_advisory_lock` ([ADR 0014](../adr/0014-rotinas-agendadas.md)), envia aviso prévio **3 dias antes** do vencimento (idempotente via `aviso_expiracao_enviado_em`), marca solicitações `aberta` com `expira_em < hoje` como `expirada`, notifica o solicitante (`solicitacao_expirada`, RF017) orientando a renovar (botão `"Renovar solicitação"` — *acréscimo da especificação*) ou cancelar e registra em `ExecucaoRotina`.
- **FA-04 — Consulta das próprias solicitações (`solicitacoes:minhas`):** filtra por `solicitante_id = request.user.id`, com filtros por **medicamento**, **status** e **período**.

### 4.3 Fluxos de exceção

- **FE-01 — Usuário atingiu o limite de solicitações abertas:** bloqueia o cadastro exibindo mensagem explicativa e link para `"Minhas solicitações"` (RS006).
- **FE-02 — Pedido em nome de terceiro sem informar quem fará a retirada:** bloqueia exigindo `pessoa_retirada`.
- **FE-03 — Tentativa de editar/cancelar solicitação `agendada`, `atendida`, `cancelada`, `expirada`, ou de terceiro:** recusa por regra de negócio no primeiro caso e retorna HTTP 404 para solicitação de outro usuário (OWASP A01).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-12-01** | Se o pedido for feito por `Cuidador/Familiar` ou marcado como `pedido_em_nome_terceiro`, é obrigatório informar **quem fará a retirada** (`pessoa_retirada`). Os dados do beneficiário são limitados ao mínimo necessário. | RF013 (regra 1), RNF10, RS002 • `solicitacoes` |
| **RN-12-02** | Quando o medicamento é sujeito a receita, o envio da receita (`JPG`, `PNG` ou `PDF`, máx. 5 MB) é obrigatório e segue o RF014 (Spec `13`) como dado sensível (`ArquivoService` — ADR 0016). | RF013 (regra 2), RF014, RS002, RS013 • `solicitacoes`, `nucleo` |
| **RN-12-03** | Status válidos da solicitação: `aberta`, `correspondida`, `agendada`, `atendida`, `cancelada`, `expirada`, sempre com histórico imutável (`AuditoriaService`). | RF013 (regra 3), RNF14 • `solicitacoes`, `auditoria` |
| **RN-12-04** | A plataforma **não coleta, não exibe e não compartilha o motivo da necessidade de saúde** (nenhum campo de diagnóstico/motivo no banco, formulários, notificações ou logs). | RF013 (regra 4), RNF10, RS002 • `solicitacoes` |
| **RN-12-05** | Existe **limite de 5 solicitações abertas simultâneas por usuário** (`SOLICITACOES_ABERTAS_MAX_POR_USUARIO = 5` em `settings`) para prevenir uso indevido. | RF013 (regra 5), RS006 • `solicitacoes` |
| **RN-12-06** | Solicitação `aberta` sem correspondência recebe aviso **3 dias antes** e expira após **30 dias** (`SOLICITACAO_EXPIRACAO_DIAS = 30` em `settings`), com notificação ao usuário (RF017) e ação `"Renovar solicitação"` (*acréscimo da especificação*) ou cancelar. | RF013 (regra 6), RNF15, [ADR 0014](../adr/0014-rotinas-agendadas.md) • `solicitacoes`, `notificacoes` |
| **RN-12-07** | Alteração e cancelamento são permitidos ao próprio solicitante enquanto `status` ∈ {`aberta`, `correspondida`}. **Não há exclusão física** (`on_delete=PROTECT`). | RF013 (Alteração, Exclusão), RNF14 • `solicitacoes` |
| **RN-12-08** | Aviso obrigatório visível: **a plataforma não substitui avaliação médica ou farmacêutica** (RNF13). | RNF13 • `solicitacoes` |

---

## 6. Modelo de dados lógico

#### `Solicitacao` (app `solicitacoes`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | Referenciado com `on_delete=PROTECT` por receitas, correspondências e agendamentos. |
| `solicitante` | FK (`Usuario`, `PROTECT`, indexado) | Sim | Usuário com perfil `Solicitante` ou `Cuidador/Familiar`. |
| `medicamento_nome` | String (150, indexado) | Sim | Nome comercial ou princípio ativo. |
| `principio_ativo` | String (150, indexado) | Sim | Normalizado para cruzamento no RF016. |
| `concentracao_dosagem` | String (80) | Sim | Ex.: `500 mg`. |
| `forma_farmaceutica` | FK (`FormaFarmaceutica`, `PROTECT`) | Sim | *Acréscimo da especificação* (obrigatória para cruzamento no RF016). |
| `quantidade_necessaria` | PositiveInteger | Sim | `CheckConstraint(quantidade_necessaria > 0)`. |
| `sujeito_receita` | Boolean | Sim | *Acréscimo da especificação* para disparar RF014. |
| `pedido_em_nome_terceiro` | Boolean | Sim | Padrão `False`. |
| `pessoa_retirada` | String (150) | Condicional | Obrigatório se `pedido_em_nome_terceiro = True` (`CheckConstraint`); se próprio, preenchido com o nome do solicitante. |
| `raio_busca_km` | PositiveInteger | Sim | `CheckConstraint(raio_busca_km >= 1)`. |
| `disponibilidade_horarios` | String (300) | Sim | Disponibilidade de dias e horários informada pelo solicitante. |
| `status` | TextChoices (indexado) | Sim | `aberta`, `correspondida`, `agendada`, `atendida`, `cancelada`, `expirada`. Padrão: `aberta`. |
| `expira_em` | Date (indexado) | Sim | `hoje + SOLICITACAO_EXPIRACAO_DIAS`. |
| `aviso_expiracao_enviado_em` | Datetime, anulável | Não | Idempotência do aviso prévio de expiração (ADR 0014). |
| `criado_em` / `atualizado_em` | Datetime | Sim | `criado_em` cobre `Data do cadastro`. |

*(A receita anexada e o histórico de verificação pertencem à [Spec 13 — RF014](13-fluxo-medicamentos-sujeitos-a-receita.md).)*

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`solicitacoes`, restritas a `Solicitante` ou `Cuidador/Familiar`):** `SolicitacaoCriarView` + `SolicitacaoCadastroForm`, `MinhasSolicitacoesListaView` + `MinhasSolicitacoesFiltroForm`, `SolicitacaoEditarView` + `SolicitacaoEditarForm`, `SolicitacaoCancelarView` (`POST`), `SolicitacaoRenovarView` (`POST`, *acréscimo da especificação*).
- **Comando:** `solicitacoes/management/commands/expirar_solicitacoes.py`.
- **Services (`SolicitacaoService`):** `cadastrar`, `atualizar`, `cancelar`, `renovar`, `listar_do_solicitante`, `expirar_solicitacoes_vencidas` — transacionais nas escritas com `AuditoriaService` e `NotificacaoService`.
- **Templates:** `solicitacao_form.html` (com aviso RNF13, nota de privacidade explicando que **não** se pede diagnóstico/motivo de saúde e campo condicional de `pessoa_retirada` + bloco de receita via JS simples) e `minhas_solicitacoes_lista.html`.
- **Rotas:** `solicitacoes:criar`, `solicitacoes:minhas`, `solicitacoes:editar`, `solicitacoes:cancelar`, `solicitacoes:renovar`.

---

## 8. Mensagens e validações

- Limite de solicitações abertas atingido: `"Você atingiu o limite máximo de solicitações abertas simultaneamente"`;
- Pedido em nome de terceiro sem `pessoa_retirada`: `"Informe quem fará a retirada do medicamento"`;
- Sucesso: `"Solicitação cadastrada com sucesso"` + aviso obrigatório RNF13 (`"O ReMed não substitui avaliação médica ou farmacêutica"`).

---

## 9. Segurança e privacidade

- **RS002 (OWASP A01/A04):** zero coleta de motivo de saúde/diagnóstico; dados do beneficiário limitados a `pessoa_retirada`; checagem por objeto em todas as rotas (`solicitante_id == request.user.id`, 404 para terceiros).
- **RS006 (OWASP A06):** limite configurável de solicitações abertas por usuário, conta com CPF único e e-mail confirmado (RF001/RF002).
- **RS013 (OWASP A01/A05):** receita tratada pelo `ArquivoService` (Spec `13` — RF014).

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** formulário simples e acessível (WCAG 2.1 AA), com nota clara de privacidade.
- **RNF04, RNF06, RNF07, RNF10, RNF13, RNF14, RNF15, RNF16:** aplicados conforme seções acima.

---

## 11. Critérios de aceite

1. **CA-12-01 (Cadastro válido sem coleta de motivo de saúde — RN-12-01, RN-12-04, RN-12-08):** Dado um `Solicitante` autenticado preenchendo os campos válidos, quando envia, então a `Solicitacao` nasce `aberta` com `expira_em` definido, aviso RNF13 exibido, nenhum dado de motivo de saúde coletado e `solicitacao.cadastrada` gravado na auditoria.
2. **CA-12-02 (Cuidador/Familiar exige `pessoa_retirada` — RN-12-01):** Dado um `Cuidador/Familiar` (ou pedido em nome de terceiro) sem informar `pessoa_retirada`, o cadastro é rejeitado; informando, salva corretamente.
3. **CA-12-03 (Limite de solicitações abertas — RN-12-05):** Dado um usuário que já atingiu `SOLICITACOES_ABERTAS_MAX_POR_USUARIO`, uma nova solicitação é bloqueada até cancelar ou concluir alguma anterior.
4. **CA-12-04 (Alteração, cancelamento sem exclusão e isolamento por dono — RN-12-07):** O dono pode editar/cancelar em `aberta` ou `correspondida`; não pode editar/cancelar em `agendada` ou `atendida`; outro usuário recebe HTTP 404; `on_delete=PROTECT` impede exclusão física.
5. **CA-12-05 (Rotina de expiração idempotente — RN-12-06):** Dada solicitação `aberta` com `expira_em < hoje`, `expirar_solicitacoes` muda o status para `expirada`, notifica o usuário uma única vez e grava `ExecucaoRotina`.

---

## 12. Plano de testes

- **Unidade (`SolicitacaoService`, `SolicitacaoCadastroForm`, constraints):** criação válida, exigência de `pessoa_retirada`, bloqueio ao atingir limite de solicitações abertas, edição/cancelamento em `aberta` e `correspondida` vs bloqueio em `agendada`/`atendida`, rotina de expiração idempotente com relógio controlado.
- **Integração (Views/Permissões):** acesso restrito a `Solicitante` e `Cuidador/Familiar` (403 para usuário que só tem perfil `Doador`), 404 para solicitação de outro usuário, exibição do aviso RNF13 e filtros em `solicitacoes:minhas`.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Validação final do limite de solicitações abertas (Questão 11 do PRD) e do prazo de expiração de 30 dias (Questão 13 do PRD):** valores iniciais adotados em `settings` (`5` solicitações abertas e `30` dias) podem ser ajustados com o cliente. | Pendência externa (Cliente / PO) | Não bloqueia o MVP; ambos são parâmetros configuráveis em `settings`. |
