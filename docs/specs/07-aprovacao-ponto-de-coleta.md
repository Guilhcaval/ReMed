# Spec 07 — Aprovação do Ponto de Coleta (RF007)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `07` — Aprovação do Ponto de Coleta (`RF007`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF007 (Importante — **MVP ⬆**, HU07). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF06 (Essencial — cancelamento transacional de agendamentos), RNF07, RNF08, RNF14 (Essencial), RNF15. **Segurança:** RS011, RS015. |
| **Apps envolvidos** | `pontos_coleta` (principal: `AnalisePontoColeta`, `AprovacaoPontoService`), `auditoria` (`AuditoriaService`), `notificacoes` (`NotificacaoService`), `correspondencias` (cancelamento/aviso de agendamentos futuros quando ponto é suspenso/inativado), `nucleo` (`ExecucaoRotina`, mixins de acesso + 2FA). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[05-cadastro-de-ponto-de-coleta.md](05-cadastro-de-ponto-de-coleta.md) (`RF005`)** e **[06-envio-documentos-ponto-de-coleta.md](06-envio-documentos-ponto-de-coleta.md) (`RF006`)**. **Depende de specs ainda não escritas:** **RF018** (agendamento da retirada — efeito da suspensão/inativação sobre agendamentos futuros) e **RF021** (v1.1 — denúncia que pode originar suspensão). **Pendência externa:** Questão 10 do PRD (critérios detalhados de aprovação a confirmar com o cliente). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0014](../adr/0014-rotinas-agendadas.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0016](../adr/0016-armazenamento-seguro-de-arquivos.md). |

---

## 2. Objetivo e escopo

Permitir que o Administrador com função **`aprovacao_pontos_coleta`** (+ 2FA) analise os dados e documentos enviados de pontos de coleta pendentes, aprove, reprove ou marque pendência de documentação, altere a situação de pontos ativos (suspender, inativar ou reativar após nova análise) e realize a revisão periódica dos pontos ativos.

### Inclui

- Fila administrativa de pontos `pendente_aprovacao` (mostrando claramente se os documentos obrigatórios do RF006 já foram enviados) e pesquisa por **status, tipo de estabelecimento, município e CNPJ**.
- Tela de análise consolidando dados do ponto, endereço, horários, responsáveis vinculados, link seguro (URL pré-assinada 60 s com auditoria — RF006) para visualizar os documentos obrigatórios e histórico de análises anteriores.
- Registro de análise com resultado **`aprovado`**, **`reprovado`** ou **`pendente_documentacao`**:
  - `aprovado`: aprova os documentos vigentes, muda `PontoColeta.status` para `ativo` (tornando-o visível em RF008/RF015/RF018) e notifica os responsáveis ativos (RF017);
  - `reprovado` ou `pendente_documentacao`: mantém o ponto oculto (`pendente_aprovacao`), exige motivo obrigatório informado aos responsáveis ativos (RF017) e orienta o reenvio no RF006.
- Alteração de situação de ponto `ativo` para `suspenso` ou `inativo` (com motivo obrigatório) — retirando imediatamente o ponto das listas públicas e tratando agendamentos futuros (RF018) com aviso às partes (RF017) — e reativação após nova análise/conferência de documentos válidos.
- Suporte à **revisão periódica dos pontos ativos** (RS011, RF007 regra 4): registro de `ultima_revisao_em` no ponto e filtro/fila para pontos ativos com revisão vencida.
- Registro imutável de toda análise e mudança de situação em `AnalisePontoColeta` (`on_delete=PROTECT`) e `RegistroAuditoria` (`AuditoriaService` — RNF14).

### Não inclui

- Alteração de CNPJ (já coberta na Spec `05` — RF005) ou envio de documentos pelo representante (Spec `06` — RF006).
- Fluxo de denúncia que origina suspensão (v1.1 — RF021).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Administrador (`aprovacao_pontos_coleta`)** | Listar/pesquisar pontos, consultar documentos, aprovar/reprovar/marcar pendência de documentação, suspender/inativar/reativar pontos e registrar revisão periódica. | Conta ativa, e-mail confirmado, função explícita `aprovacao_pontos_coleta` e sessão com 2FA TOTP concluído ([ADRs 0009 e 0010](../adr/0010-perfis-e-permissoes.md)). Para aprovar cadastro inicial, o ponto deve estar `pendente_aprovacao` com os 2 documentos obrigatórios enviados e dentro da validade (RF006). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Análise e aprovação/reprovação de cadastro pendente

1. O Administrador (`aprovacao_pontos_coleta` + 2FA) acessa `pontos_coleta:admin_lista`, filtra por `status = pendente_aprovacao` e abre `pontos_coleta:admin_detalhe`.
2. Consulta os dados cadastrais, endereço, horários e abre a licença de funcionamento e o alvará sanitário via `pontos_coleta:documento_acessar` (registrando `arquivo.acessado` na auditoria — RF006).
3. Seleciona o **Resultado** (`aprovado`, `reprovado` ou `pendente_documentacao`), informa o **Motivo** (obrigatório em reprovação/pendência e, como *acréscimo da especificação* alinhado à Spec 04, em todas as decisões administrativas; na aprovação pode ser observação curta) e envia via `POST` com CSRF.
4. Dentro de `transaction.atomic()` com `select_for_update()` no `PontoColeta`:
   - Se `aprovado`: verifica que licença e alvará vigentes existem e têm `data_validade >= hoje`, marca esses documentos como `aprovado`, atualiza `PontoColeta.status = ativo` e `ultima_revisao_em = agora`, grava `AnalisePontoColeta`, registra `ponto_coleta.aprovado` em `AuditoriaService` e notifica os responsáveis ativos (`ponto_analisado`, RF017);
   - Se `reprovado` ou `pendente_documentacao`: exige motivo (`"Informe o motivo da reprovação ou da suspensão"`), marca os documentos pendentes indicados como `reprovado` (quando aplicável), mantém o ponto em `pendente_aprovacao` (oculto), grava `AnalisePontoColeta`, registra `ponto_coleta.reprovado` / `ponto_coleta.pendente_documentacao` em `AuditoriaService` e notifica os responsáveis ativos com o motivo e orientação para reenvio (RF006, RF017).
5. Redireciona (PRG) exibindo `"Situação do ponto de coleta atualizada com sucesso"`.

### 4.2 Fluxos alternativos

- **FA-01 — Suspensão ou inativação de ponto `ativo` (`pontos_coleta:admin_situacao`):** dentro de `transaction.atomic()` com `select_for_update()` (seguindo a ordem da ADR 0013 para agendamentos afetados), exige motivo (`"Informe o motivo da reprovação ou da suspensão"`), altera `status` para `suspenso` ou `inativo`, **cancela automaticamente os agendamentos futuros mantendo a correspondência aceita/reservada** para que doador e solicitante reagendem em outro local no RF018 — **reiniciando o prazo de expiração da reserva da ADR 0013 (`RESERVA_EXPIRACAO_HORAS`, 48 h) a partir do momento do cancelamento automático do agendamento** para que as partes não sejam penalizadas por um evento externo do ponto —, notifica ambas as partes e os responsáveis ativos do ponto (RF017) e registra `AnalisePontoColeta` + `RegistroAuditoria`.
- **FA-02 — Reativação de ponto `suspenso` ou `inativo`:** exige nova conferência de que licença e alvará estão `aprovado` e com `data_validade >= hoje` (caso vencidos, exige envio de nova versão no RF006 antes de reativar), motivo obrigatório, grava `AnalisePontoColeta` + `RegistroAuditoria` e notifica os responsáveis.
- **FA-03 — Revisão periódica de ponto `ativo` (`pontos_coleta:admin_revisar`):** Administrador confere validade dos documentos e regularidade do estabelecimento, registra confirmação de revisão (atualizando `ultima_revisao_em`, gravando `AnalisePontoColeta` + `RegistroAuditoria`) ou aciona FA-01 se detectar irregularidade.

### 4.3 Fluxos de exceção

- **FE-01 — Tentativa de aprovar ponto sem os 2 documentos obrigatórios ou com documento vencido:** `AprovacaoPontoService` recusa a aprovação orientando o representante a regularizar no RF006.
- **FE-02 — Motivo vazio em reprovação, pendência ou suspensão/inativação:** bloqueia exibindo `"Informe o motivo da reprovação ou da suspensão"`.
- **FE-03 — Acesso por perfil sem `aprovacao_pontos_coleta` ou sem 2FA concluído:** negado (HTTP 403 ou redirect para 2FA).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-07-01** | Resultados da análise inicial: `aprovado` (passa o ponto a `ativo`, visível em RF008 e RF018), `reprovado` ou `pendente_documentacao` (mantém o ponto em `pendente_aprovacao` — preservando os 4 status exatos do RF005 — exibindo o resultado da última `AnalisePontoColeta` e orientando reenvio no RF006). Só é possível aprovar se os documentos obrigatórios do RF006 estiverem enviados e com `data_validade >= hoje`. | RF007 (regra 1, Pré-condição), RS011 • `pontos_coleta` |
| **RN-07-02** | O motivo é obrigatório em reprovação, pendência e suspensão/inativação (`"Informe o motivo da reprovação ou da suspensão"`) e é informado ao representante (RF017). Os critérios detalhados de conferência (CNPJ ativo/compatível, documentos legíveis e válidos, endereço conferido) aparecem como **checklist orientativo não bloqueante** na tela (pendente de detalhamento formal do cliente — Questão 10 do PRD). | RF007 (regra 2, Mensagens), RS015 (solução 4) • `pontos_coleta`, `notificacoes` |
| **RN-07-03** | Um ponto `ativo` pode ser `suspenso` ou `inativo` pelo Administrador (e reativado apenas após nova análise/conferência de documentos válidos). Ponto suspenso ou inativo deixa de ser exibido; agendamentos futuros nele são **cancelados automaticamente mantendo a correspondência aceita/reservada** para reagendamento em outro local (RF018), **reiniciando o prazo de expiração da reserva (`RESERVA_EXPIRACAO_HORAS`, 48 h — [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)) a partir do cancelamento automático**, tudo dentro da mesma transação e com aviso às duas partes (RF017). | RF007 (regra 3), RS011, [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md) • `pontos_coleta`, `correspondencias`, `notificacoes` |
| **RN-07-04** | Deve haver **revisão periódica dos pontos ativos**, combinando a verificação diária automática de vencimento de documentos (RF006) com a revisão periódica administrativa registrada em `ultima_revisao_em`, com periodicidade padrão configurável de **180 dias** (`PONTO_REVISAO_PERIODICA_DIAS = 180` em `settings` — *acréscimo da especificação*). | RF007 (regra 4), RS011 • `pontos_coleta` |
| **RN-07-05** | Toda análise, mudança de situação e revisão gera registro imutável (quem analisou, resultado/status, motivo, data e hora) que não pode ser apagado (`on_delete=PROTECT` + `RegistroAuditoria`). | RF007 (regra 5), RNF14, [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `pontos_coleta`, `auditoria` |

---

## 6. Modelo de dados lógico

#### `AnalisePontoColeta` (app `pontos_coleta` — `append-only` / `on_delete=PROTECT`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `ponto_coleta` | FK (`PontoColeta`, `PROTECT`, indexado) | Sim | |
| `tipo_acao` | TextChoices | Sim | `analise_cadastro`, `alteracao_situacao`, `revisao_periodica`. |
| `resultado` | TextChoices (anulável) | Não | `aprovado`, `reprovado`, `pendente_documentacao` (em `analise_cadastro`). |
| `status_anterior` / `status_novo` | TextChoices | Sim | Valores de `PontoColeta.status`. |
| `motivo` | Text | Condicional | Obrigatório em `reprovado`, `pendente_documentacao`, `suspenso`, `inativo` (`CheckConstraint` no PostgreSQL). |
| `responsavel` | FK (`Usuario`, `PROTECT`) | Sim | Administrador (`aprovacao_pontos_coleta`). |
| `criado_em` | Datetime (indexado) | Sim | Data e hora UTC da análise. |

*(Adiciona em `PontoColeta` o campo `ultima_revisao_em` — Datetime anulável, indexado — atualizado na aprovação e em cada revisão periódica.)*

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`pontos_coleta`, todos restritos a `aprovacao_pontos_coleta` + 2FA):** `AdminPontoColetaDetalheView` (`GET`), `AdminPontoColetaAnalisarView` + `AdminAnalisePontoForm` (`POST`), `AdminPontoColetaSituacaoView` + `AdminSituacaoPontoForm` (`POST`), `AdminPontoColetaRevisarView` (`POST`).
- **Services (`AprovacaoPontoService`):** `analisar_cadastro(...)`, `alterar_situacao(...)`, `registrar_revisao_periodica(...)`, `listar_pendentes_revisao(...)` — todos transacionais com `select_for_update()`, `AuditoriaService` e `NotificacaoService`.
- **Templates:** `templates/pontos_coleta/admin_ponto_detalhe.html` (dados do ponto, checklist de critérios do RF007 regra 2, links de visualização dos documentos com auditoria, formulários de análise/situação/revisão e histórico de `AnalisePontoColeta`).
- **Rotas:** `pontos_coleta:admin_detalhe` (`/admin-remed/pontos-coleta/<int:ponto_id>/`), `pontos_coleta:admin_analisar`, `pontos_coleta:admin_situacao`, `pontos_coleta:admin_revisar`.

---

## 8. Mensagens e validações

Textos literais exigidos pela fonte (RF007):

| Condição | Mensagem literal |
| --- | --- |
| Reprovação, pendência ou suspensão sem motivo informado | `"Informe o motivo da reprovação ou da suspensão"` |
| Análise ou mudança de situação concluída com sucesso | `"Situação do ponto de coleta atualizada com sucesso"` |

---

## 9. Segurança e privacidade

- **RS011 (OWASP A06/A09):** exibição pública somente após aprovação com documentos obrigatórios válidos; revisão periódica; suspensão imediata com tratamento de agendamentos futuros.
- **RS015 (OWASP A01/A07/A09):** acesso isolado à função `aprovacao_pontos_coleta` + 2FA (sem acesso a receitas médicas — RF014), motivo obrigatório e registro imutável.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** interface administrativa clara com checklist de critérios, mensagens literais e WCAG 2.1 AA.
- **RNF04 & RNF06:** pesquisa paginada em ≤ 3 s; suspensão com cancelamento de agendamentos futuros em transação atômica.
- **RNF14:** `AnalisePontoColeta` e `RegistroAuditoria` imutáveis (`on_delete=PROTECT`).

---

## 11. Critérios de aceite

1. **CA-07-01 (Aprovação com documentos válidos — RN-07-01):** Dado um ponto `pendente_aprovacao` com licença e alvará enviados e válidos, quando `aprovacao_pontos_coleta` (+ 2FA) aprova, então os documentos e o ponto passam a `ativo`, o ponto aparece nas buscas públicas, os responsáveis recebem notificação `ponto_analisado`, `AnalisePontoColeta` e `RegistroAuditoria` gravam a ação e `"Situação do ponto de coleta atualizada com sucesso"` é exibido.
2. **CA-07-02 (Bloqueio sem documentos ou sem motivo — RN-07-01, RN-07-02):** Dado um ponto sem os 2 documentos obrigatórios (ou com documento vencido), a aprovação é bloqueada; dada reprovação/pendência/suspensão sem motivo, o sistema exibe `"Informe o motivo da reprovação ou da suspensão"`.
3. **CA-07-03 (Suspensão/inativação com efeito em agendamentos futuros — RN-07-03):** Dado um ponto `ativo` com agendamentos futuros confirmados, quando `aprovacao_pontos_coleta` suspende ou inativa com motivo, então o ponto sai imediatamente da busca pública, os agendamentos futuros são tratados transacionalmente com aviso às partes e os responsáveis do ponto são notificados.
4. **CA-07-04 (Reativação exigindo documentos válidos — RN-07-03):** Dado um ponto `suspenso` com alvará vencido, quando o Administrador tenta reativar sem nova versão válida do alvará, então a reativação é bloqueada.
5. **CA-07-05 (Isolamento de permissão — ADR 0010):** Qualquer usuário sem `aprovacao_pontos_coleta` (inclusive `gestao_usuarios`, `verificacao_receitas`, `is_superuser` sem função explícita ou Admin sem 2FA) recebe HTTP 403 / redirect para 2FA.

---

## 12. Plano de testes

- **Unidade (`AprovacaoPontoService`):** aprovação exigindo ambos os documentos válidos; reprovação e pendência exigindo motivo e mantendo ponto oculto; suspensão/inativação tratando agendamentos futuros e notificando partes; reativação bloqueada com documento vencido; revisão periódica atualizando `ultima_revisao_em`; imutabilidade e auditoria.
- **Integração (Views/Permissões):** matriz de acesso nas 4 rotas (403 para demais funções e `is_superuser` sem `aprovacao_pontos_coleta`, redirect para 2FA sem verificação, mensagens literais e PRG).

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Critérios detalhados de aprovação de pontos de coleta (Questão 10 do PRD):** detalhamento formal pendente de validação com o cliente. | Pendência externa (Cliente) | Não bloqueia o MVP; a tela exibe checklist orientativo não bloqueante (CNPJ ativo/compatível, documentos legíveis/válidos, endereço conferido) além das validações técnicas obrigatórias. |
