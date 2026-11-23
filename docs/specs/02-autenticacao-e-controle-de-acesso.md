# Spec 02 — Autenticação, Controle de Acesso e 2FA do Administrador (RF002)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `02` — Autenticação, Controle de Acesso e 2FA do Administrador (`RF002`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF002 (Essencial — MVP, HU02). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF08, RNF10 (Essencial), RNF14 (Essencial). **Segurança:** RS005, RS006, RS015. |
| **Apps envolvidos** | `contas` (principal: autenticação, bloqueio por tentativas, tabela `RegistroAcesso`, TOTP/`pyotp`, códigos de recuperação, criação dos 8 grupos administrativos e bootstrap do primeiro Admin), `nucleo` (mixins declarativos de acesso e 2FA, exceções base), `auditoria` (`AuditoriaService` para eventos de 2FA e segurança). |
| **Dependências de outras specs** | **[01-cadastro-de-usuario.md](01-cadastro-de-usuario.md) (`RF001`)** — exige `AUTH_USER_MODEL`, `Argon2PasswordHasher`, `email_confirmado_em` e `AuditoriaService`. |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0004](../adr/0004-pip-venv-requirements-fixado.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0007](../adr/0007-modelo-de-usuario-customizado.md), [0008](../adr/0008-hash-de-senha-argon2-ou-bcrypt.md), [0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md). |

---

## 2. Objetivo e escopo

Garantir acesso seguro ao ReMed com login por **e-mail ou CPF** e senha, bloqueio temporário por tentativas inválidas, expiração de sessão por inatividade, registro imutável de todos os acessos (sucesso e falha), **autenticação em dois fatores (TOTP)** obrigatória para contas com funções administrativas e controle declarativo de acesso por perfil e pelas **8 funções administrativas separadas** ([ADR 0010](../adr/0010-perfis-e-permissoes.md)).

### Inclui

- Tela **"Entrar no ReMed"** fiel a [Login ReMed.png](../prd/telas/Login%20ReMed.png), com o rótulo do identificador ajustado para **`"E-mail ou CPF"`** (divergência da tela de origem corrigida na implementação conforme [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md), pendente de confirmação com o professor).
- Backend de autenticação customizado aceitando **e-mail** (case-insensitive) ou **CPF** (com ou sem máscara), recusando CNPJ, contas anonimizadas (`email = NULL`), contas sem e-mail confirmado (`email_confirmado_em = NULL`) e contas com status `inativo`, `suspenso` ou `bloqueado` ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)).
- Configuração de sessões no PostgreSQL (`backends.db`), expiração deslizante de **30 minutos de inatividade** (`SESSION_COOKIE_AGE = 1800`, `SESSION_SAVE_EVERY_REQUEST = True`), cookies seguros (`HttpOnly`, `Secure` em produção/TLS 1.2+, `SameSite = "Lax"`), rotação do ID de sessão no login e **logout exclusivo por `POST`** com CSRF.
- Tabela `append-only` **`RegistroAcesso`** (com trigger `BEFORE UPDATE OR DELETE` no PostgreSQL — [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) e [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)) registrando todos os acessos (sucesso e falha) e controle de **bloqueio temporário de 15 minutos** (configurável em `settings`) após **5 tentativas inválidas em 15 minutos** na mesma conta (unificando e-mail e CPF), mais um limite secundário por IP (*acréscimo da especificação, não consta no RF002*).
- **2FA TOTP (RFC 6238)** na camada de service usando **`pyotp`** e **`segno`** para geração local do QR code em SVG (Python puro, zero dependências externas; compatibilidade do `segno` com Python 3.14 a conferir na instalação no `.venv` antes de fixar ambos por `==` no `requirements.txt` — [ADR 0004](../adr/0004-pip-venv-requirements-fixado.md), [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md)):
  - Fluxo de ativação/pareamento obrigatório para contas com função administrativa (QR code local em SVG + chave manual + confirmação do primeiro código + exibição única de **8 códigos de recuperação alfanuméricos** armazenados apenas como hash);
  - Verificação TOTP (ou código de recuperação de uso único) obrigatória no login administrativo antes de liberar qualquer rota administrativa;
  - Regeneração de um novo conjunto de 8 códigos de recuperação pelo próprio Administrador (invalidando o conjunto anterior) mediante ***step-up* de 2FA**;
  - Serviço de **reconfirmação imediata (*step-up* 2FA)** reutilizado pelo RF004 ao atribuir/remover funções administrativas;
  - Serviço de **reset de 2FA por outro Administrador ativo** (somente quando existirem ≥ 2 Administradores ativos com `gestao_administradores`, nunca auto-reset — [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md)).
- Link **"Esqueci minha senha"** mantido visível na tela de login durante o MVP, levando a um aviso de `"recurso disponível em breve"` e orientação de contato (será substituído pelo fluxo real na spec do **RF003** na v1.1).
- Inicialização idempotente dos **8 grupos/funções administrativas** (`gestao_usuarios`, `aprovacao_pontos_coleta`, `conferencia_doacoes`, `verificacao_receitas`, `moderacao_denuncias`, `metricas_e_parametros`, `gestao_administradores`, `auditoria`) e mixins de controle de acesso em `nucleo/mixins.py` (negação por padrão; `is_superuser` sem privilégio implícito nas rotas da aplicação — [ADR 0010](../adr/0010-perfis-e-permissoes.md)).
- Comando de terminal para bootstrap do primeiro Administrador (Questão 20 do PRD), exigindo pareamento TOTP no primeiro login.

### Não inclui

- Fluxo real de recuperação de senha por e-mail (v1.1 — RF003; no MVP o link leva apenas à tela temporária de aviso).
- Telas de gestão de usuários, alteração de status e atribuição/remoção de funções administrativas (Spec `04` — RF004).
- Tela somente leitura de consulta à auditoria (entra com `auditoria` / RF004).
- Cadastro e gerenciamento de conta de cidadão (Spec `01` — RF001).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Visitante** | Acessar a tela de login, escolher `"Continuar como visitante"` (busca resumida — RF015) ou navegar para cadastro (RF001). | Nenhuma. |
| **Usuário cadastrado (Doador, Solicitante, Cuidador/Familiar, Representante de ponto de coleta)** | Entrar com e-mail ou CPF e senha; encerrar sessão (`POST`). | Conta criada (RF001), `status = ativo` e `email_confirmado_em != NULL` ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)). |
| **Usuário com função administrativa** (qualquer uma das 8 funções da ADR 0010) | Entrar com e-mail ou CPF e senha, parear TOTP no primeiro acesso (se ainda não pareado), validar código TOTP (ou código de recuperação) em todo login e reconfirmar código TOTP (*step-up*) em ações críticas. | Conta ativa com e-mail confirmado e ao menos uma das 8 funções administrativas atribuídas. |

---

## 4. Fluxos

### 4.1 Fluxo principal — Login de usuário comum (sem função administrativa)

1. O usuário acessa **"Entrar no ReMed"** (`contas:login`), informa **E-mail ou CPF** e **Senha** e aciona **Entrar** (`POST` com CSRF).
2. A view valida preenchimento no `LoginForm` e chama `AutenticacaoService.autenticar(identificador, senha, ip)`.
3. `AutenticacaoService.autenticar(...)`:
   - Normaliza o identificador (e-mail em minúsculas ou 11 dígitos de CPF; rejeita formato de CNPJ ou vazio);
   - Verifica o limite secundário por IP e se a conta correspondente está em **bloqueio temporário** (≥ 5 falhas nos últimos 15 minutos, dentro da janela de bloqueio de 15 minutos configurada em `settings`);
   - Valida credenciais via `check_password` (Argon2id — executando verificação em tempo constante quando o usuário não existe para mitigar diferença de tempo), verifica `status == ativo`, `anonimizado_em is None` e `email_confirmado_em is not None`;
   - Grava o registro `sucesso` em `RegistroAcesso` (data/hora UTC, identificador normalizado, usuário, IP);
   - Retorna o usuário autenticado.
4. A view chama `django.contrib.auth.login(request, usuario)` (rotacionando o ID de sessão), valida o destino `next` (usando `url_has_allowed_host_and_scheme` contra *open redirect* — OWASP A01) e redireciona.

### 4.2 Fluxo principal — Login de conta administrativa (2FA TOTP obrigatório)

1. Passos 1 a 3 idênticos ao fluxo 4.1.
2. Ao constatar que o usuário possui ao menos uma das **8 funções administrativas** ([ADR 0010](../adr/0010-perfis-e-permissoes.md)), a sessão entra em estado **pendente de 2FA** (`2fa_verificado = False`), sem acesso a nenhuma rota administrativa:
   - **Se ainda não possui dispositivo TOTP confirmado:** redireciona para `contas:totp_configurar`, onde o sistema gera segredo base32 (`pyotp.random_base32()`), exibe QR code gerado localmente e chave manual; o Administrador informa o código de 6 dígitos do aplicativo autenticador; `TotpService.confirmar_pareamento(...)` valida o código, ativa o dispositivo, gera os códigos de recuperação (salvos apenas como hash), registra `usuario.totp_ativado` na auditoria, marca `2fa_verificado = True` na sessão e exibe os códigos de recuperação **uma única vez**.
   - **Se já possui dispositivo TOTP ativo:** redireciona para `contas:totp_verificar`, onde o Administrador informa o código TOTP de 6 dígitos (ou alterna para informar um código de recuperação de uso único). `TotpService.verificar_codigo(...)` valida o código (impedindo reuso do mesmo código dentro da janela de tempo de 30 s — proteção contra *replay*), marca `2fa_verificado = True` na sessão, registra sucesso em `RegistroAcesso` e redireciona ao destino.

### 4.3 Fluxos alternativos

- **FA-01 — Continuar como visitante:** na tela de login, o usuário aciona `"Continuar como visitante"` e é direcionado à busca resumida (RF015), sem criar sessão autenticada.
- **FA-02 — Uso de código de recuperação no 2FA:** caso o Administrador esteja sem o celular, informa um código de recuperação de uso único na tela de verificação; `TotpService.consumir_codigo_recuperacao(...)` valida o hash, marca o código como usado em `transaction.atomic()`, grava `usuario.codigo_recuperacao_usado` na auditoria e conclui o login com aviso da quantidade restante de códigos.
- **FA-03 — Encerramento de sessão (Logout):** o usuário aciona Sair (`POST` em `contas:logout` com CSRF); a view chama `logout(request)` invalidando a sessão no PostgreSQL e redireciona para a página inicial/login.
- **FA-04 — Reconfirmação imediata (*step-up* 2FA) para ações críticas (RF004 e regeneração de códigos):** antes de executar ação sensível (atribuir/remover função administrativa no RF004 ou regenerar os 8 códigos de recuperação), o service exige chamada a `TotpService.verificar_step_up(usuario, codigo_totp)`, validando um código TOTP atual (não aceitando código de recuperação nem reutilização do último passo de tempo). Na regeneração de códigos (`contas:totp_regenerar_codigos`), todos os códigos anteriores não usados são invalidados, 8 novos códigos alfanuméricos são gerados em hash, exibidos uma única vez, e o evento `usuario.codigos_recuperacao_regenerados` é gravado na auditoria.
- **FA-05 — Invalidação de todas as sessões ativas de uma conta (suporte a RF003 e RF004):** `SessaoService.encerrar_todas_sessoes(usuario_id)` remove todas as sessões ativas vinculadas à conta no PostgreSQL (complementado pelo `get_session_auth_hash()` do Django em troca de senha).
- **FA-06 — Link `"Esqueci minha senha"` no MVP:** direciona para `contas:recuperar_senha_em_breve`, exibindo aviso `"Recurso disponível em breve"` e orientação de contato; será substituído pelo fluxo real na spec do **RF003** (v1.1).

### 4.4 Fluxos de exceção

- **FE-01 — Identificador inexistente ou senha incorreta:** grava registro `falha` em `RegistroAcesso` e exibe **sempre** `"E-mail/CPF ou senha incorretos"`, sem revelar se a conta existe ou qual seu status.
- **FE-02 — 5 tentativas inválidas em 15 minutos (conta bloqueada temporariamente):** grava tentativa bloqueada em `RegistroAcesso` e exibe `"Muitas tentativas. Tente novamente mais tarde"` por 15 minutos (configurável em `settings`), unificando tentativas por e-mail e por CPF da mesma conta (e aplicando o limite secundário por IP — *acréscimo da especificação, não consta no RF002*).
- **FE-03 — Senha correta, mas conta não confirmada, `inativo`, `suspenso` ou `bloqueado`:** somente após validar que a senha confere, grava falha em `RegistroAcesso` com motivo interno, nega o login e exibe orientação específica ao usuário (para e-mail não confirmado, informa que é preciso confirmar o e-mail e oferece link para `contas:reenviar_confirmacao`; para conta `inativo`, `suspenso` ou `bloqueado`, informa o impedimento de acesso conforme o status). Contas anonimizadas (com senha inutilizada) caem sempre em FE-01.
- **FE-04 — Código TOTP ou código de recuperação inválido:** incrementa contagem de falhas de 2FA (aplicando limite de tentativas para impedir força bruta sobre 6 dígitos — `NOVO`), grava falha em `RegistroAcesso` e mantém `2fa_verificado = False`.
- **FE-05 — Sessão expirada após 30 minutos de inatividade:** na próxima requisição protegida, o middleware de sessão descarta a sessão expirada e o mixin redireciona para `contas:login`.
- **FE-06 — Acesso a rota sem perfil ou função administrativa autorizada (ou Admin sem 2FA concluído):** rota administrativa sem 2FA redireciona para `contas:totp_verificar` (ou `contas:totp_configurar`); usuário autenticado sem o perfil/função exigida recebe **HTTP 403**; `is_superuser` sem a função explícita também recebe **HTTP 403** ([ADR 0010](../adr/0010-perfis-e-permissoes.md)).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-02-01** | O login aceita **apenas E-mail ou CPF** (mais senha), nunca CNPJ. E-mail é comparado sem diferenciar maiúsculas/minúsculas; CPF aceita entrada com ou sem máscara (`xxx.xxx.xxx-xx` ou 11 dígitos). | RF002 (Campos), [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md) • `contas` |
| **RN-02-02** | Contas com `email_confirmado_em = NULL`, `anonimizado_em != NULL` ou status `inativo`, `suspenso` ou `bloqueado` não podem autenticar; o backend de autenticação customizado e o `AutenticacaoService` verificam explicitamente `usuario.status == "ativo"`, `email_confirmado_em is not None` e `anonimizado_em is None` (sem depender apenas de `is_active`, que é sincronizado exclusivamente na camada de service). Quando a senha **não confere** (ou a conta não existe/foi anonimizada), exibe-se **sempre** `"E-mail/CPF ou senha incorretos"`; orientações específicas (confirmar e-mail, conta `inativo`, `suspenso` ou `bloqueado`) só são exibidas **depois que a senha está correta**. | RF004 (regra 2), RS006, RNF02, [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md) • `contas` |
| **RN-02-03** | Após **5 tentativas de login inválidas em 15 minutos** para a mesma conta (somando tentativas feitas via e-mail e via CPF dessa conta), a conta fica em **bloqueio temporário de 15 minutos** (parâmetro configurável em `settings`), exibindo `"Muitas tentativas. Tente novamente mais tarde"`. Um limite secundário por IP (*acréscimo da especificação, não consta no RF002*) complementa a proteção contra *password spraying*. | RF002 (regra 1), RS005, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) • `contas` |
| **RN-02-04** | A sessão do usuário fica armazenada no PostgreSQL (`backends.db`) e expira após **30 minutos de inatividade** (`SESSION_COOKIE_AGE = 1800`, `SESSION_SAVE_EVERY_REQUEST = True`). O ID da sessão é rotacionado no login e o logout só ocorre via `POST` com CSRF. | RF002 (regra 2), RS005, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) • `contas` |
| **RN-02-05** | Todos os acessos (sucesso e falha, incluindo tentativas bloqueadas e falhas de 2FA) são registrados em `RegistroAcesso` (tabela `append-only` com trigger `BEFORE UPDATE OR DELETE` no PostgreSQL) com data/hora UTC, identificador normalizado, usuário vinculado (quando existir), IP e resultado. | RF002 (regra 5), RNF14, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `contas` |
| **RN-02-06** | Toda conta com qualquer uma das **8 funções administrativas** (`gestao_usuarios`, `aprovacao_pontos_coleta`, `conferencia_doacoes`, `verificacao_receitas`, `moderacao_denuncias`, `metricas_e_parametros`, `gestao_administradores`, `auditoria`) exige **2FA TOTP (RFC 6238)** via `pyotp` (com QR code local gerado em SVG via `segno`) antes de acessar qualquer rota administrativa. O segredo TOTP é protegido no banco e no disco (como o CPF na ADR 0007), nunca aparece em log nem em auditoria e só é exibido durante o pareamento inicial. | RF002 (regra 4), RS005, RS015, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md), [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `contas`, `nucleo` |
| **RN-02-07** | Um código TOTP validado não pode ser reutilizado dentro da mesma janela de tempo (*anti-replay*), e falhas consecutivas na etapa de 2FA são limitadas (5 falhas em 15 minutos invalidam a sessão pendente de 2FA e bloqueiam temporariamente a conta — *acréscimo da especificação, não consta no RF002*). | RS005, RS015, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) • `contas` |
| **RN-02-08** | Na ativação do 2FA, são gerados **8 códigos de recuperação alfanuméricos de uso único**, exibidos uma única vez e armazenados exclusivamente como **hash**. O próprio Administrador pode gerar um novo conjunto de 8 códigos (invalidando o conjunto anterior) mediante ***step-up* de 2FA**. O reset de 2FA por outro Administrador ativo só é permitido quando existirem **pelo menos dois Administradores ativos** com `gestao_administradores` (nunca auto-reset), sempre registrado na auditoria. | RS015, RNF14, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) • `contas`, `auditoria` |
| **RN-02-09** | A atribuição ou remoção de funções administrativas (RF004) exige **reconfirmação imediata do código 2FA (*step-up*)**, mesmo dentro de sessão já verificada com 2FA. | RF004 (regra 4), RS015, [ADR 0009](../adr/0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) • `contas` |
| **RN-02-10** | Controle de acesso por perfil (RF002 regra 3 + [ADR 0010](../adr/0010-perfis-e-permissoes.md)): Visitante acessa apenas RF001, RF002, RF003 (v1.1) e busca resumida (RF015); Doador acessa RF008–RF010, RF016, RF018–RF020; Solicitante/Cuidador acessa RF013–RF014, RF016, RF018–RF020; Representante de ponto de coleta (vínculo ativo com `PontoColeta`) acessa RF005–RF006 do seu ponto; cada rota administrativa exige sua função explícita entre as 8 funções + 2FA; todos os autenticados acessam RF017 e RF021 (v1.1). | RF002 (regra 3), [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `nucleo`, `contas` |
| **RN-02-11** | `is_superuser` fica restrito ao bootstrap inicial pelo terminal (Questão 20 do PRD); nas rotas da aplicação ReMed, **não concede atalho** de permissão nem dispensa 2FA. | RS015, [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `nucleo`, `contas` |

---

## 6. Modelo de dados lógico

*(Nível lógico — sem código de models. Todas as datas/horas usam `USE_TZ = True`.)*

### 6.1 Entidades e campos

#### `RegistroAcesso` (app `contas` — tabela `append-only` com trigger `BEFORE UPDATE OR DELETE` no PostgreSQL)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `criado_em` | Datetime (indexado) | Sim | Data e hora UTC da tentativa. |
| `identificador` | String (254, indexado) | Sim | E-mail normalizado ou CPF normalizado (sem máscara); **nunca** a senha. |
| `usuario` | FK (`Usuario`, `PROTECT`, anulável, indexado) | Não | Preenchido quando o identificador corresponde a uma conta existente (permite consolidar tentativas feitas por e-mail e por CPF da mesma conta). |
| `ip_origem` | GenericIPAddressField (indexado) | Sim | IP do cliente para limite secundário e auditoria. |
| `etapa` | TextChoices | Sim | `senha`, `totp`, `codigo_recuperacao`, `step_up`. |
| `resultado` | TextChoices | Sim | `sucesso`, `falha`, `bloqueado`. |
| `motivo_interno` | String (60) | Não | Código técnico interno (ex.: `senha_invalida`, `email_nao_confirmado`, `conta_suspensa`, `totp_invalido`, `limite_tentativas`) — **nunca** exibido cru ao usuário. |

**Índices e constraints obrigatórias (`RegistroAcesso`):**
- Índice composto `(usuario, criado_em)` e `(ip_origem, criado_em)` para consulta rápida da janela de 15 minutos;
- Trigger PostgreSQL `BEFORE UPDATE OR DELETE` bloqueando alterações e exclusões pela credencial da aplicação ([ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)).

#### `DispositivoTotp` (app `contas` — relação `OneToOne` com `Usuario`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `usuario` | OneToOne (`Usuario`, `CASCADE`) | Sim | Apenas um dispositivo TOTP ativo/pendente por Administrador. |
| `segredo` | String | Sim | Segredo base32 gerado via `pyotp.random_base32()`, protegido por criptografia no banco e no disco (como o CPF na ADR 0007); nunca gravado em logs ou auditoria e exibido apenas no pareamento inicial. |
| `confirmado_em` | Datetime, anulável | Não | Nulo até confirmar o primeiro código de 6 dígitos. |
| `ultimo_passo_usado` | BigInteger, anulável | Não | Contador TOTP (`int(timestamp // 30)`) do último código aceito, impedindo *replay* na mesma janela de 30 s (`RN-02-07`). |
| `criado_em` / `atualizado_em` | Datetime | Sim | |

#### `CodigoRecuperacaoTotp` (app `contas`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `usuario` | FK (`Usuario`, `CASCADE`) | Sim | |
| `codigo_hash` | String (128) | Sim | Hash criptográfico do código de recuperação (código em texto aberto exibido apenas uma vez na criação). |
| `criado_em` | Datetime | Sim | |
| `usado_em` | Datetime, anulável | Não | Preenchido no uso único; código já usado é recusado. |

#### `SessaoUsuario` (app `contas` — índice auxiliar opcional para revogação rápida de sessões por usuário)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `usuario` | FK (`Usuario`, `CASCADE`, indexado) | Sim | Liga o usuário à `session_key` na `django_session` para encerramento imediato de todas as sessões no RF003/RF004/RF001 sem varrer toda a tabela `django_session`. |
| `session_key` | String (40, único) | Sim | Chave da sessão no backend `db` do Django. |
| `criado_em` | Datetime | Sim | |

### 6.2 Grupos/funções administrativas (migração de dados / comando idempotente — [ADR 0010](../adr/0010-perfis-e-permissoes.md))

Criação garantida dos 8 grupos com suas respectivas permissões explícitas:
`gestao_usuarios`, `aprovacao_pontos_coleta`, `conferencia_doacoes`, `verificacao_receitas`, `moderacao_denuncias`, `metricas_e_parametros`, `gestao_administradores`, `auditoria`.

### 6.3 Histórico obrigatório (RNF14 / [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md))

- Todo login, falha, bloqueio e verificação de 2FA grava em `RegistroAcesso` (`append-only`);
- Eventos de ciclo de vida do 2FA gravam também em `RegistroAuditoria` via `AuditoriaService.registrar(...)`: `usuario.totp_ativado`, `usuario.codigo_recuperacao_usado`, `usuario.codigos_recuperacao_regenerados` e `usuario.totp_resetado` (com ator = outro Admin ativo e alvo = Admin resetado).

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

### 7.1 Camada de entrada (Views, Mixins e Forms)

| Componente | App | Métodos | Acesso | Responsabilidade |
| --- | --- | --- | --- | --- |
| `AutenticadoAtivoMixin`, `PerfilObrigatorioMixin`, `FuncaoAdminObrigatoriaMixin` | `nucleo` | — | — | Mixins declarativos de controle de acesso: verificam autenticação, `status == ativo`, `email_confirmado_em != NULL`, perfil de cidadão ou função administrativa explícita + `2fa_verificado == True` (ignorando `is_superuser` sem função explícita). |
| `LoginView` + `LoginForm` | `contas` | `GET`, `POST` | Público | Renderiza "Entrar no ReMed", valida preenchimento, chama `AutenticacaoService.autenticar(...)`, executa `login(request, usuario)` e registra `SessaoUsuario`; se conta administrativa, marca `2fa_verificado = False` e redireciona para pareamento/verificação TOTP; valida `next` antes de redirecionar. |
| `LogoutView` | `contas` | `POST` | Autenticado | Valida CSRF, remove vínculo em `SessaoUsuario`, executa `logout(request)` e redireciona. |
| `TotpConfigurarView` + `TotpCodigoForm` | `contas` | `GET`, `POST` | Autenticado com função admin (sem TOTP ativo) | Gera/exibe QR code local (SVG via `segno`) e chave manual via `TotpService.iniciar_pareamento`, valida o primeiro código via `TotpService.confirmar_pareamento`, marca `2fa_verificado = True` na sessão e exibe os 8 códigos de recuperação uma única vez. |
| `TotpVerificarView` + `TotpCodigoForm` | `contas` | `GET`, `POST` | Autenticado com função admin (`2fa_verificado = False`) | Valida código TOTP de 6 dígitos ou código de recuperação via `TotpService`, marca `2fa_verificado = True` na sessão e redireciona ao destino seguro. |
| `TotpRegenerarCodigosView` + `TotpCodigoForm` | `contas` | `GET`, `POST` | Autenticado com função admin (`2fa_verificado = True`) | Exige *step-up* de 2FA, chama `TotpService.regenerar_codigos_recuperacao(...)` e exibe os 8 novos códigos alfanuméricos uma única vez. |
| `RecuperarSenhaEmBreveView` | `contas` | `GET` | Público | Exibe o aviso temporário `"Recurso disponível em breve"` e orientação de contato (substituída pelo fluxo real na spec do RF003 na v1.1). |

### 7.2 Camada de regra de negócio (Services)

| Service e método | App | Transacional? | Entradas / saídas e regras aplicadas |
| --- | --- | --- | --- |
| `AutenticacaoService.autenticar(identificador, senha, ip)` | `contas` | Não (grava `RegistroAcesso` mesmo em falha!) | Aplica `RN-02-01` a `RN-02-05`: verifica bloqueio de conta (5 falhas/15 min -> 15 min bloqueio, unificando e-mail e CPF) e limite secundário por IP (*acréscimo da especificação*), valida senha (Argon2id) primeiro (lançando `CredenciaisInvalidas` se não conferir) e só então verifica confirmação de e-mail e status da conta, gravando sempre `RegistroAcesso`. |
| `TotpService.iniciar_pareamento(usuario)` | `contas` | **Sim** (`transaction.atomic`) | Exige conta com função administrativa e sem dispositivo confirmado; gera segredo `pyotp.random_base32()`, salva `DispositivoTotp` pendente e retorna URI `otpauth://`, segredo (exibição única no pareamento) e QR code SVG gerado localmente via `segno`. |
| `TotpService.confirmar_pareamento(usuario, codigo, ip)` | `contas` | **Sim** (`transaction.atomic`) | Valida código TOTP (`pyotp`), marca `confirmado_em` e `ultimo_passo_usado`, gera **8 códigos de recuperação alfanuméricos** (salvos apenas como hash), registra `usuario.totp_ativado` na auditoria e retorna os 8 códigos em texto claro **uma única vez**. |
| `TotpService.verificar_codigo(usuario, codigo, ip, etapa="totp")` | `contas` | **Sim** (`transaction.atomic` + `select_for_update` no `DispositivoTotp`) | Aplica limite de tentativas de 2FA, valida código TOTP contra `ultimo_passo_usado` (*anti-replay*), atualiza `ultimo_passo_usado` e grava `RegistroAcesso`. Usado tanto no login quanto no *step-up* (`etapa="step_up"`). |
| `TotpService.consumir_codigo_recuperacao(usuario, codigo, ip)` | `contas` | **Sim** (`transaction.atomic` + `select_for_update`) | Valida hash contra códigos não usados da conta, marca `usado_em`, grava `RegistroAcesso` e `usuario.codigo_recuperacao_usado` na auditoria. |
| `TotpService.regenerar_codigos_recuperacao(usuario, codigo_step_up, ip)` | `contas` | **Sim** (`transaction.atomic` + `select_for_update`) | Valida *step-up* 2FA (`etapa="step_up"`), invalida/remove códigos anteriores não usados, gera 8 novos códigos alfanuméricos (em hash), grava `usuario.codigos_recuperacao_regenerados` na auditoria e retorna os 8 novos códigos uma única vez. |
| `TotpService.resetar_por_administrador(ator, usuario_alvo, codigo_step_up, ip)` | `contas` | **Sim** (`transaction.atomic`) | Exige `ator != usuario_alvo`, `ator` com `gestao_administradores`, **≥ 2 Administradores ativos com `gestao_administradores`**, valida *step-up* 2FA de `ator`, remove `DispositivoTotp` e códigos antigos de `usuario_alvo`, encerra sessões de `usuario_alvo` e grava `usuario.totp_resetado` na auditoria. |
| `SessaoService.encerrar_todas_sessoes(usuario_id)` | `contas` | **Sim** (`transaction.atomic`) | Remove sessões da conta em `django_session` e `SessaoUsuario` (reutilizado em RF001, RF003, RF004 e reset de 2FA). |

### 7.3 Interface (Telas e templates)

- **Tela principal — `templates/contas/login.html`** (fiel a [Login ReMed.png](../prd/telas/Login%20ReMed.png), com correção do campo identificador):
  - Logo ReMed, título **"Entrar no ReMed"** e subtítulo **"Acesse sua conta para continuar."**.
  - Campo **`E-mail ou CPF`** (placeholder `"Digite seu e-mail ou CPF"` — sem CNPJ, conforme [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)).
  - Campo **`Senha`** com botão **"Mostrar"** em JavaScript simples ([ADR 0006](../adr/0006-javascript-simples-sem-framework.md)).
  - Link **"Esqueci minha senha"** (`contas:recuperar_senha_em_breve` no MVP; vira o fluxo real no RF003), botão primário **Entrar** e link **"Ainda não tem uma conta? Criar conta"** (`contas:cadastro`).
  - Separador, link **"Continuar como visitante"** e quadro informativo: `"Consulte o resumo dos medicamentos disponíveis. Para doar ou solicitar, entre na sua conta."`.
  - Rodapé `"ReMed · Conectando cuidado, compartilhando saúde."`.
- **Telas de 2FA e aviso temporário:**
  - `templates/contas/totp_configurar.html`: instruções claras, SVG local do QR code (`segno`), chave manual copiável (exibida somente nesta tela), campo para confirmar o código de 6 dígitos; após confirmação, exibição única dos 8 códigos de recuperação com botão para continuar.
  - `templates/contas/totp_verificar.html`: campo numérico para código de 6 dígitos do aplicativo autenticador, opção para usar código de recuperação e botão de sair (`POST`).
  - `templates/contas/totp_regenerar_codigos.html`: confirmação via código TOTP atual (*step-up*) e exibição única dos 8 novos códigos.
  - `templates/contas/recuperar_senha_em_breve.html`: aviso `"Recurso disponível em breve"` com orientação de contato e link de volta ao login.

### 7.4 Rotas

| Nome da URL | Caminho proposto | Propósito |
| --- | --- | --- |
| `contas:login` | `/contas/entrar/` | Exibir e processar o login por e-mail ou CPF. |
| `contas:logout` | `/contas/sair/` | Encerrar sessão via `POST`. |
| `contas:recuperar_senha_em_breve` | `/contas/esqueci-minha-senha/` | Aviso temporário no MVP (substituído pelo fluxo real na spec do RF003). |
| `contas:totp_configurar` | `/contas/2fa/configurar/` | Pareamento inicial do TOTP (`segno`) e exibição única dos 8 códigos de recuperação. |
| `contas:totp_verificar` | `/contas/2fa/verificar/` | Verificação do código TOTP (ou código de recuperação) no login administrativo. |
| `contas:totp_regenerar_codigos` | `/contas/2fa/codigos-recuperacao/` | Regeneração dos 8 códigos de recuperação mediante *step-up* de 2FA. |

---

## 8. Mensagens e validações

Textos literais exigidos pela fonte (RF002):

| Condição | Mensagem literal |
| --- | --- |
| E-mail/CPF inexistente ou senha incorreta | `"E-mail/CPF ou senha incorretos"` |
| Conta atingiu 5 tentativas inválidas em 15 minutos (bloqueio temporário de 15 min) | `"Muitas tentativas. Tente novamente mais tarde"` |

---

## 9. Segurança e privacidade

### Mapeamento de requisitos de segurança × OWASP Top 10:2025

| Requisito | Perigo resumido | Categoria OWASP 2025 | Controle aplicado nesta spec |
| --- | --- | --- | --- |
| **RS005** | Força bruta, hijacking de sessão, acesso indevido, open redirect, CSRF/XSS | A01, A02, A04, A05, A07, A09 | Bloqueio 15 min após 5 falhas/15 min (e-mail + CPF unificados) + limite por IP; sessão no PostgreSQL com 30 min de inatividade e cookies `HttpOnly`/`Secure`/`SameSite=Lax`; rotação de ID no login; logout só `POST` com CSRF; validação de `next`; TLS 1.2+ em produção; registro `append-only` de todos os acessos. |
| **RS006** | Acesso por contas não confirmadas ou punidas | A06, A07 | Bloqueio de login para `email_confirmado_em = NULL`, `inativo`, `suspenso`, `bloqueado` e contas anonimizadas. |
| **RS015** | Invasão ou abuso de contas de Administrador | A01, A07, A09 | 2FA TOTP obrigatório via `pyotp` (com *anti-replay* e *step-up* no RF004); códigos de recuperação em hash; reset de 2FA apenas com ≥ 2 Admins ativos; 8 funções administrativas separadas sem atalho por `is_superuser`. |

### Proteções críticas adicionais

- **Nunca registrar segredos em logs ou `RegistroAcesso` (OWASP A09):** senhas, códigos TOTP informados, segredos base32 e códigos de recuperação nunca são gravados em logs nem em `RegistroAcesso`.
- **Anti-enumeração e tempo constante (OWASP A07):** quando o identificador não existe, o service executa um hash fictício com o mesmo hasher Argon2id para evitar inferência de contas por tempo de resposta.

---

## 10. Requisitos não funcionais aplicáveis

| ID | Exigência aplicada a esta spec |
| --- | --- |
| **RNF01–RNF03** | Tela de login e 2FA em linguagem simples, mensagens claras e WCAG 2.1 AA (rótulos, foco visível, `autocomplete="username"` / `"current-password"` / `"one-time-code"`, `aria-live` para erros). |
| **RNF04** | Tela de login responde em até 3 s (p95) com até 500 usuários simultâneos. |
| **RNF07–RNF08** | Web responsiva (*mobile first*) com Bootstrap local e JS mínimo; sessões no PostgreSQL compatíveis com escalabilidade horizontal. |
| **RNF10** | Retenção futura dos registros de IP em `RegistroAcesso` alinhada à política de privacidade (Questão 8 do PRD). |
| **RNF14** | `RegistroAcesso` e `RegistroAuditoria` imutáveis (`append-only` com trigger no PostgreSQL — [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)). |

---

## 11. Critérios de aceite

1. **CA-02-01 (Login por e-mail e por CPF — RN-02-01):** Dado um usuário `ativo` com e-mail confirmado, quando entra com seu e-mail (mesmo em maiúsculas) ou com seu CPF (com ou sem máscara) e senha correta, então o login é aceito, o ID de sessão é rotacionado, `RegistroAcesso` grava `sucesso` e o usuário é redirecionado.
2. **CA-02-02 (Recusa de CNPJ e de contas bloqueadas/não confirmadas com ordem de mensagem — RN-02-01, RN-02-02):** Dado um CNPJ cadastrado em ponto de coleta, ou uma conta com `email_confirmado_em = NULL`, `inativo`, `suspenso`, `bloqueado` ou anonimizada, quando a senha não confere, então recebe `"E-mail/CPF ou senha incorretos"`; quando a senha confere em conta não confirmada, `inativo`, `suspenso` ou `bloqueado`, então o login é negado com a orientação específica correspondente (incluindo link para reenvio no caso de e-mail não confirmado) e `RegistroAcesso` grava `falha`.
3. **CA-02-03 (Credenciais inválidas — RF002 Mensagens):** Dada senha errada ou identificador inexistente, quando o usuário tenta entrar, então recebe `"E-mail/CPF ou senha incorretos"` e `RegistroAcesso` grava `falha`.
4. **CA-02-04 (Bloqueio temporário após 5 falhas unificando e-mail e CPF — RN-02-03, ADR 0009):** Dada uma mesma conta que sofre 3 tentativas inválidas por e-mail e 2 tentativas inválidas por CPF dentro de 15 minutos, quando ocorre a 6ª tentativa (mesmo com a senha correta) dentro dos 15 minutos de bloqueio, então o acesso é recusado com `"Muitas tentativas. Tente novamente mais tarde"`; após expirar o tempo de bloqueio configurado (15 min), o login válido volta a funcionar.
5. **CA-02-05 (Expiração de sessão em 30 minutos de inatividade — RN-02-04):** Dada uma sessão autenticada, quando permanece sem requisições por mais de 30 minutos, então a próxima requisição protegida redireciona para `contas:login`; quando recebe requisições dentro de 30 minutos, o prazo é renovado.
6. **CA-02-06 (Logout apenas por POST — RN-02-04, OWASP A07):** Dada uma sessão autenticada, quando há `GET` em `contas:logout`, então o método não é permitido (HTTP 405) e a sessão permanece ativa; quando há `POST` com CSRF, a sessão é encerrada no PostgreSQL.
7. **CA-02-07 (2FA obrigatório para conta administrativa — RN-02-06, ADR 0009):** Dado um usuário com qualquer uma das 8 funções administrativas, quando autentica com senha válida, então não consegue acessar nenhuma rota administrativa enquanto `2fa_verificado = False`, sendo direcionado para `contas:totp_configurar` (se primeiro acesso) ou `contas:totp_verificar`.
8. **CA-02-08 (Pareamento TOTP e anti-replay — RN-02-06, RN-02-07):** Dado um Administrador pareando o TOTP, quando confirma um código válido de 6 dígitos gerado pelo segredo, então o dispositivo é ativado, os códigos de recuperação são salvos apenas como hash e exibidos uma única vez, e uma segunda submissão do mesmo código na mesma janela de 30 s é recusada.
9. **CA-02-09 (8 códigos de recuperação de uso único e regeneração — RN-02-08):** Dado um Administrador ativando 2FA, então são gerados 8 códigos alfanuméricos em hash exibidos uma única vez; ao usar um código na tela de 2FA, o login conclui, `usuario.codigo_recuperacao_usado` é gravado na auditoria e uma segunda tentativa com o mesmo código é recusada; ao regenerar códigos com *step-up* 2FA válido, os códigos anteriores são invalidados e 8 novos códigos são gerados.
10. **CA-02-10 (Reset de 2FA exigindo ≥ 2 Admins ativos — RN-02-08, ADR 0009):** Dado um sistema com apenas 1 Administrador ativo com `gestao_administradores`, quando tenta resetar 2FA (próprio ou de outro), então é recusado; com ≥ 2 Administradores ativos com `gestao_administradores`, um consegue resetar o 2FA do outro mediante *step-up* 2FA, encerrando as sessões do alvo e gravando `usuario.totp_resetado` na auditoria.
11. **CA-02-11 (Isolamento das 8 funções e restrição de `is_superuser` — RN-02-10, RN-02-11, ADR 0010):** Dado um usuário autenticado com `is_superuser = True` mas sem a função explícita exigida pela rota (ou um Administrador com `gestao_usuarios` acessando rota de `verificacao_receitas`), quando acessa a rota, então recebe HTTP 403.
12. **CA-02-12 (Proteção contra *open redirect* e imutabilidade de `RegistroAcesso` — RS005, RNF14):** Dado `?next=https://externo.exemplo` no login, quando o login conclui, então o redirecionamento externo é ignorado; tentativas de `UPDATE`/`DELETE` em `RegistroAcesso` no PostgreSQL são rejeitadas pelo trigger `append-only`.

---

## 12. Plano de testes

*(Executor: `python manage.py test` contra PostgreSQL — [ADR 0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md). Sem código de aplicação.)*

### 12.1 Testes de unidade (Models, Forms e Services — sem `request`)

- **Models e PostgreSQL:** trigger `append-only` bloqueia `UPDATE`/`DELETE` em `RegistroAcesso`; migração/comando idempotente cria exatamente os 8 grupos administrativos; `CodigoRecuperacaoTotp` armazena apenas hash.
- **Autenticação e bloqueio (`AutenticacaoService`):** login por e-mail (case-insensitive) e CPF (com e sem máscara); recusa de CNPJ; mensagem `"E-mail/CPF ou senha incorretos"` sempre que a senha não conferir; orientações específicas (confirmar e-mail, `inativo`, `suspenso`, `bloqueado`) somente quando a senha conferir; contagem unificada de 5 falhas (e-mail + CPF) em janela móvel de 15 min acionando bloqueio de 15 min e liberação após 15 min; limite secundário por IP (*acréscimo da especificação, não consta no RF002*); registro de sucesso, falha e bloqueado sem gravar senha.
- **2FA (`TotpService`) e sessões (`SessaoService`):** pareamento e confirmação TOTP com `pyotp` + QR code SVG local com `segno` sob relógio controlado; rejeição de reuso do mesmo código (*anti-replay*); consumo único dos 8 códigos de recuperação e regeneração com *step-up* invalidando os anteriores; *step-up* 2FA recusando código de recuperação; reset de 2FA bloqueado para si mesmo e quando há apenas 1 Admin ativo, e permitido com ≥ 2 Admins ativos + *step-up*; `encerrar_todas_sessoes` invalidando todas as sessões ativas da conta.

### 12.2 Testes de integração (Views, rotas, sessões e mixins de permissão)

- `contas:login`: `GET` renderiza `"E-mail ou CPF"` (sem CNPJ), botão "Mostrar", links de cadastro, `"Esqueci minha senha"` (`contas:recuperar_senha_em_breve`) e visitante; `POST` válido rotaciona `session_key` e rejeita `next` externo; `POST` inválido exibe `"E-mail/CPF ou senha incorretos"`; 6ª tentativa exibe `"Muitas tentativas. Tente novamente mais tarde"`.
- `contas:logout`: `GET` retorna 405; `POST` com CSRF encerra sessão e remove `SessaoUsuario`.
- Expiração de sessão: requisição após 30 min sem atividade redireciona para `contas:login`; cookies de produção (`DEBUG=False`) com `HttpOnly`, `Secure` e `SameSite=Lax`.
- Fluxo de 2FA nas views: Admin sem TOTP é redirecionado para `contas:totp_configurar` e não acessa rotas administrativas; Admin com TOTP é redirecionado para `contas:totp_verificar` e só acessa após validar código; QR code gerado localmente em SVG (`segno`) sem URL externa; `contas:totp_regenerar_codigos` exige *step-up* 2FA.
- Matriz de permissões dos mixins (`nucleo/mixins.py`): testar cada rota protegida com visitante, usuário comum sem perfil, usuário com perfil correto, Admin sem 2FA, Admin com função errada, Admin com função correta + 2FA e `is_superuser` sem função explícita.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Confirmação da tela de login sem CNPJ:** divergência de `Login ReMed.png` (`"E-mail, CPF ou CNPJ"`) corrigida na implementação para `"E-mail ou CPF"` (alinhada ao RF002 e ao RF005). | Pendência externa com o professor (Questão 14 do PRD, [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)) | Não bloqueia a implementação; confirmar com o professor. |
| 2 | **Validação do `segno` no `.venv` com Python 3.14:** embora seja Python puro com zero dependências externas, confirmar instalação e testes no `.venv` (Python 3.14) antes de fixar no `requirements.txt` na implementação do RF002 ([ADR 0004](../adr/0004-pip-venv-requirements-fixado.md)). | Validação técnica na implementação | Executada ao iniciar o código do RF002. |
