# Spec 10 — Conferência e Aprovação de Validade (RF011)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `10` — Conferência e Aprovação de Validade (`RF011`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF011 (Essencial — MVP, HU11). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF13 (Essencial), RNF14 (Essencial), RNF16. **Segurança:** RS001, RS003, RS013, RS015. |
| **Apps envolvidos** | `medicamentos` (principal: `ConferenciaDoacao`, `ConferenciaDoacaoService`), `nucleo` (`ArquivoService` — URL pré-assinada 60 s das fotos da embalagem, mixins de acesso + 2FA), `auditoria` (`AuditoriaService`), `notificacoes` (`NotificacaoService`), `correspondencias` (gatilho de cruzamento automático ao disponibilizar — RF016). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[06-envio-documentos-ponto-de-coleta.md](06-envio-documentos-ponto-de-coleta.md) (`RF006` — `ArquivoService`)**, **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008`)** e **[09-medicamentos-refrigerados.md](09-medicamentos-refrigerados.md) (`RF010`)**. **Depende de specs em rascunho ou ainda não escritas:** **[11-rotina-automatica-de-vencimento.md](11-rotina-automatica-de-vencimento.md) (`RF012` — parâmetro de validade mínima restante)**, **RF016** (cruzamento de correspondência ao aprovar), **RF020** (direito de recusa na retirada se validade divergir), **RF009** (v2.0 — sugestões da IA) e **RF022** (v1.1 — métricas). **Pendência com o professor:** Questão 4 do PRD (critérios detalhados de conferência e validade mínima restante — prazo vencido em 03/11/2026). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0016](../adr/0016-armazenamento-seguro-de-arquivos.md). |

---

## 2. Objetivo e escopo

Permitir que o Administrador com função **`conferencia_doacoes`** (+ 2FA) confira a validade, a integridade aparente da embalagem (pelas fotos enviadas no RF008), a coerência dos dados cadastrados e a ausência de medicamento de controle especial (RS003), decidindo pela **aprovação** (liberando a doação para `disponivel`) ou **reprovação** (com motivo obrigatório informado ao doador).

### Inclui

- Fila administrativa de doações com `status = em_analise` (ordenada das mais antigas ou com validade mais próxima primeiro — *acréscimo da especificação*), filtrável por medicamento, conservação (`refrigerado`/ambiente), sujeito a receita e período.
- Tela de conferência exibindo todos os dados da doação (RF008), dados de refrigeração se aplicável (RF010), aviso médico/farmacêutico (RNF13), fotos da embalagem via link temporário autenticado de 60 s (`ArquivoService` + auditoria de leitura — ADR 0016) e histórico de conferências anteriores (caso a doação tenha retornado a `em_analise` após edição).
- Registro de conferência (`ConferenciaDoacao`, `append-only`) com resultado **`aprovada`** ou **`reprovada`**:
  - `aprovada`: valida validade restante contra o parâmetro do RF012 (**30 dias provisórios**, *pendência com o professor*), altera `Doacao.status` para `disponivel`, notifica o doador (`doacao_conferida` — RF017) e dispara o cruzamento de correspondência (RF016, quando implementado);
  - `reprovada`: exige motivo obrigatório, altera `Doacao.status` para `reprovado` e notifica o doador com o motivo (RF017).
- Registro imutável de toda conferência em `ConferenciaDoacao` (`on_delete=PROTECT`) e `RegistroAuditoria` (`AuditoriaService`).

### Não inclui

- Retirada automática de doações vencidas (Spec `11` — RF012).
- Sugestão de leitura automática da embalagem por IA (v2.0 — RF009).
- Conferência de receitas médicas (Spec `13` — RF014, função separada `verificacao_receitas`).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Administrador (`conferencia_doacoes`)** | Consultar a fila de doações `em_analise`, visualizar fotos da embalagem, aprovar ou reprovar com motivo obrigatório e consultar histórico de conferências. | Conta ativa, e-mail confirmado, função explícita `conferencia_doacoes` ([ADR 0010](../adr/0010-perfis-e-permissoes.md) — resolve a Questão 19 do PRD sobre *"responsável pela conferência"*) e sessão com 2FA TOTP concluído ([ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md)). A doação deve estar em `status = em_analise`. |

---

## 4. Fluxos

### 4.1 Fluxo principal — Conferência e aprovação/reprovação de doação

1. O Administrador (`conferencia_doacoes` + 2FA) acessa `medicamentos:admin_conferencia_lista` e abre uma doação `em_analise` em `medicamentos:admin_conferencia_detalhe`.
2. Confere os dados declarados (nome, princípio ativo, dosagem, forma, quantidade, fabricante, lote, validade, condição de conservação/refrigeração, sujeito a receita), abre a(s) foto(s) da embalagem via `medicamentos:doacao_foto_acessar` (URL pré-assinada 60 s + registro `arquivo.acessado` na auditoria) e verifica a ausência de indício de medicamento de controle especial (RS003).
3. Seleciona **Resultado** (`aprovada` ou `reprovada`), informa o **Motivo** (obrigatório apenas quando `reprovada`, com lista orientativa de motivos comuns + detalhe livre como *acréscimo da especificação*; opcional na aprovação) e aciona **Registrar conferência** (`POST` com CSRF).
4. Dentro de `transaction.atomic()` com `select_for_update()` em `Doacao`:
   - Reconfere que `doacao.status == em_analise`;
   - Se `aprovada`: valida se `doacao.data_validade >= hoje + validade_minima_restante_dias` (parâmetro do RF012); se vencida ou abaixo do mínimo, bloqueia a aprovação e disponibiliza transição direta para **`vencido`** (com orientação de descarte sanitário conforme RF012); se válida, atualiza `doacao.status = disponivel`, grava `ConferenciaDoacao`, registra `doacao.aprovada` via `AuditoriaService`, agenda notificação ao doador via `NotificacaoService` e invoca o gancho de correspondência automática (RF016);
   - Se `reprovada`: exige `motivo` não vazio, atualiza `doacao.status = reprovado` (**estado final** no histórico — fiel ao RF008; caso queira corrigir foto ou dado, o doador faz novo cadastro), grava `ConferenciaDoacao`, registra `doacao.reprovada` via `AuditoriaService` e agenda notificação ao doador informando o motivo (RF017).
5. Redireciona (PRG) para a fila de conferência exibindo mensagem de confirmação.

### 4.2 Fluxos de exceção

- **FE-01 — Reprovação sem motivo:** bloqueia e orienta informar o motivo da reprovação.
- **FE-02 — Doação não está mais `em_analise` (ex.: cancelada pelo doador ou já conferida por outro conferente concorrentemente):** `select_for_update()` detecta mudança de estado e recusa com mensagem clara sem sobrescrever.
- **FE-03 — Doação vencida ou abaixo da validade mínima restante na fila:** bloqueia a aprovação e permite marcá-la diretamente como **`vencido`** (com aviso de descarte sanitário do RF012).
- **FE-04 — Acesso sem função `conferencia_doacoes` ou sem 2FA concluído:** HTTP 403 ou redirect para verificação 2FA.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-10-01** | Toda doação nasce `em_analise` (RF008) e **só passa a `disponivel` após aprovação** registrada na conferência. O doador é sempre notificado do resultado (RF017). | RF011 (regra 1) • `medicamentos`, `notificacoes` |
| **RN-10-02** | Em caso de **reprovação**, o motivo é **obrigatório** (com lista orientativa de motivos comuns + detalhe livre — *acréscimo da especificação*) e é informado ao doador (RF017); na aprovação, observação é opcional. O status `reprovado` é **estado final** no histórico (fiel ao RF008; para corrigir, o doador faz novo cadastro). | RF011 (regra 1), RF008, RS015 • `medicamentos`, `notificacoes` |
| **RN-10-03** | A aprovação exige validade acima da **validade mínima restante** definida no parâmetro do RF012 (**30 dias provisórios**, *pendência com o professor* — Questão 4 do PRD) e verificação visual da foto (legibilidade de lote/validade, integridade aparente e ausência de medicamento de controle especial — RS003). Doações na fila que já ficaram vencidas ou abaixo do mínimo têm a aprovação bloqueada e podem ser marcadas diretamente como **`vencido`** (com orientação de descarte do RF012). Os critérios detalhados finais permanecem como *pendência com o professor* (checklist orientativo na tela até confirmação). | RF011 (regra 2), RF012, RS001, RS003 • `medicamentos` |
| **RN-10-04** | Mesmo após aprovação na conferência, o solicitante mantém o **direito de recusar** o medicamento na retirada se a validade ou embalagem divergir do cadastro (RF020). | RF011 (regra 3), RF020, RS001 • `correspondencias` |
| **RN-10-05** | Toda conferência gera registro imutável (`ConferenciaDoacao` com `on_delete=PROTECT` + `RegistroAuditoria`) contendo quem conferiu, resultado, motivo, data e hora (RNF14). | RF011 (regra 4), RNF14, [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `medicamentos`, `auditoria` |
| **RN-10-06** | Apenas Administradores com a função explícita **`conferencia_doacoes`** (+ 2FA) podem conferir doações ([ADR 0010](../adr/0010-perfis-e-permissoes.md)); essa função **não** concede acesso a receitas médicas (RF014). | RS015, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `medicamentos` |

---

## 6. Modelo de dados lógico

#### `ConferenciaDoacao` (app `medicamentos` — `append-only`, `on_delete=PROTECT`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `doacao` | FK (`Doacao`, `PROTECT`, indexado) | Sim | Uma doação pode ter > 1 conferência se retornar a `em_analise` após edição (RF008). |
| `resultado` | TextChoices | Sim | `aprovada`, `reprovada`. |
| `motivo` | Text | Condicional | Obrigatório se `resultado == reprovada` (`CheckConstraint` no PostgreSQL). |
| `responsavel` | FK (`Usuario`, `PROTECT`) | Sim | Administrador com `conferencia_doacoes`. |
| `conferido_em` | Datetime (indexado) | Sim | Timestamp UTC. |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`medicamentos`, restritas a `conferencia_doacoes` + 2FA):** `AdminConferenciaListaView` + `AdminConferenciaFiltroForm` (`GET`), `AdminConferenciaDetalheView` (`GET`), `AdminConferenciaRegistrarView` + `ConferenciaDoacaoForm` (`POST`).
- **Services (`ConferenciaDoacaoService`):** `listar_pendentes(filtros)` e `registrar_conferencia(ator, doacao_id, resultado, motivo)` (transacional com `select_for_update`, validação de validade mínima contra `ParametroVencimento`, `AuditoriaService`, `NotificacaoService` e gancho para `CorrespondenciaService`).
- **Templates:** `templates/medicamentos/admin_conferencia_lista.html` e `templates/medicamentos/admin_conferencia_detalhe.html` (exibe aviso RNF13, checklist orientativo de conferência, fotos via link seguro 60 s e histórico).
- **Rotas:** `medicamentos:admin_conferencia_lista` (`/admin-remed/doacoes/conferencia/`), `medicamentos:admin_conferencia_detalhe` (`/admin-remed/doacoes/<int:doacao_id>/conferencia/`), `medicamentos:admin_conferencia_registrar` (`/admin-remed/doacoes/<int:doacao_id>/conferencia/registrar/`).

---

## 8. Mensagens e validações

- Reprovação sem motivo: `"Informe o motivo da reprovação da doação"`;
- Tentativa de aprovar doação já vencida ou abaixo da validade mínima: `"A doação está vencida ou abaixo da validade mínima restante configurada e não pode ser aprovada"`;
- Sucesso: `"Conferência registrada com sucesso"`;
- Aviso RNF13 mantido visível na tela de conferência.

---

## 9. Segurança e privacidade

- **RS001 & RS003 (OWASP A06):** impede liberação sem conferência humana da foto/validade e barra medicamentos de controle especial antes de entrarem na busca pública.
- **RS013 (OWASP A01/A09):** acesso às fotos apenas por URL pré-assinada de 60 s com auditoria de leitura.
- **RS015 (OWASP A01/A07/A09):** isolamento na função `conferencia_doacoes` + 2FA, motivo obrigatório em reprovações e registro imutável.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** fila clara com destaque visual (texto + cor) para refrigerados e validades mais próximas (WCAG 2.1 AA).
- **RNF04:** lista paginada em ≤ 3 s.
- **RNF13 & RNF14 & RNF16:** aviso médico/farmacêutico, auditoria imutável e acesso seguro às fotos.

---

## 11. Critérios de aceite

1. **CA-10-01 (Aprovação disponibiliza e notifica — RN-10-01):** Dada uma doação `em_analise` dentro da validade mínima, quando `conferencia_doacoes` (+ 2FA) aprova, então o status muda para `disponivel`, `ConferenciaDoacao` e `RegistroAuditoria` gravam o evento e o doador é notificado.
2. **CA-10-02 (Reprovação exige motivo — RN-10-02):** Dada reprovação sem motivo, a operação é recusada; com motivo preenchido, a doação passa a `reprovado` e o doador recebe o motivo na notificação.
3. **CA-10-03 (Bloqueio de doação abaixo da validade mínima — RN-10-03):** Dada uma doação `em_analise` cuja validade ficou abaixo do parâmetro do RF012, o service impede a aprovação.
4. **CA-10-04 (Concorrência e isolamento de permissão — RN-10-06):** Dois conferentes submetendo simultaneamente sobre a mesma doação não gravam duas conferências conflitantes (`select_for_update`); usuários sem `conferencia_doacoes` (ou sem 2FA, ou `is_superuser` sem função) recebem HTTP 403 / redirect para 2FA.

---

## 12. Plano de testes

- **Unidade (`ConferenciaDoacaoService`, `ConferenciaDoacao`):** aprovação válida, reprovação com e sem motivo (`CheckConstraint`), bloqueio quando validade < mínimo do RF012, recusa quando status ≠ `em_analise`, auditoria e enfileiramento de notificação no outbox.
- **Integração (Views/Permissões):** matriz de acesso (`conferencia_doacoes` + 2FA vs demais perfis/funções), leitura da foto gerando `arquivo.acessado`, PRG e exibição do histórico quando a doação passou por reanálise após edição.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Critérios detalhados de conferência e validade mínima restante (Questão 4 do PRD — prazo vencido em 03/11/2026):** confirmar com o professor/cliente os critérios formais e o valor definitivo em dias. | **Pendência com o professor** (Cliente / Ata) | Não bloqueia o MVP; a tela exibe checklist orientativo e usa o parâmetro provisório de **30 dias** no RF012, ajustável sem mudança de código. |
