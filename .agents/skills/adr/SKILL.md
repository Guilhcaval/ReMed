---
name: adr
description: 'Cria e atualiza ADRs (registros de decisão de arquitetura) do ReMed em docs/adr/. Use SEMPRE que o usuário pedir uma ADR, "registrar uma decisão", "documentar por que escolhemos X", comparar opções técnicas (banco de dados, framework, biblioteca, padrão de camadas, armazenamento, autenticação), ou quando uma decisão técnica relevante for tomada ou mudada, mesmo que ele não diga "ADR" explicitamente.'
license: MIT
---

# ADRs do ReMed

## Visão geral

Uma ADR registra **uma** decisão de arquitetura, o contexto em que foi tomada, as opções consideradas e as consequências. Serve para que quem chegar depois (inclusive agentes em novas sessões) entenda **por que** o projeto é como é. ADRs ficam em `docs/adr/`.

## Contexto

- **Projeto**: ReMed, plataforma web de doação e redistribuição de medicamentos não vencidos.
- **Fontes**: `docs/prd/01-remed.md` e `docs/prd/02-catalogo-requisitos.md` (requisitos RF, RNF e RS). O PDF original **não** fica no repositório; cite os requisitos pelos IDs.
- **Decisões já tomadas pelo usuário** (devem virar as duas primeiras ADRs, se ainda não existirem):
  1. Django com padrão **MVT**, com **camada de service** e **views baseadas em classe**. Regras: toda regra de negócio e consulta ao ORM ficam nos services; toda view é uma classe que herda de `django.views.View` e implementa só os métodos HTTP necessários (mixins de acesso, como `LoginRequiredMixin`, são permitidos); services não recebem `request` nem retornam `HttpResponse`.
  2. **PostgreSQL** como banco de dados.

## Quando usar

- Registrar uma decisão técnica tomada ou confirmada pelo usuário.
- Propor uma decisão pendente, com opções, para o usuário decidir.
- Mudar uma decisão anterior (cria-se uma nova ADR que a substitui).

---

## Fluxo de trabalho

### Fase 1: Leitura

1. Leia `AGENTS.md`, `docs/state.md`, `docs/arquitetura.md` e as ADRs existentes. Não duplique uma decisão já registrada.
2. Leia os requisitos relacionados no PRD e no catálogo (RNF e RS, principalmente).

### Fase 2: Quem decide

- **Decisão que o usuário já tomou**: registre com status `aceita`. Não reabra a decisão nem acrescente alternativas como se estivessem em discussão; registre as opções consideradas apenas se o usuário as informar ou se forem óbvias e relevantes.
- **Decisão ainda não tomada**: crie a ADR com status `proposta`, liste as opções com prós e contras e, se quiser, indique qual recomenda e por quê. **O agente nunca marca `aceita` por conta própria.**
- Se o usuário pediu "as ADRs do projeto" sem detalhar, crie `0001` e `0002` (acima) e **liste** as demais candidatas para ele escolher quais viram `proposta`.

### Fase 3: Redação

Uma decisão por arquivo, em português, em `docs/adr/`, seguindo o padrão de nome e numeração dos arquivos existentes. Se a pasta estiver vazia, use `NNNN-titulo-em-kebab-case.md` (por exemplo, `0001-django-mvt-com-camada-de-service.md`), com numeração sequencial que nunca é reutilizada.

### Fase 4: Fechamento

- Atualize `docs/arquitetura.md` para refletir a decisão, apontando para a ADR.
- Atualize `docs/state.md` com o que foi feito e as decisões pendentes.

---

## Modelo de ADR

```markdown
# NNNN. Título curto no imperativo ou como afirmação da decisão

- Status: proposta | aceita | rejeitada | substituída por NNNN
- Data: AAAA-MM-DD
- Requisitos relacionados: RNFxx, RSxxx, RFxxx

## Contexto

O problema e as forças em jogo, com os requisitos que motivam a decisão.

## Direcionadores da decisão

- Critério 1 (com o ID do requisito, quando houver)
- Critério 2

## Opções consideradas

1. Opção A
2. Opção B

## Decisão

Opção escolhida e a justificativa, em termos dos direcionadores. Regras concretas que passam a valer.

## Consequências

- Positivas: ...
- Negativas e custos: ...
- Impacto em specs e arquitetura: ...

## Como verificar

Como saber se a decisão está sendo cumprida (revisão de código, teste, checagem automática).

## Notas

Pendências, links para outras ADRs e para specs.
```

---

## ADRs iniciais

### 0001: Django com MVT, camada de service e views baseadas em classe

Conteúdo mínimo:

- **Regras**: as de "Contexto" acima, escritas como regras verificáveis em revisão de código.
- **Consequências**: view fina; regra de negócio testável sem `request`; operações transacionais (reserva, agendamento e entrega, RNF06 e RS007) ficam nos services.
- **Relação com RNF09**: o documento pede "API REST" (RNF09, prioridade Desejável). Esta ADR **não decide** sobre API REST; registre como decisão pendente e aponte para a ADR correspondente, se existir.
- **Como verificar**: nenhum `request` em services; nenhuma consulta ao ORM em views ou templates.

### 0002: PostgreSQL como banco de dados

Conteúdo mínimo:

- **Direcionadores**: banco relacional (RNF09), operações transacionais (RNF06), backup diário com retenção mínima de 30 dias (RNF05), integridade e unicidade (CPF, CNPJ e e-mail únicos).
- **Consequências**: o que o projeto passa a exigir (configuração por variáveis de ambiente, backup, restauração testada).
- **Como verificar**: configuração de banco no projeto aponta para PostgreSQL em todos os ambientes.

---

## Candidatas a ADR (a partir do documento de requisitos)

Liste-as ao usuário; só escreva como `proposta` as que ele escolher.

| Tema | Requisitos | Por que decidir |
| --- | --- | --- |
| API REST vs. MVT puro | RNF09 | O documento pede API REST e a decisão é MVT |
| Hash de senha | RS005, RF001 | O documento cita bcrypt ou argon2 |
| Reserva e concorrência | RNF06, RS007, RF009 a RF011 | Evitar reserva dupla |
| Rotinas agendadas | RF006, RF009, RF010 | Validade diária, expirações, lembretes |
| Armazenamento de arquivos criptografado | RNF08, RF012, RS002 | Fotos e receitas (dado sensível) |
| Autenticação, sessão e bloqueio | RF003, RS005 | Sessão de 30 min, bloqueio após 5 tentativas, 2FA do Administrador |
| Geolocalização e cálculo de distância | RF008, RS010 | Localização aproximada, cálculo no servidor |
| Integração de IA para leitura da embalagem | RF005, RNF12, RS009 | Serviço externo, privacidade, fallback |
| Notificações (e-mail e na plataforma) | RF009 | Canais, registro de envios |
| Histórico e auditoria | RF001, RF004, RS006 | Quem, o quê, data e hora em várias entidades |

---

## Regras de qualidade

- **Uma decisão por ADR.** Se há duas decisões, são duas ADRs.
- **Imutabilidade**: uma ADR `aceita` não é reescrita. Para mudar, crie uma nova ADR e marque a antiga como "substituída por NNNN".
- **Rastreabilidade**: relacione os RNF, RS e RF que motivam a decisão.
- **Sem invenção**: não afirme versões de bibliotecas, preços, limites de serviços ou conteúdo de leis sem fonte. Se precisar, marque como "a confirmar".
- **Consequências honestas**: inclua os custos e riscos, não só os benefícios.
- **Sem código de aplicação**: trechos curtos de configuração ou de exemplo só quando essenciais para entender a regra.
- **Normas**: cite apenas as que o documento nomeia e não afirme seu conteúdo além dele.

## Faça (sempre)

- Verifique se a decisão já existe antes de criar.
- Atualize `docs/arquitetura.md` e `docs/state.md` ao concluir.
- Peça a decisão do usuário quando houver mais de uma opção razoável.

## Não faça

- Não marque uma ADR como `aceita` sem decisão do usuário.
- Não reescreva ADRs aceitas.
- Não misture várias decisões numa só ADR.
- Não remeta o leitor ao PDF: ele não está no projeto.
