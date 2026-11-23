# Spec 18 — Confirmação de Retirada e Entrega (RF020)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `18` — Confirmação de Retirada e Entrega (`RF020`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF020 (Essencial — MVP, HU20). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF06 (Essencial — entrega transacional), RNF07, RNF13 (Essencial — aviso médico/farmacêutico na retirada), RNF14 (Essencial — registro imutável). **Segurança:** RS001, RS003, RS004, RS006, RS007, RS008. |
| **Apps envolvidos** | `correspondencias` (principal: `EntregaConfirmacao`, `CorrecaoEntrega`, `EntregaService`), `medicamentos` (`Doacao`, atualização de `quantidade_disponivel` e retorno do saldo a `disponivel` ou `entregue`/`reprovado`), `solicitacoes` (`Solicitacao` → `atendida` ou `aberta`), `notificacoes` (`NotificacaoService`), `auditoria` (`AuditoriaService`). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008` — foto da embalagem para conferência)**, **[09-medicamentos-refrigerados.md](09-medicamentos-refrigerados.md) (`RF010` — recusa por quebra de cadeia de frio muda doação automaticamente para `reprovado`)**, **[11-rotina-automatica-de-vencimento.md](11-rotina-automatica-de-vencimento.md) (`RF012`)**, **[13-fluxo-medicamentos-sujeitos-a-receita.md](13-fluxo-medicamentos-sujeitos-a-receita.md) (`RF014` — conferência de `pessoa_retirada`)**, **[15-correspondencia-oferta-e-necessidade.md](15-correspondencia-oferta-e-necessidade.md) (`RF016` — rascunho)**, **[16-agendamento-da-retirada.md](16-agendamento-da-retirada.md) (`RF018` — rascunho)** e **[17-mensagens-na-plataforma.md](17-mensagens-na-plataforma.md) (`RF019` — rascunho)**. **Depende de specs futuras (v1.1):** **RF021** (Denúncia e Moderação — PRD Questão 16) e **RF022** (Relatório de Métricas de Entregas, que usa os registros desta spec como métrica principal). **Pendência externa:** nenhuma bloqueante para o MVP (Questão 21 do PRD fechada por motivo sanitário × não sanitário nesta spec). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0016](../adr/0016-armazenamento-seguro-de-arquivos.md). |

---

## 2. Objetivo e escopo

Registrar de forma segura, transacional e imutável a efetiva entrega do medicamento (total ou parcial) validada pelo **código de confirmação** enviado apenas ao solicitante, garantindo conferência presencial de validade, lote, integridade da embalagem (comparada à foto do RF008), conservação refrigerada (RF010) e identidade de quem retira (RF014), oferecendo direito de recusa e produzindo a base confiável para a principal métrica da plataforma (RF022).

### Inclui

- **Código de confirmação de retirada** (gerado ao confirmar o agendamento no RF018 — 6 caracteres alfanuméricos sem ambiguidade, guardado em hash com limite de tentativas — *acréscimo da especificação*, OWASP A07 — e exibido **somente ao solicitante**), validado no ato da entrega (RS008).
- Tela de conferência presencial exibindo ao solicitante os dados do medicamento, link temporário autenticado (60 s com auditoria — RF008) para a(s) foto(s) da embalagem, `pessoa_retirada` (RF014), item de conferência térmica para refrigerados (RF010) e o **aviso obrigatório RNF13** (*"O ReMed não substitui avaliação médica ou farmacêutica"*).
- **Confirmação de entrega (total ou parcial):**
  - Valida `1 <= quantidade_entregue <= doacao.quantidade_disponivel` e conferência de validade/embalagem marcada;
  - Atualiza `doacao.quantidade_disponivel -= quantidade_entregue`: se zerar, `Doacao.status = entregue`; se restar saldo (`> 0`), **saldo volta automaticamente para `Doacao.status = disponivel`** ([ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)), desde que ainda dentro da validade do RF012 (caso contrário, `vencido`);
  - Atualiza `Agendamento.status = retirado`, `Solicitacao.status = atendida`, encerra a conversa do RF019 em somente leitura, grava `EntregaConfirmacao` (`append-only`) + `RegistroAuditoria` e notifica ambas as partes (RF017).
- **Recusa presencial na retirada pelo solicitante:** informando o motivo estruturado; motivos sanitários (**validade divergente**, **embalagem violada/adulterada** ou **quebra de cadeia de frio** em refrigerados — Spec `09`) mudam a doação automaticamente para **`reprovado`** (RS001/RS004); motivo não sanitário (**desistência/outro**) devolve a doação para **`disponivel`** (se dentro da validade do RF012).
- **Imutabilidade e correções (RF020 regra 6):** `EntregaConfirmacao` nunca pode ser apagada nem editada (`on_delete=PROTECT` + ausência de mutação); eventuais correções registradas por Administrador autorizado geram um **novo registro `CorrecaoEntrega`** vinculado, com autor, motivo, data e hora (`AuditoriaService`).
- Campo opcional de comentário de avaliação da retirada (salvo em `EntregaConfirmacao`, sem ranking público no MVP) e placeholder `"Denunciar problema (disponível na v1.1)"` + orientação de contato (fluxo real no RF021).

### Não inclui

- Fluxo completo de denúncia/moderação (v1.1 — RF021) e painel de métricas/exportação CSV/PDF (v1.1 — RF022).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Doador** | Registrar a confirmação de entrega digitando o código informado presencialmente pelo solicitante e a quantidade entregue. | Agendamento `confirmado` (RF018) onde é o doador. |
| **Solicitante / Cuidador/Familiar** | Conferir presencialmente validade, lote, integridade (comparando com a foto do RF008), conservação (RF010) e `pessoa_retirada` (RF014); fornecer o código de confirmação ao doador ou registrar **recusa** com motivo; registrar avaliação opcional. | Agendamento `confirmado` (RF018) onde é o solicitante. |
| **Administrador (correção formal — RF020 regra 6)** | Registrar nova `CorrecaoEntrega` (sem apagar nem alterar a entrega original) com motivo obrigatório e auditoria. | Conta administrativa ativa com `conferencia_doacoes` (+ 2FA). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Conferência presencial e confirmação da entrega

1. No encontro agendado (`Agendamento.status == confirmado`), o **Solicitante / Cuidador/Familiar** abre `correspondencias:retirada_conferir` (onde visualiza o aviso RNF13, a foto da embalagem via URL pré-assinada 60 s, validade, lote, `pessoa_retirada` e o seu **código de confirmação**).
2. Confere presencialmente o medicamento físico contra os dados e a foto cadastrada (e a conservação, se `refrigerado` — RF010). Estando tudo conforme, informa o **código de confirmação** ao Doador.
3. O **Doador** acessa `correspondencias:entrega_confirmar`, informa o **Código de confirmação**, a **Quantidade entregue** (`1` até `doacao.quantidade_disponivel`), confirma a conferência de validade/embalagem (e identidade de `pessoa_retirada` se sujeito a receita — RF014) e envia via `POST` com CSRF.
4. Dentro de `transaction.atomic()` com `select_for_update()` na ordem fixa **`Doacao -> Solicitacao -> Correspondencia -> Agendamento`** ([ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)):
   - Confere `Agendamento.status == confirmado` e valida o hash do código de confirmação (incrementando contador de falhas em caso de erro; bloqueando após 5 erros consecutivos para impedir força bruta — *acréscimo da especificação*, OWASP A07);
   - Valida `1 <= quantidade_entregue <= doacao.quantidade_disponivel`;
   - Atualiza `doacao.quantidade_disponivel -= quantidade_entregue`; se `== 0`, muda `Doacao.status = entregue`; se `> 0`, confere validade (RF012) e muda `Doacao.status = disponivel` (ou `vencido` se já abaixo da validade mínima);
   - Atualiza `Agendamento.status = retirado`, `Solicitacao.status = atendida` e encerra a conversa (RF019) em somente leitura;
   - Cria `EntregaConfirmacao` (`tipo = entregue`, imutável) e registra `entrega.confirmada` via `AuditoriaService`;
   - Notifica doador e solicitante (`entrega_confirmada`, RF017).
5. Redireciona (PRG) exibindo confirmação + campo opcional de comentário de avaliação.

### 4.2 Fluxos alternativos

- **FA-01 — Recusa presencial pelo solicitante (`correspondencias:retirada_recusar`):** antes de fornecer o código, se houver divergência de validade, embalagem violada, suspeita de quebra de cadeia de frio (RF010) ou desistência, o solicitante aciona `"Recusar medicamento"` (`POST` com CSRF) informando o motivo estruturado e detalhe obrigatório. Sob `transaction.atomic()` + `select_for_update()`:
  - Motivos sanitários (`validade_divergente`, `embalagem_violada`, `quebra_cadeia_frio`) → `Doacao.status = reprovado` (RS001/RS004);
  - Motivo não sanitário (`desistencia_outro`) → `Doacao.status = disponivel` (se dentro da validade do RF012; senão `vencido`);
  - Muda `Agendamento.status = cancelado`, `Correspondencia.status = recusada`, devolve `Solicitacao.status = aberta` (se não vencida), encerra conversa (RF019), grava `EntregaConfirmacao` (`tipo = recusada`, com motivo) + `RegistroAuditoria` e notifica ambas as partes (RF017).
- **FA-02 — Correção administrativa de entrega (RF020 regra 6):** Administrador com `conferencia_doacoes` (+ 2FA) registra `CorrecaoEntrega` vinculada à `EntregaConfirmacao` original (nunca alterando ou excluindo o registro original), com motivo obrigatório e auditoria.

### 4.3 Fluxos de exceção

- **FE-01 — Código de confirmação incorreto:** bloqueia a confirmação; após 5 erros consecutivos no mesmo agendamento, bloqueia novas tentativas orientando conferência/suporte (*acréscimo da especificação*).
- **FE-02 — Quantidade entregue maior que `quantidade_disponivel` ou ≤ 0:** rejeitada pelo form e `CheckConstraint`.
- **FE-03 — Tentativa de confirmar entrega em agendamento não `confirmado` (ex.: `cancelado`, `nao_compareceu` ou já `retirado`):** recusada transacionalmente sem duplicar registro.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-18-01** | O **código de confirmação** é gerado ao confirmar o agendamento (RF018), enviado/exibido **somente ao solicitante** e exigido no ato da retirada para validar a entrega. | RF020 (regra 1), RS008 • `correspondencias` |
| **RN-18-02** | Na retirada, o solicitante confere validade, lote, integridade da embalagem (comparada à foto do RF008), conservação (se `refrigerado` — RF010) e identidade de `pessoa_retirada` (se sujeito a receita — RF014), podendo **recusar** informando o motivo. Motivos sanitários (`validade_divergente`, `embalagem_violada`, `quebra_cadeia_frio`) mudam a doação automaticamente para **`reprovado`**; motivo não sanitário (`desistencia_outro`) devolve para **`disponivel`** (se dentro da validade do RF012). | RF020 (regra 2), RF010, RF014, RS001, RS003, RS004 • `correspondencias`, `medicamentos` |
| **RN-18-03** | A entrega pode ser **parcial** (`1 <= quantidade_entregue <= quantidade_disponivel`). O saldo `quantidade_disponivel` é atualizado transacionalmente; ao zerar, `Doacao.status = entregue`; havendo saldo > 0, **o saldo volta a `disponivel`** (conferindo RF012 — [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)). | RF020 (regra 4), RNF06, RS007, [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md) • `correspondencias`, `medicamentos` |
| **RN-18-04** | A confirmação muda `Solicitacao.status = atendida` e `Agendamento.status = retirado`, encerra a conversa (RF019) e serve de fonte para os indicadores do RF022 (v1.1). | RF020 (regra 5), RF019, RF022 • `correspondencias`, `solicitacoes` |
| **RN-18-05** | O registro da entrega **nunca pode ser apagado nem editado** (`on_delete=PROTECT`). Correções geram um **novo registro vinculado** (`CorrecaoEntrega`) com quem fez, motivo, data e hora (RNF14). | RF020 (regra 6), RNF14, [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `correspondencias`, `auditoria` |
| **RN-18-06** | Aviso obrigatório visível na tela de retirada: **a plataforma não substitui avaliação médica ou farmacêutica** (RNF13). | RNF13 • `correspondencias` |

---

## 6. Modelo de dados lógico

#### `EntregaConfirmacao` (app `correspondencias` — `append-only`, `on_delete=PROTECT`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `agendamento` | OneToOne (`Agendamento`, `PROTECT`) | Sim | Um desfecho de entrega/recusa por agendamento. |
| `tipo_desfecho` | TextChoices | Sim | `entregue`, `recusada`. |
| `quantidade_entregue` | PositiveInteger | Sim | `>= 1` se `entregue`; `0` se `recusada` (`CheckConstraint`). |
| `conferencia_validade_embalagem` | Boolean | Sim | Obrigatório `True` se `entregue` (`CheckConstraint`). |
| `motivo_recusa_categoria` / `motivo_recusa_detalhe` | TextChoices / Text | Condicional | Obrigatórios se `recusada` (`validade_divergente`, `embalagem_violada`, `quebra_cadeia_frio`, `desistencia_outro`). |
| `avaliacao_comentario` | String (500) | Não | Opcional (RF020 regra 3 — salvo sem ranking público no MVP). |
| `registrado_por` | FK (`Usuario`, `PROTECT`) | Sim | Doador (na entrega) ou Solicitante (na recusa). |
| `entregue_em` | Datetime (indexado) | Sim | Data e hora UTC da entrega/recusa. |

#### `CorrecaoEntrega` (app `correspondencias` — `append-only`, `on_delete=PROTECT`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `entrega` | FK (`EntregaConfirmacao`, `PROTECT`, indexado) | Sim | |
| `motivo` | Text | Sim | Justificativa obrigatória da correção. |
| `quantidade_corrigida` | PositiveInteger, anulável | Não | Opcional quando a correção ajusta quantidade registrada. |
| `responsavel` | FK (`Usuario`, `PROTECT`) | Sim | Administrador (`conferencia_doacoes` + 2FA). |
| `criado_em` | Datetime | Sim | |

*(No model `Agendamento` da Spec `16`, guardam-se `codigo_confirmacao_hash` e `codigo_tentativas_falhas` para validação segura sem armazenar o código em texto claro no banco — ou exibição cifrada/gerada ao solicitante na confirmação.)*

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`correspondencias`):** `RetiradaConferirView` (`GET` — solicitante), `EntregaConfirmarView` + `EntregaConfirmarForm` (`GET`/`POST` — doador), `RetiradaRecusarView` + `RetiradaRecusarForm` (`POST` — solicitante), `EntregaAvaliarView` (`POST`, opcional), `AdminEntregaCorrigirView` + `CorrecaoEntregaForm` (`POST` — `conferencia_doacoes` + 2FA).
- **Services (`EntregaService`):** `confirmar_entrega`, `recusar_retirada`, `registrar_avaliacao`, `registrar_correcao` — todos transacionais com `select_for_update()` na ordem fixa da ADR 0013 e `AuditoriaService`.
- **Templates:** `retirada_conferir.html` (aviso RNF13, foto 60 s, código de retirada só para o solicitante, botão `"Recusar medicamento"`), `entrega_confirmar.html` (aviso RNF13, campo do código e quantidade entregue).
- **Rotas:** `correspondencias:retirada_conferir`, `correspondencias:entrega_confirmar`, `correspondencias:retirada_recusar`, `correspondencias:admin_entrega_corrigir`.

---

## 8. Mensagens e validações

- Código inválido: `"Código de confirmação inválido. Confira o código com quem está retirando o medicamento"`;
- Sucesso na entrega total: `"Entrega confirmada com sucesso!"`;
- Sucesso na entrega parcial: `"Entrega parcial confirmada! O saldo restante voltou a ficar disponível para doação"`;
- Aviso obrigatório RNF13: `"O ReMed não substitui avaliação médica ou farmacêutica"`.

---

## 9. Segurança e privacidade

- **RS008 (OWASP A06/A07):** código de confirmação exclusivo do solicitante + limite de 5 tentativas inválidas impede que o doador confirme uma entrega fictícia sozinho.
- **RS001, RS003, RS004:** conferência presencial com a foto do RF008, checagem de `pessoa_retirada` (RF014) e direito de recusa com proteção sanitária (refrigerado → `reprovado`).
- **RNF14:** `EntregaConfirmacao` e `CorrecaoEntrega` imutáveis (`on_delete=PROTECT` + `AuditoriaService`).

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03 & RNF07:** fluxo rápido e claro em celular (3G/4G) no momento presencial da retirada, WCAG 2.1 AA.
- **RNF06, RNF13, RNF14:** transacionalidade, aviso médico/farmacêutico e histórico imutável.

---

## 11. Critérios de aceite

1. **CA-18-01 (Entrega total com código válido — RN-18-01, RN-18-03, RN-18-04):** Com código correto e `quantidade_entregue == quantidade_disponivel`, `Doacao` muda para `entregue` (`quantidade_disponivel = 0`), `Agendamento -> retirado`, `Solicitacao -> atendida`, conversa RF019 é encerrada e `EntregaConfirmacao` + auditoria são gravados.
2. **CA-18-02 (Entrega parcial retorna saldo a `disponivel` — RN-18-03, ADR 0013):** Com `quantidade_disponivel = 20` e `quantidade_entregue = 10`, `quantidade_disponivel` vira `10`, `Doacao.status` retorna para `disponivel` (se ainda válida no RF012), `Solicitacao -> atendida` e `Agendamento -> retirado`.
3. **CA-18-03 (Código incorreto e limite de tentativas — RN-18-01):** Código inválido não altera nenhum status; 5 erros bloqueiam novas tentativas.
4. **CA-18-04 (Recusa presencial e imutabilidade — RN-18-02, RN-18-05):** Recusa de refrigerado por quebra de cadeia de frio muda `Doacao -> reprovado`; `EntregaConfirmacao` não pode ser excluída (`on_delete=PROTECT`) e correções criam nova `CorrecaoEntrega` preservando a original.

---

## 12. Plano de testes

- **Unidade (`EntregaService`, constraints):** entrega total e parcial (inclusive parcial cuja doação venceu no mesmo dia → `vencido`); validação do hash do código e bloqueio após 5 erros; recusa de refrigerado (`reprovado`) vs demais motivos; `CorrecaoEntrega` preservando `EntregaConfirmacao` intacta; `on_delete=PROTECT`.
- **Integração (Views/Permissões):** código visível apenas ao solicitante (nunca ao doador na view); somente doador confirma entrega e somente solicitante recusa; 404 para terceiros; aviso RNF13 visível em ambas as telas.

---

## 13. Questões em aberto

Nenhuma questão em aberto bloqueante para o MVP. Denúncias estruturadas entram na Spec `21` (`RF021` — v1.1) e o relatório de entregas entra na Spec `22` (`RF022` — v1.1).
