---
name: prd
description: 'Cria e atualiza o PRD (Documento de Requisitos de Produto) do ReMed, plataforma web de doação e redistribuição de medicamentos não vencidos, em docs/prd/. Use SEMPRE que o usuário pedir para escrever, criar, revisar ou atualizar o PRD, "documentar requisitos", "planejar uma funcionalidade" ou transformar o Documento de Requisitos do ReMed em PRD, mesmo que ele não diga "PRD" explicitamente.'
license: MIT
---

# PRD do ReMed

## Visão geral

Produz o PRD do ReMed a partir do Documento de Requisitos fornecido pelo usuário. O PRD responde **o quê** e **por quê**. O **como** fica em `docs/specs/` (especificações), `docs/adr/` (decisões de arquitetura) e `docs/arquitetura.md`. Não detalhe implementação aqui; aponte para esses documentos.

## Contexto do produto

- **ReMed**: plataforma web (responsiva, mobile first) que conecta doadores e solicitantes de medicamentos não vencidos, com retirada combinada em pontos de coleta, para reduzir o desperdício de medicamentos e ampliar o acesso a eles. A principal métrica do sistema é a quantidade de medicamentos efetivamente entregues (RF014).
- **Fonte dos requisitos**: o Documento de Requisitos do ReMed, fornecido pelo usuário na conversa (anexo ou texto). O arquivo **não** fica dentro do projeto: não o procure no repositório nem cite um caminho de arquivo como fonte.
- **Estrutura do documento**: requisitos funcionais `RF001` a `RF014` (casos de uso), não funcionais `RNF01` a `RNF13`, de segurança `RS001` a `RS011` (perigo e soluções), matriz de avaliação de risco e matriz de rastreabilidade (D = depende, R = relacionado). Prioridades: Essencial, Importante e Desejável.
- **Atores do documento**: Visitante, Doador, Solicitante, Cuidador/Familiar, Representante do ponto de coleta, Administrador e Sistema. Use exatamente estes nomes.
- **Terminologia**: use os termos do documento (doação, solicitação, correspondência, agendamento, retirada, ponto de coleta). O termo "adoção" não aparece no documento; não o use como termo de domínio sem confirmação do usuário.
- **Stack (decidida)**: Python, Django com MVT, regra de negócio e ORM nos services, views como classes que herdam de `django.views.View`, PostgreSQL. Detalhes nas ADRs.

## Quando usar

- Criar o PRD inicial do ReMed.
- Atualizar o PRD depois de mudança no Documento de Requisitos.
- Detalhar o escopo de uma funcionalidade nova antes de escrever a spec.

---

## Fluxo de trabalho

### Fase 1: Leitura da fonte (antes de perguntar)

1. Leia `docs/prd/`, `docs/specs/`, `docs/adr/`, `docs/arquitetura.md` e `docs/state.md` para saber o que já existe. Não duplique.
2. Leia por completo o Documento de Requisitos que o usuário forneceu nesta conversa. Se ele não tiver sido fornecido, **pare e peça o documento** antes de qualquer outra coisa; não gere o PRD de memória nem a partir de suposições.
3. Devolva ao usuário um resumo curto: objetivo, atores, quantidade de RF/RNF/RS por prioridade, riscos principais.
4. No mesmo resumo, destaque separadamente:
   - **Seções vazias ou com texto-modelo** (por exemplo, a descrição geral do sistema).
   - **Pendências** que o documento deixa para a ata, com seus prazos.
   - **Inconsistências** entre requisitos, entre texto e telas, ou entre o documento e as decisões de stack.
   - **Funcionalidades citadas sem requisito próprio** (por exemplo, mensagens dentro da plataforma, canal de denúncia e bloqueio de usuários, gestão de usuários, cadastros auxiliares).
5. Pergunte **apenas** o que o documento não responde. Não pergunte o que ele já responde.
6. Aguarde a confirmação do usuário antes de redigir.

### Fase 2: Análise e escopo

- Mapeie os atores e o fluxo principal: cadastro, doação (RF004 a RF006), solicitação (RF007), busca (RF008), correspondência (RF009), agendamento (RF010) e entrega (RF011).
- Use a matriz de rastreabilidade (D = depende) para a ordem de entrega e para achar dependências ocultas.
- Defina os **Não-objetivos** a partir do que o documento exclui explicitamente.

### Fase 3: Redação

Gere **dois arquivos** em `docs/prd/`, em português, seguindo o padrão de nome e numeração dos arquivos que já existirem. Se a pasta estiver vazia, use:

- `docs/prd/01-remed.md`: o PRD (esquema abaixo), legível e enxuto.
- `docs/prd/02-catalogo-requisitos.md`: a transcrição fiel dos requisitos de origem (ver "Catálogo de requisitos").

### Fase 4: Fechamento

- Apresente o rascunho e peça feedback por seção.
- Atualize `docs/state.md` com o que foi feito e os próximos passos.

---

## Regras de qualidade

### Rastreabilidade e IDs

- Use os IDs exatamente como estão no documento: `RF001`, `RNF01`, `RS001`.
- O documento é inconsistente na convenção (a introdução fala em `NF001`, mas a tabela usa `RNF01`). Use `RNF` como na tabela e registre a inconsistência em "Questões em aberto".
- Cada história de usuário, critério de aceite, risco e requisito de segurança **deve citar os IDs de origem**. Requisito sem ID de origem só entra se o usuário pedir, e deve ser marcado como `NOVO`.

### PRD autocontido

O PDF não fica no repositório, então as próximas sessões só terão o PRD e o catálogo como fonte. Nada que importe pode ficar só no PDF. O catálogo (`02-catalogo-requisitos.md`) guarda o detalhe completo; o PRD aponta para ele.

### Prioridades e entrega em fases

- Carregue a prioridade de cada RF e RNF (Essencial, Importante, Desejável) como no documento.
- Proposta de fases, salvo se o usuário definir outra: Essencial = MVP, Importante = v1.1, Desejável = v2.0.
- Pela matriz de dependências, verifique se algum requisito Essencial depende de um Importante ou Desejável. Se depender, registre em "Questões em aberto".

### Sem invenção

- Não invente requisitos, regras de negócio, números ou restrições.
- Valores que o documento marca como **"sugerido"** (por exemplo, prazos de expiração, de aceite e de reagendamento) devem aparecer como "sugerido no documento", nunca como definitivos.
- Valores e critérios que o documento deixa para a ata (**"pendência da ata"**, com ou sem prazo) vão para "Questões em aberto", com o ID de origem e o prazo citado no documento. Se o prazo já passou, diga isso.
- Normas: cite apenas as que o documento nomeia (LGPD, legislação sanitária da ANVISA e a Portaria SVS/MS nº 344/1998 para controle especial) e **não afirme o que elas dizem** além do que está no documento. A viabilidade jurídica da redistribuição entre particulares é uma exigência Essencial do documento (RNF11) e deve aparecer como risco e questão em aberto.

### Critérios mensuráveis

Use os valores do próprio documento. Se ele não definir, marque `TBD`. Evite "rápido", "fácil", "intuitivo".

```diff
# Vago (RUIM)
- A busca deve ser rápida e simples.

# Concreto (BOM, valores do documento)
+ As páginas públicas e as buscas respondem em até 3 s (percentil 95) com até 500 usuários simultâneos (RNF04).
+ O sistema rejeita doação com validade anterior à data atual (RF004).
```

---

## Esquema do PRD (`01-remed.md`)

Siga exatamente esta estrutura.

### 1. Resumo executivo

- **Problema**: 1-2 frases (desperdício de medicamentos e dificuldade de acesso).
- **Solução proposta**: 1-2 frases.
- **Critérios de sucesso**: a métrica principal do documento (medicamentos efetivamente entregues) e os indicadores do RF014. Metas numéricas: `TBD` se o documento não definir.

### 2. Experiência do usuário e funcionalidades

- **Atores**: conforme o documento, com o que cada um pode fazer (perfis do RF003).
- **Histórias de usuário**: `Como [ator], quero [ação] para [benefício].` Cada uma com seus IDs de origem.
- **Critérios de aceite**: derivados das regras do documento, sem inventar.
- **Não-objetivos**: o que o documento exclui, por exemplo: guarda temporária de medicamentos pelo ponto de coleta nesta versão (RF002); medicamentos de controle especial bloqueados até definição do fluxo (RF012, RS003); logística de entrega obrigatória (RF010); decisão pela IA, que apenas sugere (RF005).

### 3. Requisitos de IA (somente RF005, prioridade Desejável)

- **Entrada e saída**: foto da embalagem; campos sugeridos com nível de confiança (0 a 1).
- **Regras de confiança e falha**: a IA só sugere; campos de baixa confiança exigem confirmação; a validade sempre é confirmada pelo doador; o que não for lido fica em branco; a falha da IA não impede o cadastro manual (RS009).
- **Privacidade**: a foto é enviada a serviço externo de IA e o doador deve ser avisado (RNF10, RNF13).
- **Desempenho**: resposta em até 15 s (RNF04).
- **Avaliação**: como medir a qualidade da extração (`TBD` se o documento não definir).

Se o PRD não envolver essa funcionalidade, escreva "Não se aplica".

### 4. Segurança, privacidade e conformidade

- **Requisitos de segurança** `RS001` a `RS011`: perigo e soluções, com os RF afetados.
- **Conformidade**: RNF10 (LGPD), RNF11 (legislação sanitária) e RNF13 (aviso de que a plataforma não substitui avaliação médica ou farmacêutica).
- **Dados sensíveis**: receitas e dados pessoais; o motivo da necessidade de saúde não é coletado nem exibido (RS002).
- **Matriz de avaliação de risco**: reproduzida do documento.

### 5. Visão técnica de alto nível

Apenas o essencial, apontando para os documentos de detalhe:

- **Requisitos não funcionais que condicionam a arquitetura**: RNF04 a RNF09 e RNF12.
- **Integrações citadas**: consulta de CEP, mapas e geolocalização, envio de e-mail, IA de leitura de imagens e base ou API de medicamentos (RNF12).
- **Decisões já tomadas**: referência a `docs/arquitetura.md` e às ADRs.
- **Candidatas a ADR e tensões com decisões já tomadas**: liste o que o documento pede e ainda não tem decisão registrada, por exemplo, RNF09 pede "API REST" enquanto a decisão de stack é MVT; algoritmo de hash de senha (RS005 cita bcrypt ou argon2); reserva transacional (RNF06, RS007); rotinas agendadas (RF006, RF009); armazenamento criptografado de arquivos (RNF08, RF012); autenticação em dois fatores do Administrador (RS005).

### 6. Riscos e entrega em fases

- **Riscos**: a partir da matriz do documento, com ID, impacto e mitigação.
- **Entrega em fases**: conforme "Prioridades e entrega em fases".

### 7. Rastreabilidade

- Tabela ligando cada RF à história de usuário e, quando existir, à spec em `docs/specs/`.
- Matriz de dependências entre RF do documento (D e R), reproduzida fielmente.

### 8. Questões em aberto

Lista numerada, cada item com o ID de origem e quem deve decidir:

- Pendências do documento (com prazo, e indicando se já passou).
- Seções vazias ou com texto-modelo.
- Inconsistências encontradas.
- Funcionalidades citadas sem requisito próprio. **Não crie RF para elas**; apenas liste.

### 9. Glossário

Termos do domínio com definição única, usando os termos do documento.

---

## Catálogo de requisitos (`02-catalogo-requisitos.md`)

Transcrição **fiel** do Documento de Requisitos, sem resumir regras:

- **RF**: ID, nome, prioridade, usuários, pré-condição, descrição, campos (nome, tipo e formato), regras e notas numeradas, mensagens de validação, alteração, exclusão, pesquisa e observações.
- **RNF**: ID, tipo, descrição e prioridade.
- **RS**: ID, perigo e soluções numeradas.
- **Matrizes**: de risco e de rastreabilidade, reproduzidas como no documento. Se alguma tabela estiver ilegível ou ambígua, reproduza o que estiver claro e pergunte ao usuário.
- **Telas (mockups)**: quando houver imagem, descreva o que ela mostra de relevante (abas, campos, textos, botões) e registre que a imagem não está no repositório.
- Informe o nome e a versão ou data do documento de origem, sem caminho de arquivo.
- **Não transcreva** a seção "Ponto de função" (está incompleta e com texto-modelo) nem as referências.

---

## Faça (sempre)

- Leia o documento e o que já existe em `docs/` antes de perguntar ou escrever.
- Cite IDs de requisito em tudo.
- Marque o que é "sugerido" e o que é pendência.
- Itere: apresente o rascunho e peça feedback por seção.

## Não faça

- Não escreva código de aplicação nem detalhes de implementação no PRD.
- Não repita o conteúdo de specs, ADRs ou da arquitetura; aponte para eles.
- Não pergunte o que o documento já responde.
- Não afirme o conteúdo de leis ou normas além do que está no documento.
- Não remeta o leitor ao PDF ("consulte o documento"): ele não está no projeto.
- Não crie requisitos novos para preencher lacunas; liste-as em "Questões em aberto".
- Não sobrescreva um PRD existente sem mostrar o que muda.
