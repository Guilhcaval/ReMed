# Spec 22 — Relatório de Métricas de Entregas (RF022 — v1.1)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `22` — Relatório de Métricas de Entregas (`RF022` — **v1.1**) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF022 (Importante — **v1.1**, HU22). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF10 (Essencial — apenas dados agregados e anônimos), RNF14 (Essencial). **Segurança:** RS002, RS015. |
| **Apps envolvidos** | `moderacao` (principal: `MetricasService`, views/forms de relatório e exportação CSV/PDF), leitura agregada (sem PII) sobre `correspondencias` (`EntregaConfirmacao`, `Agendamento`), `medicamentos` (`Doacao`), `solicitacoes` (`Solicitacao`), `pontos_coleta` (`PontoColeta`), `moderacao` (`Denuncia`), `auditoria` (`AuditoriaService` — registro de exportações). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[05-cadastro-de-ponto-de-coleta.md](05-cadastro-de-ponto-de-coleta.md) (`RF005`)**, **[07-aprovacao-ponto-de-coleta.md](07-aprovacao-ponto-de-coleta.md) (`RF007`)**, **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008`)**, **[10-conferencia-e-aprovacao-de-validade.md](10-conferencia-e-aprovacao-de-validade.md) (`RF011`)**, **[11-rotina-automatica-de-vencimento.md](11-rotina-automatica-de-vencimento.md) (`RF012`)**, **[12-cadastro-de-solicitacao.md](12-cadastro-de-solicitacao.md) (`RF013`)**, **[16-agendamento-da-retirada.md](16-agendamento-da-retirada.md) (`RF018`)**, **[18-confirmacao-de-retirada-e-entrega.md](18-confirmacao-de-retirada-e-entrega.md) (`RF020`)** e **[21-denuncia-e-moderacao.md](21-denuncia-e-moderacao.md) (`RF021` — rascunho)**. **Pendência externa:** Questão 2 do PRD (metas numéricas dos indicadores ainda não definidas pelo cliente/PO). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0004](../adr/0004-pip-venv-requirements-fixado.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md). |

---

## 2. Objetivo e escopo

Apresentar ao Administrador com a função **`metricas_e_parametros`** (+ 2FA) os **8 indicadores de desempenho** do ReMed — tendo como métrica principal a **quantidade de medicamentos efetivamente entregues** — em tabela e gráfico, com filtros por período, região e medicamento/forma farmacêutica, exportáveis em **CSV** e **PDF**, garantindo **exclusivamente dados agregados e anônimos** (RS002, RNF10).

### Inclui

- Cálculo agregado no PostgreSQL (`Count`, `Sum`, `Avg`) para todos os **8 indicadores do RF022**:
  1. **Quantidade de medicamentos efetivamente entregues** *(indicador principal — soma de `EntregaConfirmacao.quantidade_entregue` em entregas confirmadas, considerando eventuais `CorrecaoEntrega`, RF020)*;
  2. **Quantidade de doações cadastradas e de solicitações atendidas** (RF008, RF013, RF020);
  3. **Taxa de atendimento:** `solicitações atendidas ÷ solicitações abertas` no período (protegendo divisão por zero);
  4. **Tempo médio entre o cadastro da doação e a entrega** (em dias/horas, a partir de `Doacao.criado_em` até `EntregaConfirmacao.entregue_em`);
  5. **Quantidade de medicamentos vencidos antes da entrega** (RF012 — soma de `quantidade_disponivel` em doações `vencido`);
  6. **Quantidade de agendamentos com não comparecimento** (`Agendamento.status == nao_compareceu`, RF018);
  7. **Quantidade de pontos de coleta ativos por região** (RF005, RF007);
  8. **Quantidade de denúncias registradas e procedentes** (RF021).
- Filtros obrigatórios do RF022: **Período** (`data_inicio` e `data_fim`), **Região, município ou bairro** e **Medicamento ou forma farmacêutica**.
- Exibição em **tabela e gráfico SVG simples gerado no servidor** (zero biblioteca JS externa, acessível com `<title>`/`<desc>` — ADRs 0005 e 0006) e exportação em **CSV** (biblioteca padrão `csv`, com neutralização de *CSV formula injection* — OWASP) e **PDF** via **`ReportLab`** (a validar no Python 3.14 ao iniciar a v1.1 — ADR 0004).
- Garantia estrita de anonimato: **nenhum dado pessoal (nome, CPF, e-mail, endereço) ou dado de saúde individual** aparece na tela, nas tabelas ou nos arquivos exportados (RF022 regra 2, RS002, RNF10), suprimindo subgrupos por bairro + medicamento com `< 3` ocorrências exibindo `"< 3"` (*k-anonimato* — *acréscimo da especificação*).
- Registro de cada exportação na auditoria (`relatorio.exportado` com filtros e formato — *acréscimo da especificação*, RNF14).

### Não inclui

- Relatórios individuais por cidadão ou visualização de receitas/conversas (vedados pelo RF022 regra 2 e RS002).
- Metas numéricas fixas de sucesso (ainda pendentes de definição pelo cliente/PO — Questão 2 do PRD).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Administrador (`metricas_e_parametros`)** | Filtrar, consultar tabela/gráficos dos 8 indicadores e exportar relatório agregado em CSV ou PDF. | Conta ativa, função explícita **`metricas_e_parametros`** ([ADR 0010](../adr/0010-perfis-e-permissoes.md)) e sessão com 2FA TOTP concluído. |

---

## 4. Fluxos

### 4.1 Fluxo principal — Consulta e exportação de relatório

1. O Administrador (`metricas_e_parametros` + 2FA) acessa `moderacao:metricas` (`/admin-remed/metricas/`).
2. Aplica filtros opcionais (período padrão dos últimos 30 dias — *acréscimo da especificação*, região/município/bairro e medicamento/forma farmacêutica) via `GET`.
3. `MetricasService.gerar_relatorio(filtros)` executa consultas agregadas no PostgreSQL e retorna exclusivamente números, séries temporais/regionais agregadas e totais (sem qualquer campo identificável de pessoa física).
4. A tela exibe cartões de destaque (com a métrica principal no topo), tabela estruturada e gráficos acessíveis (com legenda textual equivalente — WCAG 2.1 AA).
5. Ao acionar **Exportar CSV** ou **Exportar PDF**, `MetricasService.exportar(...)` gera o arquivo agregado, grava `relatorio.exportado` em `AuditoriaService` e devolve o download com `Content-Disposition: attachment`.

### 4.2 Fluxos de exceção

- **FE-01 — Período inválido (`data_inicio > data_fim`):** exibe erro claro no formulário.
- **FE-02 — Período sem movimentações:** exibe zeros e `"—"` na taxa de atendimento (sem divisão por zero).
- **FE-03 — Acesso sem função `metricas_e_parametros` ou sem 2FA:** HTTP 403 / redirect para 2FA.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-22-01** | Os 8 indicadores são calculados a partir dos registros reais de RF020 (entregas), RF018 (não comparecimentos), RF011/RF012 (validade/vencimento), RF005/RF007 (pontos de coleta) e RF021 (denúncias), tendo como métrica principal a **quantidade de medicamentos efetivamente entregues**. | RF022 (Indicadores, regra 3) • `moderacao` |
| **RN-22-02** | Exibição em **tabela e gráfico**, exportáveis em **CSV** e **PDF**. | RF022 (regra 1) • `moderacao` |
| **RN-22-03** | **Apenas dados agregados e anônimos**, nunca dados pessoais ou de saúde (RS002, RNF10), com supressão de subgrupos por bairro + medicamento com `< 3` ocorrências exibindo `"< 3"` (*k-anonimato* — *acréscimo da especificação*). | RF022 (regra 2), RNF10, RS002 • `moderacao` |
| **RN-22-04** | Acesso restrito à função **`metricas_e_parametros`** (+ 2FA); exportações registradas em `AuditoriaService`. | RS015, RNF14, [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `moderacao`, `auditoria` |

---

## 6. Modelo de dados lógico

Esta spec não cria tabelas operacionais novas: lê agregações sobre `Doacao`, `Solicitacao`, `Agendamento`, `EntregaConfirmacao`, `CorrecaoEntrega`, `PontoColeta` e `Denuncia`, aproveitando os índices em datas, status e regiões já definidos nas specs `05` a `21`.

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`moderacao`, restritas a `metricas_e_parametros` + 2FA):** `AdminMetricasView` + `MetricasFiltroForm` (`GET`), `AdminMetricasExportarView` (`GET` com `formato=csv|pdf`).
- **Services (`MetricasService`):** `gerar_relatorio(filtros)`, `gerar_csv(relatorio)` (escapando fórmulas iniciadas por `=`, `+`, `-`, `@`), `gerar_pdf(relatorio)`.
- **Templates:** `templates/moderacao/admin_metricas.html` (tabela acessível + gráfico SVG/local sem CDN — ADRs 0005 e 0006).
- **Rotas:** `moderacao:metricas` (`/admin-remed/metricas/`), `moderacao:metricas_exportar` (`/admin-remed/metricas/exportar/`).

---

## 8. Mensagens e validações

- Período invertido: `"A data inicial não pode ser posterior à data final"`;
- Sem registros no período: `"Nenhum dado encontrado para os filtros informados"`.

---

## 9. Segurança e privacidade

- **RS002 & RNF10 (OWASP A01/A04):** consultas projetam exclusivamente agregações (`COUNT`/`SUM`/`AVG`); sanitização contra *CSV Injection*; zero PII nos gráficos, tabelas ou arquivos.
- **RS015 (OWASP A01/A07/A09):** restrito a `metricas_e_parametros` + 2FA, com auditoria de exportações.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** gráficos acompanhados de tabela/descrição textual acessível (WCAG 2.1 AA).
- **RNF04:** agregações indexadas respondendo em ≤ 3 s.
- **RNF10 & RNF14:** anonimato garantido e trilha de exportação.

---

## 11. Critérios de aceite

1. **CA-22-01 (Cálculo exato dos 8 indicadores — RN-22-01):** Dado um conjunto conhecido de entregas (incluindo entrega parcial e correção), vencidos, não comparecimentos, pontos ativos e denúncias, todos os 8 indicadores e a taxa de atendimento retornam os valores exatos.
2. **CA-22-02 (Exportação CSV/PDF sem PII — RN-22-02, RN-22-03):** Exportações em CSV e PDF baixam arquivos válidos contendo apenas dados agregados (nenhum nome, CPF, e-mail ou endereço) e gravam `relatorio.exportado` na auditoria.
3. **CA-22-03 (Isolamento de permissão — RN-22-04):** Apenas `metricas_e_parametros` (+ 2FA) acessa as rotas; demais funções e `is_superuser` sem função recebem HTTP 403.

---

## 12. Plano de testes

- **Unidade (`MetricasService`):** cálculo dos 8 indicadores com e sem filtros, proteção contra divisão por zero, neutralização de *CSV Injection*, geração de CSV e PDF válidos.
- **Integração (Views/Privacidade):** matriz de acesso (`metricas_e_parametros` + 2FA), checagem negativa garantindo ausência de PII no HTML/CSV/PDF e registro em `RegistroAuditoria`.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Metas numéricas dos indicadores (Questão 2 do PRD):** ainda não definidas pelo cliente/PO. | Pendência externa (Cliente / PO) | Não bloqueia a v1.1; relatório exibe os 8 indicadores reais sem metas fixas até definição. |
