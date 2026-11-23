# Spec 01 — Cadastro de Usuário (RF001)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `01` — Cadastro de Usuário (`RF001`) |
| **Status** | `aprovada` *(formato de spec aprovado como padrão do projeto)* |
| **Requisitos de origem** | **Funcionais:** RF001 (Essencial — MVP, HU01). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF08, RNF10 (Essencial), RNF12, RNF14 (Essencial). **Segurança:** RS002, RS005, RS006. |
| **Apps envolvidos** | `contas` (principal), `nucleo` (`CepService`, `CacheCep`, exceções e mixins base), `auditoria` (`RegistroAuditoria`, `AuditoriaService`), `notificacoes` (subconjunto mínimo do RF017: *Transactional Outbox* de e-mail e despacho de confirmação). |
| **Dependências de outras specs** | Nenhuma spec anterior completa. **Pré-requisito parcial do RF017 (`03-notificacoes.md`):** o RF001 envia e-mail de confirmação (RF001 regra 3) e o login fica bloqueado até a confirmação ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)), o que exige implementar junto com esta spec o **núcleo mínimo de `notificacoes`** (tabela de *Transactional Outbox* de e-mails, método de enfileiramento de e-mail de confirmação no `NotificacaoService` e comando `manage.py` de despacho SMTP com até 3 retentativas — [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)). O restante do RF017 (notificações na plataforma, leitura, pesquisa, demais tipos de evento e limite por usuário) fica na spec do RF017. |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0003](../adr/0003-python-3-14.md), [0004](../adr/0004-pip-venv-requirements-fixado.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0007](../adr/0007-modelo-de-usuario-customizado.md), [0008](../adr/0008-hash-de-senha-argon2-ou-bcrypt.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md), [0018](../adr/0018-consulta-de-cep.md). |

---

## 2. Objetivo e escopo

Permitir que qualquer pessoa física maior de 18 anos crie sua conta no ReMed, confirme seu e-mail, consulte e atualize os próprios dados cadastrais (exceto o CPF) e solicite o encerramento da própria conta conforme a LGPD (eliminação/anonimização de dados pessoais com preservação de registros anônimos para métricas).

### Inclui

- Definição do modelo de usuário customizado (`AUTH_USER_MODEL`, antes da migração `0001_initial`), endereço privado do usuário, registro de aceite de Termos de Uso e Política de Privacidade e token de confirmação de e-mail (`contas`).
- Configuração do hasher **Argon2id** (`Argon2PasswordHasher` com padrões do Django 6.1.3 — [ADR 0008](../adr/0008-hash-de-senha-argon2-ou-bcrypt.md)), entrada de `argon2-cffi` no `requirements.txt`, `ruff`/`pip-audit`/`coverage` no `requirements-dev.txt` ([ADR 0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md)) e Bootstrap hospedado localmente ([ADR 0005](../adr/0005-bootstrap-hospedado-no-projeto.md)).
- Tela e fluxo de **Cadastro de Pessoa Física** fiel ao protótipo ([Cadastro Pessoa Física.png](../prd/telas/Cadastro%20Pessoa%20F%C3%ADsica.png)) e ao catálogo (RF001).
- Consulta de CEP via proxy no servidor (`CepService` + `CacheCep` no PostgreSQL, BrasilAPI primário + ViaCEP fallback, `urllib.request`, preenchimento manual em caso de falha — [ADR 0018](../adr/0018-consulta-de-cep.md)).
- Enfileiramento do e-mail de confirmação no *Transactional Outbox* mínimo de `notificacoes` ([ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)) e confirmação do e-mail por link de uso único (com opção de reenvio sob limite de taxa).
- Consulta e **alteração dos próprios dados cadastrais** pelo usuário autenticado (exceto CPF), sempre com histórico imutável (`AuditoriaService` — [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)).
- **Encerramento voluntário de conta** pelo próprio usuário com anonimização LGPD ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)), bloqueado para contas `suspenso` ou `bloqueado`.
- Implantação da base mínima de `auditoria` (`RegistroAuditoria` + `AuditoriaService` + trigger `append-only` no PostgreSQL — [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)).

### Não inclui

- Login, bloqueio por tentativas inválidas, expiração de sessão e 2FA do Administrador (ficam na Spec `02` — RF002).
- Recuperação de senha (v1.1 — RF003).
- Alteração de status ou atribuição/remoção de funções administrativas (Spec `04` — RF004).
- Cadastro de Pessoa Jurídica / Ponto de Coleta (a aba `"Pessoa Jurídica · Ponto de Coleta"` na tela de cadastro direciona para a rota da Spec `05` — RF005).
- Lista de notificações na plataforma, marcação de leitura, pesquisa e demais eventos de notificação (Spec `03` — RF017).
- Gestão administrativa de versões de Termos de Uso e Política de Privacidade (sem requisito próprio na fonte — Questão 27 do PRD; nesta spec a versão vigente vem de configuração nomeada).
- Busca por proximidade com geolocalização do navegador (Spec do RF015; aqui apenas salvam-se coordenadas aproximadas do CEP no endereço quando disponíveis no `CacheCep`, de forma degradável — [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md)).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Visitante** (futuro doador, solicitante ou cuidador/familiar) | Cadastrar usuário (pessoa física); consultar CEP na tela de cadastro; confirmar e-mail pelo link recebido; solicitar reenvio do link de confirmação. | Maior de 18 anos (menores são representados por cuidador/familiar — RF001 regra 2); CPF e e-mail ainda não cadastrados em conta não anonimizada; aceite obrigatório dos Termos de Uso e Política de Privacidade. |
| **Usuário autenticado** (status `ativo`, e-mail confirmado) | Consultar e alterar os próprios dados cadastrais (exceto CPF), perfis de uso e endereço; solicitar encerramento da própria conta. | Sessão autenticada válida (RF002); para encerramento de conta, o usuário **não** pode estar com status `suspenso` ou `bloqueado` ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)). |
| **Sistema** (rotina de despacho do outbox — pré-requisito mínimo do RF017) | Enviar os e-mails de confirmação pendentes no outbox via SMTP e executar até 3 novas tentativas em caso de falha. | Registro pendente na tabela de outbox (`notificacoes`). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Cadastro de pessoa física e confirmação de e-mail

1. O Visitante acessa a tela **"Criar conta · ReMed — Cadastro de pessoa física"** (`contas:cadastro`).
2. Preenche **Dados pessoais** (Nome completo, CPF, Data de nascimento, E-mail, Celular, Senha), seleciona um ou mais perfis em **Como você quer usar o ReMed?** (`Doador`, `Solicitante`, `Cuidador/Familiar`), informa o **CEP** em **Seu endereço** (com preenchimento automático de Logradouro, Bairro, Município e Estado pelo endpoint `nucleo:cep_consultar`, editando Número e Complemento) e marca o aceite dos Termos de Uso e Política de Privacidade.
3. Aciona **Cadastrar usuário** (`POST` com token CSRF).
4. A view valida o formato dos campos no `UsuarioCadastroForm` e chama `UsuarioService.cadastrar(...)`.
5. Dentro de um único `transaction.atomic()`, `UsuarioService.cadastrar(...)`:
   - Revalida regras de domínio (unicidade de CPF e e-mail normalizado em minúsculas, maioridade ≥ 18 anos, ao menos um perfil de uso, aceite dos termos);
   - Cria o `Usuario` com senha em hash Argon2id ([ADR 0008](../adr/0008-hash-de-senha-argon2-ou-bcrypt.md)), `status = ativo`, `email_confirmado_em = None` e data do cadastro automática;
   - Cria o `EnderecoUsuario` (associando coordenadas aproximadas do `CacheCep`, se disponíveis — [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md));
   - Registra o `AceiteTermo` com versão vigente dos documentos, data e hora em UTC (RF001 regra 6);
   - Gera token aleatório criptograficamente seguro (`secrets`) de uso único, persiste apenas seu **hash** em `TokenConfirmacaoEmail` e enfileira o e-mail de confirmação no outbox mínimo via `NotificacaoService.enfileirar_email_confirmacao(...)` ([ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md));
   - Registra o evento `usuario.cadastrado` via `AuditoriaService.registrar(...)` ([ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)).
6. A view exibe `"Cadastro realizado com sucesso"` com orientação para confirmar o e-mail recebido antes de entrar e redireciona (padrão POST/Redirect/GET).
7. O comando agendado do outbox (1 min — [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)) envia o e-mail com o link de confirmação.
8. O usuário acessa o link (`contas:confirmar_email`). `UsuarioService.confirmar_email(token)` valida o hash do token, verifica se não expirou nem foi usado, preenche `email_confirmado_em`, marca o token como utilizado, registra `usuario.email_confirmado` na auditoria e libera a conta para login (RF002).

### 4.2 Fluxos alternativos

- **FA-01 — Preenchimento manual do endereço quando o webservice de CEP falha ([ADR 0018](../adr/0018-consulta-de-cep.md)):** se BrasilAPI e ViaCEP falharem ou expirarem o timeout (3 s), o endpoint `nucleo:cep_consultar` retorna indisponibilidade e a interface mantém os campos `Logradouro`, `Bairro`, `Município` e `Estado` editáveis para preenchimento manual, sem perder os dados já digitados e sem bloquear o cadastro.
- **FA-02 — Cadastro sem JavaScript ativo ([ADR 0006](../adr/0006-javascript-simples-sem-framework.md)):** os campos de endereço continuam preenchíveis manualmente e todas as validações de formato e negócio ocorrem no servidor.
- **FA-03 — Reenvio do link de confirmação de e-mail (`NOVO`, decorrente de RF001 regra 3 + ADR 0007):** caso o usuário não receba o e-mail ou o link expire (validade de **24 horas**, configurável em `settings`), pode solicitar novo link informando o e-mail, com **limite de 5 solicitações por hora por e-mail e por IP** e resposta sempre genérica (sem revelar se o e-mail existe — OWASP A07); o novo pedido invalida tokens anteriores não usados e enfileira novo e-mail no outbox.
- **FA-04 — Alteração dos próprios dados cadastrais (RF001 — Alteração):** usuário autenticado acessa `contas:perfil_editar`, atualiza Nome completo, Data de nascimento (mantendo ≥ 18 anos), E-mail, Celular, Perfis de uso (`Doador`, `Solicitante`, `Cuidador/Familiar`) e/ou Endereço. O campo CPF é exibido apenas para leitura e rejeitado pelo service caso enviado alterado. `UsuarioService.atualizar_perfil(...)` salva dentro de `transaction.atomic()` e registra em `AuditoriaService` quais campos mudaram (sem copiar valores brutos de PII — [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)). **Alteração de e-mail:** o **e-mail atual permanece ativo** até que o novo e-mail seja confirmado pelo link (token de uso único válido por 24 h gravando `novo_email` em `TokenConfirmacaoEmail` e enviado ao novo endereço via outbox); somente ao confirmar o link o `email` do usuário é substituído (revalidando unicidade) e registrado na auditoria.
- **FA-05 — Encerramento voluntário da conta pelo próprio usuário (RF001 — Exclusão, RNF10, [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)):** usuário autenticado acessa `contas:encerrar_conta`, visualiza aviso claro sobre a irreversibilidade da eliminação/anonimização dos dados pessoais e manutenção anônima das estatísticas de doações/entregas, e confirma via `POST` (com reconfirmação de senha). Dentro de `transaction.atomic()`, `UsuarioService.encerrar_conta(...)`:
  1. Verifica que o status **não** é `suspenso` nem `bloqueado`;
  2. Verifica que **não existem agendamentos confirmados em andamento** (RF018) para o usuário; se houver, bloqueia o encerramento com mensagem explicando que é necessário concluir ou cancelar os agendamentos confirmados antes de encerrar a conta;
  3. **Cancela automaticamente** as doações do usuário com status `"disponível"` (RF008) e as solicitações com status `"aberta"` (RF013), **notificando a outra parte** via `NotificacaoService` caso haja correspondência/interesse vinculado;
  4. Anonimiza `Usuario` (`email = NULL`, `cpf = NULL`, `nome_completo = ""`, `celular = ""`, `data_nascimento = NULL`, `anonimizado_em = agora`, `status = inativo`, `is_active = False`, senha inutilizada via `set_unusable_password()`), exclui `EnderecoUsuario` e `TokenConfirmacaoEmail`, encerra sessões ativas da conta e registra `usuario.conta_encerrada` na auditoria.

### 4.3 Fluxos de exceção

- **FE-01 — Campos obrigatórios vazios:** formulário rejeita e exibe `"Campo(s) obrigatório(s) não preenchido(s)"`, destacando cada campo vazio e preservando os valores já preenchidos (exceto a senha).
- **FE-02 — Campo com formato ou regra inválida (CPF inválido, menor de 18 anos, nome < 3 ou > 120 caracteres, senha < 8 caracteres, celular/CEP/e-mail malformado, nenhum perfil selecionado, termos não aceitos):** rejeita exibindo `"Campo preenchido incorretamente"` junto à orientação específica do campo.
- **FE-03 — CPF já cadastrado:** `UsuarioService.cadastrar` detecta unicidade (e trata `IntegrityError` em condição de corrida) e lança `CpfJaCadastrado`, exibindo `"CPF já cadastrado"`.
- **FE-04 — E-mail já cadastrado:** `UsuarioService.cadastrar` (comparação case-insensitive) lança `EmailJaCadastrado`, exibindo `"E-mail já cadastrado"`.
- **FE-05 — Token de confirmação inválido, já usado ou expirado (após 24 h):** exibe mensagem clara orientando a solicitar novo envio do link de confirmação, sem alterar `email_confirmado_em` nem o e-mail da conta.
- **FE-06 — Tentativa de encerramento de conta por usuário `suspenso` ou `bloqueado` ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)):** `UsuarioService.encerrar_conta` recusa a operação com `PermissaoNegada` / `RegraNegocioViolada`, impedindo contornar a punição administrativa por recadastro.
- **FE-07 — Tentativa de encerramento de conta com agendamento confirmado em andamento:** `UsuarioService.encerrar_conta` bloqueia a operação com `RegraNegocioViolada`, exibindo mensagem explicando que o usuário deve concluir ou cancelar seus agendamentos confirmados antes de encerrar a conta.
- **FE-08 — Limite de taxa excedido na consulta de CEP ou no cadastro/reenvio (5/hora por e-mail e por IP):** retorna HTTP 429 com mensagem clara, sem derrubar o serviço nem expor detalhes internos.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-01-01** | O nome completo é obrigatório e deve ter no mínimo 3 e no máximo 120 caracteres (após remoção de espaços nas extremidades). | RF001 (Campos) • `contas` |
| **RN-01-02** | O CPF é obrigatório, deve ter os dígitos verificadores válidos (formato `xxx.xxx.xxx-xx` na interface, armazenado com 11 dígitos sem máscara) e ser único entre contas não anonimizadas. | RF001 (regra 1), RS006, [ADR 0002](../adr/0002-postgresql-como-banco-de-dados.md), [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md) • `contas` |
| **RN-01-03** | O CPF **não pode ser alterado** após o cadastro, nem pelo próprio usuário nem pelo Administrador. | RF001 (Alteração), RF004 (regra 1) • `contas` |
| **RN-01-04** | Cadastro permitido apenas para **maiores de 18 anos** na data do cadastro (considerando data completa de nascimento). Menores de idade são representados por um cuidador/familiar. | RF001 (regra 2) • `contas` |
| **RN-01-05** | O e-mail é obrigatório, normalizado em minúsculas e único entre contas não anonimizadas. Após o cadastro, um link de confirmação de uso único (token aleatório guardado apenas como hash, **válido por 24 horas**, configurável em `settings`) é enviado ao e-mail informado via outbox mínimo do `NotificacaoService`. O reenvio é limitado a **5 solicitações por hora por e-mail e por IP**. | RF001 (regra 3), RS006, [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md), [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md) • `contas`, `notificacoes` |
| **RN-01-06** | O acesso (login — RF002) fica **bloqueado até a confirmação do e-mail**. | [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md), RS006 • `contas` |
| **RN-01-07** | A senha deve ter no mínimo 8 caracteres e ser armazenada exclusivamente como hash **Argon2id** (`Argon2PasswordHasher`, padrões do Django 6.1.3), nunca em texto aberto nem em logs. | RF001 (regra 4), RS005, [ADR 0008](../adr/0008-hash-de-senha-argon2-ou-bcrypt.md) • `contas` |
| **RN-01-08** | O usuário seleciona um ou mais perfis de uso acumuláveis entre `Doador`, `Solicitante` e `Cuidador/Familiar` (pelo menos 1 obrigatório). Nenhuma rota de cadastro ou edição de perfil permite atribuir funções administrativas nem o papel de ponto de coleta (que decorre de vínculo ativo com `PontoColeta` no RF005). | RF001 (regra 5), [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `contas` |
| **RN-01-09** | O aceite dos Termos de Uso e da Política de Privacidade é obrigatório no cadastro, registrando a **versão do documento aceito, a data e a hora** (UTC). No MVP, usa-se versão placeholder configurável (`"1.0-rascunho"`) até a entrega do texto final. | RF001 (regra 6), RNF10 • `contas` |
| **RN-01-10** | Todo usuário nasce com `status = ativo` e `data_cadastro` preenchida automaticamente pelo sistema. Os status válidos são `ativo`, `inativo`, `suspenso` e `bloqueado` — sendo `inativo` interpretado como conta que não consegue entrar mas pode ser reativada (distinto de `suspenso`, que exige motivo do Administrador). | RF001 (regra 7), [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md) • `contas` |
| **RN-01-11** | O endereço é preenchido automaticamente pelo CEP (`CepService`: cache no PostgreSQL, BrasilAPI primário, ViaCEP fallback, `urllib.request`) com edição de número e complemento (opcional). Se ambos os webservices falharem, o preenchimento manual é liberado. O link `"Não sei meu CEP"` abre a busca oficial dos Correios em nova aba (`rel="noopener noreferrer"`), com preenchimento manual como alternativa. O endereço do usuário serve **apenas para geolocalização aproximada (RF015)** e **nunca é exibido a outros usuários**. | RF001 (regra 8), RS002, RNF12, [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md), [ADR 0018](../adr/0018-consulta-de-cep.md) • `contas`, `nucleo` |
| **RN-01-12** | O usuário pode alterar seus próprios dados cadastrais (exceto CPF), perfis de uso e endereço. Toda criação ou alteração gera registro imutável em `AuditoriaService` (quem, o quê — lista de campos alterados, sem PII bruto — data e hora). Ao alterar o e-mail, o **e-mail atual permanece ativo até que o novo e-mail seja confirmado** via link de uso único (24 h). | RF001 (Alteração), RNF14, [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `contas`, `auditoria`, `notificacoes` |
| **RN-01-13** | O usuário pode solicitar o encerramento da própria conta. Não há exclusão física quando existirem registros históricos vinculados (`on_delete=PROTECT`): o sistema **cancela automaticamente** as doações `"disponíveis"` e solicitações `"abertas"` do usuário (com aviso à outra parte quando houver vínculo), anonimiza os dados pessoais (`email = NULL`, `cpf = NULL`, limpeza de nome/celular/data de nascimento, exclusão do endereço, `anonimizado_em` preenchido, `status = inativo`, senha inutilizada), mantém registros anônimos para métricas (RF022) e libera CPF/e-mail para eventual recadastro futuro. | RF001 (Exclusão), RNF10, [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md) • `contas`, `notificacoes` |
| **RN-01-14** | O encerramento de conta é **proibido** enquanto o usuário estiver com status `suspenso` ou `bloqueado` pelo Administrador (impedindo contornar o bloqueio por recadastro com o mesmo CPF ou e-mail) **ou enquanto houver agendamento confirmado em andamento** (RF018), exibindo mensagem explicando o que o usuário precisa fazer antes de encerrar. | [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md), RS006, RF004, RF018 • `contas` |
| **RN-01-15** | O CPF **não** é criptografado em campo na aplicação; sua proteção ocorre por criptografia no banco/disco, controle de acesso por perfil e ocultação parcial nas telas administrativas (RF004). | [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md), RS002, RF004 • `contas` |

---

## 6. Modelo de dados lógico

*(Nível lógico — sem código de models. Todas as datas/horas usam fuso horário com `USE_TZ = True`.)*

### 6.1 Entidades e campos

#### `Usuario` (app `contas` — `AUTH_USER_MODEL`, herda de `AbstractBaseUser` e `PermissionsMixin`, sem campo `username`)

| Campo | Tipo lógico | Obrigatório | Formato / regras / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | Identificador técnico preservado após anonimização (`on_delete=PROTECT` nas relações históricas). |
| `nome_completo` | String (120) | Sim (enquanto não anonimizado) | Mín. 3 e máx. 120 caracteres. Limpo (`""`) após anonimização. |
| `cpf` | String (11), anulável | Sim (enquanto não anonimizado) | 11 dígitos sem máscara; validado por dígito verificador; imutável após criação. `UniqueConstraint` parcial (`cpf IS NOT NULL`). `NULL` após anonimização. |
| `data_nascimento` | Date, anulável | Sim (enquanto não anonimizado) | `xx/xx/xxxx` na interface; idade ≥ 18 anos. `NULL` após anonimização. |
| `email` | EmailField (254), anulável | Sim (enquanto não anonimizado) | `USERNAME_FIELD`; normalizado em minúsculas. Unicidade condicional/parcial (com tratamento explícito de `auth.W004` ou `unique=True, null=True` — [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)). `NULL` após anonimização. |
| `email_confirmado_em` | Datetime, anulável | Não | Nulo até confirmação pelo link; bloqueia login enquanto nulo ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)). |
| `celular` | String (11) | Sim (enquanto não anonimizado) | Formato `(xx)xxxxx-xxxx` na interface (10 ou 11 dígitos armazenados sem máscara). Limpo (`""`) após anonimização. |
| `password` | String (herdado) | Sim | Hash Argon2id ([ADR 0008](../adr/0008-hash-de-senha-argon2-ou-bcrypt.md)); inutilizado no encerramento. |
| `perfil_doador` | Boolean | Sim | Padrão `False`; ao menos um entre os 3 perfis deve ser `True` (verificado por constraint/service enquanto não anonimizado). |
| `perfil_solicitante` | Boolean | Sim | Padrão `False`. |
| `perfil_cuidador` | Boolean | Sim | Padrão `False` (corresponde a `Cuidador/Familiar`). |
| `status` | TextChoices | Sim | Valores: `ativo`, `inativo`, `suspenso`, `bloqueado`. Padrão: `ativo`. |
| `is_staff` / `is_superuser` / `is_active` | Boolean | Sim | Compatibilidade com Django (`is_superuser` restrito ao bootstrap por terminal — [ADR 0010](../adr/0010-perfis-e-permissoes.md)). A sincronização `is_active = (status == "ativo" and anonimizado_em is None)` ocorre **exclusivamente na camada de service** (nunca em `save()` — ADR 0001). |
| `criado_em` | Datetime | Sim | Preenchido automaticamente (cobre `Data do cadastro`). |
| `atualizado_em` | Datetime | Sim | Atualizado automaticamente. |
| `anonimizado_em` | Datetime, anulável | Não | Nulo enquanto a conta existir; preenchido no encerramento LGPD. |

**Constraints obrigatórias no PostgreSQL (`Usuario`):**
- `UniqueConstraint` parcial em `cpf` onde `cpf IS NOT NULL`;
- `CheckConstraint` garantindo que, quando `cpf IS NOT NULL`, o valor contenha exatamente **11 dígitos numéricos** (`cpf ~ '^[0-9]{11}$'`);
- `UniqueConstraint` em `email` (com `unique=True, null=True` + `UniqueConstraint` parcial em `Lower("email")` — [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md));
- `CheckConstraint` garantindo que, quando `anonimizado_em IS NULL`, `email IS NOT NULL` e `cpf IS NOT NULL` (e quando `anonimizado_em IS NOT NULL`, `email IS NULL` e `cpf IS NULL`) — inclusive para o comando `bootstrap_admin` (Etapa 3), que coleta um CPF válido;
- `CheckConstraint` garantindo que, quando `anonimizado_em IS NULL` e `is_superuser = False`, ao menos um perfil (`perfil_doador`, `perfil_solicitante` ou `perfil_cuidador`) é `True`.

#### `EnderecoUsuario` (app `contas`, relação `OneToOne` com `Usuario`)

| Campo | Tipo lógico | Obrigatório | Formato / regras |
| --- | --- | --- | --- |
| `usuario` | FK/OneToOne (`Usuario`) | Sim | `on_delete=CASCADE` (eliminado fisicamente no encerramento LGPD — sem exposição pública). |
| `cep` | String (8) | Sim | `xxxxx-xxx` na interface; 8 dígitos armazenados. |
| `logradouro` | String (150) | Sim | Preenchido pelo CEP ou manualmente em fallback. |
| `numero` | String (20) | Sim | Editável pelo usuário. |
| `bairro` | String (100) | Sim | Preenchido pelo CEP ou manualmente. |
| `municipio` | String (100) | Sim | Preenchido pelo CEP ou manualmente. |
| `estado` | String (2) | Sim | Sigla UF válida (27 UFs brasileiras). |
| `complemento` | String (100) | Não | Opcional. |
| `latitude_aprox` / `longitude_aprox` | Decimal (anulável) | Não | Coordenadas aproximadas (centróide do CEP / ~2 casas decimais) para uso interno na busca (RF015, [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md)); **nunca exibidas**. |

#### `AceiteTermo` (app `contas`, relação `ForeignKey` com `Usuario`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `usuario` | FK (`Usuario`, `PROTECT`) | Sim | Mantém registro de consentimento conforme política de privacidade (RNF10). |
| `versao_termos_uso` | String (30) | Sim | Versão vigente dos Termos de Uso no momento do aceite. |
| `versao_politica_privacidade` | String (30) | Sim | Versão vigente da Política de Privacidade no momento do aceite. |
| `aceito_em` | Datetime | Sim | Data e hora do aceite em UTC (RF001 regra 6). |

#### `TokenConfirmacaoEmail` (app `contas`)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `usuario` | FK (`Usuario`, `CASCADE`) | Sim | Eliminado no encerramento da conta. |
| `tipo` | TextChoices | Sim | `cadastro` (confirmação inicial) ou `alteracao_email` (troca de e-mail mantendo o atual ativo até confirmar). |
| `email_destino` | EmailField (254) | Sim | E-mail a ser confirmado (no cadastro, igual ao `usuario.email`; na troca, o novo e-mail pendente). |
| `token_hash` | String (64, único) | Sim | Hash SHA-256 do token gerado via `secrets`; token em texto aberto **nunca** é persistido. |
| `criado_em` | Datetime | Sim | Data/hora de geração. |
| `expira_em` | Datetime | Sim | Padrão: `criado_em + 24 horas` (configurável em `settings`). |
| `usado_em` | Datetime, anulável | Não | Preenchido no uso único ou invalidado ao gerar novo token. |

#### Entidades de apoio criadas/usadas nesta spec

- **`CacheCep` (`nucleo` — [ADR 0018](../adr/0018-consulta-de-cep.md)):** `cep` (PK, 8 dígitos), `logradouro`, `bairro`, `municipio`, `estado`, `latitude_aprox`, `longitude_aprox`, `fonte` (`brasilapi` / `viacep`), `atualizado_em`.
- **`RegistroAuditoria` (`auditoria` — [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)):** tabela `append-only` com trigger `BEFORE UPDATE OR DELETE` no PostgreSQL (`criado_em`, `ator`, `acao`, `entidade_tipo`, `entidade_id`, `motivo`, `detalhes` sem PII bruto, `origem`).
- **`OutboxEmail` (`notificacoes` — pré-requisito mínimo do RF017, [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)):** `destinatario_usuario` (FK `PROTECT` ou `SET_NULL` após anonimização), `email_destino`, `tipo` (`confirmacao_email` nesta spec), `assunto`, `corpo_texto`, `status` (`pendente`, `enviada`, `falha`), `tentativas` (0..3), `proxima_tentativa_em`, `criado_em`, `enviado_em`, `erro_ultimo`.

### 6.2 Status e transições (no escopo do RF001)

| Origem | Destino | Condição | Quem dispara |
| --- | --- | --- | --- |
| *(novo)* | `ativo` (`email_confirmado_em = NULL`) | Cadastro válido + aceite dos termos | Visitante (`RF001`) |
| `ativo` (não confirmado) | `ativo` (confirmado) | Token de confirmação válido, não expirado e não utilizado | Usuário via link (`RF001`) |
| `ativo` | `inativo` (`anonimizado_em != NULL`) | Pedido voluntário de encerramento da própria conta (com reconfirmação de senha) | Próprio usuário (`RF001`) |
| `suspenso` / `bloqueado` | *(bloqueado)* | Encerramento voluntário **vedado** ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)) | Sistema recusa |

*(As transições administrativas `ativo <-> inativo / suspenso / bloqueado` pertencem à Spec `04` — RF004.)*

### 6.3 Histórico obrigatório (RNF14 / [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md))

Eventos gravados via `AuditoriaService.registrar(...)` dentro da mesma transação:
- `usuario.cadastrado` (ator: próprio usuário criado; `detalhes`: perfis escolhidos e versões aceitas dos termos — sem CPF, e-mail, endereço ou senha);
- `usuario.email_confirmado` (ator: próprio usuário);
- `usuario.perfil_alterado` (ator: próprio usuário; `detalhes`: lista dos nomes dos campos alterados, ex.: `["celular", "endereco", "perfil_doador"]` — sem valores brutos de PII);
- `usuario.conta_encerrada` (ator: próprio usuário; `detalhes`: `{"anonimizado": true}`).

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

### 7.1 Camada de entrada (Views e Forms)

| View / Form | App | Métodos | Acesso | Responsabilidade (sem regra de negócio nem ORM) |
| --- | --- | --- | --- | --- |
| `UsuarioCadastroView` + `UsuarioCadastroForm` | `contas` | `GET`, `POST` | Visitante (usuário já autenticado é redirecionado à página inicial/perfil) | Exibe o formulário, valida formato dos campos, chama `UsuarioService.cadastrar(...)`, traduz exceções (`CpfJaCadastrado`, `EmailJaCadastrado`, `RegraNegocioViolada`) em erros de formulário/mensagens literais e faz redirect (PRG) no sucesso. |
| `ConfirmarEmailView` | `contas` | `GET` | Público (link com token) | Extrai o token da URL, chama `UsuarioService.confirmar_email(token)` e renderiza confirmação ou mensagem de link inválido/expirado com opção de reenvio. |
| `ReenviarConfirmacaoEmailView` + `ReenviarConfirmacaoForm` | `contas` | `GET`, `POST` | Público (com rate limit por IP/e-mail) | Valida formato do e-mail, chama `UsuarioService.reenviar_confirmacao_email(email)` e exibe sempre a mesma mensagem genérica de confirmação de solicitação. |
| `UsuarioPerfilEditarView` + `UsuarioPerfilEditarForm` | `contas` | `GET`, `POST` | Autenticado (`ativo`, e-mail confirmado) | Carrega dados via `UsuarioService.obter_perfil(request.user.id)`, valida formato (CPF somente leitura, excluído de `Meta.fields`), chama `UsuarioService.atualizar_perfil(...)` e redireciona no sucesso. |
| `UsuarioEncerrarContaView` + `UsuarioEncerrarContaForm` | `contas` | `GET`, `POST` | Autenticado (`ativo`, e-mail confirmado) | Exibe aviso de consequências LGPD, valida preenchimento da senha de confirmação, chama `UsuarioService.encerrar_conta(request.user, senha)`, executa `logout(request)` na view e redireciona com mensagem de confirmação. |
| `CepConsultarView` | `nucleo` | `GET` | Público (com rate limit por IP) | Valida 8 dígitos do CEP, chama `CepService.consultar(cep)` e devolve JSON mínimo (`logradouro`, `bairro`, `municipio`, `estado`) ou status adequado em erro/indisponibilidade. |

### 7.2 Camada de regra de negócio (Services)

| Service e método | App | Transacional? | Entradas / saídas e regras aplicadas |
| --- | --- | --- | --- |
| `UsuarioService.cadastrar(dados)` | `contas` | **Sim** (`transaction.atomic`) | Aplica `RN-01-01` a `RN-01-11`: normaliza CPF/e-mail, valida dígitos do CPF, maioridade ≥ 18 anos, unicidade (tratando corrida via `IntegrityError`), cria `Usuario` + `EnderecoUsuario` + `AceiteTermo` + `TokenConfirmacaoEmail`, enfileira e-mail no outbox (`NotificacaoService`) e registra `usuario.cadastrado` (`AuditoriaService`). |
| `UsuarioService.confirmar_email(token_claro)` | `contas` | **Sim** (`transaction.atomic`) | Calcula SHA-256 do token, busca `TokenConfirmacaoEmail` não usado e não expirado (`select_for_update`), marca `usado_em` e `usuario.email_confirmado_em`, e registra `usuario.email_confirmado` na auditoria. |
| `UsuarioService.reenviar_confirmacao_email(email)` | `contas` | **Sim** (`transaction.atomic`) | Se existir conta ativa não anonimizada com e-mail ainda não confirmado, invalida tokens anteriores, gera novo token, enfileira e-mail no outbox. Silencioso se o e-mail não existir ou já estiver confirmado (evita enumeração). |
| `UsuarioService.atualizar_perfil(usuario_id, dados)` | `contas` | **Sim** (`transaction.atomic`) | Bloqueia alteração de CPF (`RN-01-03`), revalida maioridade/unicidade de e-mail/perfis (`RN-01-08`), atualiza `Usuario` e `EnderecoUsuario` e grava `usuario.perfil_alterado` (apenas nomes dos campos modificados). |
| `UsuarioService.encerrar_conta(usuario, senha_atual)` | `contas` | **Sim** (`transaction.atomic`) | Confirma `check_password`, aplica `RN-01-14` (recusa se `suspenso`/`bloqueado`), aplica `RN-01-13` (anonimiza `Usuario`, apaga `EnderecoUsuario` e tokens, invalida sessões da conta no banco) e grava `usuario.conta_encerrada`. |
| `CepService.consultar(cep)` | `nucleo` | Não (upsert de cache) | Consulta `CacheCep` (TTL configurável, ex.: 30 dias); em *miss*, chama BrasilAPI (timeout 3 s, `urllib.request`) e faz fallback para ViaCEP; persiste cache (incluindo coordenadas aproximadas se retornadas) ou lança `ServicoCepIndisponivel`. |
| `NotificacaoService.enfileirar_email_confirmacao(usuario, url_confirmacao)` | `notificacoes` | Participa da transação chamadora | Grava registro `pendente` em `OutboxEmail` com template sem dados sensíveis (RS002, RS014). Despachado pelo comando `manage.py despachar_emails` (1 min, até 3 tentativas — [ADR 0015](../adr/0015-notificacoes-email-e-plataforma.md)). |
| `AuditoriaService.registrar(...)` | `auditoria` | Participa da transação chamadora | Insere registro imutável em `RegistroAuditoria` validando que `detalhes` não contém chaves proibidas (senha/token/CPF bruto). |

### 7.3 Interface (Telas e templates)

- **Tela principal — `templates/contas/usuario_cadastro.html`** (fiel a [Cadastro Pessoa Física.png](../prd/telas/Cadastro%20Pessoa%20F%C3%ADsica.png) e ao catálogo):
  - Cabeçalho com logo ReMed, título **"Criar conta · ReMed"** e subtítulo **"Cadastro de pessoa física"**.
  - Duas abas: **"Pessoa Física · Doador / Solicitante"** (ativa) e **"Pessoa Jurídica · Ponto de Coleta"** (link para RF005).
  - Seção **Dados pessoais** (`"Preencha seus dados para fazer parte da rede. Os campos com * são obrigatórios."`):
    - `Nome completo *` (dica: `"De 3 a 120 caracteres."`);
    - `CPF *` (máscara `000.000.000-00`, dica: `"Informe um CPF válido e ainda não cadastrado."`);
    - `Data de nascimento *` (`dd/mm/aaaa`, dica: `"Cadastro para maiores de 18 anos."`) + aviso `"Menores de 18 anos devem ser representados por um cuidador ou familiar."`;
    - `E-mail *` (dica: `"Use um e-mail não cadastrado. Enviaremos a confirmação."`);
    - `Celular *` (máscara `(00) 00000-0000`);
    - `Senha *`, com botão **"Mostrar"** em JavaScript simples ([ADR 0006](../adr/0006-javascript-simples-sem-framework.md)) e dica `"Use no mínimo 8 caracteres."`.
  - Seção **Como você quer usar o ReMed?** (`"Selecione um ou mais perfis. Você pode doar, solicitar e cuidar."`): caixas de seleção `Doador`, `Solicitante` e `Cuidador/Familiar`.
  - Seção **Seu endereço** (`"Informe o CEP para preencher o endereço automaticamente. Depois, edite o número e o complemento."`):
    - `CEP *` + link `"Não sei meu CEP"`;
    - `Logradouro *`, `Número *`, `Bairro *`, `Município *`, `Estado *` (UF), `Complemento (opcional)`;
    - Quadro informativo: `"Seu endereço é usado apenas para localização aproximada e não será exibido a outros usuários."`.
  - Caixa de seleção `"Li e aceito os Termos de Uso e a Política de Privacidade. *"` + nota `"A data do cadastro é registrada automaticamente pelo sistema."`.
  - Botão primário **Cadastrar usuário**, link `"Já tem uma conta? Entrar"` e rodapé `"ReMed · Conectando cuidado, compartilhando saúde."`.
- **Demais templates da spec:**
  - `templates/base.html` e `templates/partials/_mensagens.html` (Bootstrap hospedado em `static/vendor/bootstrap/` + tokens em `static/css/remed.css`);
  - `templates/contas/confirmacao_email_resultado.html` e `templates/contas/reenviar_confirmacao.html`;
  - `templates/contas/usuario_perfil_editar.html` (com CPF somente leitura e link para encerrar conta);
  - `templates/contas/usuario_encerrar_conta.html` (aviso claro de irreversibilidade LGPD + campo de senha + botão de confirmação).

### 7.4 Rotas

| Nome da URL | Caminho proposto | Propósito |
| --- | --- | --- |
| `contas:cadastro` | `/contas/cadastro/` | Exibir e processar o cadastro de pessoa física. |
| `contas:confirmar_email` | `/contas/confirmar-email/<str:token>/` | Validar token e confirmar e-mail da conta. |
| `contas:reenviar_confirmacao` | `/contas/reenviar-confirmacao/` | Solicitar novo envio de link de confirmação de e-mail. |
| `contas:perfil_editar` | `/contas/meu-perfil/` | Consultar e alterar os próprios dados cadastrais (exceto CPF). |
| `contas:encerrar_conta` | `/contas/encerrar-conta/` | Solicitar e confirmar o encerramento/anonimização da própria conta. |
| `nucleo:cep_consultar` | `/enderecos/cep/<str:cep>/` | Proxy interno (JSON) para preenchimento automático de endereço por CEP. |

---

## 8. Mensagens e validações

Textos literais exigidos pela fonte (RF001):

| Condição | Mensagem literal |
| --- | --- |
| Um ou mais campos obrigatórios vazios (incluindo nenhum perfil marcado ou termos não aceitos) | `"Campo(s) obrigatório(s) não preenchido(s)"` *(destacando cada campo vazio)* |
| Campo com formato ou regra inválida (CPF inválido, menor de 18 anos, nome < 3 ou > 120, senha < 8, celular/CEP/e-mail inválido) | `"Campo preenchido incorretamente"` *(acompanhada da instrução clara de como corrigir — RNF02)* |
| CPF já existente em conta não anonimizada | `"CPF já cadastrado"` |
| E-mail já existente em conta não anonimizada (case-insensitive) | `"E-mail já cadastrado"` |
| Cadastro concluído com sucesso | `"Cadastro realizado com sucesso"` |

---

## 9. Segurança e privacidade

### Mapeamento de requisitos de segurança × OWASP Top 10:2025

| Requisito | Perigo resumido | Categoria OWASP 2025 | Controle aplicado nesta spec |
| --- | --- | --- | --- |
| **RS002** | Exposição de dados pessoais ou endereço do usuário | A01 (Controle de acesso quebrado), A04 (Falhas criptográficas) | Endereço privado em tabela dedicada nunca exibido a terceiros; e-mail de confirmação sem PII extra; auditoria sem cópia bruta de PII; CPF protegido no banco/disco ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)). |
| **RS005** | Acesso indevido a contas, senhas fracas, CSRF/XSS/SQLi | A04, A05 (Injeção), A07 (Falhas de autenticação) | Senha ≥ 8 caracteres com hash Argon2id ([ADR 0008](../adr/0008-hash-de-senha-argon2-ou-bcrypt.md)); `{% csrf_token %}` em todo POST; autoescape ativo nos templates (sem `|safe`); ORM parametrizado; token de confirmação via `secrets` salvo só como hash SHA-256. |
| **RS006** | Perfis falsos e contorno de suspensão/bloqueio | A06 (Design inseguro), A07 | CPF único validado no banco (`UniqueConstraint`), e-mail confirmado obrigatório para login ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)), proibição de encerramento de conta para usuários `suspenso` ou `bloqueado`, histórico imutável (RNF14). |

### Pontos adicionais de segurança

- **Risco aceito de enumeração no cadastro (OWASP A07):** a fonte exige literalmente as mensagens `"CPF já cadastrado"` e `"E-mail já cadastrado"`. Esse risco é mitigado por limite de taxa por IP na rota `contas:cadastro`. Já na rota `contas:reenviar_confirmacao`, a resposta é sempre genérica (sem revelar se o e-mail existe).
- **Mass assignment (OWASP A01):** `UsuarioCadastroForm` e `UsuarioPerfilEditarForm` declaram `Meta.fields` explicitamente; `status`, `is_staff`, `is_superuser`, `groups`, `user_permissions`, `email_confirmado_em` e `cpf` (na edição) nunca são aceitos via formulário.
- **Proteção contra abuso do proxy de CEP (OWASP A03/A06):** `nucleo:cep_consultar` valida 8 dígitos, aplica rate limit por IP, usa timeout curto (3 s) e nunca expõe credenciais ou *stack traces*.

---

## 10. Requisitos não funcionais aplicáveis

| ID | Exigência aplicada a esta spec |
| --- | --- |
| **RNF01** | Linguagem simples, dicas junto aos campos (conforme protótipo) e ações claras ("Cadastrar usuário"). |
| **RNF02** | Mensagens de erro claras indicando o motivo e como corrigir, mantendo os dados digitados pelo usuário (exceto senha). |
| **RNF03** | Conformidade WCAG 2.1 AA: rótulos `<label for>`, `aria-describedby` nos erros, `aria-live` no resumo de erros, contraste ≥ 4,5:1, foco visível e navegação completa por teclado (inclusive no botão "Mostrar" senha). |
| **RNF04** | Página pública de cadastro e consulta de CEP respondem em até 3 segundos (p95) com até 500 usuários simultâneos (cache de CEP no PostgreSQL + timeout de 3 s nos provedores). |
| **RNF07** | Layout web responsivo (*mobile first* a partir de 375 px) nas duas últimas versões de Chrome, Edge, Firefox e Safari, usando Bootstrap local ([ADR 0005](../adr/0005-bootstrap-hospedado-no-projeto.md)). |
| **RNF08** | Baixo consumo de dados (sem CDNs externas, CSS/JS enxutos — [ADRs 0005 e 0006](../adr/0006-javascript-simples-sem-framework.md)). |
| **RNF10** | LGPD: coleta do mínimo necessário, aceite registrado com versão/data/hora, encerramento com anonimização/eliminação dos dados pessoais preservando estatísticas anônimas. |
| **RNF12** | Interoperabilidade com webservice de CEP (`CepService`: BrasilAPI + fallback ViaCEP + preenchimento manual em falha). |
| **RNF14** | Histórico imutável de criação, alteração de perfil, confirmação de e-mail e encerramento de conta em `RegistroAuditoria` com trigger `append-only` ([ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)). |

---

## 11. Critérios de aceite

1. **CA-01-01 (Cadastro válido — RF001, RN-01-01..RN-01-11):** Dado um Visitante maior de 18 anos com CPF válido inédito, e-mail inédito, senha com 8+ caracteres, ao menos um perfil marcado, endereço preenchido e termos aceitos, quando submete o cadastro, então o sistema cria o usuário com `status = ativo`, `email_confirmado_em = NULL`, senha em hash `argon2$argon2id$`, registra o aceite com versão/data/hora, grava `usuario.cadastrado` na auditoria, enfileira o e-mail de confirmação no outbox e exibe `"Cadastro realizado com sucesso"`.
2. **CA-01-02 (Campos obrigatórios vazios — RF001 Mensagens):** Dado um Visitante que envia o formulário com um ou mais campos obrigatórios vazios (ou sem perfil marcado, ou sem marcar o aceite dos termos), quando submete o cadastro, então o sistema não cria o usuário, destaca os campos pendentes, mantém os demais dados preenchidos (exceto senha) e exibe `"Campo(s) obrigatório(s) não preenchido(s)"`.
3. **CA-01-03 (Limites de nome completo — RN-01-01):** Dado um nome com 2 caracteres ou 121 caracteres, quando o Visitante submete, então é rejeitado com `"Campo preenchido incorretamente"`; com 3 ou 120 caracteres, é aceito.
4. **CA-01-04 (Validação de CPF — RN-01-02):** Dado um CPF com dígito verificador inválido (ou sequência repetida como `111.111.111-11`), quando o Visitante submete, então é rejeitado com `"Campo preenchido incorretamente"`.
5. **CA-01-05 (Unicidade de CPF — RN-01-02):** Dado um CPF já vinculado a uma conta não anonimizada, quando outro Visitante tenta cadastrar esse CPF, então o cadastro é rejeitado com `"CPF já cadastrado"`.
6. **CA-01-06 (Limite de maioridade — RN-01-04):** Dado um Visitante com 17 anos e 364 dias na data atual, quando submete o cadastro, então é rejeitado com `"Campo preenchido incorretamente"`; com exatamente 18 anos completos na data atual, é aceito.
7. **CA-01-07 (Unicidade de e-mail case-insensitive — RN-01-05):** Dado o e-mail `maria@exemplo.com` já cadastrado, quando outro Visitante tenta cadastrar `MARIA@Exemplo.com`, então é rejeitado com `"E-mail já cadastrado"`.
8. **CA-01-08 (Limite mínimo de senha e hash Argon2id — RN-01-07, ADR 0008):** Dada uma senha com 7 caracteres, quando o Visitante submete, então é rejeitada com `"Campo preenchido incorretamente"`; com 8 caracteres, é aceita e gravada no banco iniciando por `argon2$argon2id$`.
9. **CA-01-09 (Confirmação de e-mail por token de uso único — RN-01-05, RN-01-06):** Dado um usuário recém-cadastrado com token válido, quando acessa o link de confirmação, então `email_confirmado_em` é preenchido, `usuario.email_confirmado` é gravado na auditoria e uma segunda tentativa com o mesmo link é recusada como já utilizado/inválido.
10. **CA-01-10 (Falha e fallback da consulta de CEP — RN-01-11, ADR 0018):** Dada uma consulta de CEP válida, quando a BrasilAPI falha/expira, então o `CepService` consulta o ViaCEP e preenche os campos (armazenando em `CacheCep`); quando ambos falham, a tela informa a indisponibilidade e permite preencher manualmente e concluir o cadastro sem perda de dados.
11. **CA-01-11 (Alteração de dados sem alterar CPF — RN-01-03, RN-01-12):** Dado um usuário autenticado alterando celular, endereço e perfis de uso, quando salva, então os dados são atualizados, o CPF permanece inalterado (mesmo que enviado adulterado no `POST`) e `RegistroAuditoria` grava `usuario.perfil_alterado` contendo apenas os nomes dos campos alterados (sem valores brutos de PII).
12. **CA-01-12 (Proteção contra mass assignment — RN-01-08, OWASP A01):** Dado um `POST` de cadastro ou edição enviando campos extras (`status=suspenso`, `is_superuser=true`, `is_staff=true`), quando processado, então esses campos são ignorados e o usuário não recebe privilégios administrativos.
13. **CA-01-13 (Encerramento voluntário e recadastro — RN-01-13, ADR 0007):** Dado um usuário com status `ativo` que confirma sua senha para encerrar a conta, quando o encerramento conclui, então `email` e `cpf` ficam `NULL`, nome/celular/data de nascimento são limpos, `EnderecoUsuario` é removido, `anonimizado_em` é preenchido, `status` passa a `inativo`, `usuario.conta_encerrada` é gravado na auditoria, os registros históricos referenciados permanecem íntegros e um novo cadastro posterior com o mesmo CPF e e-mail é aceito.
14. **CA-01-14 (Encerramento vedado a conta suspensa, bloqueada ou com agendamento confirmado — RN-01-14, ADR 0007):** Dado um usuário com status `suspenso`, `bloqueado` ou com agendamento confirmado em andamento, quando tenta encerrar a própria conta pelo service ou pela rota, então a operação é negada com mensagem explicativa clara; para conta `ativo` sem agendamentos confirmados, doações `"disponíveis"` e solicitações `"abertas"` são canceladas automaticamente com aviso à outra parte (quando vinculada).
15. **CA-01-15 (Alteração de e-mail mantendo o atual ativo até confirmar — RN-01-12):** Dado um usuário autenticado que solicita alterar seu e-mail para um novo endereço inédito, quando salva, então o e-mail atual continua ativo na conta, um token válido por 24 h é enviado ao novo e-mail e somente após confirmar o link o `email` da conta é efetivamente substituído.
16. **CA-01-16 (Imutabilidade da auditoria — RNF14, ADR 0011):** Dado um registro criado em `RegistroAuditoria`, quando ocorre tentativa de `UPDATE` ou `DELETE` pela conexão da aplicação no PostgreSQL, então o banco rejeita a operação por meio do trigger `append-only`.
17. **CA-01-17 (Proteção contra XSS — RS005, OWASP A05):** Dado um nome completo ou complemento contendo `<script>alert(1)</script>`, quando exibido na tela de perfil, então o texto é escapado pelo autoescape e nenhum script é executado.
18. **CA-01-18 (Limite de reenvio de confirmação — RN-01-05):** Dado um solicitante que pede reenvio do link de confirmação mais de 5 vezes em 1 hora para o mesmo e-mail ou pelo mesmo IP, quando realiza a 6ª tentativa, então é bloqueado com HTTP 429; nas tentativas permitidas, a resposta é idêntica exista ou não o e-mail cadastrado.

---

## 12. Plano de testes

*(Executor: `python manage.py test` contra PostgreSQL — [ADR 0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md). Sem código de aplicação.)*

### 12.1 Testes de unidade (Models, Forms e Services — sem `request`)

- **Model e constraints PostgreSQL (`contas`, `auditoria`):**
  - `AUTH_USER_MODEL` aponta para o modelo customizado sem `username` e `python manage.py check` passa sem `auth.E003` nem `auth.W004` não tratado;
  - `UniqueConstraint` impede dois usuários não anonimizados com mesmo CPF ou mesmo e-mail (case-insensitive), mas permite múltiplos usuários anonimizados com `email = NULL` e `cpf = NULL`;
  - `CheckConstraint` impede `email = NULL` ou `cpf = NULL` quando `anonimizado_em IS NULL`;
  - `on_delete=PROTECT` impede exclusão física de usuário com `AceiteTermo` ou registros vinculados;
  - Trigger `append-only` em `RegistroAuditoria` lança erro no PostgreSQL em tentativas de `UPDATE` e `DELETE`.
- **Forms (`contas`):**
  - Validação de campos obrigatórios, limites de nome (2, 3, 120, 121), CPF válido/inválido, maioridade (17a 364d vs 18a), celular, CEP, UF, senha (7 vs 8 caracteres), pelo menos 1 perfil, aceite obrigatório e ausência de campos de sistema em `Meta.fields`.
- **Services (`UsuarioService`, `CepService`, `NotificacaoService`, `AuditoriaService`):**
  - Cadastro feliz criando todas as entidades na mesma transação + hash `argon2$argon2id$` + outbox de e-mail + evento de auditoria sem PII bruto;
  - *Rollback* completo em erro induzido durante o cadastro (nenhum usuário, outbox ou auditoria órfãos);
  - Rejeição de CPF duplicado (`"CPF já cadastrado"`) e e-mail duplicado (`"E-mail já cadastrado"`);
  - Confirmação de e-mail: token válido, token reutilizado (recusado), token expirado (recusado) e reenvio invalidando token anterior;
  - Atualização de perfil ignorando/recusando mudança de CPF e gravando apenas os nomes dos campos alterados na auditoria;
  - Encerramento de conta: sucesso para `ativo` (liberando recadastro com mesmo CPF/e-mail), recusa com senha errada e recusa para `suspenso` e `bloqueado`;
  - `CepService` (com dublês de `urllib.request`): hit de cache sem HTTP, miss chamando BrasilAPI, fallback para ViaCEP em timeout/erro e exceção tratada quando ambos falham;
  - Comando `despachar_emails` (com backend `locmem` e dublê de falha SMTP): envio bem-sucedido e até 3 novas tentativas antes de marcar `falha`.

### 12.2 Testes de integração (Views, rotas e permissões)

- `contas:cadastro`: `GET` renderiza todos os campos, dicas, avisos e `csrf_token`; `POST` válido redireciona (PRG) com `"Cadastro realizado com sucesso"`; `POST` inválido preserva campos preenchidos (exceto senha) e exibe mensagens literais; tentativa de *mass assignment* ignorada; verificação de XSS escapado.
- `contas:confirmar_email` e `contas:reenviar_confirmacao`: acesso público funcionando; reenvio retorna resposta idêntica para e-mail existente e inexistente e aplica limite de taxa.
- `contas:perfil_editar` e `contas:encerrar_conta`: visitante redirecionado para login; usuário autenticado altera apenas o próprio perfil (impossível editar ou encerrar conta de terceiro); encerramento executa `logout` e invalida sessão.
- `nucleo:cep_consultar`: CEP válido retorna JSON esperado; CEP malformado retorna 400; falha dos provedores retorna erro amigável sem 500; excesso de chamadas aciona rate limit (429).

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Texto final e prazos da Política de Privacidade e Termos de Uso:** o RF001 (regra 6 e Exclusão) diz que a política de privacidade, o consentimento e o prazo de eliminação serão definidos em pendência da ata, sem prazo. | Pendência externa da fonte (Questão 8 do PRD, RNF10) | Não bloqueia o desenvolvimento do MVP: usa-se a versão placeholder configurável `"1.0-rascunho"` até a entrega do texto jurídico/cliente para substituir antes da produção real. |
