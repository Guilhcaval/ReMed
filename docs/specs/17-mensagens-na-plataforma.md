# Spec 17 — Mensagens dentro da Plataforma (RF019)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `17` — Mensagens dentro da Plataforma (`RF019`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF019 (Importante — **MVP ⬆**, HU19). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF08, RNF10 (Essencial), RNF14 (Essencial). **Segurança:** RS002, RS008, RS014, RS015. |
| **Apps envolvidos** | `correspondencias` (principal: `Conversa`, `Mensagem`, `BloqueioUsuario`, `MensagemService`), `notificacoes` (`NotificacaoService` — `nova_mensagem` sem conteúdo do texto), `auditoria` (`AuditoriaService` — sem jamais gravar o texto das mensagens em `detalhes`), `moderacao` (leitura restrita pelo moderador em caso de denúncia na v1.1 — RF021). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[15-correspondencia-oferta-e-necessidade.md](15-correspondencia-oferta-e-necessidade.md) (`RF016` — rascunho)**, **[16-agendamento-da-retirada.md](16-agendamento-da-retirada.md) (`RF018` — rascunho)** e **[18-confirmacao-de-retirada-e-entrega.md](18-confirmacao-de-retirada-e-entrega.md) (`RF020` — rascunho)**. **Depende de spec futura (v1.1):** **RF021** (Denúncia e Moderação — PRD Questão 16). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md). |

---

## 2. Objetivo e escopo

Permitir que doador e solicitante (com correspondência aceita no RF016) troquem mensagens de texto simples dentro da plataforma para combinar a retirada sem expor telefone, e-mail, endereço ou links, com identificação reduzida, ciclo de vida fechado (somente leitura após entrega ou cancelamento), imutabilidade das mensagens e bloqueio imediato entre usuários.

### Inclui

- Conversa vinculada 1:1 à `Correspondencia` aceita (RF016), acessível exclusivamente às duas partes (`doador` e `solicitante`; HTTP 404 para qualquer outro usuário).
- Envio de mensagens em **texto puro de até 500 caracteres**, **sem anexos nem links**, com escape HTML estrito do Django (proteção XSS — RS005) e validação no servidor que **detecta e bloqueia telefone, e-mail, endereço/CEP, links/URLs e pedidos de pagamento/Pix/dinheiro** (RS014), exibindo a mensagem literal **`"Não é permitido compartilhar telefone, e-mail, endereço ou links"`**.
- **Identificação reduzida** das partes no formato **`Primeiro nome + inicial do sobrenome`** (ex.: `"Maria S."`) acompanhado do papel (`"Doador"` / `"Solicitante"`), sem nome completo, telefone, e-mail ou endereço (RS002).
- Status `enviada` e `lida`, atualizando para `lida` ao abrir a conversa; envio de notificação `nova_mensagem` via `NotificacaoService` **sem jamais incluir o texto da mensagem** no corpo do e-mail ou da notificação (RF017 regra 3, RF019 regra 2, RS014).
- Ciclo de vida da conversa: ativa entre o aceite da correspondência (RF016) e a confirmação da entrega (RF020) ou o cancelamento/expiração/não comparecimento (RF016/RF018); encerrada, passa a **somente leitura** (`"Esta conversa foi encerrada"`).
- **Imutabilidade:** mensagens nunca são editadas nem apagadas (`on_delete=PROTECT` + ausência de endpoints de edição/exclusão).
- **Bloqueio de usuário** (`BloqueioUsuario` — RF019 regra 5, RS008, RS014): encerra imediatamente a conversa em somente leitura, cancela eventual correspondência/agendamento em aberto entre os dois (devolvendo doação a `disponivel` e solicitação a `aberta`) e impede novas correspondências futuras entre o par; para `"Denunciar conversa"`, o MVP exibe aviso `"Canal de denúncia disponível em breve (v1.1)"` com orientação de bloqueio imediato e contato administrativo (substituído pelo fluxo real do RF021 na v1.1).
- Aviso permanente na tela de que a confirmação oficial do agendamento acontece no fluxo do **RF018**, nunca por mensagem (RS008).
- Pesquisa das próprias conversas por **correspondência e período**.

### Não inclui

- Envio de arquivos, imagens, áudios ou links externos (expressamente proibido — RF019 regra 1, RS014).
- Chat em tempo real por WebSocket (templates renderizados no servidor com atualização manual/simples — ADRs 0001 e 0006, RNF08).
- Fluxo completo de denúncia e leitura moderada por `moderacao_denuncias` (v1.1 — RF021).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Doador / Solicitante / Cuidador/Familiar (partes da correspondência)** | Listar/pesquisar suas conversas, ler mensagens (marcando como `lida`), enviar mensagens de texto (≤ 500 caracteres) enquanto a conversa estiver ativa e bloquear a outra parte. | Conta ativa autenticada (RF002) e participação na `Correspondencia` aceita (RF016). |
| **Administrador (`moderacao_denuncias`, v1.1)** | Consultar o histórico da conversa **exclusivamente quando houver denúncia vinculada (RF021)**, limitado ao necessário e registrado em `AuditoriaService` (RNF10, RS015). | Especificado em detalhe na spec do RF021 (v1.1); fora de acesso para qualquer outra função no MVP. |

---

## 4. Fluxos

### 4.1 Fluxo principal — Envio e leitura de mensagens

1. A conversa nasce automaticamente (`status = ativa`) no momento em que a `Correspondencia` passa para `aceita` (RF016).
2. Uma das partes abre `correspondencias:conversa_detalhe`. `MensagemService.abrir_conversa(conversa_id, usuario)` verifica participação (404 caso contrário) e marca como `lida` (`lida_em = agora`) as mensagens recebidas ainda `enviada`.
3. O usuário digita o texto (máx. 500 caracteres) e aciona **Enviar** (`POST` com CSRF).
4. `MensagemService.enviar_mensagem(conversa_id, remetente, texto)`:
   - Verifica participação (404) e que `conversa.status == ativa` (se encerrada, bloqueia exibindo `"Esta conversa foi encerrada"`) e ausência de `BloqueioUsuario` entre as partes;
   - Rejeita texto vazio/só espaços exibindo **`"Digite uma mensagem"`** e texto > 500 caracteres;
   - Executa `validador_conteudo_seguro(texto)` detectando padrões de telefone/WhatsApp, e-mail, URLs/domínios, endereços (CEP/logradouro) e termos de pagamento/Pix/cobrança; em caso de detecção, **bloqueia o envio** exibindo **`"Não é permitido compartilhar telefone, e-mail, endereço ou links"`** (e aviso específico de proibição de cobrança/comércio quando detectar pedido de pagamento — RS006/RS014);
   - Dentro de `transaction.atomic()`, persiste `Mensagem` (`status = enviada`), grava `mensagem.enviada` na auditoria (apenas IDs, **nunca o texto**) e agenda `nova_mensagem` via `NotificacaoService` para a outra parte (**sem o texto da mensagem**).
5. Redireciona (PRG) para a conversa exibindo a nova mensagem com identificação reduzida.

### 4.2 Fluxos alternativos

- **FA-01 — Encerramento automático da conversa:** ao confirmar a entrega (RF020) ou cancelar/expirar o agendamento/correspondência (RF016/RF018), `MensagemService.encerrar_conversa(...)` dentro da mesma transação muda `Conversa.status = encerrada`; ambas as partes continuam podendo ler o histórico em modo somente leitura, mas o campo de envio é bloqueado com **`"Esta conversa foi encerrada"`**.
- **FA-02 — Bloqueio de usuário (`correspondencias:bloquear_usuario`):** qualquer parte pode acionar `"Bloquear usuário"` (`POST` com CSRF e confirmação); grava `BloqueioUsuario`, encerra imediatamente a conversa em somente leitura, cancela eventual correspondência/agendamento em aberto entre os dois (devolvendo doação a `disponivel` e solicitação a `aberta`), impede novas correspondências futuras entre o par e registra `usuario.bloqueio_p2p` em `AuditoriaService`.
- **FA-03 — Pesquisa das próprias conversas (`correspondencias:conversas_lista`):** filtra por correspondência e período (`criado_em`), exibindo contador de mensagens não lidas.

### 4.3 Fluxos de exceção

- **FE-01 — Mensagem vazia:** exibe **`"Digite uma mensagem"`**.
- **FE-02 — Mensagem contendo telefone, e-mail, endereço, link ou pedido de pagamento:** bloqueada no servidor exibindo **`"Não é permitido compartilhar telefone, e-mail, endereço ou links"`**.
- **FE-03 — Envio em conversa encerrada:** bloqueado exibindo **`"Esta conversa foi encerrada"`**.
- **FE-04 — Terceiro (inclusive Administrador sem denúncia RF021) tenta acessar a conversa:** recebe HTTP 404 (usuário comum) ou 403 (Admin).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-17-01** | Somente **texto puro de até 500 caracteres**, sem anexos e sem links. O servidor detecta e bloqueia telefone, e-mail, endereço, links e pedidos de pagamento (RS014). As partes são exibidas com **identificação reduzida** (sem nome completo, telefone, e-mail ou endereço — RS002). | RF019 (regra 1), RS002, RS014 • `correspondencias` |
| **RN-17-02** | Status da mensagem: `enviada` ou `lida`. O destinatário recebe aviso `nova_mensagem` (RF017), **sem o conteúdo da mensagem**. | RF019 (regra 2), RF017 (regra 3), RS014 • `correspondencias`, `notificacoes` |
| **RN-17-03** | A conversa permanece `ativa` entre o aceite da correspondência (RF016) e a confirmação da entrega (RF020) ou o cancelamento/expiração (RF018/RF016); após isso, fica **somente leitura** (`"Esta conversa foi encerrada"`). | RF019 (regra 3), RS014 • `correspondencias` |
| **RN-17-04** | Mensagens **não podem ser editadas nem apagadas** (`on_delete=PROTECT`). Acesso restrito às duas partes e, apenas quando houver denúncia vinculada (RF021 — v1.1), ao moderador (`moderacao_denuncias` + 2FA), limitado ao necessário (RNF10). | RF019 (regra 4), RNF10, RNF14 • `correspondencias` |
| **RN-17-05** | Cada parte pode **bloquear a outra** (encerrando a conversa, cancelando correspondência/agendamento em aberto entre o par e impedindo novos cruzamentos futuros); o link `"Denunciar conversa"` aponta no MVP para aviso de disponibilidade na v1.1 com orientação de bloqueio/contato (virando o fluxo real no RF021). A confirmação oficial do agendamento ocorre **sempre no RF018**, nunca por mensagem. | RF019 (regra 5), RS008, RS014 • `correspondencias` |

---

## 6. Modelo de dados lógico

#### `Conversa` (app `correspondencias`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `correspondencia` | OneToOne (`Correspondencia`, `PROTECT`) | Sim | Uma conversa por correspondência aceita. |
| `status` | TextChoices (indexado) | Sim | `ativa`, `encerrada`. |
| `encerrada_em` | Datetime, anulável | Não | |
| `criado_em` | Datetime (indexado) | Sim | |

#### `Mensagem` (app `correspondencias` — `append-only`, `on_delete=PROTECT`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `conversa` | FK (`Conversa`, `PROTECT`, indexado) | Sim | |
| `remetente` | FK (`Usuario`, `PROTECT`) | Sim | Deve ser o doador ou o solicitante da correspondência. |
| `texto` | String (500) | Sim | Texto puro (`CheckConstraint(length(trim(texto)) >= 1)`). |
| `status` | TextChoices | Sim | `enviada`, `lida`. |
| `enviada_em` | Datetime (indexado) | Sim | |
| `lida_em` | Datetime, anulável | Não | |

#### `BloqueioUsuario` (app `correspondencias`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `bloqueador` | FK (`Usuario`, `PROTECT`, indexado) | Sim | |
| `bloqueado` | FK (`Usuario`, `PROTECT`, indexado) | Sim | `UniqueConstraint(bloqueador, bloqueado)` e `CheckConstraint(bloqueador != bloqueado)`. |
| `criado_em` | Datetime | Sim | |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`correspondencias`):** `MinhasConversasListaView` + `ConversaFiltroForm` (`GET`), `ConversaDetalheView` (`GET`/`POST` via `MensagemForm`), `BloquearUsuarioView` (`POST`).
- **Services (`MensagemService`):** `criar_para_correspondencia`, `abrir_conversa`, `enviar_mensagem`, `validar_conteudo_seguro`, `encerrar_conversa`, `bloquear_usuario`, `listar_conversas`.
- **Templates:** `conversas_lista.html` e `conversa_detalhe.html` (contador de caracteres `0/500` em JS simples, aviso de que o agendamento é confirmado no RF018, aviso de proibição de dados de contato/pagamentos, botão `"Bloquear usuário"`).
- **Rotas:** `correspondencias:conversas_lista`, `correspondencias:conversa_detalhe`, `correspondencias:bloquear_usuario`.

---

## 8. Mensagens e validações

Textos literais exigidos pela fonte (RF019):

| Condição | Mensagem literal |
| --- | --- |
| Mensagem vazia | `"Digite uma mensagem"` |
| Detecção de telefone, e-mail, endereço, links (ou pedido de pagamento) | `"Não é permitido compartilhar telefone, e-mail, endereço ou links"` |
| Tentativa de envio após encerramento da conversa | `"Esta conversa foi encerrada"` |

---

## 9. Segurança e privacidade

- **RS014 (OWASP A03/A06):** bloqueio de contatos externos, links e pedidos de pagamento no servidor; proibição de anexos; escape automático contra XSS; notificações sem conteúdo da mensagem; conversa encerrada automaticamente.
- **RS002 & RS008 (OWASP A01):** identificação reduzida; controle por objeto (apenas as 2 partes — 404 para terceiros); bloqueio imediato entre usuários; confirmação formal separada no RF018.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** interface limpa e legível com contraste AA e aviso de segurança claro.
- **RNF04, RNF07, RNF08:** páginas leves em HTML renderizado no servidor, baixo consumo em 3G/4G.
- **RNF10 & RNF14:** mensagens imutáveis, sem conteúdo em auditoria/e-mails, acesso administrativo apenas sob denúncia (RF021).

---

## 11. Critérios de aceite

1. **CA-17-01 (Envio, leitura e notificação sem conteúdo — RN-17-01, RN-17-02):** Doador envia texto válido (≤ 500 chars); mensagem nasce `enviada`, solicitante recebe notificação `nova_mensagem` **sem o texto**, e ao abrir a conversa a mensagem passa para `lida`.
2. **CA-17-02 (Mensagens literais de validação — RF019 Mensagens):** Envio vazio retorna `"Digite uma mensagem"`; mensagem com telefone, e-mail, URL ou pedido de Pix é bloqueada retornando `"Não é permitido compartilhar telefone, e-mail, endereço ou links"`; envio após encerramento retorna `"Esta conversa foi encerrada"`.
3. **CA-17-03 (Imutabilidade e isolamento de acesso — RN-17-04):** Não existem rotas de edição/exclusão de mensagem; terceiro (ou Admin sem denúncia RF021) recebe HTTP 404/403 ao tentar abrir a conversa.
4. **CA-17-04 (Bloqueio entre usuários — RN-17-05):** Ao bloquear a outra parte, a conversa é encerrada imediatamente e o par bloqueado não gera novas correspondências.

---

## 12. Plano de testes

- **Unidade (`MensagemService`, `validar_conteudo_seguro`):** bloqueio de telefones (formatos BR com/sem DDD), e-mails, URLs (`http`, `www`, domínios), CEPs/endereços, termos de Pix/pagamento; rejeição de vazio e > 500 caracteres; encerramento automático; criação de `BloqueioUsuario` impedindo novos cruzamentos no RF016.
- **Integração (Views/Segurança):** 404 para terceiros, ausência de nome completo/contatos no HTML renderizado, escape de payload `<script>` (XSS), e verificação de que o outbox do RF017 não contém o texto da mensagem.

---

## 13. Questões em aberto

Nenhuma questão em aberto bloqueante para o MVP. O fluxo completo de denúncia de conversas entra na Spec `21` (`RF021` — v1.1).
