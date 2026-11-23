# Spec 20 — Recuperação de Senha (RF003 — v1.1)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `20` — Recuperação de Senha (`RF003` — **v1.1**) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF003 (Importante — **v1.1**, HU03). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF14 (Essencial), RNF15. **Segurança:** RS005, RS012. |
| **Apps envolvidos** | `contas` (principal: `TokenRecuperacaoSenha`, `RecuperacaoSenhaService`, views substituindo o aviso provisório da Spec `02`), `notificacoes` (`NotificacaoService` — e-mails de `seguranca_conta` nunca limitados por cota), `auditoria` (`AuditoriaService`). |
| **Dependências de outras specs** | **[01-cadastro-de-usuario.md](01-cadastro-de-usuario.md) (`RF001`)**, **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002` — substitui o placeholder `"Esqueci minha senha"`)** e **[03-notificacoes.md](03-notificacoes.md) (`RF017` — e-mails críticos de segurança)**. **Pendência externa:** Questão 13 do PRD (confirmar limite sugerido de 5 pedidos por hora). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0007](../adr/0007-modelo-de-usuario-customizado.md), [0008](../adr/0008-hash-de-senha-argon2-ou-bcrypt.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md). |

---

## 2. Objetivo e escopo

Permitir que qualquer usuário cadastrado com e-mail confirmado redefina sua senha esquecida por meio de um link de uso único válido por **1 hora** enviado exclusivamente ao e-mail cadastrado, sem revelar se um e-mail existe na base (RS012), encerrando todas as sessões ativas após a redefinição e registrando todas as tentativas (sucesso e falha) na auditoria.

### Inclui

- Substituição do aviso provisório do link `"Esqueci minha senha"` (Spec `02`) pelo fluxo completo em `contas:recuperar_senha` e `contas:redefinir_senha`.
- Solicitação por e-mail com **resposta única e idêntica** exista ou não o e-mail informado (`"Se o e-mail estiver cadastrado, você receberá as instruções para redefinir a senha"` — RS012).
- Geração de token criptograficamente aleatório (`secrets.token_urlsafe(32)`), armazenado **apenas como hash SHA-256** em `TokenRecuperacaoSenha`, válido por **1 hora**, de **uso único** e invalidando automaticamente qualquer token anterior pendente da mesma conta.
- Limite configurável de **5 solicitações por hora por e-mail e por IP** (`RECUPERACAO_SENHA_LIMITE_POR_HORA = 5` em `settings` — RS012).
- Para contas `suspensa`, `bloqueada` ou `inativa`, nenhum link é enviado, preservando resposta neutra na tela (RS012).
- Redefinição de senha aplicando política do RF001 (mín. 8 caracteres, letra + número, Argon2id — ADR 0008) e **bloqueando reutilização da senha atual** (RF003 regra 3).
- Encerramento imediato de **todas as sessões ativas** do usuário no PostgreSQL (`backends.db` — ADR 0009) e envio de e-mail crítico de `seguranca_conta` avisando que a senha foi alterada (RF017).
- Registro imutável de todas as solicitações e redefinições (sucesso e falha) em `RegistroAcesso` / `AuditoriaService` (sem jamais gravar o token em claro ou a senha — ADR 0011).

### Não inclui

- Recuperação via SMS ou WhatsApp (canais desejáveis não adotados nesta fase — RF017).
- Reset de 2FA do Administrador (já coberto via outro Administrador com step-up 2FA na Spec `04`).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Qualquer usuário cadastrado** (`Doador`, `Solicitante`, `Cuidador/Familiar`, `Representante`, `Administrador`) | Solicitar link de recuperação por e-mail e definir nova senha dentro de 1 hora. | Conta cadastrada (`RF001`), `email_confirmado_em` preenchido e status `ativo` (contas `suspensa`, `bloqueada` ou `inativa` não recebem link, mantendo resposta neutra na tela). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Solicitação e redefinição

1. O usuário clica em `"Esqueci minha senha"` na tela de login (`contas:login`) e informa seu **E-mail** (`POST` com CSRF).
2. `RecuperacaoSenhaService.solicitar(email, ip_origem)`:
   - Normaliza o e-mail, registra tentativa em `RegistroAcesso` e verifica limite por e-mail e por IP (`5/hora`);
   - Se o limite não foi excedido e existir usuário elegível (`ativo` e e-mail confirmado): dentro de `transaction.atomic()`, invalida tokens anteriores não usados, cria `TokenRecuperacaoSenha` com `token_hash = sha256(token)` e `expira_em = agora + 1 hora`, registra `usuario.recuperacao_solicitada` na auditoria e enfileira e-mail crítico (`seguranca_conta`) no outbox com o link de uso único;
   - Retorna sempre sucesso neutro; a view exibe literalmente **`"Se o e-mail estiver cadastrado, você receberá as instruções para redefinir a senha"`**.
3. O usuário acessa o link recebido (`contas:redefinir_senha`), informa **Nova senha** e **Confirmação da nova senha** e envia (`POST` com CSRF).
4. `RecuperacaoSenhaService.redefinir(token_em_claro, nova_senha, ip_origem)`:
   - Calcula `sha256(token_em_claro)` e busca token válido (`usado_em IS NULL`, `invalidado_em IS NULL`, `expira_em >= agora`) sob `transaction.atomic()` + `select_for_update()`;
   - Se inválido/expirado: registra falha em `RegistroAcesso` e lança erro com mensagem literal **`"Link inválido ou expirado. Solicite uma nova recuperação"`**;
   - Valida política do RF001 e impede senha igual à atual (`check_password(nova_senha)` → erro);
   - Atualiza `password` (Argon2id), marca `usado_em = agora`, encerra todas as sessões ativas da conta na tabela de sessões do PostgreSQL, grava `usuario.senha_redefinida` na auditoria e enfileira e-mail crítico `seguranca_conta` avisando que a senha foi alterada.
5. Redireciona (PRG) para `contas:login` exibindo **`"Senha alterada com sucesso"`**.

### 4.2 Fluxos de exceção

- **FE-01 — Token inválido, já utilizado, substituído por pedido mais novo ou expirado (> 1 h):** exibe `"Link inválido ou expirado. Solicite uma nova recuperação"`.
- **FE-02 — Nova senha fora do padrão ou igual à senha atual:** exibe `"Campo preenchido incorretamente"` com orientação clara.
- **FE-03 — E-mail inexistente ou não confirmado:** nenhum e-mail de link é enviado, mas a resposta HTTP/tela é **idêntica** à de sucesso (RS012).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-20-01** | A resposta à solicitação é sempre idêntica, exista ou não o e-mail cadastrado, e o link só é enviado ao e-mail cadastrado e confirmado. | RF003 (regra 1), RS012 • `contas` |
| **RN-20-02** | O token é aleatório, salvo **somente como hash**, válido por **1 hora**, de **uso único**, e uma nova solicitação invalida o anterior. | RF003 (regra 2), RS012 • `contas` |
| **RN-20-03** | A nova senha respeita o RF001 (Argon2id — ADR 0008) e **não pode ser igual à senha atual**. | RF003 (regra 3), RS005 • `contas` |
| **RN-20-04** | Após redefinição, todas as sessões ativas do usuário são encerradas e um aviso crítico (`seguranca_conta`) é enviado por e-mail (RF017). | RF003 (regra 4), RF017, RS012 • `contas`, `notificacoes` |
| **RN-20-05** | Limite configurável de **5 solicitações por hora por e-mail e por IP** (`RECUPERACAO_SENHA_LIMITE_POR_HORA = 5` em `settings`); todas as solicitações e redefinições (sucesso e falha) são registradas com data, hora e identificação do usuário. | RF003 (regra 5), RF002, RS012, RNF14 • `contas`, `auditoria` |

---

## 6. Modelo de dados lógico

#### `TokenRecuperacaoSenha` (app `contas`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `usuario` | FK (`Usuario`, `PROTECT`, indexado) | Sim | |
| `token_hash` | String (64, único) | Sim | SHA-256 hex do token; nunca guarda token em claro. |
| `criado_em` / `expira_em` | Datetime (indexado) | Sim | `expira_em = criado_em + 1 hora`. |
| `usado_em` / `invalidado_em` | Datetime, anulável | Não | Garante uso único e invalidação ao pedir novo token. |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`contas`):** `RecuperarSenhaSolicitarView` + `RecuperarSenhaForm`, `RedefinirSenhaView` + `RedefinirSenhaForm` (com cabeçalho `Referrer-Policy: no-referrer` para evitar vazamento do token na URL — OWASP A07).
- **Services (`RecuperacaoSenhaService`):** `solicitar(email, ip_origem)` e `redefinir(token, nova_senha, ip_origem)`.
- **Templates:** `templates/contas/recuperar_senha.html` e `templates/contas/redefinir_senha.html`.
- **Rotas:** `contas:recuperar_senha` (`/conta/recuperar-senha/`), `contas:redefinir_senha` (`/conta/redefinir-senha/<str:token>/`).

---

## 8. Mensagens e validações

Textos literais exigidos pela fonte (RF003):
- Solicitação enviada: `"Se o e-mail estiver cadastrado, você receberá as instruções para redefinir a senha"`;
- Link inválido ou expirado: `"Link inválido ou expirado. Solicite uma nova recuperação"`;
- Senha fora do padrão: `"Campo preenchido incorretamente"`;
- Sucesso: `"Senha alterada com sucesso"`.

---

## 9. Segurança e privacidade

- **RS012 & RS005 (OWASP A07):** resposta anti-enumeração, token apenas em hash SHA-256, validade 1 h, uso único, invalidação do anterior, rate limit por e-mail e IP, `Referrer-Policy: no-referrer`, encerramento de todas as sessões e auditoria sem segredos.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03, RNF04, RNF07, RNF14, RNF15:** formulário simples acessível, outbox de e-mail crítico (até 5 min) e histórico imutável.

---

## 11. Critérios de aceite

1. **CA-20-01 (Anti-enumeração — RN-20-01):** Solicitar recuperação para e-mail inexistente ou cadastrado retorna a mesma resposta literal e status HTTP; e-mail só vai ao cadastrado e confirmado.
2. **CA-20-02 (Hash, uso único, expiração 1 h e invalidação — RN-20-02):** Token salvo só como hash; novo pedido invalida o anterior; token usado ou > 1 h exibe `"Link inválido ou expirado. Solicite uma nova recuperação"`.
3. **CA-20-03 (Nova senha, sessões encerradas e aviso — RN-20-03, RN-20-04):** Rejeita senha igual à atual; ao redefinir, atualiza com Argon2id, derruba todas as sessões ativas da conta, envia e-mail `seguranca_conta` e exibe `"Senha alterada com sucesso"`.
4. **CA-20-04 (Rate limit e auditoria — RN-20-05):** 6ª solicitação na mesma hora pelo mesmo e-mail/IP é contida sem gerar novo envio; sucesso e falhas ficam registrados.

---

## 12. Plano de testes

- **Unidade (`RecuperacaoSenhaService`):** geração de hash sem salvar token em claro, invalidação do token anterior, expiração de 1 h com relógio controlado, bloqueio de reuso de senha atual, encerramento de sessões e rate limit 5/hora.
- **Integração (Views):** resposta idêntica para e-mail existente/inexistente, mensagens literais, `Referrer-Policy: no-referrer` e verificação do e-mail crítico no outbox.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Validação final do limite sugerido de 5 pedidos por hora (Questão 13 do PRD):** confirmar com o cliente na v1.1. | Pendência externa (Cliente / PO) | Parâmetro configurável em `settings` (`RECUPERACAO_SENHA_LIMITE_POR_HORA = 5`). |
