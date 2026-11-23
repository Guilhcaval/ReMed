# 0009. Definir sessão, bloqueio por tentativas inválidas e dois fatores do Administrador

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RF002, RF003, RF004, RF007, RF011, RF014, RF021, RS005, RS012, RS015, RNF08, RNF14

## Contexto

O RF002 (Autenticação e Controle de Acesso) e os requisitos de segurança RS005 e RS015 impõem controles estritos para proteger as contas do ReMed — em especial a conta de Administrador, que aprova pontos de coleta (RF007), suspende usuários (RF004), confere doações (RF011), modera denúncias (RF021) e pode ter acesso a documentos restritos:

- **Bloqueio temporário por tentativas inválidas (RF002 regra 1, RS005):** após **5 tentativas de login inválidas em 15 minutos**, a conta é bloqueada temporariamente e o usuário recebe a mensagem `"Muitas tentativas. Tente novamente mais tarde"`.
- **Expiração de sessão (RF002 regra 2, RS005):** a sessão expira após **30 minutos de inatividade**, e toda comunicação ocorre em TLS 1.2 ou superior.
- **Encerramento de sessões ativas (RF003 regra 4, RS012, RF004):** após redefinição de senha (e ao suspender ou bloquear um usuário), as sessões ativas da conta devem ser encerradas.
- **Autenticação em dois fatores do Administrador (RF002 regra 4, RF004 regra 4, RS005, RS015):** obrigatória para todo acesso do perfil Administrador. O mecanismo de 2FA não está definido na fonte.
- **Registro de acessos (RF002 regra 5, RNF14):** todos os acessos (sucesso e falha) são registrados com data, hora e identificação do usuário.
- **Escalabilidade horizontal (RNF08):** o servidor em nuvem deve suportar escalabilidade horizontal, o que impede guardar estado de sessão ou contadores de tentativas apenas na memória local de um processo.

## Direcionadores da decisão

- Garantir expiração por **inatividade** em 30 minutos (RF002) e revogação imediata de sessões ativas na troca de senha ou bloqueio/suspensão (RF003, RF004, RS012).
- Garantir que o limite de 5 tentativas inválidas em 15 minutos funcione de forma consistente mesmo com login por **e-mail ou CPF** (RF002, ADR 0007) e em ambiente com múltiplas instâncias (RNF08).
- Registrar todo acesso (sucesso e falha) para auditoria (RF002, RNF14), sem vazar senhas nem facilitar enumeração de contas (RS005, OWASP A07).
- Exigir 2FA confiável para o Administrador, sem introduzir ponto único de falha nem depender de infraestrutura complexa no MVP (RS015).
- Manter aderência à camada de service (ADR 0001) e parcimônia em novas dependências externas (ADR 0004).

## Opções consideradas

Para clareza, as alternativas estão separadas em três partes: **sessão**, **bloqueio por tentativas** e **mecanismo de 2FA (ponto principal a decidir)**.

### Parte A — Sessão e expiração por inatividade

#### A1. Sessões do Django no PostgreSQL (`backends.db`) com expiração deslizante de 30 minutos (recomendada)

Usar o backend padrão de banco de dados do Django (`django.contrib.sessions.backends.db`) armazenado no PostgreSQL (ADR 0002), com `SESSION_COOKIE_AGE = 1800`, `SESSION_SAVE_EVERY_REQUEST = True`, `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SECURE = True` (produção/TLS) e `SESSION_COOKIE_SAMESITE = "Lax"`.

- **Prós:**
  - Nenhuma infraestrutura adicional no MVP (reutiliza o PostgreSQL da ADR 0002).
  - Compatível com escalabilidade horizontal (RNF08), pois o estado fica centralizado no banco.
  - Permite revogar sessões ativas no servidor (usando `get_session_auth_hash()` na troca de senha e invalidação/remoção de sessões em suspensão ou bloqueio).
  - `SESSION_SAVE_EVERY_REQUEST = True` renova o prazo a cada requisição, atendendo exatamente à regra de 30 minutos de **inatividade**.
- **Contras:**
  - Realiza uma escrita na tabela de sessões a cada requisição autenticada.
  - Exige rodar periodicamente o comando `clearsessions` do Django para remover sessões expiradas (na ADR de rotinas agendadas).

#### A2. Sessões em cache distribuído (`cached_db` ou `cache` com Redis)

- **Prós:**
  - Reduz escritas no PostgreSQL sob tráfego intenso e expira chaves automaticamente via TTL.
- **Contras:**
  - Exige provisionar, monitorar e proteger um serviço extra (Redis) já no MVP, antes de haver evidência de gargalo na tabela de sessões (o RNF04 prevê até 500 usuários simultâneos).

#### A3. Sessões em cookies assinados (`signed_cookies`)

- **Prós:**
  - Não consome armazenamento nem escritas no servidor.
- **Contras:**
  - Dificulta revogar sessões específicas no servidor e aumenta o tráfego de rede em conexões 3G/4G (RNF08).

---

### Parte B — Bloqueio por tentativas inválidas e registro de acessos

#### B1. Controle na camada de service com tabela própria no PostgreSQL (recomendada)

Registrar cada tentativa de autenticação (sucesso e falha: data/hora, identificador normalizado, usuário vinculado se encontrado, IP e resultado) em tabela própria no PostgreSQL, consultada pelo service de autenticação para aplicar o bloqueio temporário após 5 falhas em 15 minutos para a conta (independentemente de o usuário tentar com e-mail ou CPF), complementado por um limite secundário por IP contra *password spraying*.

- **Prós:**
  - Segue fielmente a camada de service (ADR 0001), sem acoplar regras de negócio a middlewares ou backends de terceiros.
  - Resolve em um único lugar o bloqueio temporário (RF002 regra 1) e o registro obrigatório de todos os acessos com sucesso e falha (RF002 regra 5).
  - Trata de forma unificada login por e-mail e por CPF na mesma conta (impedindo burlar o limite alternando entre e-mail e CPF).
  - Zero dependência externa adicional no `requirements.txt` (ADR 0004) e controle total sobre as mensagens exatas do RF002.
- **Contras:**
  - A lógica de contagem em janela móvel, bloqueio temporário e os testes correspondentes ficam sob responsabilidade da equipe.
  - Exige atenção contra enumeração de contas (não revelar se o identificador existe nas respostas de erro) e política de retenção dos logs de acesso (LGPD, RNF10).

#### B2. Biblioteca `django-axes`

Usar `django-axes` (compatível com Django 6.1 a partir da v9.0.0 e Python 3.14) para controlar falhas de login e tempo de bloqueio (*cooloff*).

- **Prós:**
  - Solução madura e amplamente usada no ecossistema Django, com bloqueio por usuário, IP ou combinação configurável.
- **Contras:**
  - Exige adaptação para consolidar tentativas feitas por e-mail e por CPF da mesma conta (evitando dividir o contador em dois identificadores) e para alinhar mensagens e registro de sucessos/falhas ao RF002.
  - Adiciona dependência externa ao `requirements.txt` e desloca parte da regra de negócio para fora da camada de service (ADR 0001).

---

### Parte C — Mecanismo de 2FA do Administrador (ponto a decidir)

#### C1. TOTP — Aplicativo autenticador (RFC 6238) com códigos de recuperação de uso único (recomendada)

O Administrador vincula um aplicativo autenticador padrão (como Google Authenticator, FreeOTP, Aegis ou Authy) por meio de QR code gerado no próprio servidor, validando códigos temporários de 6 dígitos (30 segundos) no login. Na ativação, são gerados códigos de recuperação de uso único (armazenados apenas como hash).

- **Prós:**
  - Padrão aberto (RFC 6238), recomendado pelo OWASP e gratuito para a equipe e para os Administradores.
  - Funciona off-line no dispositivo do Administrador, sem depender da disponibilidade ou latência do serviço de e-mail nem de custos de SMS.
  - Mantém separação real de fatores: mesmo que a conta de e-mail do Administrador seja invadida, o invasor não obtém o segundo fator.
  - Pode ser implementado via `django-otp` (compatível com Django 6 e Python 3.14 nas versões atuais) ou diretamente na camada de service com `pyotp` (compatível com Python 3.14) + geração local de QR code.
- **Contras:**
  - Exige fluxo inicial de configuração (QR code) e procedimento documentado de contingência caso o Administrador perca o dispositivo (códigos de recuperação ou reset por outro Administrador ativo, preservando ao menos 1 Administrador ativo — RS015).
  - O segredo TOTP armazenado no banco precisa de proteção rigorosa (controle de acesso restrito e criptografia).

#### C2. Código temporário (OTP) enviado por e-mail

Após validar e-mail/CPF e senha, o sistema gera um código aleatório temporário de uso único (armazenado como hash) e o envia ao e-mail cadastrado do Administrador.

- **Prós:**
  - Mais simples para o Administrador (não exige instalar aplicativo autenticador nem gerenciar QR code).
  - Reutiliza a integração de e-mail já exigida por RF001, RF003 e RF017, sem dependência de biblioteca TOTP.
- **Contras:**
  - Segurança inferior ao TOTP: o e-mail já é o canal de recuperação de senha (RF003); se o e-mail do Administrador for comprometido, ambos os fatores ficam vulneráveis.
  - Depende da entrega rápida do servidor de e-mail (se o e-mail atrasar ou cair em spam, o Administrador não consegue entrar; o RNF15 prevê até 5 minutos para notificações).

#### C3. WebAuthn / Passkeys (chaves FIDO2 / biometria)

Uso de chaves de segurança físicas ou passkeys do navegador/dispositivo via padrão WebAuthn.

- **Prós:**
  - Maior resistência a *phishing* entre as três opções.
- **Contras:**
  - Maior complexidade de implementação no MVP (exige JavaScript dedicado para a API WebAuthn, gestão de credenciais por dispositivo e biblioteca específica), além de depender de dispositivos compatíveis e ainda exigir mecanismo de recuperação.

## Decisão

Adotadas as opções **A1**, **B1** e **C1**, com as seguintes regras que passam a valer:

- **Sessão (A1):** sessões do Django no PostgreSQL (`django.contrib.sessions.backends.db`) com expiração deslizante de **30 minutos de inatividade** (`SESSION_COOKIE_AGE = 1800`, `SESSION_SAVE_EVERY_REQUEST = True`), cookies `HttpOnly`, `Secure` (em produção sob TLS 1.2+, RS005) e `SameSite = "Lax"`. O ID de sessão é rotacionado no login (`django.contrib.auth.login`), e todas as sessões ativas da conta são invalidadas na redefinição de senha (RF003) e em suspensão ou bloqueio (RF004).
- **Bloqueio por tentativas e registro de acessos (B1):** controle próprio na camada de service (ADR 0001) com tabela de registros de acesso no PostgreSQL (sucesso e falha, com data/hora, identificador normalizado, usuário vinculado quando existir, IP e resultado). Após **5 tentativas inválidas em 15 minutos** para a mesma conta (unificando tentativas por e-mail e por CPF), a conta sofre **bloqueio temporário de 15 minutos** — duração definida como **parâmetro nomeado e configurável em `settings`** — exibindo `"Muitas tentativas. Tente novamente mais tarde"`. Um limite secundário por IP complementa a proteção contra *password spraying*.
- **2FA do Administrador (C1 — TOTP com `pyotp`):**
  - Mecanismo: **TOTP (RFC 6238)** implementado na camada de service com a biblioteca **`pyotp`** (Python puro, sem dependências externas e desacoplada da versão do Django; compatível com Python `>= 3.10`, a validar no `.venv` com Python 3.14 antes de fixar a versão).
  - **Cadastro do dispositivo e códigos de recuperação próprios:** modelagem própria para o dispositivo TOTP (segredo protegido em repouso; QR code gerado localmente no servidor, sem enviar o segredo a terceiros) e para os **códigos de recuperação de uso único**, armazenados apenas como **hash**.
  - **Login de Administrador:** nenhuma rota administrativa é acessível sem a verificação concluída do segundo fator.
  - **Reconfirmação imediata (*step-up*) no RF004:** atribuir o perfil Administrador exige **reconfirmação imediata do código 2FA**, mesmo dentro de uma sessão já autenticada com 2FA (RF004 regra 4, RS015).
  - **Perda do dispositivo 2FA:** a recuperação ocorre por meio dos **códigos de recuperação de uso único** (armazenados em hash) ou por **reset de 2FA feito por outro Administrador ativo** (sempre com registro imutável de auditoria, RNF14). **O reset por outro Administrador só funciona quando houver pelo menos dois Administradores ativos** (impedindo auto-reset e respeitando a existência mínima de um Administrador ativo, RS015).
- **Entrada de dependências no `requirements.txt` (ADR 0004):** `pyotp` (e eventual biblioteca leve de geração local de QR code, se necessária) **não** são instalados agora; entram no `requirements.txt` com versões fixadas por `==` (e dependências indiretas) apenas na implementação do **RF002**.

## Consequências

- Positivas:
  - Atende integralmente ao RF002, RF004, RS005 e RS015 sem adicionar Redis nem serviços externos de SMS no MVP.
  - Unifica bloqueio por tentativas, auditoria de acessos (RF002 regra 5) e 2FA dentro da camada de service (ADR 0001), sem acoplar regras críticas a bibliotecas de middleware.
  - Mantém compatibilidade com escalabilidade horizontal (RNF08) e revogação de sessões (RF003, RF004).
- Negativas e custos:
  - Escrita na tabela de sessões a cada requisição autenticada e necessidade de rotina agendada para limpar sessões expiradas (`clearsessions`).
  - Exige implementar e testar telas e services próprios para pareamento TOTP (QR code + confirmação do primeiro código), verificação no login, *step-up* no RF004, códigos de recuperação e reset por outro Administrador.
  - Se houver apenas um Administrador ativo e ele perder tanto o dispositivo quanto todos os códigos de recuperação, o reset pela interface web não estará disponível, exigindo procedimento operacional controlado fora da interface (documentado junto à Questão 20 do PRD).
  - Exige definir a política de retenção dos registros de acesso (contendo IP e data/hora) em conformidade com a LGPD (RNF10, Questão 8 do PRD).
- Impacto em specs e arquitetura:
  - Condiciona diretamente as specs de **RF002** (login, sessão, bloqueio de 15 minutos, 2FA TOTP com `pyotp`, pareamento e códigos de recuperação), **RF003** (encerramento de sessões na troca de senha) e **RF004** (encerramento de sessões na suspensão/bloqueio, *step-up* 2FA ao atribuir Administrador e reset de 2FA por outro Administrador ativo).
  - A limpeza de sessões expiradas entra na ADR de rotinas agendadas (RNF15).

## Como verificar

- Testes automatizados confirmam que:
  - Sessões sem atividade por mais de 30 minutos são invalidadas; requisições dentro de 30 minutos renovam o prazo.
  - Em produção (`DEBUG = False`), `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SECURE = True` e `SESSION_COOKIE_SAMESITE = "Lax"` (verificado também via `python manage.py check --deploy`).
  - 5 tentativas inválidas em 15 minutos (combinando ou não e-mail e CPF da mesma conta) bloqueiam a conta pelo tempo configurado em `settings` (padrão: 15 minutos), com a mensagem `"Muitas tentativas. Tente novamente mais tarde"`.
  - Todo acesso (sucesso e falha) gera registro na tabela de acessos com data, hora e identificação do usuário.
  - Redefinir senha (RF003) ou suspender/bloquear usuário (RF004) invalida imediatamente as sessões ativas da conta.
  - Conta com perfil Administrador não acessa rotas administrativas sem concluir o TOTP; atribuir o perfil Administrador no RF004 exige reconfirmação imediata (*step-up*) do código 2FA.
  - Códigos de recuperação são salvos apenas como hash, funcionam uma única vez e o reset de 2FA por outro Administrador só é permitido quando existem ao menos dois Administradores ativos (nunca para si mesmo).
  - Na implementação do RF002: `pyotp` (e eventual gerador de QR code) está fixado com `==` no `requirements.txt` e passa em `pip check` no Python 3.14.

## Notas

- **Compatibilidade verificada do `pyotp`:** biblioteca em Python puro sem dependências externas em tempo de execução e sem acoplamento ao Django (logo, independente da versão Django 6.1). Exige Python `>= 3.10` a partir da versão 2.11.0; a instalação no `.venv` (Python 3.14) será validada antes de fixar a versão no `requirements.txt` no RF002.
- **Contingência com Administrador único:** manter operacionalmente ao menos dois Administradores ativos para que o reset de 2FA pela interface funcione; em último caso (perda total com apenas um Administrador), prever procedimento controlado fora da interface (relacionado à Questão 20 do PRD).
- **ADRs relacionadas:**
  - [ADR 0001](0001-django-mvt-com-camada-de-service.md) (camada de service)
  - [ADR 0002](0002-postgresql-como-banco-de-dados.md) (PostgreSQL)
  - [ADR 0004](0004-pip-venv-requirements-fixado.md) (dependências entram apenas quando necessárias)
  - [ADR 0007](0007-modelo-de-usuario-customizado.md) (modelo de usuário customizado)
  - [ADR 0008](0008-hash-de-senha-argon2-ou-bcrypt.md) (hash de senha)
  - Próxima ADR candidata relacionada: **Perfis e permissões, inclusive permissões administrativas por função (RS015)**.
