# 0011. Implementar histórico imutável e auditoria por service dedicado e tabela append-only no PostgreSQL

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF14, RF001, RF002, RF004, RF005, RF006, RF007, RF008, RF011, RF012, RF013, RF014, RF018, RF020, RF021, RNF10, RS002, RS011, RS013, RS015

## Contexto

O **RNF14 (Essencial)** exige que toda operação que altere dados (cadastros, status, aprovações, reservas, entregas, denúncias e ações administrativas) gere um **registro de histórico imutável** contendo **quem, o quê, data e hora**, mantido pelo prazo da política de privacidade (RNF10), acessível apenas ao Administrador e que **não pode ser alterado nem apagado**.

Além do RNF14, vários outros requisitos impõem exigências de auditoria específicas:

- **Motivos e decisões de negócio:** alterações administrativas de status (RF004), reprovações/suspensões de pontos de coleta (RF007), reprovações de doações (RF011) e decisões de denúncias (RF021) exigem registrar o motivo/resultado junto ao histórico.
- **Envio e acesso a arquivos restritos (RS013, solução 5):** cada envio **e cada acesso (leitura)** a arquivos (fotos de embalagem, receitas e documentos de pontos de coleta) precisa ser registrado com quem, o quê, data e hora.
- **Ações administrativas e revisão periódica (RS015, solução 3):** toda ação administrativa gera registro imutável sujeito a revisão periódica.
- **Acessos de login (RF002 regra 5):** já cobertos pela tabela própria de tentativas/acessos da [ADR 0009](0009-sessao-bloqueio-tentativas-e-2fa-administrador.md).
- **Tensão com a LGPD (RNF10, RS002, ADR 0007):** o histórico precisa ser imutável durante o prazo de retenção, mas não pode vazar segredos (senhas, segredos TOTP, tokens de recuperação), conteúdo de receitas nem duplicar indiscriminadamente dados pessoais identificáveis (CPF, e-mail, endereço) que deveriam ser anonimizados no encerramento de conta (ADR 0007). Além disso, ao final do prazo de retenção definido na política de privacidade (Questão 8 do PRD), os registros expirados precisam poder ser descartados de forma controlada.

A [ADR 0001](0001-django-mvt-com-camada-de-service.md) concentra toda regra de negócio na camada de service (evitando lógica em `save()` ou `signals`), e a [ADR 0002](0002-postgresql-como-banco-de-dados.md) adota o PostgreSQL, que permite reforçar a imutabilidade diretamente no banco de dados.

## Direcionadores da decisão

- Garantir imutabilidade real (não permitir `UPDATE` nem `DELETE` pela aplicação, pelo Admin ou por engano no ORM) conforme o RNF14.
- Capturar de forma uniforme tanto alterações de estado/dados quanto eventos de domínio que não alteram linhas do banco — em especial **leitura de arquivos sensíveis** (RS013) e **execuções do Sistema** (RF012).
- Registrar o autor (`quem`), a ação (`o quê`), o timestamp em UTC (`data e hora`) e o motivo/contexto dentro da **mesma transação atômica** da operação principal.
- Evitar vazamento ou retenção indevida de segredos e dados pessoais sensíveis na trilha de auditoria (RNF10, RS002, ADR 0007).
- Manter aderência à camada de service (ADR 0001), sem depender de `signals` nem de estado implícito por thread/middleware, e evitar dependências externas desnecessárias (ADR 0004).

## Opções consideradas

### 1. Tabela própria `append-only` de auditoria + `AuditoriaService` explícito + trigger de imutabilidade no PostgreSQL (recomendada)

Criar um model próprio (por exemplo, `RegistroAuditoria`) e um service dedicado (`AuditoriaService.registrar(...)`) chamado explicitamente dentro do mesmo `transaction.atomic()` de cada service de domínio que altera dados ou concede acesso a arquivos restritos (RS013).

- **Estrutura proposta do registro:** `id`, `criado_em` (UTC, `USE_TZ = True`), `ator` (`ForeignKey` para `AUTH_USER_MODEL` com `on_delete=PROTECT`, nulo quando a ação for do `Sistema`/rotina automática), `acao` (código de domínio, ex.: `usuario.status_alterado`, `ponto_coleta.aprovado`, `doacao.reservada`, `arquivo.acessado`), `entidade_tipo`, `entidade_id`, `motivo` (texto quando exigido pelo requisito), `detalhes` (`JSONField` estruturado com transições de status e nomes dos campos alterados — nunca senhas, segredos TOTP, tokens, receitas ou cópia bruta de PII) e `origem` (`web`, `rotina_automatica`, `terminal`).
- **Imutabilidade em duas camadas:**
  - **Aplicação:** `AuditoriaService` expõe apenas inserção e consulta (sem métodos de edição/exclusão); no Django Admin, o model fica estritamente somente leitura.
  - **PostgreSQL:** trigger `BEFORE UPDATE OR DELETE` na tabela de auditoria rejeitando qualquer tentativa de alteração ou exclusão pela credencial da aplicação.
- **Prós:**
  - Totalmente alinhada à [ADR 0001](0001-django-mvt-com-camada-de-service.md): sem `signals`, sem middleware mágico para descobrir o autor e na mesma transação atômica da operação (se a operação sofrer *rollback*, o registro de auditoria também é desfeito; se confirmar, o histórico é garantido).
  - Cobre nativamente eventos que bibliotecas de `save()` não cobrem, como **acesso/leitura a arquivos** (RS013), **motivo obrigatório** (RF004, RF007, RF011, RF021), **rotinas do Sistema** (RF012) e operações `QuerySet.update()`.
  - Controle explícito de privacidade (LGPD, RNF10, RS002): decide-se exatamente o que entra em `detalhes`, evitando guardar PII bruto ou dados de saúde em JSON imutável.
  - Imutabilidade garantida no PostgreSQL (trigger `append-only`), não apenas por convenção de código.
  - Zero dependência externa adicional no `requirements.txt` (ADR 0004).
- **Contras:**
  - Exige disciplina da equipe para chamar `AuditoriaService.registrar(...)` em todo service de escrita ou acesso a arquivo (mitigado por revisão de código e testes exigindo o registro de auditoria em cada caso de uso).
  - Não gera automaticamente snapshots completos de todas as colunas antigas e novas de cada tabela (embora evitar snapshots brutos de PII seja benéfico para a LGPD).

### 2. Biblioteca baseada em sinais/ORM do Django (`django-auditlog` ou `django-simple-history`)

Adotar uma biblioteca pronta de auditoria do ecossistema Django (ambas declaram suporte a Django 6.1 e Python 3.14 nas versões recentes: `django-auditlog >= 3.4.2` e `django-simple-history >= 3.12.0`).

- **Prós:**
  - Registro automático em chamadas `model.save()`, com menos código repetitivo nos services e diff pronto de campos alterados.
- **Contras:**
  - Baseia-se em `signals` do Django e middleware com estado implícito por requisição para capturar o autor ("quem"), contrariando a separação explícita da camada de service (ADR 0001) e exigindo trabalho extra em rotinas agendadas/comandos do Sistema (RF012) e em `QuerySet.update()`.
  - Não cobre nativamente **leitura/acesso a arquivos** (RS013) nem motivos de negócio padronizados, exigindo de qualquer forma uma tabela/mecanismo paralelo.
  - Grava por padrão diffs/snapshots completos de campos do model (incluindo nome, CPF, e-mail, endereço), gerando risco direto de violação da anonimização LGPD (RNF10, ADR 0007) se qualquer campo sensível deixar de ser excluído.
  - Não aplica bloqueio de `UPDATE`/`DELETE` no nível do PostgreSQL por padrão e adiciona dependência externa ao `requirements.txt` (ADR 0004).

### 3. Triggers automáticos no PostgreSQL por tabela (`django-pghistory` ou triggers SQL genéricos)

Usar `django-pghistory` (suporte documentado a Python 3.14 e Django até 6.0; compatibilidade explícita com Django 6.1 ainda a confirmar) ou triggers SQL genéricos em todas as tabelas do domínio.

- **Prós:**
  - Captura alterações diretamente no banco de dados, inclusive fora do ORM ou via `QuerySet.update()`.
- **Contras:**
  - Triggers de banco não conhecem naturalmente o ator da aplicação (exigem injetar contexto por transação na conexão SQL) nem capturam **acessos de leitura a arquivos** (RS013) ou **motivos de negócio**.
  - Criam uma tabela de histórico por tabela auditada e copiam linhas inteiras com dados pessoais, dificultando a consulta unificada de auditoria (RS015) e o encerramento/anonimização LGPD (RNF10, ADR 0007).
  - `django-pghistory` adicionaria dependência externa com suporte ao Django 6.1 ainda pendente de confirmação.

## Decisão

**Opção 1** — tabela própria `append-only` de auditoria no PostgreSQL, alimentada explicitamente por um `AuditoriaService` dentro das transações dos services de domínio, com trigger `BEFORE UPDATE OR DELETE` no PostgreSQL bloqueando alterações e exclusões.

Regras que passam a valer:

- **Escopo mínimo obrigatório:** toda operação de criação, alteração de dados, mudança de status, aprovação/reprovação, reserva, agendamento, confirmação/recusa de entrega, denúncia/moderação, ação administrativa (RF004, RF007, RF011, RF014, RF021), envio de arquivo e **acesso/leitura a arquivo restrito** (RS013) registra um evento via `AuditoriaService.registrar(...)` dentro do mesmo `transaction.atomic()` da operação (quando houver escrita).
- **8ª função administrativa dedicada `auditoria` (Opção B — RNF14, RS015):** a consulta ao histórico imutável é restrita a uma função administrativa dedicada **`auditoria`** (adicionada à [ADR 0010](0010-perfis-e-permissoes.md)), com acesso exclusivamente somente leitura, 2FA obrigatório (ADR 0009) e filtros por período, ator, ação e entidade — reforçando a segregação de funções do RS015 (quem revisa ações administrativas não precisa ter poder de alterar contas).
- **Proteção de dados sensíveis e LGPD (RNF10, RS002):** `detalhes` registra apenas *quais campos* mudaram e transições de status/motivos; **nunca** armazena senhas, hashes de senha, segredos TOTP, códigos de recuperação, tokens de redefinição, conteúdo de receitas nem cópias brutas de dados pessoais identificáveis (CPF, e-mail, endereço, celular), evitando conflito com a anonimização de conta (ADR 0007).
- **Imutabilidade técnica e expurgo futuro por retenção LGPD (Opção B):** nenhum service expõe `update` ou `delete` sobre `RegistroAuditoria`; o Django Admin é somente leitura; uma migração SQL cria trigger `BEFORE UPDATE OR DELETE` no PostgreSQL rejeitando mutações pela credencial da aplicação. Mantém-se uma tabela simples no MVP; quando a política de privacidade definir o prazo de retenção (Questão 8 do PRD), a eliminação de registros expirados será executada apenas por uma **role administrativa de banco separada** (fora da credencial usada pela aplicação Django), em procedimento operacional controlado.
- **Tabela de acessos de login (RF002, ADR 0009):** permanece separada da `RegistroAuditoria` (por servir também ao cálculo da janela de 5 falhas em 15 minutos) e recebe o **mesmo trigger `append-only`** no PostgreSQL.

## Consequências

- Positivas:
  - Cumpre o RNF14, o RS013 (solução 5) e o RS015 (solução 3) com um mecanismo unificado, explícito e testável sem `request`.
  - Mantém total aderência à camada de service (ADR 0001) e zero novas dependências externas (ADR 0004).
  - Evita retenção oculta de dados pessoais ou de saúde em snapshots imutáveis, conciliando RNF14 com a LGPD (RNF10, ADR 0007).
  - A função dedicada `auditoria` reforça a segregação de funções exigida pelo RS015.
- Negativas e custos:
  - Todo novo service de escrita ou acesso a arquivo precisa incluir a chamada a `AuditoriaService.registrar(...)` e os testes correspondentes.
  - A tabela de auditoria cresce continuamente, exigindo índices adequados (por `criado_em`, `ator`, `entidade_tipo`/`entidade_id` e `acao`) e execução futura do expurgo via role administrativa de banco quando o prazo da política de privacidade for definido (Questão 8 do PRD).
  - Como não há snapshot automático de valores anteriores de PII, não é possível "reverter" um cadastro antigo apenas lendo o log (apenas auditar quem alterou quais campos e quando).
- Impacto em specs e arquitetura:
  - Transversal a todas as specs do MVP e v1.1: cada spec deverá listar os eventos de auditoria gerados por seus services.
  - Atualiza a [ADR 0010](0010-perfis-e-permissoes.md) com a 8ª função administrativa (`auditoria`).

## Como verificar

- Testes de banco no PostgreSQL (ADR 0002) confirmam que tentativas de `UPDATE` e `DELETE` na tabela `RegistroAuditoria` e na tabela de acessos de login (ADR 0009) pela credencial da aplicação falham com erro gerado pelo trigger.
- Testes de cada service do MVP confirmam que a operação grava o registro de auditoria correspondente na mesma transação (e que em caso de erro/rollback nenhum registro órfão é gravado).
- Testes garantem que nenhum segredo (senha, TOTP, token), conteúdo de receita nem cópia bruta de PII (CPF, e-mail, endereço, celular) é persistido em `detalhes`.
- Testes de view confirmam que apenas contas com a função administrativa `auditoria` (e 2FA concluído) conseguem consultar os registros de auditoria, e que não existem endpoints de edição ou exclusão.

## Notas

- **Prazo de retenção (Questão 8 do PRD):** o expurgo futuro por role administrativa de banco separada depende da definição dos prazos na política de privacidade (RNF10).
- **ADRs relacionadas:**
  - [ADR 0001](0001-django-mvt-com-camada-de-service.md) (camada de service sem `signals`)
  - [ADR 0002](0002-postgresql-como-banco-de-dados.md) (PostgreSQL e triggers de integridade)
  - [ADR 0004](0004-pip-venv-requirements-fixado.md) (parcimônia em dependências externas)
  - [ADR 0007](0007-modelo-de-usuario-customizado.md) (anonimização LGPD e `on_delete=PROTECT`)
  - [ADR 0009](0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) (tabela de acessos de login com trigger `append-only`)
  - [ADR 0010](0010-perfis-e-permissoes.md) (8 funções administrativas separadas, incluindo `auditoria`).
