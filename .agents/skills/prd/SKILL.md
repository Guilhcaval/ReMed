---
name: prd
description: 'Cria, revisa e atualiza o PRD (Documento de Requisitos de Produto) de qualquer projeto de software, a partir de um documento de requisitos, briefing, ata ou conversa. Use SEMPRE que o usuário pedir para escrever, criar, revisar ou atualizar um PRD, "documentar requisitos", "planejar uma funcionalidade", transformar um documento de requisitos em PRD, definir escopo, histórias de usuário, critérios de aceite ou fases de entrega, mesmo que ele não diga "PRD" explicitamente.'
license: MIT
---

# PRD (Documento de Requisitos de Produto)

## Visão geral

O PRD responde **o quê** e **por quê**. O **como** fica em outros documentos: specs (detalhe de cada funcionalidade), ADRs (decisões de arquitetura) e o documento de arquitetura. Não detalhe implementação no PRD; aponte para esses documentos.

Esta skill é independente de projeto. Antes de começar, descubra o contexto lendo o repositório e as informações do usuário (veja a Fase 1).

## Quando usar

- Criar o PRD inicial de um produto ou de uma funcionalidade grande.
- Atualizar o PRD depois de mudança nos requisitos.
- Transformar um documento de requisitos, briefing ou ata em PRD.
- Detalhar o escopo de uma funcionalidade nova antes de escrever a spec.

---

## Fluxo de trabalho

### Fase 1: Leitura da fonte (antes de perguntar)

1. Veja o que já existe: pastas de documentação (por exemplo `docs/prd/`, `docs/specs/`, `docs/adr/`), documento de arquitetura, arquivo de estado ou progresso, `README`. Siga o padrão de pastas e nomes encontrado; se não houver, use os padrões deste guia. Não duplique o que já existe.
2. Leia por completo a **fonte dos requisitos** fornecida pelo usuário (documento, ata, briefing, texto colado). Se nenhuma fonte foi fornecida, **pare e peça** antes de qualquer outra coisa. Não gere o PRD de memória nem de suposições.
3. Devolva um resumo curto: objetivo do produto, atores, quantidade de requisitos por tipo e prioridade, riscos principais.
4. No mesmo resumo, destaque separadamente:
   - **Seções vazias ou com texto-modelo** na fonte;
   - **Pendências** que a fonte deixa para decisão futura, com prazos, se houver;
   - **Inconsistências** entre requisitos, entre texto e telas, ou entre a fonte e decisões técnicas já tomadas;
   - **Funcionalidades citadas sem requisito próprio**.
5. Pergunte **apenas** o que a fonte não responde. Não pergunte o que ela já responde.
6. Aguarde a confirmação do usuário antes de redigir.

### Fase 2: Análise e escopo

- Mapeie os atores (perfis) e o fluxo principal de ponta a ponta.
- Se a fonte tiver matriz de dependências ou rastreabilidade, use-a para definir a ordem de entrega e achar dependências ocultas.
- Defina os **não-objetivos** a partir do que a fonte exclui explicitamente.

### Fase 3: Redação

Gere os arquivos em português (ou no idioma do projeto), seguindo o padrão de nome e numeração existente. Se a pasta estiver vazia, use:

- `docs/prd/01-<produto>.md`: o PRD (esquema abaixo), legível e enxuto.
- `docs/prd/02-catalogo-requisitos.md`: **somente quando** existir um documento de requisitos detalhado como fonte (ver "Catálogo de requisitos").

### Fase 4: Fechamento

- Apresente o rascunho e peça feedback por seção.
- Atualize o arquivo de estado do projeto (se existir) com o que foi feito e os próximos passos.

---

## Regras de qualidade

### Rastreabilidade e IDs

- Use os IDs de requisito **exatamente como estão na fonte** (por exemplo `RF001`, `RNF01`, `RS001`, `REQ-12`). Se a fonte não tiver IDs, proponha uma convenção simples e peça aprovação.
- Se a convenção de IDs da fonte for inconsistente, use a da tabela principal e registre a inconsistência em "Questões em aberto".
- Cada história, critério de aceite, risco e requisito de segurança **cita os IDs de origem**. Requisito sem origem só entra se o usuário pedir e deve ser marcado como `NOVO`.

### PRD autocontido

Se a fonte original não ficará no repositório, as próximas sessões só terão o PRD e o catálogo. Nada importante pode ficar só na fonte. Não remeta o leitor ao arquivo original ("consulte o documento"); traga o conteúdo necessário.

### Prioridades e entrega em fases

- Carregue a prioridade de cada requisito como na fonte (por exemplo Essencial, Importante, Desejável; ou Must, Should, Could).
- Proposta de fases, salvo se o usuário definir outra: prioridade máxima = MVP; segunda = v1.1; terceira = v2.0.
- Pela matriz de dependências, verifique se algum requisito prioritário depende de um menos prioritário. Se depender, registre em "Questões em aberto".

### Sem invenção

- Não invente requisitos, regras de negócio, números ou restrições.
- Valores que a fonte marca como **"sugerido"** aparecem como "sugerido na fonte", nunca como definitivos.
- Valores que a fonte deixa para decisão posterior (pendência, ata, TBD) vão para "Questões em aberto", com o ID de origem e o prazo. Se o prazo já passou, diga isso.
- Normas e leis: cite apenas as que a fonte nomeia e **não afirme o que elas dizem** além do que está na fonte. Viabilidade jurídica ou regulatória incerta vira risco e questão em aberto.

### Critérios mensuráveis

Use valores da própria fonte. Se ela não definir, marque `TBD`. Evite "rápido", "fácil", "intuitivo" sem número ou critério verificável.

```diff
# Vago (RUIM)
- A busca deve ser rápida e simples.

# Concreto (BOM, valores vindos da fonte)
+ As páginas públicas e as buscas respondem em até 3 s (percentil 95) com até 500 usuários simultâneos.
+ O sistema rejeita cadastro com data de validade anterior à data atual.
```

---

## Esquema do PRD

Siga esta estrutura. Remova ou marque "Não se aplica" nas seções que não fizerem sentido para o produto.

### 1. Resumo executivo

- **Problema**: 1-2 frases.
- **Solução proposta**: 1-2 frases.
- **Critérios de sucesso**: a métrica principal e os indicadores. Metas numéricas: `TBD` se a fonte não definir.

### 2. Experiência do usuário e funcionalidades

- **Atores**: perfis da fonte, com o que cada um pode fazer. Use exatamente os nomes da fonte.
- **Histórias de usuário**: `Como [ator], quero [ação] para [benefício].` Cada uma com seus IDs de origem.
- **Critérios de aceite**: derivados das regras da fonte, sem inventar.
- **Não-objetivos**: o que a fonte exclui ou adia explicitamente.

### 3. Requisitos de IA (somente se o produto usa IA)

- **Entrada e saída**: o que a IA recebe e devolve, incluindo nível de confiança se houver.
- **Regras de confiança e falha**: a IA sugere, o usuário confirma; o que fazer com baixa confiança; a falha da IA não pode bloquear o fluxo principal.
- **Privacidade**: que dados saem para serviços externos e se o usuário é avisado.
- **Desempenho**: tempo de resposta esperado.
- **Avaliação**: como medir a qualidade (`TBD` se a fonte não definir).

Se o produto não usa IA, escreva "Não se aplica".

### 4. Segurança, privacidade e conformidade

- **Requisitos de segurança**: perigo e solução, com os requisitos funcionais afetados.
- **Conformidade**: leis, normas e políticas citadas na fonte (por exemplo proteção de dados, regulação setorial), sem afirmar o conteúdo delas além da fonte.
- **Dados sensíveis**: quais são, quem acessa e o que nunca deve ser exibido ou coletado.
- **Matriz de risco**: reproduzida da fonte, se existir.

### 5. Visão técnica de alto nível

Apenas o essencial, apontando para os documentos de detalhe:

- **Requisitos não funcionais que condicionam a arquitetura** (desempenho, disponibilidade, escala, compatibilidade, backup).
- **Integrações externas citadas**.
- **Decisões já tomadas**: referência ao documento de arquitetura e às ADRs.
- **Candidatas a ADR e tensões** entre o que a fonte pede e decisões já tomadas (por exemplo, a fonte pede API REST e a decisão é renderização no servidor).

### 6. Riscos e entrega em fases

- **Riscos**: a partir da matriz da fonte ou levantados na análise, com ID, impacto e mitigação.
- **Entrega em fases**: conforme "Prioridades e entrega em fases".

### 7. Rastreabilidade

- Tabela ligando cada requisito funcional à história de usuário e, quando existir, à spec.
- Matriz de dependências da fonte, reproduzida fielmente.

### 8. Questões em aberto

Lista numerada, cada item com o ID de origem e quem deve decidir:

- Pendências da fonte (com prazo, indicando se já passou).
- Seções vazias ou com texto-modelo.
- Inconsistências encontradas.
- Funcionalidades citadas sem requisito próprio. **Não crie requisito para elas**; apenas liste.

### 9. Glossário

Termos do domínio com definição única, usando o vocabulário da fonte. Não troque termos do domínio por sinônimos sem confirmação.

---

## Catálogo de requisitos (opcional)

Quando há um documento de requisitos detalhado como fonte, crie uma transcrição **fiel**, sem resumir regras:

- **Requisitos funcionais**: ID, nome, prioridade, usuários, pré-condição, descrição, campos (nome, tipo, formato), regras e notas numeradas, mensagens de validação, regras de alteração, exclusão e pesquisa, observações.
- **Requisitos não funcionais**: ID, tipo, descrição, prioridade.
- **Requisitos de segurança**: ID, perigo e soluções numeradas.
- **Matrizes** (risco, rastreabilidade): reproduzidas como na fonte. Se alguma tabela estiver ilegível ou ambígua, reproduza o que estiver claro e pergunte.
- **Telas e mockups**: descreva o que a imagem mostra de relevante (abas, campos, textos, botões) e registre se a imagem não estará no repositório.
- Informe o nome e a versão ou data da fonte, sem caminho de arquivo.
- **Não transcreva** seções incompletas, com texto-modelo, nem referências bibliográficas.

---

## Faça (sempre)

- Leia a fonte e o que já existe na documentação antes de perguntar ou escrever.
- Cite IDs de requisito em tudo.
- Marque o que é "sugerido" e o que é pendência.
- Itere: apresente o rascunho e peça feedback por seção.

## Não faça

- Não escreva código nem detalhes de implementação no PRD.
- Não repita o conteúdo de specs, ADRs ou da arquitetura; aponte para eles.
- Não pergunte o que a fonte já responde.
- Não afirme o conteúdo de leis ou normas além do que está na fonte.
- Não crie requisitos novos para preencher lacunas; liste-as em "Questões em aberto".
- Não sobrescreva um PRD existente sem mostrar o que muda.
