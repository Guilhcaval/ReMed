# Spec 13 — Fluxo para Medicamentos Sujeitos a Receita (RF014)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `13` — Fluxo para Medicamentos Sujeitos a Receita (`RF014`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF014 (Essencial — MVP, HU14). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF08, RNF10 (Essencial — LGPD/dados sensíveis de saúde), RNF11 (Essencial — Portaria SVS/MS nº 344/1998), RNF13 (Essencial), RNF14 (Essencial), RNF16. **Segurança:** RS002, RS003, RS013, RS015. |
| **Apps envolvidos** | `solicitacoes` (principal: `ReceitaMedica`, `VerificacaoReceita`, `ReceitaService`), `nucleo` (`ArquivoService` da ADR 0016, mixins de permissão `verificacao_receitas` + 2FA), `auditoria` (`AuditoriaService` — sem jamais gravar conteúdo da receita em `detalhes`), `notificacoes` (`NotificacaoService`), `correspondencias` (bloqueio de correspondência sem receita `valida` — RF016 — e conferência de quem retira — RF020). |
| **Dependências de outras specs** | **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)**, **[04-gestao-de-usuarios-administrador.md](04-gestao-de-usuarios-administrador.md) (`RF004` — proibição de combinar `gestao_usuarios` + `verificacao_receitas`)**, **[06-envio-documentos-ponto-de-coleta.md](06-envio-documentos-ponto-de-coleta.md) (`RF006` — `ArquivoService`)** e **[12-cadastro-de-solicitacao.md](12-cadastro-de-solicitacao.md) (`RF013` — rascunho)**. **Depende de specs ainda não escritas:** **RF016** (só gera correspondência para medicamento sujeito a receita quando `ReceitaMedica.status == valida`) e **RF020** (conferência na retirada de que quem retira é `pessoa_retirada` informada no RF013). **Pendências críticas:** **Pendência com o professor** (Questões 6 e 7 do PRD — quem verifica receitas, prazo vencido em 10/11/2026) e pendência externa de LGPD (Questão 8 do PRD — prazo de eliminação de receitas na Política de Privacidade). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0016](../adr/0016-armazenamento-seguro-de-arquivos.md). |

---

## 2. Objetivo e escopo

Exigir, proteger como dado sensível de saúde (LGPD) e verificar a receita médica antes de liberar a correspondência (RF016) e a retirada (RF020) de medicamentos sujeitos a prescrição, bloqueando expressamente prescrições de controle especial (Portaria SVS/MS nº 344/1998 — RS003, RNF11) e assegurando o isolamento estrito de acesso definido na [ADR 0010](../adr/0010-perfis-e-permissoes.md).

### Inclui

- Envio obrigatório da receita (`JPG`, `PNG` ou `PDF`, máx. 5 MB) e da **data de emissão da receita** para toda solicitação de medicamento sujeito a receita (RF013), processado pelo **`ArquivoService`** ([ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md): *magic bytes*, remoção de EXIF/GPS via `Pillow >= 12.0`, interface antimalware, nome interno UUID em Object Storage privado com SSE, acesso exclusivo por URL pré-assinada de **60 segundos** com auditoria de envio e **de cada leitura**).
- Autodeclaração bloqueante no envio (*acréscimo da especificação*, alinhado ao RF008) e bloqueio explícito na verificação contra prescrições de **controle especial** (RS003, RNF11).
- Fila isolada de verificação acessível **exclusivamente** a usuários com função administrativa explícita **`verificacao_receitas`** (+ 2FA TOTP), **tecnicamente incompatível com `gestao_usuarios`** ([ADR 0010](../adr/0010-perfis-e-permissoes.md) — implementação técnica adotada enquanto a definição humana/organizacional do verificador permanece como **pendência com o professor**, Questões 6 e 7 do PRD).
- Verificação dos requisitos mínimos da receita: medicamento compatível, data de emissão, profissional prescritor e assinatura, registrando resultado **`valida`** ou **`invalida`** (com observação/motivo) em `VerificacaoReceita` (`append-only`) e `RegistroAuditoria`.
- Bloqueio total de acesso da receita ao **doador**, a visitantes e a qualquer Administrador sem `verificacao_receitas` (inclusive `gestao_usuarios`, `conferencia_doacoes`, `auditoria` e `is_superuser` sem função explícita — RS002, RS013, RS015).
- Gancho de regra para RF016 (nenhuma correspondência para medicamento sujeito a receita sem `status_verificacao == valida`) e RF020 (quem retira deve ser `pessoa_retirada` informada no RF013).
- Aviso obrigatório RNF13 (a plataforma não substitui avaliação médica ou farmacêutica).

### Não inclui

- Fluxo especial para medicamentos de controle especial / retenção de receita (expressamente bloqueado nesta versão — RS003, RNF11).
- Expurgo automático de receitas antigas por prazo LGPD (a rotina de eliminação será ativada assim que o prazo for definido na Política de Privacidade — Questão 8 do PRD).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Solicitante / Cuidador/Familiar** | Anexar receita médica e data de emissão em solicitação de medicamento sujeito a receita (RF013); acompanhar apenas os **metadados seguros** da verificação (data de envio, data de emissão e status `pendente`, `valida` ou `invalida` — sem reabrir o arquivo após envio) e reenviar nova versão se `invalida` (*acréscimo da especificação*). | Conta ativa, e-mail confirmado, perfil `Solicitante` ou `Cuidador/Familiar`. |
| **Verificador (`verificacao_receitas`)** | Listar fila de receitas `pendente`, visualizar a imagem/PDF via URL pré-assinada 60 s (com registro de leitura na auditoria) e marcar como `valida` ou `invalida` com observação. | Conta administrativa ativa com função explícita **`verificacao_receitas`** (nunca combinada com `gestao_usuarios` — [ADR 0010](../adr/0010-perfis-e-permissoes.md)) e sessão com 2FA TOTP concluído. *(Papel organizacional definitivo é **pendência com o professor** — Questões 6 e 7 do PRD.)* |

---

## 4. Fluxos

### 4.1 Fluxo principal — Envio e verificação de receita médica

1. Ao cadastrar uma solicitação sujeita a receita (RF013), o solicitante/cuidador informa a **Data de emissão da receita**, confirma a autodeclaração de que não se trata de medicamento de controle especial (*acréscimo da especificação*) e anexa o arquivo (`JPG`, `PNG` ou `PDF`, máx. 5 MB).
2. `ReceitaService.anexar(...)` valida formato/tamanho/*magic bytes*/EXIF/antimalware via `ArquivoService`, grava no storage privado com chave UUID (`receitas/<uuid>.<ext>`), cria `ReceitaMedica` com `status = pendente` e registra `receita.enviada` (e `arquivo.enviado`) em `AuditoriaService` (**sem jamais gravar nome do medicamento clínico, prescrição ou texto da receita nos detalhes da auditoria** — ADR 0011).
3. A solicitação permanece `aberta`, porém **bloqueada para correspondência no RF016** enquanto não houver receita `valida`.
4. O Verificador (`verificacao_receitas` + 2FA) acessa `solicitacoes:admin_receitas_lista`, abre um item `pendente` em `solicitacoes:admin_receita_detalhe` e solicita a visualização da receita em `solicitacoes:admin_receita_acessar`.
5. `ReceitaService.gerar_acesso_temporario(ator, receita_id)` confere `verificacao_receitas` + 2FA, grava `arquivo.acessado` (`receita_id`, `ator_id`, timestamp) em `AuditoriaService` (RS013 solução 5) e retorna redirect para URL pré-assinada de **60 segundos**.
6. O Verificador confere presença de **medicamento compatível**, **data de emissão**, **profissional prescritor**, **assinatura** e **ausência de controle especial** (RS003), escolhe `valida` ou `invalida`, informa **Observação** (obrigatória em `invalida`) e envia via `POST` com CSRF.
7. Dentro de `transaction.atomic()` com `select_for_update()`:
   - Grava `VerificacaoReceita` (`append-only`), atualiza `ReceitaMedica.status` e grava `receita.verificada` na auditoria (apenas IDs e resultado, sem conteúdo sensível);
   - Se `valida`: notifica o solicitante (`receita_verificada`, RF017 — sem expor dados sensíveis no e-mail, RS002/RS014) e libera a solicitação para o cruzamento automático do RF016;
   - Se `invalida`: notifica o solicitante (`receita_verificada`, RF017) com mensagem neutra segura no e-mail e exibe o motivo na plataforma, permitindo o **reenvio versionado de nova receita** na mesma solicitação `aberta` (*acréscimo da especificação*, sem excluir a versão anterior, voltando a `pendente`).

### 4.2 Fluxos de exceção

- **FE-01 — Receita de medicamento de controle especial (Portaria SVS/MS nº 344/1998):** bloqueada na autodeclaração do cadastro ou marcada como `invalida` pelo verificador com indicação de que medicamentos de controle especial não são aceitos nesta versão (RS003, RNF11).
- **FE-02 — Doador, visitante ou Administrador sem `verificacao_receitas` tenta acessar qualquer rota de receita:** recebe HTTP 403 (ou 404 para usuários comuns), **nunca** recebendo URL ou metadados da receita.
- **FE-03 — Arquivo inválido (> 5 MB, *magic bytes* fora de JPG/PNG/PDF ou bloqueado por antimalware):** rejeitado pelo `ArquivoService` sem gravar no storage.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-13-01** | A receita deve conter: **medicamento**, **data de emissão**, **profissional prescritor** e **assinatura**. Prescrições de **controle especial** (Portaria SVS/MS nº 344/1998) ficam **bloqueadas** nesta versão. | RF014 (regra 1), RS003, RNF11 • `solicitacoes` |
| **RN-13-02** | Status válidos da verificação: **`pendente`**, **`valida`** ou **`invalida`**. A correspondência (RF016) de qualquer medicamento sujeito a receita **só ocorre quando a receita está `valida`**. | RF014 (regra 2), RS003 • `solicitacoes`, `correspondencias` |
| **RN-13-03** | O acesso de verificação é restrito à função administrativa isolada **`verificacao_receitas`** (+ 2FA), **tecnicamente incompatível com `gestao_usuarios`** ([ADR 0010](../adr/0010-perfis-e-permissoes.md)). A definição de quem (papel humano/profissional) exerce essa função permanece como **pendência com o professor** (Questões 6 e 7 do PRD). | RF014 (regra 3), RS015, [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `solicitacoes`, `contas` |
| **RN-13-04** | A receita é **dado sensível de saúde (LGPD — RNF10)**: armazenada criptografada (SSE) com nome aleatório UUID fora de diretório público ([ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md)), acessível apenas por URL pré-assinada de **60 segundos** com auditoria de envio e **de cada leitura**, visível **exclusivamente ao verificador** (`verificacao_receitas` + 2FA) — o solicitante visualiza apenas metadados seguros (data de envio, data de emissão e status), **nunca** o arquivo após o envio, e o doador e demais Administradores **nunca** têm acesso —, ficando o esquema preparado (`expurgada_em`, `arquivo_chave` anulável) para eliminação futura conforme o prazo da Política de Privacidade (Questão 8 do PRD). | RF014 (regra 4), RNF10, RNF16, RS002, RS013, [ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md) • `solicitacoes`, `nucleo`, `auditoria` |
| **RN-13-05** | Na retirada (RF020) de medicamento sujeito a receita, quem retira **deve ser a pessoa informada na solicitação** (`Solicitacao.pessoa_retirada` — RF013). | RF014 (regra 5), RF013, RF020, RS003 • `correspondencias` |
| **RN-13-06** | O sistema **não substitui avaliação médica ou farmacêutica** (aviso visível no envio e na verificação — RNF13). | RF014 (regra 6), RNF13 • `solicitacoes` |
| **RN-13-07** | Todo envio, leitura e verificação gera registro imutável em `VerificacaoReceita` e `RegistroAuditoria` (`on_delete=PROTECT`), **nunca** registrando imagem, prescrição ou conteúdo de saúde em `detalhes` ou logs ([ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)). | RNF14, RS002, RS013, [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `solicitacoes`, `auditoria` |

---

## 6. Modelo de dados lógico

#### `ReceitaMedica` (app `solicitacoes`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `solicitacao` | FK (`Solicitacao`, `PROTECT`, indexado) | Sim | Suporta versionamento quando o solicitante reenvia após `invalida` (*acréscimo da especificação*). |
| `versao` | PositiveInteger | Sim | `UniqueConstraint(solicitacao, versao)`. |
| `arquivo_chave` | String (255, único, anulável) | Sim* | Chave UUID (`receitas/<uuid>.<ext>`); pode ficar `NULL` apenas quando expurgada futuramente conforme prazo da Política de Privacidade (mantendo o histórico de auditoria). |
| `mime_verificado` / `tamanho_bytes` | String (60) / PositiveInteger | Sim | `PDF`/`JPG`/`PNG`, `<= 5242880`. |
| `data_emissao` | Date | Sim | Data de emissão da receita (não aceita data futura). |
| `status` | TextChoices (indexado) | Sim | `pendente`, `valida`, `invalida`. Padrão: `pendente`. |
| `enviada_em` | Datetime | Sim | |
| `expurgada_em` | Datetime, anulável | Não | Preenchido pela futura rotina de retenção LGPD (Questão 8 do PRD). |

#### `VerificacaoReceita` (app `solicitacoes` — `append-only`, `on_delete=PROTECT`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `receita` | FK (`ReceitaMedica`, `PROTECT`, indexado) | Sim | |
| `resultado` | TextChoices | Sim | `valida`, `invalida`. |
| `observacao` | Text | Condicional | Obrigatória se `invalida` (`CheckConstraint`); nunca exibida em e-mails (só na plataforma se destinada ao solicitante). |
| `responsavel` | FK (`Usuario`, `PROTECT`) | Sim | Usuário com função `verificacao_receitas`. |
| `verificada_em` | Datetime (indexado) | Sim | Timestamp UTC. |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`solicitacoes`):**
  - Verificador (`verificacao_receitas` + 2FA): `AdminReceitaListaView` (`GET`), `AdminReceitaDetalheView` (`GET`), `AdminReceitaAcessarView` (`GET` → URL pré-assinada 60 s + auditoria), `AdminReceitaVerificarView` + `VerificacaoReceitaForm` (`POST`).
  - Solicitante/Cuidador: envio integrado ao RF013 e `SolicitacaoReceitaReenviarView` (`POST`, *acréscimo da especificação*, para nova versão após `invalida`).
- **Services (`ReceitaService`):** `anexar`, `gerar_acesso_temporario`, `registrar_verificacao`, `possui_receita_valida(solicitacao)` — transacionais com `select_for_update`, `ArquivoService`, `AuditoriaService` e `NotificacaoService`.
- **Templates:** `admin_receitas_lista.html`, `admin_receita_detalhe.html` (aviso RNF13, checklist dos 4 itens do RF014 regra 1 + alerta de bloqueio de controle especial, link de abertura segura 60 s).
- **Rotas:** `solicitacoes:admin_receitas_lista` (`/admin-remed/receitas/`), `solicitacoes:admin_receita_detalhe` (`/admin-remed/receitas/<int:receita_id>/`), `solicitacoes:admin_receita_acessar` (`/admin-remed/receitas/<int:receita_id>/acessar/`), `solicitacoes:admin_receita_verificar` (`/admin-remed/receitas/<int:receita_id>/verificar/`).

---

## 8. Mensagens e validações

- Formato/tamanho inválido: `"Envie a receita em PDF, JPG ou PNG"` / `"O arquivo deve ter no máximo 5 MB"`;
- Data de emissão futura: `"A data de emissão da receita não pode ser posterior à data atual"`;
- Medicamento de controle especial: `"Medicamentos de controle especial (Portaria SVS/MS nº 344/1998) não são aceitos nesta versão da plataforma"`;
- E-mail de notificação ao solicitante: texto neutro sem mencionar nome do medicamento ou conteúdo da receita (RS002/RS014 — *"O status da verificação da sua solicitação foi atualizado. Acesse a plataforma para consultar."*).

---

## 9. Segurança e privacidade

- **RS002 & RNF10 (OWASP A01/A04):** receita é dado sensível de saúde; proibição de exposição ao doador, a outros Administradores, em e-mails ou em `RegistroAuditoria.detalhes`.
- **RS003 (OWASP A06):** bloqueio de correspondência sem receita `valida`, bloqueio de controle especial e conferência de `pessoa_retirada` na entrega (RF020).
- **RS013 (OWASP A01/A05/A08/A09):** validação rigorosa + remoção de EXIF/GPS + antimalware + UUID + SSE + URL pré-assinada 60 s + auditoria de envio e **de cada leitura**.
- **RS015 (OWASP A01/A07):** segregação de função (`verificacao_receitas` incompatível com `gestao_usuarios` + 2FA obrigatório).

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** orientações claras ao solicitante e checklist explícito ao verificador (WCAG 2.1 AA).
- **RNF10, RNF11, RNF13, RNF14, RNF16:** aplicados rigorosamente conforme seções acima.

---

## 11. Critérios de aceite

1. **CA-13-01 (Bloqueio de correspondência sem receita válida — RN-13-02):** Dada uma solicitação sujeita a receita com `ReceitaMedica.status` em `pendente` ou `invalida`, `ReceitaService.possui_receita_valida` retorna `False` e o RF016 não gera correspondência; após marcação como `valida`, retorna `True` e libera correspondência.
2. **CA-13-02 (Segregação absoluta de acesso — RN-13-03, RN-13-04):** Doador, solicitante de outra conta, visitante e Administradores com `gestao_usuarios`, `conferencia_doacoes`, `auditoria` ou `is_superuser` sem `verificacao_receitas` recebem HTTP 403/404 ao acessar qualquer rota de receita; apenas `verificacao_receitas` (+ 2FA) obtém URL pré-assinada de 60 s e grava `arquivo.acessado` na auditoria.
3. **CA-13-03 (Bloqueio de controle especial — RN-13-01):** Prescrição marcada como controle especial na autodeclaração é bloqueada no cadastro; prescrição identificada como controle especial pelo verificador é marcada como `invalida` sem liberar correspondência.
4. **CA-13-04 (Zero vazamento em auditoria e e-mails — RN-13-07):** Os registros em `RegistroAuditoria` e o corpo do e-mail no outbox do RF017 não contêm imagem, URL da receita, nome do médico, diagnóstico ou conteúdo da prescrição.

---

## 12. Plano de testes

- **Unidade (`ReceitaService`, `ReceitaMedica`, `VerificacaoReceita`):** upload via `ArquivoService` (PDF/JPG/PNG, ≤ 5 MB, remoção EXIF/GPS, antimalware *fail-closed*); rejeição de data de emissão futura; `possui_receita_valida` para `pendente`/`valida`/`invalida`; auditoria sem dados sensíveis; notificação de e-mail neutra.
- **Integração (Views/Permissões):** matriz completa de acesso testando todos os perfis e todas as 8 funções administrativas (garantindo que apenas `verificacao_receitas` + 2FA acessa); geração de URL pré-assinada 60 s + registro `arquivo.acessado`; verificação registrando `VerificacaoReceita`.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Quem verifica receitas (Questões 6 e 7 do PRD — prazo vencido em 10/11/2026):** definir formalmente qual pessoa/profissional humano exerce o papel de verificador. | **Pendência com o professor** (Cliente / Ata) | Não bloqueia tecnicamente o MVP; implementado via função isolada **`verificacao_receitas`** (+ 2FA, incompatível com `gestao_usuarios` conforme ADR 0010). |
| 2 | **Prazo de eliminação/expurgo LGPD das receitas (Questão 8 do PRD):** ainda não definido na Política de Privacidade. | Pendência externa (Cliente / Jurídico) | Esquema já preparado (`expurgada_em` e `arquivo_chave` anulável); rotina de expurgo será ativada após definição legal do prazo. |
