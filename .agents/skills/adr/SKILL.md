---
name: adr
description: 'Cria e atualiza ADRs (registros de decisão de arquitetura) em qualquer projeto, normalmente em docs/adr/. Use SEMPRE que o usuário pedir uma ADR, "registrar uma decisão", "documentar por que escolhemos X", comparar opções técnicas (banco de dados, framework, biblioteca, padrão de camadas, armazenamento, autenticação, mensageria, hospedagem), ou quando uma decisão técnica relevante for tomada ou mudada, mesmo que ele não diga "ADR" explicitamente.'
license: MIT
---

# ADRs (Registros de Decisão de Arquitetura)

## Visão geral

Uma ADR registra **uma** decisão de arquitetura, o contexto em que foi tomada, as opções consideradas e as consequências. Serve para que quem chegar depois (pessoas e agentes em novas sessões) entenda **por que** o projeto é como é. ADRs ficam, por padrão, em `docs/adr/`.

## Quando usar

- Registrar uma decisão técnica tomada ou confirmada pelo usuário.
- Propor uma decisão pendente, com opções, para o usuário decidir.
- Mudar uma decisão anterior (cria-se uma nova ADR que substitui a antiga).
- Sempre que o PRD, uma spec ou uma revisão de segurança apontar uma "decisão pendente".

---

## Fluxo de trabalho

### Fase 1: Leitura

1. Leia a documentação existente: ADRs já criadas, documento de arquitetura, arquivo de estado do projeto (se houver), PRD e specs. **Não duplique** uma decisão já registrada.
2. Leia os requisitos relacionados (principalmente não funcionais e de segurança), porque são eles que motivam a maioria das decisões.

### Fase 2: Quem decide

- **Decisão que o usuário já tomou**: registre com status `aceita`. Não reabra a decisão nem apresente alternativas como se estivessem em discussão; registre as opções consideradas apenas se o usuário as informar ou se forem óbvias e relevantes.
- **Decisão ainda não tomada**: crie a ADR com status `proposta`, liste as opções com prós e contras e, se quiser, indique qual recomenda e por quê. **O agente nunca marca `aceita` por conta própria.**
- Se o usuário pediu "as ADRs do projeto" sem detalhar, registre as decisões que ele já tomou e **liste as demais candidatas** para ele escolher quais viram `proposta`.

### Fase 3: Redação

Uma decisão por arquivo, no idioma do projeto, em `docs/adr/`, seguindo o padrão de nome e numeração dos arquivos existentes. Se a pasta estiver vazia, use `NNNN-titulo-em-kebab-case.md` (por exemplo, `0001-usar-postgresql.md`), com numeração sequencial que **nunca é reutilizada**.

### Fase 4: Fechamento

- Atualize o documento de arquitetura para refletir a decisão, apontando para a ADR.
- Atualize o arquivo de estado do projeto (se existir) com o que foi feito e as decisões pendentes.

---

## Modelo de ADR

```markdown
# NNNN. Título curto no imperativo ou como afirmação da decisão

- Status: proposta | aceita | rejeitada | substituída por NNNN
- Data: AAAA-MM-DD
- Requisitos relacionados: IDs dos requisitos que motivam a decisão

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

Para ADRs `proposta`, na seção "Opções consideradas" detalhe prós e contras de cada opção e, opcionalmente, uma recomendação marcada como tal.

---

## Como identificar candidatas a ADR

Procure decisões que sejam **caras de reverter** ou que **afetem várias partes do sistema**. Fontes comuns:

- Requisitos não funcionais (desempenho, disponibilidade, escala, backup, compatibilidade).
- Requisitos de segurança (autenticação, sessão, criptografia, armazenamento de arquivos sensíveis, auditoria).
- Tensões entre o que o PRD pede e o que já foi decidido (por exemplo, o PRD pede uma API e a arquitetura é renderização no servidor).
- Concorrência e consistência (reservas, transações, bloqueios).
- Tarefas agendadas e processamento em segundo plano.
- Integrações externas (IA, mapas, e-mail, pagamentos) e o que fazer quando falham.
- Escolha de linguagem, framework, banco, hospedagem, padrão de camadas.
- Histórico e auditoria de dados.

Ao listar candidatas, use uma tabela: tema, requisitos relacionados, por que decidir.

---

## Regras de qualidade

- **Uma decisão por ADR.** Se há duas decisões, são duas ADRs.
- **Imutabilidade**: uma ADR `aceita` não é reescrita. Para mudar, crie uma nova ADR e marque a antiga como "substituída por NNNN".
- **Rastreabilidade**: relacione os requisitos que motivam a decisão.
- **Sem invenção**: não afirme versões de bibliotecas, preços, limites de serviços ou conteúdo de leis sem fonte. Se precisar, marque como "a confirmar".
- **Consequências honestas**: inclua os custos e riscos, não só os benefícios.
- **Verificável**: toda decisão tem "Como verificar".
- **Sem código de aplicação**: trechos curtos de configuração só quando essenciais para entender a regra.
- **Normas**: cite apenas as que a fonte nomeia e não afirme seu conteúdo além dela.

## Faça (sempre)

- Verifique se a decisão já existe antes de criar.
- Atualize o documento de arquitetura e o arquivo de estado ao concluir.
- Peça a decisão do usuário quando houver mais de uma opção razoável.

## Não faça

- Não marque uma ADR como `aceita` sem decisão do usuário.
- Não reescreva ADRs aceitas.
- Não misture várias decisões numa só ADR.
- Não implemente algo que depende de uma ADR ainda `proposta`.
