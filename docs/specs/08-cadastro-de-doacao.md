# Spec 08 — Cadastro de Doação de Medicamento (RF008)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `08` — Cadastro de Doação de Medicamento (`RF008`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF008 (Essencial — MVP, HU08). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF06 (Essencial), RNF07, RNF08, RNF10, RNF13 (Essencial — aviso médico/farmacêutico), RNF14 (Essencial), RNF16. **Segurança:** RS001, RS002, RS003, RS007, RS008, RS013. |
| **Apps envolvidos** | `medicamentos` (principal: `Doacao`, `FotoDoacao`, `DoacaoService`), `nucleo` (`FormaFarmaceutica` em cadastro auxiliar, `ArquivoService` da ADR 0016, mixins de perfil), `pontos_coleta` (escolha opcional entre pontos `ativo`), `auditoria` (`AuditoriaService`), `notificacoes` (`NotificacaoService`). |
| **Dependências de outras specs** | **[01-cadastro-de-usuario.md](01-cadastro-de-usuario.md) (`RF001`)**, **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[05-cadastro-de-ponto-de-coleta.md](05-cadastro-de-ponto-de-coleta.md) (`RF005`)** e **[06-envio-documentos-ponto-de-coleta.md](06-envio-documentos-ponto-de-coleta.md) (`RF006` — `ArquivoService`)**. **Articula-se com specs ainda não escritas:** **[09-medicamentos-refrigerados.md](09-medicamentos-refrigerados.md) (`RF010`)**, **RF011/RF012** (conferência e rotina de vencimento), **RF014** (receitas/controle especial), **RF016/RF018/RF020** (reserva/agendamento/entrega) e **RF009** (v2.0 — leitura por IA). **Pendência externa:** Questão 4 do PRD (validade mínima restante — prazo vencido em 03/11/2026). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0013](../adr/0013-reserva-transacional-e-concorrencia.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0016](../adr/0016-armazenamento-seguro-de-arquivos.md). |

---

## 2. Objetivo e escopo

Permitir que usuários autenticados com perfil **Doador** cadastrem medicamentos não vencidos e com embalagem íntegra para doação, anexando foto obrigatória da embalagem, consultem suas doações, editem enquanto ainda em análise ou disponíveis e cancelem (sem exclusão física) enquanto não entregues.

### Inclui

- Cadastro auxiliar `FormaFarmaceutica` em `nucleo` (`Comprimido`, `Cápsula`, `Xarope`, `Injetável`, `Pomada`, `Colírio`, `Solução oral`, `Suspensão`, `Creme/Gel`, `Aerossol/Spray`, `Outros`).
- Cadastro de doação com todos os 16 campos do RF008, validação de validade (rejeitando anterior à data atual e respeitando o parâmetro configurável de validade mínima restante do RF012 — valor inicial provisório de **30 dias**, *pendência com o professor*, Questão 4 do PRD), bloqueio imediato se `Embalagem íntegra = Não`, **autodeclaração bloqueante de controle especial** (*acréscimo da especificação* — bloqueia cadastro se `"Sim"`, complementada pela conferência no RF011) e upload de **1 foto obrigatória + até 1 foto opcional (máx. 2 fotos)** (*acréscimo da especificação*, `JPG` ou `PNG`, máx. 5 MB cada via `ArquivoService` — ADR 0016, removendo EXIF/GPS via `Pillow >= 12.0`).
- Integração com **RF010** quando `Condição de conservação = refrigerado` (exigindo faixa de temperatura e declaração de conservação do doador) e sinalização de `Sujeito a receita` (RF014).
- Escolha preferencial de **Ponto de coleta `ativo`** (RF005), permitindo deixar sem ponto pré-definido quando não houver ponto próximo (para combinar outro local seguro no RF018), **nunca sugerindo a residência do doador por padrão** (RS008).
- Exibição obrigatória do aviso de que **a plataforma não substitui avaliação médica ou farmacêutica** (RNF13).
- Alteração pelo próprio doador enquanto `status` ∈ {`em_analise`, `disponivel`}, retornando automaticamente para **`em_analise`** quando qualquer campo farmacêutico ou de segurança mudar (`data_validade`, `lote`, `quantidade`, fotos, nome, princípio ativo, dosagem, forma farmacêutica, fabricante, `sujeito_receita`, `condicao_conservacao` ou dados de refrigeração — *acréscimo da especificação*, excetuando apenas `observacoes` e `ponto_coleta`).
- Cancelamento pelo doador (`status = cancelado`, sem exclusão física) enquanto não entregue, mantendo histórico imutável (`AuditoriaService`), e pesquisa das próprias doações por **medicamento, status e período**.

### Não inclui

- Leitura automática da embalagem por IA multimodal (v2.0 — RF009).
- Conferência e aprovação de validade pelo Administrador (Spec do RF011) e rotina diária de vencimento (Spec do RF012).
- Busca pública/autenticada de medicamentos por terceiros (Spec do RF015).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Doador** | Cadastrar nova doação, listar/pesquisar suas doações, editar doações `em_analise` ou `disponivel`, cancelar doações ainda não entregues e visualizar a foto da própria doação. | Usuário autenticado (`status = ativo`, e-mail confirmado — RF002) com perfil **`Doador`** ativo (RF001). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Cadastro de doação

1. O Doador acessa `medicamentos:doacao_criar`.
2. Preenche nome do medicamento (comercial ou genérico, máx. 150 caracteres), princípio ativo, concentração/dosagem (ex.: `500 mg`), forma farmacêutica, quantidade (unidades ≥ 1), fabricante, lote, data de validade (`dd/mm/aaaa`), marca **Embalagem íntegra = Sim**, responde à **autodeclaração de controle especial = Não** (*acréscimo da especificação*), anexa **1 foto obrigatória e opcionalmente uma 2ª foto** da embalagem (`JPG` ou `PNG`, máx. 5 MB cada — *acréscimo da especificação*), informa **Condição de conservação** (`temperatura_ambiente` ou `refrigerado` — se `refrigerado`, exibe e exige os campos do doador do RF010), **Sujeito a receita** (`Sim`/`Não`), escolhe preferencialmente um **Ponto de coleta ativo** (opcional se não houver próximo) e **Observações** (opcional).
3. Aciona **Cadastrar doação** (`POST` com CSRF e `multipart/form-data`).
4. A view valida formato no `DoacaoCadastroForm` e chama `DoacaoService.cadastrar(request.user, dados, fotos)`.
5. Dentro de `transaction.atomic()`, `DoacaoService.cadastrar(...)`:
   - Reconfere perfil `Doador`, `embalagem_integra == True`, autodeclaração de controle especial `== False`, `data_validade` válida (não anterior a hoje e respeitando o parâmetro configurável de validade mínima restante do RF012 — **30 dias provisórios**, *pendência com o professor*) e, se `ponto_coleta` informado, que está `ativo`;
   - Se `refrigerado`, valida obrigatoriedade dos dados de conservação do RF010 (Spec `09`);
   - Armazena 1 ou 2 fotos via `ArquivoService.armazenar_privado(...)` (`JPG`/`PNG`, ≤ 5 MB, *magic bytes*, remoção EXIF/GPS via `Pillow`, interface antimalware, nome UUID);
   - Cria `Doacao` com `status = em_analise` e `quantidade_disponivel = quantidade_inicial` (sem expor o ponto escolhido nem endereço do doador na busca pública — RF015);
   - Registra `doacao.cadastrada` (e `arquivo.enviado`) via `AuditoriaService`.
6. A view redireciona (PRG) exibindo confirmação + **aviso obrigatório (RNF13)**: a plataforma não substitui avaliação médica ou farmacêutica.

### 4.2 Fluxos alternativos

- **FA-01 — Edição da doação pelo doador (`medicamentos:doacao_editar`):** permitida apenas ao dono enquanto `status` ∈ {`em_analise`, `disponivel`}. Se qualquer campo farmacêutico ou de segurança mudar (`data_validade`, `lote`, `quantidade`, fotos, nome, princípio ativo, dosagem, forma farmacêutica, fabricante, `sujeito_receita`, `condicao_conservacao` ou dados de refrigeração — *acréscimo da especificação*), `DoacaoService.atualizar(...)` retorna o status automaticamente para **`em_analise`** (exigindo nova conferência no RF011); apenas alterações restritas a `observacoes` ou `ponto_coleta` mantêm `disponivel`. Grava `doacao.alterada` na auditoria.
- **FA-02 — Cancelamento pelo doador (`medicamentos:doacao_cancelar`):** permitido via `POST` com CSRF enquanto `status` ∉ {`entregue`, `vencido`, `cancelado`}. Sob `transaction.atomic()` + `select_for_update()` (na ordem fixa da ADR 0013), muda `status = cancelado`, cancela eventual correspondência/reserva/agendamento em aberto notificando o solicitante (RF016/RF018/RF017) e grava `doacao.cancelada` na auditoria.
- **FA-03 — Consulta das próprias doações (`medicamentos:minhas_doacoes`):** filtra por `doador_id = request.user.id`, com filtros por **medicamento** (nome/princípio ativo), **status** e **período** (`criado_em`).

### 4.3 Fluxos de exceção

- **FE-01 — Embalagem não íntegra (`embalagem_integra = False`):** bloqueia o cadastro com mensagem explicativa clara informando que apenas medicamentos com embalagem íntegra podem ser doados (RS001).
- **FE-02 — Data de validade anterior à data atual (ou abaixo da validade mínima configurada):** bloqueia com orientação clara de descarte seguro conforme legislação sanitária (RNF11, RS001).
- **FE-03 — Foto ausente, acima de 5 MB ou formato diferente de JPG/PNG:** bloqueia exibindo erro claro no campo da foto.
- **FE-04 — Tentativa de editar doação `reservado`, `entregue`, `vencido`, `reprovado` ou `cancelado`, ou doação de terceiro:** edições fora de `em_analise`/`disponivel` recebem erro de regra de negócio; doação de terceiro recebe HTTP 404 (OWASP A01).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-08-01** | A forma farmacêutica vem de cadastro auxiliar (`FormaFarmaceutica` em `nucleo`). Nome do medicamento tem máximo de 150 caracteres; quantidade deve ser inteiro > 0. | RF008 (Campos, regra 1) • `nucleo`, `medicamentos` |
| **RN-08-02** | A data de validade é obrigatória e **não se aceita data anterior à data atual** nem abaixo da validade mínima restante configurável no RF012 (**30 dias** como valor inicial provisório, *pendência com o professor* — Questão 4 do PRD). | RF008 (regra 2), RS001 • `medicamentos` |
| **RN-08-03** | **Apenas embalagens íntegras são aceitas.** Marcar `"Não"` bloqueia o cadastro com mensagem explicativa. | RF008 (regra 3), RS001 • `medicamentos` |
| **RN-08-04** | Exige **1 foto obrigatória da embalagem** permitindo **até 1 foto opcional (máx. 2 fotos)** (*acréscimo da especificação*, frente e validade/lote, `JPG` ou `PNG`, máx. 5 MB cada), processadas pelo `ArquivoService` ([ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md): *magic bytes*, remoção de EXIF/GPS via `Pillow >= 12.0`, interface antimalware, nome UUID, storage privado com URL pré-assinada de 60 s para perfis autorizados). | RF008 (regra 4), RNF16, RS013, [ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md) • `nucleo`, `medicamentos` |
| **RN-08-05** | `Condição de conservação`: `temperatura_ambiente` ou `refrigerado`. Se `refrigerado`, aplicam-se obrigatoriamente as regras do RF010 (Spec `09`), rejeitando o cadastro sem as informações de conservação. | RF008 (regra 5), RF010 (regra 6), RS004 • `medicamentos` |
| **RN-08-06** | `Sujeito a receita`: se `Sim`, a correspondência e a retirada seguem o RF014. Medicamentos de controle especial (Portaria SVS/MS nº 344/1998) ficam bloqueados no MVP por **autodeclaração obrigatória bloqueante no cadastro** (*acréscimo da especificação*) somada à conferência humana no RF011 (RS003). | RF008 (regra 6), RF014, RS003 • `medicamentos` |
| **RN-08-07** | O ponto de coleta é escolhido preferencialmente entre os pontos **`ativo`** (RF005). Se não houver ponto próximo, pode ficar sem ponto pré-definido (local seguro combinado no RF018). A residência do doador **nunca é sugerida por padrão**. | RF008 (regra 7), RS008 • `medicamentos`, `pontos_coleta` |
| **RN-08-08** | Status válidos: `em_analise`, `disponivel`, `reservado`, `entregue`, `vencido`, `reprovado`, `cancelado`, sempre com histórico. Toda doação nasce **`em_analise`**. | RF008 (regra 8), RNF14 • `medicamentos`, `auditoria` |
| **RN-08-09** | Ao salvar (e de forma visível na tela), o sistema exibe o aviso obrigatório de que **a plataforma não substitui avaliação médica ou farmacêutica**. | RF008 (Aviso obrigatório), RNF13 • `medicamentos` |
| **RN-08-10** | O doador pode alterar a doação apenas enquanto `status` ∈ {`em_analise`, `disponivel`}. Alterar **qualquer campo farmacêutico ou de segurança** (`data_validade`, `lote`, `quantidade`, fotos, nome, princípio ativo, dosagem, forma farmacêutica, fabricante, `sujeito_receita`, `condicao_conservacao` ou dados de refrigeração — *acréscimo da especificação*) devolve a doação automaticamente para **`em_analise`**; apenas `observacoes` e `ponto_coleta` mantêm `disponivel`. Sempre com histórico imutável. | RF008 (Alteração), RNF14 • `medicamentos`, `auditoria` |
| **RN-08-11** | **Não há exclusão física** (`on_delete=PROTECT`). O doador pode cancelar (`status = cancelado`) enquanto a doação não for entregue, mantendo todo o histórico e notificando o solicitante caso estivesse reservada/agendada. | RF008 (Exclusão), RNF06, [ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md) • `medicamentos`, `correspondencias`, `notificacoes` |

---

## 6. Modelo de dados lógico

#### `FormaFarmaceutica` (app `nucleo` — cadastro auxiliar populado por migração de dados)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` / `nome` (único) / `ativo` | PK / String (80) / Boolean | Sim | Comprimido, Cápsula, Xarope, Injetável, Pomada, Colírio, etc. |

#### `Doacao` (app `medicamentos`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | Referenciado com `on_delete=PROTECT` por conferências, correspondências e entregas. |
| `doador` | FK (`Usuario`, `PROTECT`, indexado) | Sim | |
| `nome_medicamento` | String (150, indexado) | Sim | Comercial ou genérico. |
| `principio_ativo` | String (150, indexado) | Sim | |
| `concentracao_dosagem` | String (80) | Sim | Ex.: `500 mg`. |
| `forma_farmaceutica` | FK (`FormaFarmaceutica`, `PROTECT`) | Sim | |
| `quantidade_inicial` | PositiveInteger | Sim | `CheckConstraint(quantidade_inicial > 0)`. |
| `quantidade_disponivel` | PositiveInteger | Sim | `CheckConstraint(0 <= quantidade_disponivel <= quantidade_inicial)` ([ADR 0013](../adr/0013-reserva-transacional-e-concorrencia.md)). |
| `fabricante` | String (120) | Sim | |
| `lote` | String (60) | Sim | |
| `data_validade` | Date (indexado) | Sim | |
| `embalagem_integra` | Boolean | Sim | `CheckConstraint(embalagem_integra = True)` para registros salvos. |
| `condicao_conservacao` | TextChoices | Sim | `temperatura_ambiente`, `refrigerado`. |
| `sujeito_receita` | Boolean | Sim | |
| `ponto_coleta` | FK (`PontoColeta`, `PROTECT`, anulável) | Não | Apenas pontos `ativo` na criação/edição; oculto na busca pública até agendamento confirmado (RF015). |
| `observacoes` | Text | Não | Opcional. |
| `status` | TextChoices (indexado) | Sim | `em_analise`, `disponivel`, `reservado`, `entregue`, `vencido`, `reprovado`, `cancelado`. Padrão: `em_analise`. |
| `criado_em` / `atualizado_em` | Datetime | Sim | `criado_em` cobre `Data do cadastro`. |

#### `FotoDoacao` (app `medicamentos`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `doacao` | FK (`Doacao`, `PROTECT`) | Sim | |
| `ordem` | PositiveSmallInteger | Sim | `1` (obrigatória) ou `2` (opcional — *acréscimo da especificação*); `CheckConstraint(ordem in (1, 2))` e `UniqueConstraint(doacao, ordem)`. |
| `arquivo_chave` | String (255, único) | Sim | Chave UUID no storage privado (`doacoes/<uuid>.<ext>`). |
| `mime_verificado` / `tamanho_bytes` | String (40) / PositiveInteger | Sim | Apenas `image/jpeg` ou `image/png`, `<= 5242880`. |
| `criado_em` | Datetime | Sim | |

*(Os campos extras de refrigeração da doação são detalhados na [Spec 09 — RF010](09-medicamentos-refrigerados.md).)*

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`medicamentos`, restritas ao perfil `Doador`):** `DoacaoCriarView` + `DoacaoCadastroForm`, `MinhasDoacoesListaView` + `MinhasDoacoesFiltroForm`, `DoacaoEditarView` + `DoacaoEditarForm`, `DoacaoCancelarView` (`POST`), `DoacaoFotoAcessarView` (dono, `conferencia_doacoes` + 2FA, ou solicitante com correspondência aceita/agendada — URL pré-assinada 60 s + auditoria).
- **Services (`DoacaoService`):** `cadastrar`, `atualizar`, `cancelar`, `listar_do_doador`, `gerar_acesso_foto` — transacionais nas escritas com `AuditoriaService` e `NotificacaoService`.
- **Templates:** `doacao_form.html` (com aviso visível do RNF13, bloco condicional de refrigeração do RF010 via JS simples e aviso para não fotografar etiquetas com nome do paciente — RS009/RNF10), `minhas_doacoes_lista.html` (filtros por medicamento, status e período, etiquetas texto+cor e botão cancelar com confirmação).
- **Rotas:** `medicamentos:doacao_criar`, `medicamentos:minhas_doacoes`, `medicamentos:doacao_editar`, `medicamentos:doacao_cancelar`, `medicamentos:doacao_foto_acessar`.

---

## 8. Mensagens e validações

- Campos obrigatórios vazios: `"Campo(s) obrigatório(s) não preenchido(s)"`;
- Embalagem não íntegra: `"Apenas medicamentos com embalagem íntegra podem ser doados"`;
- Validade vencida: `"Não é permitido cadastrar medicamento vencido. Faça o descarte conforme a legislação sanitária"`;
- Foto inválida: `"Envie a foto da embalagem em JPG ou PNG"` / `"O arquivo deve ter no máximo 5 MB"`;
- Aviso obrigatório (RNF13): `"O ReMed não substitui avaliação médica ou farmacêutica"`.

---

## 9. Segurança e privacidade

- **RS001 (OWASP A06):** validade e foto obrigatórias, bloqueio de embalagem violada, retorno a `em_analise` ao alterar campos críticos.
- **RS002 & RS013 (OWASP A01/A04/A05):** limpeza de EXIF/GPS nas fotos via `Pillow`, storage privado com UUID e URL pré-assinada 60 s, auditoria de envio/leitura, orientação contra fotografar etiquetas com dados pessoais.
- **RS003 & RS008 (OWASP A06):** bloqueio de controle especial por autodeclaração obrigatória no cadastro (*acréscimo da especificação*) + conferência no RF011, e nunca sugerir residência do doador por padrão.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** formulário claro com dicas de campos farmacêuticos (princípio ativo, lote, validade) e WCAG 2.1 AA.
- **RNF04, RNF06, RNF07, RNF08, RNF13, RNF14, RNF16:** descritos nos controles acima.

---

## 11. Critérios de aceite

1. **CA-08-01 (Cadastro válido nasce `em_analise` com aviso RNF13 — RN-08-01..RN-08-09):** Dado um Doador autenticado preenchendo todos os campos válidos e foto JPG/PNG ≤ 5 MB, quando salva, então a doação nasce `em_analise` com `quantidade_disponivel = quantidade_inicial`, foto salva sem EXIF/GPS e com nome UUID, `doacao.cadastrada` gravado na auditoria e aviso médico/farmacêutico exibido.
2. **CA-08-02 (Bloqueios de segurança — RN-08-02, RN-08-03, RN-08-04):** Dado `embalagem_integra = False`, `data_validade < hoje`, quantidade `<= 0` ou foto em formato inválido (`PDF`/`.exe`) ou > 5 MB, então o cadastro é rejeitado com mensagem clara.
3. **CA-08-03 (Retorno automático a `em_analise` na edição — RN-08-10):** Dada uma doação `disponivel`, quando o doador altera `data_validade`, `lote` ou `quantidade`, então o status volta automaticamente para `em_analise` e `doacao.alterada` é gravado na auditoria.
4. **CA-08-04 (Cancelamento sem exclusão física — RN-08-11):** Dada uma doação não entregue, quando o doador cancela (`POST`), então o status muda para `cancelado` preservando o registro e histórico (se havia reserva/agendamento, cancela e notifica o solicitante); doação `entregue` não pode ser cancelada.
5. **CA-08-05 (Permissão por perfil e dono — ADR 0010):** Usuário sem perfil `Doador` recebe 403 ao tentar cadastrar doação; outro doador recebe 404 ao tentar editar/cancelar doação alheia.

---

## 12. Plano de testes

- **Unidade (`DoacaoService`, `DoacaoCadastroForm`, constraints):** criação com `em_analise`, `CheckConstraint` de quantidade e `embalagem_integra`, bloqueio de data vencida/embalagem violada, retorno a `em_analise` ao alterar validade/lote/quantidade, cancelamento com *rollback* seguro, remoção de EXIF/GPS da foto e filtros de `listar_do_doador`.
- **Integração (Views/Permissões):** acesso exclusivo ao perfil `Doador`, 404 para edição/cancelamento de terceiro, exibição do aviso RNF13, e autorização de `doacao_foto_acessar` (dono, `conferencia_doacoes` + 2FA, solicitante vinculado).

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Validade mínima restante no cadastro e na conferência (Questão 4 do PRD — prazo vencido em 03/11/2026):** confirmar com o professor/cliente o valor definitivo. | **Pendência com o professor** (Cliente / Ata) | Adotado **30 dias** como valor inicial provisório configurável na tabela de parâmetros do RF012; ajustável sem alteração de código após confirmação. |
| 2 | **Retenção e eliminação das fotos de embalagem pela LGPD (Questão 8 do PRD):** prazo ainda não definido na Política de Privacidade. | Pendência externa (Cliente / Jurídico) | Não bloqueia o MVP; fotos ficam em storage privado com URL pré-assinada 60 s até definição da rotina de expurgo. |
