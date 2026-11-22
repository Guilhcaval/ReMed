---
name: spec
description: 'Cria e atualiza especificações (specs) de funcionalidades de qualquer projeto de software, normalmente em docs/specs/, a partir do PRD e dos requisitos. Use SEMPRE que o usuário pedir para escrever, criar, revisar ou atualizar uma spec ou especificação, detalhar uma funcionalidade ou requisito antes de implementar, descrever fluxos, regras de negócio, modelo de dados, critérios de aceite ou plano de testes, ou quando for preciso saber exatamente o que construir para um caso de uso, mesmo que ele não diga "spec" explicitamente.'
license: MIT
---

# Especificações (specs)

## Visão geral

Uma spec descreve **exatamente o que construir** para uma funcionalidade, com detalhe suficiente para implementar e testar sem voltar ao documento de requisitos original. O PRD diz o quê e por quê; a spec diz as regras, os dados, os fluxos e a divisão entre camadas; as ADRs dizem as decisões de arquitetura. A spec **não contém código de aplicação**.

## Quando usar

- Criar a spec de um ou mais requisitos funcionais.
- Atualizar uma spec depois de mudança no PRD ou nos requisitos.
- Antes de qualquer implementação de funcionalidade que ainda não tenha spec.

---

## Fluxo de trabalho

### Fase 1: Leitura (antes de escrever)

1. Leia, nesta ordem: PRD, catálogo ou fonte dos requisitos, documento de arquitetura, ADRs, specs já existentes e arquivo de estado do projeto (se houver).
2. Se a fonte não tiver o detalhe necessário (campos, regras, mensagens, status), **pare e peça ao usuário**; não complete de memória.
3. Identifique os requisitos a especificar e suas dependências (matriz de dependências, se existir).

### Fase 2: Plano de specs

1. Proponha a lista de specs: uma por funcionalidade, normalmente uma por requisito funcional. Só agrupe quando forem inseparáveis, explicando o motivo.
2. Ordene pela **ordem de implementação**: dependências primeiro, depois prioridade. A numeração dos arquivos segue essa ordem.
3. Se houver preocupações que atravessam várias funcionalidades e não têm requisito próprio (histórico e auditoria, notificações, rotinas agendadas, cadastros auxiliares), proponha **specs transversais**, marcadas como `NOVO` e justificadas pelos requisitos que as exigem. Só as crie se o usuário aprovar.
4. Apresente a lista e **aguarde a confirmação** antes de escrever.

### Fase 3: Redação

Gere uma spec por arquivo em `docs/specs/`, no idioma do projeto, seguindo o padrão de nome e numeração existente. Se a pasta estiver vazia, use `NN-nome-em-kebab-case.md` (por exemplo, `01-cadastro-de-usuario.md`), com `NN` na ordem de implementação.

### Fase 4: Fechamento

- Atualize a tabela de rastreabilidade do PRD (requisito, história, spec).
- Atualize o arquivo de estado do projeto com o que foi feito e os próximos passos.

---

## Esquema obrigatório de cada spec

### 1. Cabeçalho

- Número e título.
- Status: `rascunho`, `aprovada` ou `implementada`.
- Requisitos de origem (funcionais, não funcionais e de segurança), com a prioridade.
- Dependências: specs que precisam existir antes.
- ADRs relacionadas.

### 2. Objetivo e escopo

O que a funcionalidade entrega, o que **inclui** e o que **não inclui**. Os "não inclui" vêm das exclusões da fonte.

### 3. Atores e pré-condições

Quem executa, com qual perfil, e o que precisa ser verdade antes.

### 4. Fluxos

Numerados: fluxo principal, fluxos alternativos e fluxos de exceção. Inclua as rotinas automáticas do sistema quando houver.

### 5. Regras de negócio

Lista identificada `RN-<spec>-NN`. Cada regra cita a nota ou o item de origem (por exemplo, "RF004, nota 3"). Reproduza as regras com fidelidade; não resuma a ponto de perder condições.

### 6. Modelo de dados lógico

- Entidades e campos: nome, tipo, formato, obrigatório, tamanho, validações e unicidade.
- **Status e transições**: liste todos os status e as transições permitidas (tabela de origem, destino, condição, quem dispara).
- **Histórico**: onde a fonte exige registro de quem, o quê, data e hora.
- Nível lógico: não escreva código de models; descreva o que precisa existir. Aponte restrições que o banco deve garantir (unicidade, integridade, transações).

### 7. Divisão por camadas

Siga a arquitetura definida no projeto. Descreva, sem código:

- **Camada de entrada** (views, controllers, endpoints): nome, métodos, perfis com permissão, e o que cada uma faz sem conter regra de negócio.
- **Camada de regra de negócio** (services, casos de uso): operações com entradas e saídas, regras que aplicam e quais precisam ser **transacionais**.
- **Interface** (templates, telas): o que cada tela exibe, campos, ações e mensagens. Se a fonte descrever mockups, use essa descrição.
- **Rotas**: só o nome e o propósito.

### 8. Mensagens e validações

Textos literais da fonte (por exemplo, "CPF já cadastrado"), com a condição que dispara cada um. Não reescreva as mensagens.

### 9. Segurança e privacidade

Requisitos de segurança aplicáveis (perigo e solução), dados sensíveis envolvidos, o que nunca pode ser exibido a outros perfis, criptografia e registro de acessos exigidos.

### 10. Requisitos não funcionais aplicáveis

Os que afetam esta spec, com os valores da fonte (desempenho, acessibilidade, transacionalidade etc.).

### 11. Critérios de aceite

Lista numerada e **testável**, no formato "Dado ... quando ... então ...". Cada critério cita a regra ou o requisito de origem. Inclua casos de erro e limites (data vencida, valor duplicado, tentativas no limite).

### 12. Plano de testes

Casos de teste por camada: unidade das regras de negócio (sem depender de requisição HTTP), integração das rotas e casos de permissão por perfil. Só os casos, sem código.

### 13. Questões em aberto

Pendências da fonte (com prazo e se já passou), valores "sugeridos" ainda não definidos, inconsistências e dependências de decisões. Itens `TBD` aparecem aqui.

---

## Regras de qualidade

- **Fidelidade**: campos, tamanhos, formatos, status, mensagens e prazos vêm da fonte. Em dúvida, pergunte.
- **Sem invenção**: não crie regras, campos, telas ou números que a fonte não tenha. Valores "sugeridos" ficam marcados como sugeridos e pendentes de decisão; valores deixados para decisão posterior ficam `TBD`.
- **Rastreabilidade**: toda regra e todo critério citam o ID de origem; o que não tiver origem leva a marca `NOVO` e deve ser aprovado pelo usuário.
- **Camadas**: nunca coloque regra de negócio na camada de entrada nem na interface.
- **Concorrência e consistência**: operações que disputam o mesmo recurso (reserva, estoque, agendamento) são descritas como transacionais, sem permitir duplicidade.
- **Segurança**: toda spec lista os requisitos de segurança aplicáveis; dados sensíveis seguem o PRD.
- **Normas**: cite apenas as que a fonte nomeia e não afirme seu conteúdo além dela.
- **Consistência entre specs**: referencie outras specs pelo número; não repita regras que já estão em outra.

## Faça (sempre)

- Leia as ADRs e a arquitetura antes de escrever.
- Preserve a ordem de implementação na numeração.
- Apresente o plano de specs e o rascunho para confirmação.

## Não faça

- Não escreva código de aplicação (models, views, services, templates).
- Não remeta o leitor a uma fonte que não está no projeto.
- Não decida pendências; registre-as.
- Não crie requisito novo para lacunas da fonte; registre-as como questão em aberto.
- Não sobrescreva uma spec existente sem mostrar o que muda.
