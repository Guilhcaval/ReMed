---
name: spec
description: 'Cria e atualiza as especificações (specs) das funcionalidades do ReMed em docs/specs/, a partir do PRD e do catálogo de requisitos. Use SEMPRE que o usuário pedir para escrever, criar, revisar ou atualizar uma spec ou especificação, detalhar uma funcionalidade ou requisito (RFxxx) antes de implementar, ou quando for preciso saber exatamente o que construir para um caso de uso, mesmo que ele não diga "spec" explicitamente.'
license: MIT
---

# Especificações (specs) do ReMed

## Visão geral

Uma spec descreve **exatamente o que construir** para uma funcionalidade, com detalhe suficiente para implementar e testar sem consultar o documento de requisitos original. O PRD (`docs/prd/`) diz o quê e por quê; a spec diz as regras, os dados, os fluxos e a divisão entre camadas; as ADRs (`docs/adr/`) dizem as decisões de arquitetura. A spec **não contém código de aplicação**.

## Contexto

- **Projeto**: ReMed, plataforma web de doação e redistribuição de medicamentos não vencidos.
- **Fontes, nesta ordem**: `docs/prd/01-remed.md`, `docs/prd/02-catalogo-requisitos.md` (transcrição fiel dos RF, RNF e RS), `docs/arquitetura.md` e as ADRs. O PDF original **não** fica no repositório.
- **Arquitetura (decidida)**: Django com MVT; regra de negócio e ORM nos **services**; views como classes que herdam de `django.views.View`, implementando só os métodos HTTP necessários (mixins de acesso, como `LoginRequiredMixin`, são permitidos); services não recebem `request` nem retornam `HttpResponse`; PostgreSQL.
- **Terminologia**: use os termos e os atores do documento (doação, solicitação, correspondência, agendamento, retirada, ponto de coleta; Visitante, Doador, Solicitante, Cuidador/Familiar, Representante do ponto de coleta, Administrador, Sistema).

## Quando usar

- Criar a spec de um ou mais requisitos funcionais (`RFxxx`).
- Atualizar uma spec depois de mudança no PRD ou no catálogo.
- Antes de qualquer implementação de funcionalidade que ainda não tenha spec.

---

## Fluxo de trabalho

### Fase 1: Leitura (antes de escrever)

1. Leia `AGENTS.md`, `docs/state.md`, `docs/arquitetura.md`, as ADRs e as specs já existentes.
2. Leia o PRD e o catálogo de requisitos. Se o catálogo não existir ou não tiver o detalhe necessário (campos, regras, mensagens, status), **pare e peça ao usuário o Documento de Requisitos**; não complete de memória.
3. Identifique os requisitos a especificar e suas dependências (matriz D/R, no PRD e no catálogo).

### Fase 2: Plano de specs

1. Proponha a lista de specs: uma por funcionalidade, normalmente uma por RF. Só agrupe RFs quando forem inseparáveis (por exemplo, quando um depende do outro para fazer sentido), explicando o motivo.
2. Ordene pela **ordem de implementação**: dependências primeiro (D na matriz), depois prioridade (Essencial, Importante, Desejável). A numeração dos arquivos segue essa ordem.
3. Se houver preocupações que atravessam vários RF e não têm requisito próprio (histórico e auditoria, notificações, rotinas agendadas, cadastros auxiliares), proponha **specs transversais**, marcadas como `NOVO` e justificadas pelos RF que as exigem. Só as crie se o usuário aprovar.
4. Apresente a lista e **aguarde a confirmação** antes de escrever.

### Fase 3: Redação

Gere uma spec por arquivo em `docs/specs/`, em português, seguindo o padrão de nome e numeração dos arquivos existentes. Se a pasta estiver vazia, use `NN-nome-em-kebab-case.md` (por exemplo, `01-cadastro-de-usuario.md`), com `NN` na ordem de implementação.

### Fase 4: Fechamento

- Atualize a tabela de rastreabilidade do PRD (RF -> história -> spec).
- Atualize `docs/state.md` com o que foi feito e os próximos passos.

---

## Esquema obrigatório de cada spec

### 1. Cabeçalho

- Número e título.
- Status: `rascunho`, `aprovada` ou `implementada`.
- Requisitos de origem: RF, RNF e RS, com a prioridade.
- Dependências: specs que precisam existir antes.
- ADRs relacionadas.

### 2. Objetivo e escopo

O que a funcionalidade entrega, o que **inclui** e o que **não inclui**. Os "não inclui" vêm das exclusões do documento.

### 3. Atores e pré-condições

Quem executa, com qual perfil, e o que precisa ser verdade antes (conforme o documento).

### 4. Fluxos

Numerados: fluxo principal, fluxos alternativos e fluxos de exceção. Inclua as rotinas automáticas do Sistema quando houver (por exemplo, a rotina diária de validade).

### 5. Regras de negócio

Lista identificada `RN-<spec>-NN`. Cada regra cita a nota ou o item de origem no catálogo (por exemplo, "RF004, nota 3"). Reproduza as regras com fidelidade; não resuma a ponto de perder condições.

### 6. Modelo de dados lógico

- Entidades e campos: nome, tipo, formato, obrigatório, tamanho, validações e unicidade (CPF, CNPJ, e-mail).
- **Status e transições**: liste todos os status do documento e as transições permitidas (tabela de origem -> destino -> condição -> quem dispara).
- **Histórico**: onde o documento exige registro de quem, o quê, data e hora.
- Nível lógico: não escreva código de models; descreva o que precisa existir. Aponte restrições que o PostgreSQL deve garantir (unicidade, integridade, transações).

### 7. Divisão por camadas

- **Views** (classes `View`): nome, métodos HTTP, perfis com permissão, e o que cada uma faz sem conter regra de negócio.
- **Services**: operações com entradas e saídas (sem `request` e sem `HttpResponse`), regras que aplicam, e quais precisam ser **transacionais** (RNF06, RS007).
- **Templates e telas**: o que cada tela exibe, campos, ações e mensagens. Se o catálogo descrever mockups, use essa descrição.
- **URLs**: rotas previstas, só o nome e o propósito.

### 8. Mensagens e validações

Textos literais do documento (por exemplo, "CPF já cadastrado"), com a condição que dispara cada um. Não reescreva as mensagens.

### 9. Segurança e privacidade

RS aplicáveis (perigo e solução), dados sensíveis envolvidos, o que nunca pode ser exibido a outros perfis, criptografia e registro de acessos exigidos.

### 10. Requisitos não funcionais aplicáveis

RNF que afetam esta spec, com os valores do documento (desempenho, acessibilidade, transacionalidade etc.).

### 11. Critérios de aceite

Lista numerada e **testável**, no formato "Dado ... quando ... então ...". Cada critério cita a regra ou o requisito de origem. Inclua os casos de erro e os limites (validade vencida, CPF duplicado, tentativas de login etc.).

### 12. Plano de testes

Casos de teste por camada: testes de unidade dos services (sem `request`), testes de integração das views, e os casos de permissão por perfil. Só os casos, sem código.

### 13. Questões em aberto

Pendências da ata (com prazo e se já passou), valores "sugeridos" ainda não definidos, inconsistências e dependências de decisões. Itens `TBD` devem aparecer aqui.

---

## Regras de qualidade

- **Fidelidade**: campos, tamanhos, formatos, status, mensagens e prazos vêm do catálogo. Em caso de dúvida, pergunte.
- **Sem invenção**: não crie regras, campos, telas ou números que não estejam no catálogo. Valores "sugeridos" ficam como "sugerido no documento" e pendência de decisão; valores deixados para a ata ficam `TBD`.
- **Rastreabilidade**: toda regra e todo critério citam o ID de origem; o que não tiver origem leva a marca `NOVO` e deve ser aprovado pelo usuário.
- **Camadas**: nunca coloque regra de negócio na view nem no template. Toda regra e toda consulta ao ORM ficam nos services.
- **Concorrência e consistência**: reserva, agendamento e entrega (RF009 a RF011) devem ser descritos como operações transacionais, sem permitir reserva dupla (RNF06, RS007).
- **Segurança**: toda spec lista os RS aplicáveis; dados sensíveis (receitas, dados pessoais) seguem o PRD.
- **Normas**: cite apenas as que o documento nomeia e não afirme seu conteúdo além do que o documento diz.
- **Consistência entre specs**: referencie outras specs pelo número; não repita regras que já estão em outra spec.

## Faça (sempre)

- Leia as ADRs e a arquitetura antes de escrever.
- Preserve a ordem de implementação na numeração.
- Apresente o plano de specs e o rascunho para confirmação.

## Não faça

- Não escreva código de aplicação (models, views, services, templates).
- Não remeta o leitor ao PDF: ele não está no projeto.
- Não decida pendências da ata; registre-as.
- Não crie RF novo para lacunas do documento; registre-as como questão em aberto.
- Não sobrescreva uma spec existente sem mostrar o que muda.
