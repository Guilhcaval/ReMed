# Spec 09 — Gestão de Medicamentos Refrigerados (RF010)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `09` — Gestão de Medicamentos Refrigerados (`RF010`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF010 (Essencial — MVP, HU10). **Não funcionais:** RNF01, RNF02, RNF03, RNF07, RNF13 (Essencial), RNF14 (Essencial). **Segurança:** RS001, RS004. |
| **Apps envolvidos** | `medicamentos` (extensão da doação refrigerada: `DadosRefrigeracaoDoacao`, validações no `DoacaoService`), `pontos_coleta` (priorização de pontos `ativo` com `possui_refrigeracao = True`), `correspondencias` (ciência do solicitante antes do agendamento, janela curta no mesmo dia e recusa por conservação na retirada), `auditoria` (`AuditoriaService`). |
| **Dependências de outras specs** | **[05-cadastro-de-ponto-de-coleta.md](05-cadastro-de-ponto-de-coleta.md) (`RF005` — campo `possui_refrigeracao`)** e **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008` — `condicao_conservacao = refrigerado`)**. **Articula-se com specs ainda não escritas:** **RF016** (correspondência respeitando regras de refrigerados), **RF018** (agendamento com janela curta no mesmo dia e ciência prévia do solicitante) e **RF020** (conferência e direito de recusa na retirada). **Pendência externa:** Questão 5 do PRD (limite de tempo da janela curta de retirada — prazo vencido em 10/11/2026). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md). |

---

## 2. Objetivo e escopo

Tratar de forma segura os medicamentos que exigem cadeia de frio (como a insulina), assegurando declaração obrigatória do doador sobre conservação adequada, ciência explícita do solicitante sobre o transporte refrigerado antes do agendamento, retirada em janela curta no mesmo dia (preferencialmente em ponto de coleta com refrigeração) e conferência com direito de recusa na retirada.

### Inclui

- Extensão obrigatória do cadastro de doação (RF008) quando `condicao_conservacao == refrigerado`: **faixa de temperatura indicada na bula** (com sugestão orientativa `"2 °C a 8 °C"`, prevalecendo a bula) e **declaração obrigatória do doador de conservação adequada** (mantido refrigerado até o cadastro e será mantido até a retirada).
- Rejeição automática no cadastro (RF008) de qualquer doação marcada como `refrigerado` sem essas informações de conservação (RF010 regra 6).
- **Orientação de transporte refrigerado** (ex.: bolsa térmica / embalagem isotérmica) exibida ao solicitante/cuidador e **confirmação obrigatória de ciência** registrada antes de permitir a confirmação do agendamento (RF018, RS004).
- Restrição de **janela curta de retirada no mesmo dia** (campo `janela_retirada_inicio` a `janela_retirada_fim`, validada contra o limite máximo configurável em `settings` — Questão 5 do PRD) e **priorização de pontos de coleta ativos com `possui_refrigeracao = True`** (RF005).
- Integração com a retirada (RF020): destaque para conferência da conservação na entrega e registro de recusa por suspeita de quebra de cadeia de frio.

### Não inclui

- Monitoramento físico por sensores IoT de temperatura ou guarda temporária refrigerada pelo ponto de coleta (fora de escopo — RF005 Observação, RNF11).
- Fluxos completos de correspondência, agendamento e confirmação de entrega (especificados nas specs do RF016, RF018 e RF020, que consomem as regras e validações desta spec).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Doador** | Informar faixa de temperatura da bula e declarar conservação adequada ao cadastrar/editar doação `refrigerado`; propor janela curta no mesmo dia no agendamento (priorizando pontos com refrigeração). | Perfil `Doador` ativo e doação marcada como `refrigerado` (RF008). |
| **Solicitante / Cuidador/Familiar** | Ler orientação de transporte refrigerado e confirmar ciência antes de concluir o agendamento (RF018); conferir a conservação na retirada e recusar caso inadequada (RF020). | Perfil `Solicitante` ou `Cuidador/Familiar` ativo e correspondência aceita para doação refrigerada (RF016). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Etapa do doador (no cadastro da doação — RF008)

1. Ao selecionar `Condição de conservação = Refrigerado` no formulário do RF008, a tela exibe o bloco **Controle de conservação (refrigerado)** com:
   - Campo obrigatório **Faixa de temperatura indicada na bula** (dica: `"Em geral entre 2 °C e 8 °C. A informação da bula prevalece."`);
   - Caixa de seleção obrigatória **Declaração do doador**: `"Declaro que o medicamento foi mantido refrigerado conforme a bula até o cadastro e será mantido refrigerado até o momento da retirada."`;
   - Filtro/destaque no campo de ponto de coleta priorizando pontos `ativo` com `possui_refrigeracao = True`.
2. `DoacaoService.cadastrar(...)` (e `atualizar(...)`) valida que ambos os campos estão preenchidos; caso contrário, rejeita o cadastro (RF010 regra 6).
3. Dentro do mesmo `transaction.atomic()` do RF008, persiste `DadosRefrigeracaoDoacao` (com `declaracao_doador_em = agora`) e inclui `refrigerado: true` nos metadados de auditoria.

### 4.2 Fluxo principal — Etapa do solicitante e janela curta (no agendamento — RF018)

1. Ao agendar a retirada de uma doação `refrigerado` (RF018), o sistema:
   - Prioriza e destaca pontos de coleta ativos com `possui_refrigeracao = True`, mas permite escolher outro ponto/local seguro combinado (fiel ao `"quando possível"` do RF010) exibindo aviso reforçado sobre transporte térmico sem bloquear a doação;
   - Exige que a proposta de retirada defina uma **janela curta no mesmo dia** (`janela_inicio` a `janela_fim`, na mesma data, respeitando o horário de funcionamento do ponto e o limite máximo provisório de **2 horas** — `REFRIGERADO_JANELA_MAX_MINUTOS = 120` configurável em `settings`, *pendência com o professor*);
   - Exibe ao solicitante/cuidador a orientação de transporte refrigerado (ex.: uso de bolsa térmica) e exige marcar **Ciência sobre o transporte refrigerado** antes de habilitar a confirmação do agendamento;
   - Registra `ciencia_solicitante_em = agora` no `Agendamento` e grava na auditoria (`agendamento.ciencia_refrigerado_confirmada`).

### 4.3 Fluxo principal — Conferência e recusa na retirada (RF020)

1. Na tela de confirmação de retirada (RF020), quando a doação é `refrigerado`, exibe-se item explícito de conferência da conservação adequada.
2. Caso o solicitante constate ou suspeite que a refrigeração foi interrompida, pode recusar o medicamento registrando o motivo; a doação muda automaticamente para **`reprovado`** (*acréscimo da especificação* — fail-safe sanitário, impedindo retorno a `"disponível"`, RS001/RS004).

### 4.4 Fluxos de exceção

- **FE-01 — Doação `refrigerado` sem faixa de temperatura ou sem declaração do doador:** cadastro/edição rejeitado imediatamente (RF010 regra 6).
- **FE-02 — Tentativa de confirmar agendamento de refrigerado sem ciência de transporte do solicitante:** `AgendamentoService` bloqueia a confirmação com `RegraNegocioViolada` (RS004).
- **FE-03 — Janela de retirada fora do mesmo dia ou acima do limite máximo configurado:** `AgendamentoService` rejeita a proposta informando o limite máximo permitido para medicamentos refrigerados.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-09-01** | Para toda doação com `condicao_conservacao == refrigerado`, a **faixa de temperatura indicada na bula** é obrigatória (orientação padrão: `2 °C a 8 °C`, prevalecendo a informação da bula). | RF010 (regra 1), RS004 • `medicamentos` |
| **RN-09-02** | O doador deve assinalar obrigatoriamente a **declaração de conservação adequada** (mantido refrigerado até o cadastro e mantido até a retirada), registrada com timestamp. Doação refrigerada sem faixa de temperatura ou sem declaração é **rejeitada no cadastro**. | RF010 (regras 2 e 6), RS004 • `medicamentos` |
| **RN-09-03** | O solicitante/cuidador recebe a **orientação de transporte refrigerado** (ex.: bolsa térmica) e deve confirmar ciência explicitamente **antes** da confirmação do agendamento (RF018). | RF010 (regra 3), RS004 • `correspondencias` |
| **RN-09-04** | A retirada de medicamento refrigerado ocorre em **janela curta, no mesmo dia**, priorizando e destacando pontos de coleta ativos com `possui_refrigeracao = True` (RF005, RF018), mas permitindo outro ponto/local seguro combinado quando não houver ponto refrigerado próximo (com aviso reforçado de transporte térmico). O limite máximo da janela é **2 horas** (`REFRIGERADO_JANELA_MAX_MINUTOS = 120` configurável em `settings` — valor inicial provisório, *pendência com o professor*, Questão 5 do PRD). | RF010 (regra 4), RS004 • `correspondencias`, `pontos_coleta` |
| **RN-09-05** | Na retirada (RF020), o solicitante confere a conservação e tem **direito expresso de recusa** se houver suspeita de quebra da cadeia de frio; nessa recusa, a doação passa automaticamente para **`reprovado`** (*acréscimo da especificação* — fail-safe sanitário, impedindo retorno a `"disponível"`, RS001/RS004). | RF010 (regra 5), RF020, RS004 • `correspondencias`, `medicamentos` |

---

## 6. Modelo de dados lógico

#### `DadosRefrigeracaoDoacao` (app `medicamentos`, `OneToOne` com `Doacao` quando `condicao_conservacao == refrigerado`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `doacao` | OneToOne (`Doacao`, `CASCADE`) | Sim | Existência obrigatória garantida pelo service quando `doacao.condicao_conservacao == refrigerado`. |
| `faixa_temperatura_bula` | String (80) | Sim | Ex.: `"2 °C a 8 °C"`. |
| `declaracao_doador_conservacao` | Boolean | Sim | `CheckConstraint(declaracao_doador_conservacao = True)`. |
| `declaracao_doador_em` | Datetime | Sim | Timestamp UTC da declaração do doador. |

#### Extensão lógica no `Agendamento` (app `correspondencias`, usada pela spec do RF018)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `ciencia_transporte_refrigerado` | Boolean | Sim (se refrigerado) | Obrigatório `True` antes de transicionar o agendamento para `confirmado`. |
| `ciencia_transporte_em` | Datetime, anulável | Sim (se refrigerado) | Timestamp UTC da confirmação de ciência do solicitante. |
| `janela_retirada_inicio` / `janela_retirada_fim` | Time (`xx:xx`) | Sim (se refrigerado) | Mesma data do agendamento; `CheckConstraint(janela_retirada_inicio < janela_retirada_fim)` e diferença ≤ limite máximo em `settings`. |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Forms/Views:** campos condicionais integrados ao `DoacaoCadastroForm` / `DoacaoEditarForm` (Spec `08` — `medicamentos`) e ao fluxo de `Agendamento` (Spec do RF018 — `correspondencias`) e `ConfirmacaoEntrega` (Spec do RF020 — `correspondencias`).
- **Services:** `RefrigeracaoService` (`medicamentos` — regras puras reutilizáveis: `validar_dados_doador`, `validar_janela_curta`, `validar_ciencia_solicitante`, `priorizar_pontos_refrigerados`), invocado dentro das transações de `DoacaoService`, `AgendamentoService` e `EntregaService`.
- **Interface:** bloco visual destacado em `templates/medicamentos/doacao_form.html` (exibido/ocultado progressivamente via JS simples da ADR 0006, mantendo validação completa no servidor), etiqueta `"Refrigerado"` (texto + cor, WCAG 2.1 AA) na busca (RF015) e nas telas de agendamento/retirada, e quadro de orientação de transporte térmico no RF018.

---

## 8. Mensagens e validações

- Doação refrigerada sem faixa de temperatura ou declaração do doador: `"Para medicamentos refrigerados, informe a faixa de temperatura da bula e confirme a declaração de conservação"`;
- Tentativa de confirmar agendamento sem ciência de transporte: `"Confirme ciência das orientações de transporte refrigerado antes de confirmar o agendamento"`;
- Janela acima do limite configurado: `"Para medicamentos refrigerados, a janela de retirada deve ocorrer no mesmo dia dentro do limite máximo permitido"`.

---

## 9. Segurança e privacidade

- **RS004 (OWASP A06 — Design inseguro / risco à saúde):** impede cadastro sem dados de conservação, bloqueia agendamento sem ciência de transporte térmico e janela curta no mesmo dia, e assegura direito de recusa na retirada.
- **RS001:** proteção contra entrega de medicamento com eficácia comprometida.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** orientações de temperatura e transporte em linguagem simples, etiqueta `"Refrigerado"` nunca só por cor (WCAG 2.1 AA).
- **RNF13:** aviso médico/farmacêutico mantido visível no cadastro e na retirada.
- **RNF14:** declarações de conservação, ciência de transporte e eventual recusa gravadas em `RegistroAuditoria`.

---

## 11. Critérios de aceite

1. **CA-09-01 (Rejeição sem dados de conservação — RN-09-01, RN-09-02):** Dada uma doação marcada como `refrigerado` sem faixa de temperatura da bula ou com `declaracao_doador_conservacao = False`, quando o doador submete, então o cadastro é rejeitado.
2. **CA-09-02 (Cadastro refrigerado válido — RN-09-01, RN-09-02):** Dada uma doação `refrigerado` com faixa `"2 °C a 8 °C"` e declaração marcada, quando salva, então `DadosRefrigeracaoDoacao` é criado na mesma transação com timestamp UTC e registrado na auditoria.
3. **CA-09-03 (Ciência obrigatória antes do agendamento — RN-09-03):** Dada uma correspondência de doação `refrigerado`, quando o solicitante tenta confirmar o agendamento sem confirmar ciência sobre o transporte térmico, então o service bloqueia a confirmação; ao confirmar ciência, grava `ciencia_transporte_em` e permite confirmar.
4. **CA-09-04 (Janela curta no mesmo dia e priorização de ponto refrigerado — RN-09-04):** Dada uma proposta de agendamento para doação `refrigerado`, quando a janela excede o limite máximo configurado em `settings` ou `inicio >= fim`, então é rejeitada; na seleção de pontos de coleta, pontos `ativo` com `possui_refrigeracao = True` aparecem primeiro e destacados.
5. **CA-09-05 (Direito de recusa na retirada — RN-09-05):** Na retirada (RF020) de doação `refrigerado`, o solicitante pode recusar por conservação inadequada informando o motivo, gerando registro imutável na auditoria.

---

## 12. Plano de testes

- **Unidade (`RefrigeracaoService`, `DoacaoService`):** cadastro refrigerado com e sem faixa/declaração; `CheckConstraint(declaracao_doador_conservacao = True)`; validação de janela curta nos limites (exato no limite, 1 minuto acima, início ≥ fim); bloqueio de confirmação sem ciência; ordenação priorizando pontos com `possui_refrigeracao = True`.
- **Integração (Views):** exibição dos campos de refrigeração no formulário de doação (inclusive com JS desligado), etiqueta `"Refrigerado"` na listagem, e validação no fluxo de agendamento/retirada (junto às specs de RF018 e RF020).

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Limite máximo da janela curta de retirada de medicamentos refrigerados (Questão 5 do PRD — prazo vencido em 10/11/2026):** confirmar com o professor/cliente o valor definitivo. | **Pendência com o professor** (Cliente / Ata) | Adotado **2 horas** (`REFRIGERADO_JANELA_MAX_MINUTOS = 120`) como valor inicial provisório configurável em `settings`; ajustável sem alteração de regra de negócio após confirmação. |
