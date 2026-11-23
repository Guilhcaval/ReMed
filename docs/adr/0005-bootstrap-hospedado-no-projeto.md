# 0005. Usar Bootstrap como base de CSS, hospedado no próprio projeto

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF07, RNF08, RNF01, RNF03

## Contexto

A interface precisa ser responsiva e mobile first nas duas últimas versões de Chrome, Edge, Firefox e Safari (RNF07). Ela também deve ter linguagem simples, mensagens claras e seguir a WCAG 2.1 nível AA (RNF01 a RNF03). O usuário pode estar em 3G/4G, com baixo consumo de dados (RNF08). As telas já desenhadas (cadastro de pessoa física, login e cadastro de ponto de coleta, em `docs/prd/telas/`) usam formulários, abas, alertas e botões comuns.

## Direcionadores da decisão

- Layout responsivo pronto (RNF07).
- Componentes de formulário, abas e alertas que cobrem as telas desenhadas.
- Nenhuma dependência de servidor externo para carregar a interface (RNF08).
- Velocidade de desenvolvimento para a equipe.

## Opções consideradas

1. Bootstrap com os arquivos servidos pelo próprio projeto.
2. Bootstrap carregado por CDN.
3. CSS próprio, sem framework.
4. Tailwind CSS.

## Decisão

Opção 1. Regras que passam a valer:

- Os arquivos do Bootstrap ficam em `static/` e são servidos pelo próprio projeto, sem CDN.
- A versão do Bootstrap é fixada quando ele for adicionado e registrada nas notas desta ADR.
- A identidade visual do ReMed é aplicada sobre o Bootstrap por estilos próprios do projeto, de preferência pelas variáveis do Bootstrap, sem estilos soltos espalhados nos templates.
- Outra biblioteca de CSS ou de ícones só entra com uma nova ADR.

## Consequências

- Positivas:
  - A grade responsiva e os componentes de formulário cobrem as telas desenhadas.
  - Sem origem externa, a página não depende de outro serviço estar no ar, e uma política de segurança de conteúdo (CSP) fica mais simples.
- Negativas e custos:
  - A atualização do Bootstrap é manual, inclusive para correções de segurança.
  - O Bootstrap não garante acessibilidade sozinho. Contraste, foco visível e rótulos precisam ser conferidos em cada tela (RNF03).
  - Os componentes interativos do Bootstrap (abas, menu recolhível) exigem o JavaScript dele (ADR 0006).
- Impacto em specs e arquitetura:
  - As specs de telas usam os componentes do Bootstrap sempre que possível.

## Como verificar

- Nenhum template carrega CSS ou JavaScript de domínio externo (buscar `https://` em `<link>` e `<script>`).
- A versão do Bootstrap está registrada nas notas desta ADR e corresponde aos arquivos em `static/`.
- Revisão de acessibilidade das telas conforme a WCAG 2.1 AA (RNF03).

## Notas

- **Versão do Bootstrap:** `5.3.9` (baixado do pacote oficial `bootstrap-5.3.9-dist.zip` em `https://github.com/twbs/bootstrap/releases/tag/v5.3.9`), arquivos `static/vendor/bootstrap/css/bootstrap.min.css` e `static/vendor/bootstrap/js/bootstrap.bundle.min.js`.
- JavaScript: [ADR 0006](0006-javascript-simples-sem-framework.md).
