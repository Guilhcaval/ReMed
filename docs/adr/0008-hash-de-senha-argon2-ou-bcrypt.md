# 0008. Escolher o algoritmo de hash de senha (Argon2id ou bcrypt)

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RS005, RF001, RF002, RF003, RNF04, RNF08

## Contexto

O cadastro de usuário (RF001, regra 4) exige senha com no mínimo 8 caracteres, guardada como hash e nunca em texto aberto. A recuperação de senha (RF003, regra 3) segue as mesmas regras e exige verificar que a nova senha não é igual à atual. O requisito de segurança RS005 especifica explicitamente: **"Senhas com no mínimo 8 caracteres, guardadas com hash (bcrypt ou argon2)."**

O hasher padrão do Django (`PBKDF2PasswordHasher`) **não atende** ao RS005, pois o requisito pede `bcrypt` ou `argon2`. Ambos exigem uma dependência externa no `requirements.txt` (ADR 0004), compatível com Python 3.14 (ADR 0003) e com o Django 6.1 (ADR 0001).

Além da resistência criptográfica em caso de vazamento do banco, a escolha precisa considerar o ambiente mínimo previsto no RNF08 (2 vCPU e 4 GB de RAM) e a meta de desempenho do RNF04 (até 500 usuários simultâneos), já que algoritmos modernos de hash de senha consomem CPU e memória intencionalmente.

## Direcionadores da decisão

- Conformidade direta com o RS005 (`argon2` ou `bcrypt`, com salt único por senha).
- Alta resistência a ataques de força bruta off-line (GPU/ASIC) em caso de comprometimento do banco (RS005, OWASP Top 10 A04).
- Não truncar senhas longas silenciosamente.
- Suporte nativo no Django 6.1 e compatibilidade com Python 3.14 (ADRs 0001 e 0003).
- Consumo controlado de CPU e memória no servidor mínimo de 2 vCPU / 4 GB de RAM (RNF08, RNF04).
- Possibilidade de atualizar parâmetros ou migrar de algoritmo de forma transparente no login futuro (recurso nativo do `PASSWORD_HASHERS` do Django).

## Opções consideradas

### 1. Argon2id via `Argon2PasswordHasher` e `argon2-cffi` (recomendada)

Configurar `django.contrib.auth.hashers.Argon2PasswordHasher` (que usa a variante **Argon2id** por padrão no Django) como primeiro item de `PASSWORD_HASHERS`, instalando a biblioteca `argon2-cffi`.

- **Prós:**
  - Vencedor da *Password Hashing Competition* (2015), recomendado pela documentação oficial do Django e apontado como escolha principal pelo *OWASP Password Storage Cheat Sheet* para sistemas novos.
  - A variante Argon2id combina resistência a ataques de canal lateral com alto custo de memória (*memory-hard*), dificultando muito a quebra paralela em GPUs e ASICs.
  - Não possui limite prático de tamanho de senha (sem o limite de 72 bytes do bcrypt).
  - `argon2-cffi` declara suporte oficial ao Python 3.14 (a partir da versão 25.1.0), distribuindo wheel universal com a dependência nativa `argon2-cffi-bindings` (instalação a confirmar no `.venv`).
  - O Django re-gera o hash automaticamente no próximo login caso os parâmetros de custo sejam ajustados no futuro.
- **Contras:**
  - Consumo elevado de memória por operação com os padrões do Django 6.1.3 (`time_cost = 2`, `memory_cost = 102400` — cerca de 100 MiB — e `parallelism = 8`). Em um servidor inicial de 2 vCPU e 4 GB de RAM (RNF08), muitos logins simultâneos podem pressionar a memória ou facilitar negação de serviço se os parâmetros não forem calibrados e combinados com o bloqueio/limite de tentativas (RF002).
  - Adiciona dependências externas (`argon2-cffi` e suas dependências nativas) ao `requirements.txt` (ADR 0004).

### 2. bcrypt com pré-hash SHA-256 via `BCryptSHA256PasswordHasher` e `bcrypt`

Configurar `django.contrib.auth.hashers.BCryptSHA256PasswordHasher` (padrão de `rounds = 12` no Django 6.1.3) como primeiro item de `PASSWORD_HASHERS`, instalando a biblioteca `bcrypt`.

- **Prós:**
  - Algoritmo consolidado há décadas e explicitamente aceito pelo RS005.
  - Baixo consumo de memória por operação, reduzindo o risco de pressão de RAM no ambiente mínimo de 4 GB do RNF08.
  - O `BCryptSHA256PasswordHasher` do Django aplica pré-hash SHA-256 antes do bcrypt, contornando o truncamento silencioso em 72 bytes do bcrypt puro.
  - O pacote `bcrypt` distribui wheels `abi3` compatíveis com Python 3.14 (instalação a confirmar no `.venv`).
- **Contras:**
  - Não é *memory-hard* como o Argon2id, oferecendo menor proteção contra ataques off-line com hardware dedicado (GPUs/ASICs); o guia do OWASP o classifica hoje como aceitável para sistemas legados, preferindo Argon2id para sistemas novos.
  - Também adiciona dependência externa (`bcrypt`) ao `requirements.txt`.

### 3. Manter o padrão do Django (`PBKDF2PasswordHasher`)

Usar `PBKDF2PasswordHasher` (`1.500.000` iterações no Django 6.1.3) sem instalar dependências adicionais.

- **Prós:**
  - Nenhuma dependência externa a adicionar ou manter.
- **Contras:**
  - **Não atende ao RS005**, que exige explicitamente `bcrypt` ou `argon2`.
  - Não é *memory-hard*; o OWASP recomenda PBKDF2 apenas quando há exigência formal de conformidade FIPS-140, o que não existe no ReMed.

## Decisão

**Opção 1 (`Argon2PasswordHasher` — Argon2id)** como primeiro e principal hasher em `PASSWORD_HASHERS`.

Regras que passam a valer:

- Configurar `django.contrib.auth.hashers.Argon2PasswordHasher` como primeiro item de `PASSWORD_HASHERS` em `settings`, mantendo os **parâmetros padrão do Django 6.1.3** (`time_cost = 2`, `memory_cost = 102400`, `parallelism = 8`) até a calibração na hospedagem. **Não criar subclasse calibrada agora.** Como o sistema parte do zero, não há senhas legadas a migrar.
- Os parâmetros de custo do Argon2id serão calibrados junto com a **ADR de hospedagem, implantação e backup** (RNF05, RNF08), por meio de benchmark no ambiente-alvo (mínimo 2 vCPU e 4 GB de RAM), partindo do piso recomendado pelo OWASP (`memory_cost >= 19 MiB` e `time_cost >= 2`).
- Conforme a [ADR 0004](0004-pip-venv-requirements-fixado.md) (uma dependência só entra quando for necessária), o `argon2-cffi` **não** é instalado agora. Ele entrará no `requirements.txt` — com versão fixada por `==`, junto com todas as suas dependências indiretas e após validação no `.venv` com Python 3.14 — somente quando for implementada a primeira spec que usar senha (**RF001**), junto com a configuração de `PASSWORD_HASHERS`.
- Toda criação, verificação e troca de senha usa os métodos nativos do Django (`set_password` e `check_password`), inclusive a verificação de que a nova senha difere da atual no RF003.
- Em configuração exclusiva de testes automatizados, pode-se usar um hasher rápido para agilizar a suíte, mantendo testes dedicados que validem a configuração de produção de `PASSWORD_HASHERS`.

## Consequências

- Positivas:
  - Atende integralmente ao RS005 e às recomendações atuais do Django e do OWASP.
  - Proteção superior contra ataques de força bruta off-line e ausência de truncamento em senhas longas.
  - Permite calibrar o custo na etapa de hospedagem sem migração manual de banco (o Django atualiza o hash automaticamente no próximo login bem-sucedido).
- Negativas e custos:
  - Introduzirá dependência externa com componente compilado (`argon2-cffi` / `argon2-cffi-bindings`) na implementação do RF001, que precisará ser acompanhada quanto a vulnerabilidades (ADR 0004).
  - Exige atenção ao consumo de RAM sob logins concorrentes até a calibração no ambiente-alvo (mitigado pelo bloqueio por tentativas da ADR 0009).
- Impacto em specs e arquitetura:
  - Aplica-se diretamente às specs de RF001, RF002 e RF003.
  - A spec do RF001 deverá incluir a instalação e fixação de `argon2-cffi` (e dependências indiretas) no `requirements.txt` e a configuração de `PASSWORD_HASHERS`.
  - A ADR de hospedagem, implantação e backup deverá incluir o benchmark e a calibração dos parâmetros do Argon2id.

## Como verificar

- Na implementação do RF001: teste de configuração confirma que `settings.PASSWORD_HASHERS[0]` é `django.contrib.auth.hashers.Argon2PasswordHasher`.
- Teste de cadastro e redefinição confirma que o campo `password` salvo no banco inicia com `argon2$argon2id$` e nunca armazena a senha em texto aberto.
- Teste de RF003 confirma que `check_password` bloqueia a reutilização da senha atual.
- `pip install -r requirements.txt` e `pip check` passam sem erros no `.venv` com Python 3.14, com `argon2-cffi` e dependências indiretas fixados por `==`.
- Na etapa de hospedagem: benchmark documentado valida tempo de resposta e uso de memória sob concorrência, respeitando `memory_cost >= 19 MiB` e `time_cost >= 2`.

## Notas

- **Calibração futura:** parâmetros padrão do Django 6.1.3 mantidos até o benchmark junto com a ADR de hospedagem, implantação e backup (piso OWASP: `>= 19 MiB` e `time_cost >= 2`).
- **Momento de entrada no `requirements.txt`:** na implementação do RF001, junto com `PASSWORD_HASHERS`.
- **ADRs relacionadas:** [ADR 0003](0003-python-3-14.md) (Python 3.14), [ADR 0004](0004-pip-venv-requirements-fixado.md) (`requirements.txt` fixado), [ADR 0007](0007-modelo-de-usuario-customizado.md) (modelo de usuário customizado) e [ADR 0009](0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) (sessão, bloqueio por tentativas e 2FA do Administrador).
