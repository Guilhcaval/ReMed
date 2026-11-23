# Spec 15 — Correspondência entre Oferta e Necessidade (RF016)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `15` — Correspondência entre Oferta e Necessidade (`RF016`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF016 (Essencial — MVP, HU16). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF06 (Essencial — reserva transacional sem reserva dupla), RNF07, RNF14 (Essencial), RNF15 (Importante — rotina de expiração de aceite/reserva). **Segurança:** RS001, RS002, RS003, RS006, RS007. |
| **Apps envolvidos** | `correspondencias` (principal: `Correspondencia`, `CorrespondenciaService`, comando `manage.py expirar_correspondencias_e_reservas`), `medicamentos` (`Doacao`, `VencimentoService`), `solicitacoes` (`Solicitacao`, `ReceitaService`), `nucleo` (`GeolocalizacaoService` — ADR 0017, `ExecucaoRotina` — ADR 0014), `notificacoes` (`NotificacaoService`), `auditoria` (`AuditoriaService`). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008`)**, **[09-medicamentos-refrigerados.md](09-medicamentos-refrigerados.md) (`RF010`)**, **[10-conferencia-e-aprovacao-de-validade.md](10-conferencia-e-aprovacao-de-validade.md) (`RF011`)**, **[11-rotina-automatica-de-vencimento.md](11-rotina-automatica-de-vencimento.md) (`RF012`)**, **[12-cadastro-de-solicitacao.md](12-cadastro-de-solicitacao.md) (`RF013`)**, **[13-fluxo-medicamentos-sujeitos-a-receita.md](13-fluxo-medicamentos-sujeitos-a-receita.md) (`RF014`)** e **[14-busca-e-geolocalizacao.md](14-busca-e-geolocalizacao.md) (`RF015`)**. **Articula-se com specs em rascunho desta leva:** **[16-agendamento-da-retirada.md](16-agendamento-da-retirada.md) (`RF018`)** e **[17-mensagens-na-plataforma.md](17-mensagens-na-plataforma.md) (`RF019`)**. **Pendências externas:** Questão 12 do PRD (prazo de expiração da reserva sem agendamento — adotado 48 h provisório pela ADR 0013 a validar com cliente) e Questão 13 (48 h sugeridas para aceite). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0014](../adr/0014-rotinas-agendadas.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md). |

---

## 2. Objetivo e escopo

Cruzar automaticamente as doações **`disponivel`** com as solicitações **`aberta`** compatíveis dentro do raio de busca (priorizando proximidade e antiguidade), gerenciar o **aceite bilateral** de doador e solicitante dentro do prazo configurável e garantir a **reserva transacional exclusiva** da doação para uma única correspondência por vez (RNF06, RS007, [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)).

### Inclui

- Motor de cruzamento automático `CorrespondenciaService.tentar_corresponder_doacao(doacao_id)` e `tentar_corresponder_solicitacao(solicitacao_id)`, disparado quando uma doação é aprovada (RF011), retorna a `disponivel` (ex.: após entrega parcial ou expiração/recusa), ou quando uma solicitação fica apta (cadastro sem receita no RF013 ou aprovação de receita no RF014).
- Critérios estritos de compatibilidade: `principio_ativo`, `concentracao_dosagem` e `forma_farmaceutica` compatíveis (normalizados), distância Haversine ≤ `Solicitacao.raio_busca_km`, doação `disponivel` com `quantidade_disponivel > 0` (permitindo **correspondência parcial** quando `quantidade_disponivel < quantidade_necessaria`, exibindo claramente a quantidade oferecida antes do aceite — alinhado ao RF020 regra 4), doador e solicitante distintos (`doador_id != solicitante_id` — *acréscimo da especificação*, RS006), ambos com conta `ativo`, sem bloqueio mútuo (RF019), validade conferida em tempo real (RF012), receita **`valida`** quando sujeito a receita (RF014) e sinalização de refrigerado (RF010).
- Priorização determinística entre múltiplas solicitações: **menor distância calculada** (RF015 / ADR 0017) e, em caso de empate, **solicitação mais antiga** (`criado_em` crescente).
- Fluxo de **aceite bilateral** (doador + solicitante) dentro do prazo configurável (`CORRESPONDENCIA_ACEITE_HORAS = 48` em `settings`), com opção de **recusa** por qualquer uma das partes.
- **Reserva transacional exclusiva ([ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)):** `transaction.atomic()` + `select_for_update()` na ordem fixa **`Doacao -> Solicitacao -> Correspondencia -> Agendamento`** + `UniqueConstraint` parcial no PostgreSQL garantindo que uma doação nunca tenha duas correspondências ativas simultâneas; a doação inteira passa a `reservado` (saldo remanescente após entrega parcial retorna a `disponivel` no RF020) e recebe `reservado_ate = agora + RESERVA_EXPIRACAO_HORAS` (48 h, ADR 0013) enquanto o agendamento (RF018) não é confirmado.
- Rotina periódica (`manage.py expirar_correspondencias_e_reservas`, [ADR 0014](../adr/0014-rotinas-agendadas.md)) para expirar prazos de aceite vencidos e reservas sem agendamento confirmado vencidas, devolvendo doação a `disponivel` (se ainda válida) e solicitação a `aberta`, notificando ambas as partes (RF017) e tentando nova correspondência.

### Não inclui

- Agendamento da retirada (Spec `16` — RF018) e troca de mensagens (Spec `17` — RF019), liberados imediatamente após `Correspondencia.status == aceita`.

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Sistema** | Executar cruzamento automático oferta × necessidade e expirar correspondências/reservas vencidas. | Doação `disponivel` (RF011) e solicitação `aberta` (RF013; com receita `valida` se sujeito a receita — RF014). |
| **Doador** | Consultar correspondências da sua doação, aceitar ou recusar dentro do prazo. | Conta ativa autenticada e dono da `Doacao`. |
| **Solicitante / Cuidador/Familiar** | Consultar correspondências da sua solicitação, aceitar ou recusar dentro do prazo. | Conta ativa autenticada e dono da `Solicitacao`. |

---

## 4. Fluxos

### 4.1 Fluxo principal — Cruzamento automático, aceite bilateral e reserva

1. Ao ficar elegível uma doação `disponivel` ou uma solicitação `aberta` (e apta quanto a RF014), `CorrespondenciaService` busca candidatas compatíveis em `principio_ativo`, `concentracao_dosagem`, `forma_farmaceutica` e raio (`GeolocalizacaoService`), ordenando por `(distancia_km ASC, solicitacao.criado_em ASC)`.
2. Sob `transaction.atomic()` com `select_for_update()` em `Doacao` e `Solicitacao` (ordem fixa da ADR 0013):
   - Reconfere em tempo real que a doação está dentro da validade (`VencimentoService.verificar_ou_vencer_doacao` — RF012);
   - Reconfere que `Doacao.status == disponivel`, `Solicitacao.status == aberta` e não existe correspondência `pendente_aceite` ou `aceita` ativa para a doação (exclusividade de 1 correspondência ativa por doação — ADR 0013);
   - Cria `Correspondencia` com `status = pendente_aceite`, `distancia_km`, `prazo_aceite_em = agora + CORRESPONDENCIA_ACEITE_HORAS` (48 h);
   - Atualiza `Solicitacao.status = correspondida`, grava `correspondencia.criada` na auditoria e notifica doador e solicitante (`nova_correspondencia`, RF017 — sem dados pessoais nem endereço do ponto, RS002).
3. Doador e Solicitante acessam `correspondencias:detalhe` e acionam **Aceitar correspondência** (`POST` com CSRF).
4. A cada aceite, sob `transaction.atomic()` + `select_for_update()` na ordem fixa `Doacao -> Solicitacao -> Correspondencia`:
   - Reconfere validade em tempo real (RF012) e prazo (`agora <= prazo_aceite_em`);
   - Registra `aceite_doador_em` ou `aceite_solicitante_em`;
   - Quando **ambas** as partes tiverem aceitado: muda `Correspondencia.status = aceita`, muda `Doacao.status = reservado`, define `reservado_ate = agora + RESERVA_EXPIRACAO_HORAS` (48 h, ADR 0013), cria a `Conversa` do RF019, grava `correspondencia.aceita` / `doacao.reservada` na auditoria e notifica ambas as partes (`correspondencia_aceita`, RF017) orientando a agendar a retirada no RF018.

### 4.2 Fluxos alternativos

- **FA-01 — Recusa por uma das partes (`correspondencias:recusar`):** via `POST` com CSRF em `pendente_aceite`. Sob `transaction.atomic()` + `select_for_update()`, muda `Correspondencia.status = recusada`, mantém/devolve `Doacao` para `disponivel` (se ainda válida) e `Solicitacao` para `aberta`, notifica a outra parte (RF017), grava auditoria e tenta novo cruzamento excluindo o par recusado.
- **FA-02 — Expiração de prazo de aceite ou reserva sem agendamento (`manage.py expirar_correspondencias_e_reservas`):** rotina agendada com `pg_try_advisory_lock` ([ADR 0014](../adr/0014-rotinas-agendadas.md)) expira:
  - Correspondências `pendente_aceite` com `prazo_aceite_em < agora`;
  - Correspondências `aceita` sem agendamento `confirmado` cujo `reservado_ate < agora` (ADR 0013 / RS007).
  Em ambos os casos, muda `Correspondencia -> expirada`, cancela eventual proposta de agendamento pendente, devolve `Doacao -> disponivel` (conferindo RF012) e `Solicitacao -> aberta`, notifica ambas as partes (RF017) e grava auditoria + `ExecucaoRotina`.

### 4.3 Fluxos de exceção

- **FE-01 — Concorrência / tentativa de reserva dupla (RNF06, RS007):** `select_for_update()` serializa as transações; a segunda tentativa encontra a doação já reservada (ou constraint parcial do PostgreSQL bloqueia), sofre *rollback* limpo e informa o usuário.
- **FE-02 — Doação venceu no mesmo dia antes do aceite final (RF012):** `VencimentoService.verificar_ou_vencer_doacao` marca a doação como `vencido`, cancela a correspondência devolvendo a solicitação a `aberta` e informa as partes.
- **FE-03 — Usuário que não é parte da correspondência tenta acessá-la:** recebe HTTP 404 (OWASP A01).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-15-01** | Status válidos da correspondência: `pendente_aceite`, `aceita`, `recusada`, `expirada`, sempre com histórico imutável. | RF016 (regra 1), RNF14 • `correspondencias`, `auditoria` |
| **RN-15-02** | Só há correspondência quando coincidem **`principio_ativo`**, **`concentracao_dosagem`** e **`forma_farmaceutica`**, dentro do **`raio_busca_km`** da solicitação, respeitando receita `valida` (RF014), regras de refrigerados (RF010), validade vigente em tempo real (RF012), contas `ativo`, sem bloqueio mútuo (RF019) e com `doador != solicitante` (*acréscimo da especificação*, RS006). Permite-se **correspondência parcial** quando `doacao.quantidade_disponivel < solicitacao.quantidade_necessaria`, exibindo explicitamente a quantidade oferecida antes do aceite. | RF016 (regra 2), RF010, RF012, RF014, RF020, RS003, RS006 • `correspondencias` |
| **RN-15-03** | Havendo várias solicitações compatíveis para uma doação, prioriza-se a **menor distância** (RF015 / ADR 0017); em empate, a **solicitação mais antiga** (`criado_em`). | RF016 (regra 3), RF015 • `correspondencias` |
| **RN-15-04** | Exige **aceite de doador e solicitante** em **48 horas** (`CORRESPONDENCIA_ACEITE_HORAS = 48` configurável em `settings`). Vencido o prazo, a correspondência expira, a doação volta a `disponivel` e a solicitação a `aberta`, notificando ambas as partes (RF017). | RF016 (regra 4), RNF15 • `correspondencias`, `notificacoes` |
| **RN-15-05** | Cada doação admite no máximo **1 correspondência ativa (`pendente_aceite` ou `aceita`) por vez** (`UniqueConstraint` parcial). Ao concluir o aceite bilateral, a **doação inteira** passa a **`reservado`** (`select_for_update()` na ordem fixa `Doacao -> Solicitacao -> Correspondencia -> Agendamento` — [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)), com prazo de expiração da reserva (`RESERVA_EXPIRACAO_HORAS = 48` em `settings`) caso o agendamento não seja confirmado no RF018. | RF016 (regra 5), RNF06, RS007, [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md) • `correspondencias`, `medicamentos` |

---

## 6. Modelo de dados lógico

#### `Correspondencia` (app `correspondencias`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | Referenciado com `on_delete=PROTECT` por `Agendamento` e `Conversa`. |
| `doacao` | FK (`Doacao`, `PROTECT`, indexado) | Sim | `UniqueConstraint(fields=["doacao"], condition=Q(status__in=["pendente_aceite", "aceita"]))` (exclusividade de 1 correspondência ativa por doação — ADR 0013). |
| `solicitacao` | FK (`Solicitacao`, `PROTECT`, indexado) | Sim | `UniqueConstraint(fields=["solicitacao"], condition=Q(status__in=["pendente_aceite", "aceita"]))`. |
| `distancia_km` | Decimal (6,2) | Sim | Distância calculada no servidor (Haversine — ADR 0017); exibida em faixa aproximada na interface antes do agendamento (RS002). |
| `status` | TextChoices (indexado) | Sim | `pendente_aceite`, `aceita`, `recusada`, `expirada`. |
| `aceite_doador_em` / `aceite_solicitante_em` | Datetime, anulável | Não | Preenchidos ao aceitar; ambos preenchidos → `aceita`. |
| `prazo_aceite_em` | Datetime (indexado) | Sim | `criado_em + CORRESPONDENCIA_ACEITE_HORAS`. |
| `reservado_ate` | Datetime, anulável (indexado) | Não | Preenchido ao transicionar para `aceita` (`agora + RESERVA_EXPIRACAO_HORAS`); limpo ao confirmar agendamento (RF018) e reiniciado em cancelamento automático por suspensão de ponto (Spec `07`). |
| `criado_em` / `atualizado_em` | Datetime | Sim | |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`correspondencias`):** `MinhasCorrespondenciasListaView` (`GET`), `CorrespondenciaDetalheView` (`GET` — restrita às duas partes, 404 para terceiros), `CorrespondenciaAceitarView` (`POST`), `CorrespondenciaRecusarView` (`POST`).
- **Comando:** `correspondencias/management/commands/expirar_correspondencias_e_reservas.py`.
- **Services (`CorrespondenciaService`):** `tentar_corresponder_doacao`, `tentar_corresponder_solicitacao`, `aceitar(correspondencia_id, usuario)`, `recusar(correspondencia_id, usuario)`, `expirar_pendentes_e_reservas()` — todas as escritas transacionais seguindo estritamente a ordem de lock da ADR 0013.
- **Templates:** `minhas_correspondencias.html` e `correspondencia_detalhe.html` (exibindo identificação reduzida das partes, faixa de distância, prazo restante para aceite e botões Aceitar/Recusar; nunca exibe endereço do doador ou ponto de retirada antes do RF018).
- **Rotas:** `correspondencias:minhas`, `correspondencias:detalhe`, `correspondencias:aceitar`, `correspondencias:recusar`.

---

## 8. Mensagens e validações

- Aceite registrado aguardando a outra parte: `"Seu aceite foi registrado. Aguardando confirmação da outra parte"`;
- Aceite bilateral concluído: `"Correspondência aceita! A doação foi reservada. Combine e agende a retirada"`;
- Concorrência/indisponibilidade: `"Esta doação não está mais disponível para reserva"`;
- Prazo expirado: `"O prazo para aceite desta correspondência expirou"`.

---

## 9. Segurança e privacidade

- **RS007 & RNF06 (OWASP A06):** lock pessimista determinístico (`select_for_update()` na ordem fixa da ADR 0013) + `UniqueConstraint` parcial no PostgreSQL eliminam reserva dupla e *deadlocks*.
- **RS002 (OWASP A01):** identificação reduzida e faixa aproximada de distância; checagem por objeto nas views (somente `doador` ou `solicitante` da correspondência — 404 para terceiros).
- **RS003 & RS006:** bloqueia cruzamento sem receita `valida` (RF014), com doador/solicitante iguais ou com bloqueio mútuo.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** prazo de aceite e status claros em texto + cor (WCAG 2.1 AA).
- **RNF06, RNF14, RNF15:** transações atômicas, auditoria imutável e rotina agendada com `pg_try_advisory_lock`.

---

## 11. Critérios de aceite

1. **CA-15-01 (Priorização por proximidade e antiguidade — RN-15-02, RN-15-03):** Dadas 3 solicitações compatíveis (duas a 2 km em datas diferentes e uma a 5 km), o cruzamento escolhe a solicitação a 2 km mais antiga.
2. **CA-15-02 (Bloqueio por receita não validada — RN-15-02):** Solicitação de medicamento sujeito a receita com `ReceitaMedica.status == pendente` ou `invalida` não gera correspondência; após marcada `valida` no RF014, gera correspondência.
3. **CA-15-03 (Aceite bilateral e reserva exclusiva — RN-15-04, RN-15-05):** Apenas quando ambas as partes aceitam dentro de 48 h a doação muda para `reservado` e recebe `reservado_ate`; tentativas simultâneas de reservar a mesma doação para duas correspondências falham com *rollback* limpo (constraint parcial + `select_for_update`).
4. **CA-15-04 (Expiração automática — RN-15-04, RN-15-05):** Passado `prazo_aceite_em` ou `reservado_ate` sem agendamento confirmado, `expirar_correspondencias_e_reservas` marca `Correspondencia` como `expirada`, devolve doação a `disponivel` e solicitação a `aberta` e notifica ambas as partes.

---

## 12. Plano de testes

- **Unidade (`CorrespondenciaService`, constraints PostgreSQL):** cruzamento por princípio ativo/concentração/forma/raio; prioridade proximidade + desempate antiguidade; bloqueio de auto-correspondência (`doador == solicitante`); bloqueio sem receita válida; conferência em tempo real de validade (RF012); aceite bilateral e `UniqueConstraint` parcial impedindo duas correspondências ativas na mesma doação; rotina de expiração idempotente.
- **Integração (Views/Permissões):** apenas doador e solicitante acessam `correspondencia_detalhe` (404 para terceiros); ações `aceitar` e `recusar` via `POST` + CSRF; ausência de dados pessoais e endereço nas telas e notificações.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Validação final dos prazos de 48 horas (aceite e expiração de reserva sem agendamento — Questões 12 e 13 do PRD):** confirmar com o cliente os valores sugeridos. | Pendência externa (Cliente / PO) | Não bloqueia o MVP; ambos são parâmetros configuráveis em `settings` (`CORRESPONDENCIA_ACEITE_HORAS = 48` e `RESERVA_EXPIRACAO_HORAS = 48`). |
