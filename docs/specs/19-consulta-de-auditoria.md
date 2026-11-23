# Spec 19 — Consulta Somente Leitura de Auditoria (NOVO — sem RF na fonte)

> [!NOTE]
> **Spec transversal marcada como `NOVO` (*acréscimo da especificação*, sem RF próprio na fonte):** nasce diretamente do **RNF14 (Essencial)**, **RS013 (solução 5)**, **RS015 (solução 3)**, **[ADR 0010](../adr/0010-perfis-e-permissoes.md)**, **[ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)** e da decisão registrada na **[Spec 04 — RF004](04-gestao-de-usuarios-administrador.md)**, garantindo uma interface somente leitura isolada para a 8ª função administrativa (`auditoria`).

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `19` — Consulta Somente Leitura de Auditoria (`NOVO` — sem RF na fonte) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** *(NOVO — transversal aos RF001, RF002, RF004–RF008, RF010–RF020)*. **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF10 (Essencial — LGPD), RNF14 (Essencial — histórico imutável acessível só ao Administrador). **Segurança:** RS002, RS013 (solução 5 — auditoria de envio e leitura de arquivos), RS015 (solução 3 — revisão periódica de ações administrativas). |
| **Apps envolvidos** | `auditoria` (principal: `RegistroAuditoria`, `AuditoriaService`, views/forms de consulta somente leitura), `contas` (aba somente leitura para `RegistroAcesso` — acessos/bloqueios de login da ADR 0009), `nucleo` (mixins de acesso para função `auditoria` + 2FA). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002` — 2FA e `RegistroAcesso`)** e **[04-gestao-de-usuarios-administrador.md](04-gestao-de-usuarios-administrador.md) (`RF004` — atribuição da função `auditoria`)**. Consome os eventos gravados por todas as demais specs do MVP (`01` a `18`). **Pendência externa:** Questão 8 do PRD (prazo de retenção/expurgo LGPD do histórico na Política de Privacidade). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md). |

---

## 2. Objetivo e escopo

Fornecer ao Administrador com a função dedicada **`auditoria`** (+ 2FA TOTP) uma interface estritamente **somente leitura** para pesquisar, inspecionar e revisar periodicamente a trilha de auditoria imutável da plataforma (`RegistroAuditoria` e a aba somente leitura de `RegistroAcesso`), reforçando a segregação de funções do RS015 sem conceder poder de alterar contas, doações, pontos ou receitas.

### Inclui

- Implantação definitiva da migração SQL de imutabilidade no PostgreSQL ([ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)): **triggers `BEFORE UPDATE OR DELETE`** bloqueando qualquer alteração ou exclusão pela credencial da aplicação nas tabelas `RegistroAuditoria` e `RegistroAcesso` (ADR 0009).
- Tela somente leitura (`GET` apenas, zero rotas de criação/edição/exclusão) restrita à função **`auditoria`** (+ 2FA), com paginação (20 registros por página) e filtros por:
  - **Período** (`criado_em` início e fim);
  - **Ator** (usuário ou `"Sistema"` / rotina automática);
  - **Ação** (ex.: `usuario.status_alterado`, `ponto_coleta.aprovado`, `arquivo.acessado`, `doacao.reservada`, `entrega.confirmada`);
  - **Entidade** (`entidade_tipo` e `entidade_id`);
  - **Origem** (`web`, `rotina_automatica`, `terminal`).
- Tela de detalhe somente leitura exibindo todos os metadados estruturados do registro (`criado_em`, ator, ação, entidade, motivo, origem e `detalhes` JSON sanitizado), garantindo ausência de senhas, segredos TOTP, códigos de recuperação, tokens, conteúdo de receitas ou cópia bruta de PII (ADR 0011).
- Django Admin configurado estritamente como `readonly` (`has_add_permission = False`, `has_change_permission = False`, `has_delete_permission = False`) para `RegistroAuditoria` e `RegistroAcesso`.

### Não inclui

- Qualquer ação de alteração, edição, exclusão ou reversão de registros pela aplicação (proibida pelo RNF14 e pelo trigger do PostgreSQL).
- Acesso a arquivos de receitas médicas, fotos ou documentos (a tela de auditoria vê apenas o evento `arquivo.acessado` / `arquivo.enviado` com IDs, nunca o arquivo — ADR 0010/0011).
- Expurgo de registros expirados pela Política de Privacidade (quando o prazo da Questão 8 do PRD for definido, será executado exclusivamente via **role administrativa de banco separada**, fora da aplicação Django — ADR 0011).
- Exportação CSV dos registros filtrados (fora do MVP para reduzir risco de cópia local de logs; possível avaliação futura na v1.1).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Administrador (`auditoria`)** | Pesquisar, filtrar e visualizar registros de `RegistroAuditoria` e `RegistroAcesso` (em abas separadas, mantendo as tabelas independentes no banco) em modo estritamente somente leitura. | Conta ativa, e-mail confirmado, função explícita **`auditoria`** ([ADR 0010](../adr/0010-perfis-e-permissoes.md)) e sessão com 2FA TOTP concluído ([ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md)). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Consulta e revisão periódica da trilha de auditoria

1. O Administrador com função `auditoria` (+ 2FA) acessa `auditoria:lista` (`/admin-remed/auditoria/`).
2. Filtra por período, ator (ou `"Sistema"`), ação, tipo/ID da entidade ou origem (`GET` — sem mutação).
3. `AuditoriaService.pesquisar(filtros, pagina)` consulta `RegistroAuditoria` com `select_related("ator")` e índices apropriados, retornando página de 20 itens ordenados por `criado_em DESC`.
4. Ao abrir `auditoria:detalhe` (`/admin-remed/auditoria/<int:registro_id>/`), visualiza o registro completo em formato legível (data/hora, ator com identificação reduzida/e-mail mascarado ou ID se conta anonimizada pela LGPD — ADR 0007, ação, entidade, motivo e `detalhes` JSON formatado).

### 4.2 Fluxos de exceção

- **FE-01 — Acesso por usuário comum, outro Administrador sem a função `auditoria`, `is_superuser` sem função explícita ou Admin sem 2FA:** negado (HTTP 403 ou redirect para 2FA).
- **FE-02 — Tentativa de `UPDATE` ou `DELETE` em `RegistroAuditoria` ou `RegistroAcesso` via ORM/SQL pela credencial da aplicação:** bloqueada pelo trigger `BEFORE UPDATE OR DELETE` no PostgreSQL (ADR 0011).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-19-01** | O acesso à consulta de auditoria é exclusivo da função administrativa **`auditoria`** (+ 2FA), **somente leitura** (`GET`), sem qualquer permissão de alteração de contas, pontos, doações ou acesso a receitas médicas. | RNF14, RS015, [ADR 0010](../adr/0010-perfis-e-permissoes.md), [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `auditoria` |
| **RN-19-02** | `RegistroAuditoria` e `RegistroAcesso` são **tecnicamente imutáveis** em duas camadas: serviço/Admin somente inserção+leitura e trigger `BEFORE UPDATE OR DELETE` no PostgreSQL. | RNF14, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `auditoria`, `contas` |
| **RN-19-03** | `RegistroAuditoria.detalhes` **nunca** armazena senhas, hashes, segredos TOTP, códigos de recuperação, tokens, conteúdo de receitas, texto de mensagens ou cópias brutas de PII (CPF, e-mail, endereço, telefone). | RNF10, RS002, [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md), [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `auditoria` |
| **RN-19-04** | Contas anonimizadas por encerramento LGPD (Spec `01` / ADR 0007) preservam o vínculo `ator` (`on_delete=PROTECT`) exibido na tela de auditoria como `"Usuário encerrado (#<id>)"`, mantendo a integridade histórica sem reexpor dados pessoais. | RNF10, RNF14, [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md) • `auditoria`, `contas` |

---

## 6. Modelo de dados lógico

#### `RegistroAuditoria` (app `auditoria` — tabela `append-only` com trigger PostgreSQL)

| Campo | Tipo lógico | Obrigatório | Observação / índices |
| --- | --- | --- | --- |
| `id` | BigAutoField (PK) | Sim | |
| `criado_em` | Datetime (UTC, indexado) | Sim | |
| `ator` | FK (`Usuario`, `PROTECT`, anulável, indexado) | Não | `NULL` quando `origem == rotina_automatica` (`"Sistema"`). |
| `acao` | String (80, indexado) | Sim | Ex.: `usuario.status_alterado`, `arquivo.acessado`, `doacao.reservada`. |
| `entidade_tipo` | String (60) | Sim | Índice composto `(entidade_tipo, entidade_id)`. |
| `entidade_id` | String (64) | Sim | |
| `motivo` | Text | Não | Preenchido em ações que exigem motivo (RF004, RF007, RF011, RF014, RF020). |
| `detalhes` | JSONField | Sim | Padrão `{}`; apenas campos alterados/transições/IDs, nunca segredos ou PII bruto. |
| `origem` | TextChoices (indexado) | Sim | `web`, `rotina_automatica`, `terminal`. |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`auditoria`, todas `GET` restritas a `auditoria` + 2FA):** `AuditoriaListaView` + `AuditoriaFiltroForm`, `AuditoriaDetalheView` e `AuditoriaAcessosListaView` (`RegistroAcesso`).
- **Services (`AuditoriaService`):** `registrar(...)` (usado pelos demais services dentro de `transaction.atomic()`), `pesquisar(filtros, pagina)`, `obter_detalhe(registro_id)` e `pesquisar_acessos(filtros, pagina)` — **sem métodos `atualizar` nem `excluir`**.
- **Templates:** `templates/auditoria/auditoria_lista.html`, `templates/auditoria/auditoria_detalhe.html` e `templates/auditoria/auditoria_acessos.html`.
- **Rotas:** `auditoria:lista` (`/admin-remed/auditoria/`), `auditoria:detalhe` (`/admin-remed/auditoria/<int:registro_id>/`) e `auditoria:acessos` (`/admin-remed/auditoria/acessos/`).

---

## 8. Mensagens e validações

- Intervalo de datas inválido (`data_inicio > data_fim`): `"A data inicial não pode ser posterior à data final"`;
- Sem resultados no filtro: `"Nenhum registro de auditoria encontrado para os filtros informados"`.

---

## 9. Segurança e privacidade

- **RS015 (OWASP A01/A07/A09):** segregação estrita na 8ª função `auditoria` + 2FA; quem revisa logs não precisa ter permissão de alterar usuários, doações ou ver receitas.
- **RNF14 & RS013:** imutabilidade garantida no PostgreSQL (`BEFORE UPDATE OR DELETE`), cobrindo também todas as leituras de arquivos restritos (`arquivo.acessado`).
- **RNF10 / RS002:** sanitização na gravação (`detalhes` sem segredos, receitas ou PII bruto) e exibição segura de contas anonimizadas.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** filtros claros, tabela acessível com navegação por teclado e contraste WCAG 2.1 AA.
- **RNF04:** consultas indexadas e paginadas (20 por página) respondendo em ≤ 3 s.
- **RNF10 & RNF14:** conciliação entre imutabilidade e LGPD conforme ADR 0011.

---

## 11. Critérios de aceite

1. **CA-19-01 (Segregação de acesso — RN-19-01):** Apenas conta com função `auditoria` (+ 2FA) acessa `auditoria:lista` e `auditoria:detalhe`; usuários comuns, `gestao_usuarios`, `verificacao_receitas`, `conferencia_doacoes` e `is_superuser` sem função `auditoria` recebem HTTP 403 / redirect para 2FA.
2. **CA-19-02 (Imutabilidade no PostgreSQL — RN-19-02):** Tentativa de executar `UPDATE` ou `DELETE` em `RegistroAuditoria` ou `RegistroAcesso` pela credencial da aplicação lança erro do trigger PostgreSQL; requisições `POST`/`PUT`/`DELETE` nas rotas de auditoria retornam HTTP 405.
3. **CA-19-03 (Filtros e exibição de conta anonimizada — RN-19-04):** Filtros por período, ator (`"Sistema"` ou usuário), ação, entidade e origem retornam os registros corretos paginados; registros de usuário encerrado (LGPD) exibem `"Usuário encerrado (#<id>)"` sem erro.
4. **CA-19-04 (Sanitização — RN-19-03):** Nenhum registro gravado pelos services do MVP contém senha, segredo TOTP, código de recuperação, receita ou texto de mensagem em `detalhes`.

---

## 12. Plano de testes

- **Unidade (`AuditoriaService` e triggers PostgreSQL):** teste real contra PostgreSQL confirmando que `UPDATE` e `DELETE` em `RegistroAuditoria` e `RegistroAcesso` falham pelo trigger; teste de `pesquisar` com todos os filtros e paginação; teste de sanitização rejeitando chaves proibidas em `detalhes`.
- **Integração (Views/Permissões):** matriz completa das 8 funções administrativas + `is_superuser` sem função + Admin sem 2FA; confirmação de HTTP 405 em métodos de escrita; exibição correta de conta anonimizada.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Prazo de retenção/expurgo LGPD do histórico de auditoria (Questão 8 do PRD):** ainda não definido na Política de Privacidade. | Pendência externa (Cliente / Jurídico) | Não bloqueia o MVP; registros permanecem imutáveis até definição legal, quando o expurgo será feito por role de banco separada (ADR 0011). |
