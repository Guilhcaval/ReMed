# 0013. Garantir reserva transacional e controle de concorrência com bloqueio pessimista no PostgreSQL

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF06, RS007, RF008, RF010, RF011, RF012, RF014, RF016, RF018, RF020

## Contexto

O núcleo de integridade do ReMed depende de impedir que o mesmo medicamento seja reservado, agendado ou entregue mais de uma vez:

- **RNF06 (Essencial):** reserva, agendamento e entrega (RF016, RF018 e RF020) são **transacionais**, sem permitir que o mesmo medicamento seja reservado para duas solicitações. Em caso de falha, a operação é desfeita e o usuário é informado.
- **RS007:** ao aceitar a correspondência, a doação passa a `"reservada"` numa operação única e transacional (RNF06); a reserva expira se o agendamento não for confirmado no prazo, voltando a `"disponível"`; a quantidade disponível é atualizada a cada reserva ou entrega parcial; as partes são notificadas de qualquer mudança de status.
- **RF012 (regra 3):** a validade também é conferida na reserva (RF016) e no agendamento (RF018), para evitar que uma doação vencida no mesmo dia seja reservada — além da disputa concorrente entre um usuário aceitando uma correspondência e a rotina diária de vencimento (RF012) marcando a doação como `"vencido"`.
- **RF020 (regra 4):** a entrega pode ser **parcial**; a quantidade disponível da doação é atualizada e, ao zerar, o status passa a `"entregue"`.
- **ADR 0001 e ADR 0002:** as operações vivem na camada de service e usam PostgreSQL, que oferece transações ACID, `SELECT ... FOR UPDATE` (`select_for_update()`) e constraints parciais/`CheckConstraint`.

## Direcionadores da decisão

- Eliminar condições de corrida em aceite de correspondência (RF016), confirmação/cancelamento de agendamento (RF018), confirmação/recusa de entrega (RF020) e rotinas de vencimento/expiração (RF012, RS007).
- Garantir atomicidade: ou todas as entidades relacionadas (`Doacao`, `Solicitacao`, `Correspondencia`, `Agendamento`, registro de auditoria da ADR 0011 e criação de notificações na fila da ADR 0015) são atualizadas juntas, ou tudo sofre *rollback* (RNF06).
- Manter invariantes protegidas também no banco de dados (constraints), não apenas na lógica Python.
- Evitar *deadlocks* e não segurar transações abertas durante chamadas externas (envio de e-mail, CEP, IA).
- Evitar infraestrutura adicional no MVP (como Redis para locks distribuídos).

## Opções consideradas

### 1. Bloqueio pessimista no PostgreSQL (`transaction.atomic()` + `select_for_update()` em ordem determinística) + constraints no banco (recomendada)

Executar toda operação concorrente dentro de `transaction.atomic()` nos services de domínio, adquirindo bloqueio de linha (`select_for_update()`) sempre na **mesma ordem fixa de tabelas** (`Doacao` -> `Solicitacao` -> `Correspondencia` -> `Agendamento`) para evitar *deadlocks*. Dentro do bloqueio, o service revalida status, validade do medicamento (RF012 regra 3), quantidade disponível e prazos antes de aplicar a transição e gravar a auditoria (ADR 0011).

Complementar com constraints no PostgreSQL:
- `CheckConstraint` impedindo `quantidade_disponivel < 0` e `quantidade_disponivel > quantidade_inicial`;
- `UniqueConstraint` parcial garantindo a regra de exclusividade de reserva ativa (conforme definição na questão em aberto 1).

Qualquer efeito colateral externo (como disparo imediato de e-mail, caso exista fora do outbox) só roda em `transaction.on_commit(...)`.

- **Prós:**
  - Serializa de forma determinística requisições simultâneas sobre a mesma doação (inclusive disputas entre aceite de correspondência e a rotina diária do RF012).
  - Recurso nativo do Django + PostgreSQL (zero dependência externa e zero infraestrutura adicional).
  - Fácil de raciocinar e de comprovar com testes concorrentes usando `TransactionTestCase` no PostgreSQL.
- **Contras:**
  - Mantém bloqueio de linha até o fim da transação; exige disciplina para manter as transações curtas e nunca fazer I/O externo (HTTP, SMTP, armazenamento externo) dentro de `transaction.atomic()`.
  - Exige respeitar rigorosamente a ordem fixa de aquisição dos locks em todos os services e rotinas para prevenir *deadlocks*.

### 2. Controle de concorrência otimista (coluna `versao` + `UPDATE ... WHERE versao = X`) com retentativa

Adicionar um campo inteiro `versao` em `Doacao` (e demais entidades disputadas) e atualizar condicionalmente verificando o número de linhas afetadas (`rows == 1`), repetindo ou abortando a operação em caso de conflito.

- **Prós:**
  - Não retém locks de linha durante o processamento em Python.
- **Contras:**
  - Mais complexo em operações que envolvem 3 ou 4 entidades acopladas (`Doacao`, `Solicitacao`, `Correspondencia`, `Agendamento`), exigindo código de retentativa e tratamento de conflitos em vários services.
  - Não dispensa `transaction.atomic()` nem constraints no banco e torna falhas sob contenção menos previsíveis para o usuário.

### 3. Nível de isolamento `SERIALIZABLE` global no PostgreSQL ou lock distribuído em Redis

- **Prós:**
  - `SERIALIZABLE` dispensa `select_for_update()` manual; Redis centraliza locks fora do banco de dados.
- **Contras:**
  - `SERIALIZABLE` provoca erros de serialização (`SerializationFailure`) que obrigam a implementar retentativa automática em toda transação da aplicação.
  - Lock distribuído em Redis adiciona um novo componente de infraestrutura ao MVP (evitado na ADR 0009) e ainda exige cuidado com expiração de lock e consistência com a transação do PostgreSQL.

## Decisão

**Opção 1** — `transaction.atomic()` + `select_for_update()` padrão (aguardando a transação curta) em ordem determinística (`Doacao` -> `Solicitacao` -> `Correspondencia` -> `Agendamento`) + constraints no PostgreSQL (`CheckConstraint` de quantidade e `UniqueConstraint` parcial de reserva ativa), mantendo transações curtas (sem chamadas externas).

Regras que passam a valer:

- **Exclusividade de reserva e entrega parcial (RF016 regra 5 × RF020 regra 4):** a **doação inteira fica reservada para uma única correspondência por vez**, garantida no banco por `UniqueConstraint` parcial de no máximo 1 reserva ativa por doação. Em caso de entrega parcial (RF020), a quantidade disponível é reduzida e, se restar saldo maior que zero, a doação volta ao status `"disponível"` para novas buscas e correspondências; ao zerar, passa a `"entregue"`.
- **Bloqueio pessimista padrão:** usar `select_for_update()` padrão (sem `nowait=True`), mantendo as transações estritamente curtas para que uma segunda requisição concorrente aguarde o commit e receba a mensagem de regra de negócio informando que a doação não está mais disponível.
- **Revalidação dentro do bloqueio:** após adquirir `select_for_update()`, o service sempre reconfere status, validade (RF012 regra 3), receita válida (quando aplicável — RF014) e quantidade disponível antes de gravar.
- **Ordem única de bloqueio:** todos os services e rotinas agendadas bloqueiam as entidades na ordem `Doacao` -> `Solicitacao` -> `Correspondencia` -> `Agendamento` (por `id` crescente quando houver múltiplos registros da mesma tabela), evitando *deadlocks*.
- **Prazo de expiração da reserva sem agendamento confirmado (Questão 12 do PRD / RS007):** adotar **48 horas** como valor inicial, definido como parâmetro nomeado e **configurável em `settings`**, sujeito a validação com o cliente.
- **Atomicidade com auditoria e notificações:** o registro de auditoria (ADR 0011) e a gravação das notificações na fila (ADR 0015) acontecem na mesma transação; em caso de falha, tudo sofre *rollback* e a view informa o usuário (RNF06).
- **Validade das rotinas automáticas:** rotinas de vencimento (RF012) e expiração (RF016, RF018) usam o mesmo bloqueio (`select_for_update()`) para não conflitar com um aceite ou confirmação de entrega simultâneos.

## Consequências

- Positivas:
  - Cumpre integralmente o RNF06 e o RS007 usando recursos nativos do PostgreSQL (ADR 0002).
  - Previne reserva dupla mesmo sob acesso simultâneo de múltiplos usuários ou durante a execução da rotina diária de vencimento.
  - A exclusividade de 1 reserva ativa por doação simplifica o estado de reserva e permite garantia direta por `UniqueConstraint` parcial no banco.
- Negativas e custos:
  - Testes de concorrência precisam rodar contra PostgreSQL com `TransactionTestCase` (mais lentos do que `TestCase` padrão).
  - Chamadas externas (como envio de e-mail) não podem ocorrer de forma síncrona dentro da transação (alinhado ao outbox da ADR 0015).
- Impacto em specs e arquitetura:
  - Condiciona diretamente as specs de **RF012**, **RF016**, **RF018** e **RF020**, que devem detalhar as pré-condições revalidadas sob bloqueio e os testes de disputa simultânea.

## Como verificar

- Testes concorrentes (`TransactionTestCase` com threads reais no PostgreSQL) simulando dois aceites simultâneos sobre a mesma doação confirmam que exatamente um vence e o outro falha de forma limpa, sem reserva dupla nem quantidade negativa.
- Teste concorrente entre aceite de correspondência (RF016) e rotina de vencimento (RF012) confirma consistência de estado sem corrupção.
- Teste de entrega parcial (RF020) confirma redução de `quantidade_disponivel` e retorno da doação a `"disponível"` enquanto houver saldo, passando a `"entregue"` ao zerar.
- Teste de falha induzida no meio da operação de reserva/entrega confirma *rollback* completo (nenhuma mudança parcial de status, auditoria ou notificação órfã).
- Migrações contêm `CheckConstraint` de quantidade não negativa e `UniqueConstraint` parcial de no máximo 1 reserva ativa por doação.

## Notas

- **Validação pendente com o cliente (não bloqueia a ADR):** confirmar o prazo inicial de **48 horas** para expiração de reserva sem agendamento confirmado (Questão 12 do PRD / RS007), já isolado como parâmetro configurável em `settings`.
- **ADRs relacionadas:** [ADR 0002](0002-postgresql-como-banco-de-dados.md), [ADR 0011](0011-historico-imutavel-e-auditoria.md), [ADR 0014](0014-rotinas-agendadas.md) e [ADR 0015](0015-notificacoes-email-e-plataforma.md).
