# 0007. Adotar modelo de usuário customizado herdando de AbstractBaseUser e PermissionsMixin

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RF001, RF002, RF004, RF005, RNF10, RNF14, RS002, RS005, RS006, RS015

## Contexto

O cadastro de usuário do ReMed (RF001) coleta nome completo (3 a 120 caracteres), CPF único e imutável após o cadastro, data de nascimento (maiores de 18 anos), e-mail único com confirmação, celular, senha, um ou mais perfis de uso (Doador, Solicitante, Cuidador/Familiar), aceite dos Termos de Uso e Política de Privacidade (com versão, data e hora), endereço (usado só para geolocalização aproximada e nunca exibido a terceiros) e status (`ativo`, `inativo`, `suspenso` ou `bloqueado`), sempre com histórico.

O login (RF002) é feito com **e-mail ou CPF** e senha — o sistema não usa nome de usuário (`username`). O RF004 prevê gestão de status e atribuição do perfil Administrador (com no mínimo um Administrador ativo, RS015), sem exclusão física pelo Administrador. Já o encerramento de conta pedido pelo usuário (RF001, RNF10) deve eliminar ou anonimizar os dados pessoais, preservando os registros anônimos de doações e entregas para as métricas (RF022).

Na documentação oficial do Django, trocar o `AUTH_USER_MODEL` depois que as tabelas do banco já foram criadas não é suportado automaticamente pelas migrações e exige intervenção manual no esquema e no histórico de migrações. Por isso, esta decisão precisa ser tomada antes da primeira migração do projeto.

## Direcionadores da decisão

- Definir `AUTH_USER_MODEL` antes da primeira migração, evitando migração manual no futuro.
- Suportar autenticação por e-mail ou CPF, sem exigir `username` (RF001, RF002).
- Garantir unicidade de e-mail e CPF no banco de dados (RF001, RS006, ADR 0002).
- Permitir acumular múltiplos perfis de uso por conta e separar permissões administrativas por função no futuro (RF001, RF002, RS015).
- Suportar os quatro status previstos (`ativo`, `inativo`, `suspenso`, `bloqueado`) com histórico imutável (RF001, RF004, RNF14).
- Permitir anonimização dos dados pessoais no encerramento de conta sem quebrar referências históricas de doações e entregas (RF001, RNF10, RF022).

## Opções consideradas

### 1. Modelo customizado com `AbstractBaseUser` e `PermissionsMixin` (recomendada)

Criar um model próprio (por exemplo, `contas.Usuario`, nome do app a confirmar) herdando de `AbstractBaseUser` e `PermissionsMixin`, com `email` como `USERNAME_FIELD`, sem `username`, acompanhado de um `BaseUserManager` próprio e de um backend de autenticação que aceita e-mail ou CPF.

- **Prós:**
  - Elimina campos que não existem nos requisitos (`username`, `first_name`, `last_name`), evitando redundância com `nome_completo` (RF001) ou preenchimento artificial de `username`.
  - Define `email` único como identificador principal (`USERNAME_FIELD = "email"`), alinhado ao RF001 e ao RF002.
  - Preserva o sistema nativo de grupos e permissões do Django (`PermissionsMixin`), facilitando a separação de permissões administrativas por função (RS015) e o uso do Django Admin.
  - Modela o `status` explicitamente com `TextChoices` (`ativo`, `inativo`, `suspenso`, `bloqueado`) e integra com `is_active` e com o backend de autenticação.
  - Define `AUTH_USER_MODEL` desde a primeira migração, seguindo a recomendação oficial do Django.
- **Contras:**
  - Exige implementar um `BaseUserManager` customizado (`create_user` e `create_superuser`) e configurar a classe de administração no Django Admin.
  - Um pouco mais de código inicial do que usar o `User` padrão ou `AbstractUser`.

### 2. Modelo customizado herdando de `AbstractUser`

Estender `django.contrib.auth.models.AbstractUser`, adicionando os campos do ReMed (`cpf`, `nome_completo`, `data_nascimento`, `celular`, `status` etc.) e definindo `AUTH_USER_MODEL`.

- **Prós:**
  - Menos código inicial: herda manager, campos padrão (`is_staff`, `is_active`, `date_joined`) e integração com o Django Admin.
  - Também define `AUTH_USER_MODEL` antes da primeira migração.
- **Contras:**
  - Carrega campos que não fazem parte do domínio (`username`, `first_name`, `last_name`), obrigando a remover/anular `username` ou preenchê-lo artificialmente (por exemplo, com UUID ou cópia do e-mail).
  - Cria risco de divergência entre `first_name`/`last_name` e `nome_completo`, ou entre `username` e `email`.

### 3. Usar o `User` padrão do Django com model `Perfil` (`OneToOneField`)

Manter `django.contrib.auth.models.User` inalterado e guardar os campos do ReMed (CPF, nome completo, celular, data de nascimento, status, perfis) em um model auxiliar ligado por `OneToOneField`.

- **Prós:**
  - Nenhuma configuração de `AUTH_USER_MODEL` nem escrita de manager customizado.
  - Compatibilidade imediata com bibliotecas de terceiros que assumam o `User` padrão.
- **Contras:**
  - O `User` padrão exige `username` obrigatório e não impõe unicidade em `email` no banco de dados.
  - Quase toda operação do sistema (login por CPF, validação de status, exibição reduzida, regras de perfil) exige `JOIN` com a tabela auxiliar.
  - Migrar para um `AUTH_USER_MODEL` customizado no futuro é custoso e não automático no Django.

## Decisão

**Opção 1 (`AbstractBaseUser` + `PermissionsMixin`)**, definido em `AUTH_USER_MODEL` antes da primeira migração.

Regras que passam a valer:

- **Identificação e login (Alternativa 1 sobre CNPJ):** `email` (normalizado em minúsculas) é o `USERNAME_FIELD`, sem campo `username`. Um backend de autenticação customizado permite entrar apenas com **e-mail ou CPF**, alinhado ao RF002 e ao RF005 (instituição não tem senha própria). A tela de login na implementação deve exibir `"E-mail ou CPF"` — trata-se de uma **divergência da tela de origem (`Login ReMed.png`, que trazia CNPJ) corrigida na implementação, a confirmar com o professor** (Questão 14 do PRD).
- **Status `inativo`:** significa uma conta que **não consegue entrar no sistema**, mas **pode ser reativada**. É diferente de `suspenso`, que exige motivo obrigatório e decorre de ação do Administrador (RF004). *Nota:* esta é a interpretação adotada pela equipe, já que o RF001 não define o significado de `inativo`.
- **Login antes de confirmar o e-mail:** **bloqueado até a confirmação do e-mail**, para combater perfis falsos (RS006, RF001 regra 3).
- **Armazenamento do CPF:** **não criptografar o CPF no campo** (nível de aplicação). A proteção é feita pela criptografia do banco e do disco, além do controle de acesso por perfil e exibição parcialmente oculta ao Administrador (RS002, RF004), preservando a busca por CPF parcial exigida no RF004. Caso o RF004 mude no futuro para busca exata, esta decisão será revisitada.
- **Campos no model de usuário:** `nome_completo` (até 120 caracteres), `cpf` (armazenado sem máscara, anulável após encerramento), `data_nascimento` (anulável após encerramento), `email` (anulável após encerramento), `email_confirmado_em` (nulo até a confirmação), `celular`, `status` (`TextChoices`: `ativo`, `inativo`, `suspenso`, `bloqueado`), `is_staff`, `is_superuser`, `criado_em`, `atualizado_em` e `anonimizado_em` (nulo enquanto a conta existir).
- **Entidades separadas:**
  - **Endereço do usuário:** em tabela própria (`OneToOne` ou `ForeignKey`), separando o dado de localização privada (RS002) e simplificando a eliminação/anonimização (RNF10).
  - **Aceite de Termos de Uso e Política de Privacidade:** em tabela própria com versão do documento, data e hora (RF001 regra 6), preservando o histórico de aceites quando os documentos forem atualizados.
  - **Perfis de uso (Doador, Solicitante, Cuidador/Familiar):** modelados de forma a permitir múltiplos perfis por usuário (RF001 regra 5). A modelagem completa de perfis e permissões administrativas separadas por função está na [ADR 0010](0010-perfis-e-permissoes.md).
- **Encerramento de conta e anonimização (Alternativa A — LGPD, RF001, RNF10):**
  - Não há exclusão física quando existirem registros históricos vinculados (`on_delete=PROTECT` em doações, solicitações e entregas), preservando a integridade referencial das métricas (RF022).
  - **`email` e `cpf` são anuláveis (`NULL`)**, com **`UniqueConstraint` parcial** (`condition=Q(email__isnull=False)` e `condition=Q(cpf__isnull=False)`) e **`CheckConstraint`** exigindo `email` e `cpf` não nulos sempre que `anonimizado_em IS NULL`. No encerramento, grava-se `email = NULL`, `cpf = NULL`, limpam-se os demais dados pessoais identificáveis (`nome_completo`, `celular`, `data_nascimento`), apaga-se o endereço, define-se `anonimizado_em`, altera-se o status para impedir login e encerram-se sessões ativas.
  - **Bloqueio de encerramento para contas punidas:** o encerramento de conta **não é permitido enquanto o usuário estiver com status `suspenso` ou `bloqueado` pelo Administrador**, impedindo que a punição seja contornada por recadastro imediato com o mesmo CPF ou e-mail (RS006, RF004).
  - **Checagem do sistema do Django para `USERNAME_FIELD` condicional:** no Django 6.1.3 (`django.contrib.auth.checks.check_user_model`), uma `UniqueConstraint` com `condition` não entra em `_meta.total_unique_constraints`. Por isso, se `email` não tiver `unique=True`, o Django emite **`auth.E003` (erro)** com o `ModelBackend` padrão ou **`auth.W004` (aviso)** quando há `AUTHENTICATION_BACKENDS` customizado. **Como tratar:** como o PostgreSQL já permite múltiplos valores `NULL` em uma constraint `UNIQUE` padrão, há duas formas válidas no código — (1) manter `unique=True` em `email` (normalizado em minúsculas antes de salvar) além do `CheckConstraint`, evitando o aviso `auth.W004` sem perder o comportamento de múltiplos `NULL`; ou (2) usar exclusivamente `UniqueConstraint` parcial (por exemplo, sobre `Lower("email")`), garantir no backend customizado que `email=None` nunca autentica e silenciar explicitamente `auth.W004` em `SILENCED_SYSTEM_CHECKS` com comentário apontando para esta ADR.
- **Regra de criação do primeiro Administrador:** prever comando de gerenciamento (`createsuperuser` ou comando específico) documentado para o bootstrap inicial (Questão 20 do PRD), mantendo o bloqueio de auto-atribuição na interface (RF004).

## Consequências

- Positivas:
  - Modelo enxuto e fiel aos campos do RF001, sem campos legados (`username`, `first_name`, `last_name`).
  - Unicidade de `email` e `cpf` para contas ativas/não anonimizadas garantida por constraints no PostgreSQL (ADR 0002), sem impedir recadastro legítimo após encerramento voluntário.
  - Impede burla de suspensão ou bloqueio administrativo via exclusão e recadastro da conta.
  - Base fechada para as ADRs de hash de senha (ADR 0008), sessão/2FA (ADR 0009), perfis/permissões (ADR 0010) e histórico imutável.
- Negativas e custos:
  - Exige manter `BaseUserManager` próprio, backend de autenticação customizado e formulário/Admin ajustados para tratar `email` e `cpf` como potencialmente `None` em contas anonimizadas.
  - Todas as referências ao usuário no restante do código devem usar `settings.AUTH_USER_MODEL` (em models) ou `get_user_model()` (em services e testes), nunca importar `django.contrib.auth.models.User`.
  - A remoção de "CNPJ" do campo de login diverge da imagem `Login ReMed.png` e precisa de validação formal com o professor.
- Impacto em specs e arquitetura:
  - Deve ser a primeira migração do app de contas antes de gerar migrações dos demais apps.
  - As specs de RF001, RF002, RF003 e RF004 seguem as regras fechadas nesta ADR.

## Como verificar

- `AUTH_USER_MODEL` está configurado em `settings` antes da criação da migração `0001_initial`.
- O model herda de `AbstractBaseUser` e `PermissionsMixin`, define `USERNAME_FIELD = "email"` e não possui campo `username`.
- `python manage.py check` passa sem erros (`auth.E003`) nem avisos não tratados (`auth.W004`).
- Testes de model/banco confirmam: unicidade de `email` e `cpf` em contas não anonimizadas; `CheckConstraint` impedindo `email` ou `cpf` nulos quando `anonimizado_em IS NULL`; múltiplas contas anonimizadas com `email=NULL` e `cpf=NULL`; busca por CPF parcial (RF004); e recusa de exclusão física quando há registros protegidos.
- Testes do service de encerramento confirmam que contas `suspenso` ou `bloqueado` não podem solicitar encerramento de conta.
- Testes do backend de autenticação confirmam login por e-mail e por CPF, recusa de CNPJ, recusa de contas anonimizadas (`email=None`) e bloqueio de usuários com e-mail não confirmado ou com status `inativo`, `suspenso` ou `bloqueado`.

## Notas

- **Confirmação externa pendente (não bloqueia o modelo):** confirmar com o professor a correção do rótulo da tela de login (`Login ReMed.png`) de `"E-mail, CPF ou CNPJ"` para `"E-mail ou CPF"` (Questão 14 do PRD).
- **ADRs relacionadas:**
  - [ADR 0002](0002-postgresql-como-banco-de-dados.md) (PostgreSQL e constraints parciais/`CheckConstraint`)
  - [ADR 0008](0008-hash-de-senha-argon2-ou-bcrypt.md) (hash de senha)
  - [ADR 0009](0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) (sessão, bloqueio por tentativas e 2FA do Administrador)
  - [ADR 0010](0010-perfis-e-permissoes.md) (perfis e permissões)
  - ADR candidata de histórico imutável de alterações (RNF14).
