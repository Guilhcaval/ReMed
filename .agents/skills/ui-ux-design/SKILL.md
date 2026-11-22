---
name: ui-ux-design
description: Projeta e revisa a interface (UI/UX) de aplicações web com visual moderno, minimalista e agradável, seguindo princípios de usabilidade e acessibilidade. Use sempre que for criar ou alterar templates, CSS, telas, formulários, componentes, mensagens de interface, navegação ou layout, ou quando o usuário pedir para "melhorar o visual", "revisar a UI", "corrigir o layout" ou "achar problemas de design", mesmo que ele não diga "design" explicitamente.
---

# UI/UX

Quando houver conflito, o documento de arquitetura, as ADRs e a spec da tela prevalecem sobre esta skill. Esta skill cuida da **aparência e da usabilidade**; ela nunca muda regra de negócio. Se uma melhoria de design exigir mudar comportamento, isso vira alteração de spec.

## Contexto: descubra antes de desenhar

Antes de projetar ou revisar, levante com o PRD, as specs e o usuário:

- **Produto e tom**: o que o sistema faz e que sensação deve transmitir (confiança, leveza, seriedade).
- **Público**: familiaridade com tecnologia, idade, idioma, dispositivos e qualidade de conexão.
- **Requisitos que condicionam o design**: acessibilidade (por exemplo, WCAG 2.1 AA), desempenho, navegadores e dispositivos suportados, linguagem simples, mensagens de erro definidas.
- **Tecnologia de front-end**: o que o projeto já usa. Não adicione framework de CSS, biblioteca de componentes, framework JavaScript nem ícones externos sem ADR `aceita`. Siga o que a arquitetura definir.

## Identidade visual

- Se existir identidade visual (mockups, guia de marca, CSS atual), **siga-a**. Extraia dela cores, tipografia e estilo de componentes.
- Se os valores exatos não existirem, **proponha** uma paleta de 4 a 6 tokens nomeados e **peça confirmação** antes de aplicar. Nunca invente a identidade visual em silêncio.
- Uma única cor de destaque. A cor semântica (sucesso, aviso, erro, informação) tem papel próprio e nunca é decorativa.

## Princípios de design

1. **Minimalismo com função**: cada elemento existe para ajudar o usuário a entender ou agir. Corte o que for decoração.
2. **Hierarquia clara**: uma ação principal por tela, bem visível; ações secundárias discretas.
3. **Espaço em branco generoso**: agrupe por proximidade, separe por espaço antes de usar linhas ou caixas.
4. **Consistência**: o mesmo componente se parece e se comporta igual em todo o sistema. Uma ação mantém o mesmo nome em todo o fluxo.
5. **Ousadia em um só lugar**: deixe um elemento ser o mais marcante da tela e mantenha o resto quieto.
6. **Confiança**: em domínios sensíveis (saúde, dinheiro, dados pessoais), priorize clareza e avisos visíveis, sem visual "chamativo".

### Evite

- Gradientes decorativos, sombras em tudo, cartões idênticos para qualquer conteúdo e o mesmo raio de borda em todos os elementos sem relação com a hierarquia.
- Rótulos em caixa alta acima de todo título, numeração de passos quando o conteúdo não é uma sequência, ícones sem texto em ações importantes.
- Animações de entrada em cada seção e efeitos em todo `hover`.
- Mais de duas famílias de fonte.

## Design tokens

Centralize em **um** arquivo CSS, com variáveis (`:root`), e use só os tokens no restante do CSS. Nada de cores, tamanhos ou espaçamentos soltos.

- **Cores**: primária, texto, texto secundário, fundo, superfície, borda, e as semânticas (sucesso, aviso, erro, informação), cada uma com par fundo e texto que atenda ao contraste.
- **Tipografia**: fontes do sistema ou uma única família hospedada no projeto (evita requisições externas e economiza dados). Tamanho base de pelo menos 16 px, altura de linha em torno de 1,5, linhas de texto com no máximo cerca de 75 caracteres. Escala de tamanhos definida (base, grande, título 1, título 2).
- **Espaçamento**: escala fixa (por exemplo, múltiplos de 4 ou 8 px).
- **Forma**: raios de borda e sombras em poucos níveis, ligados à hierarquia.
- **Camadas** (`z-index`): poucos níveis nomeados.
- **Pontos de quebra**: definidos como tokens.

> **Nota:** se o projeto usa um framework de CSS (por exemplo, Bootstrap), personalize por tokens e use os componentes dele, em vez de criar componentes próprios ou estilos soltos.

## Regras de usabilidade

Aplique as heurísticas de Nielsen:

1. **Visibilidade do estado do sistema**: mostre carregando, salvo, erro e sucesso.
2. **Linguagem do usuário**: termos do domínio, sem jargão técnico. Explique termos difíceis com dica ou glossário.
3. **Controle e liberdade**: dá para voltar, cancelar e corrigir.
4. **Consistência e padrões**.
5. **Prevenção de erros**: campos com o tipo certo, máscaras, validação ao sair do campo e confirmação antes de ações irreversíveis.
6. **Reconhecer em vez de lembrar**: opções visíveis, valores padrão sensatos, preenchimento automático (por exemplo, endereço pelo CEP).
7. **Eficiência**: poucos passos, atalhos de teclado nativos.
8. **Design estético e minimalista**.
9. **Ajudar a reconhecer e corrigir erros**: diga o que houve e como resolver.
10. **Ajuda e documentação**: ajuda contextual onde o usuário costuma travar.

Também: ações frequentes ao alcance do polegar no celular, poucas opções por tela, agrupamento de campos longos em seções.

## Padrões de interface

### Formulários

- Rótulo **sempre visível** acima do campo (o texto de exemplo não substitui o rótulo). Marque os obrigatórios e mostre o texto de ajuda quando o formato não for óbvio.
- Agrupe em seções com título.
- Use os tipos e atributos certos (`type`, `inputmode`, `autocomplete`).
- Mensagens de validação junto do campo e, quando houver vários erros, um resumo no topo. Use os textos definidos nos requisitos.
- Ao errar, **mantenha o que o usuário digitou**.
- Senha com opção "Mostrar" e a regra à vista.
- Envio de arquivo com formato e tamanho aceitos informados, pré-visualização e erro claro.
- Um único botão primário por formulário, com texto que diz o que acontece ("Cadastrar pedido"), não "Enviar".

### Estados de tela

Toda tela de dados define: carregando, vazio, erro e sucesso. O estado vazio convida a agir.

### Status e etiquetas

Status de entidades (pedido, solicitação, agendamento etc.) aparecem como etiqueta com **texto e cor**, nunca só cor, usando os nomes exatos definidos nos requisitos.

### Busca e listas

Filtros claros, resultados paginados, ordenação previsível, e cada item mostrando só o que ajuda a decidir. Nunca exiba dados que o perfil não pode ver.

### Informações críticas

- Avisos de responsabilidade exigidos pelo domínio ficam visíveis e sem ruído nas telas indicadas.
- Dados sugeridos por IA aparecem **identificados como sugestão**, editáveis, com campos de baixa confiança destacados.
- Ações irreversíveis ou de risco (cancelar, excluir, encerrar conta) pedem confirmação com texto claro sobre a consequência.

### Navegação

Simples e igual para o mesmo perfil. Mostre ao usuário só o que o perfil dele pode fazer. A interface nunca é a única barreira de permissão: o service confere.

## Acessibilidade (WCAG 2.1 AA, salvo outra meta do projeto)

- HTML semântico: `lang` correto, marcos (`header`, `nav`, `main`, `footer`), títulos em ordem, listas e tabelas reais.
- Contraste mínimo de 4,5:1 para texto comum e 3:1 para texto grande, ícones e bordas de componentes. Verifique os pares do tema.
- **Foco visível** em todo elemento interativo e navegação completa por teclado, com ordem lógica e link para pular ao conteúdo.
- Não dependa só de cor para transmitir informação (status, erro, obrigatório).
- Todo campo com rótulo associado. Erros ligados ao campo (`aria-describedby`) e anunciados (`aria-live`).
- Texto alternativo em imagens com significado, e vazio em imagens decorativas.
- Alvos de toque com pelo menos 44 px.
- Ampliação a 200% sem perda de conteúdo. Respeite `prefers-reduced-motion`.

## Responsivo e desempenho

- **Mobile first**: projete a partir de 375 px e amplie.
- Sem rolagem horizontal. Imagens e tabelas se adaptam à largura.
- CSS enxuto, JavaScript mínimo e com melhoria progressiva: o fluxo principal funciona sem depender dele.
- Imagens otimizadas, com dimensões declaradas e carregamento tardio quando fora da tela. Nada de fontes ou scripts externos desnecessários.

## Movimento

Só quando ajuda: confirmar uma ação, mostrar o que mudou, indicar carregamento. Duração curta, sem animação decorativa nem de entrada automática, e desligada com `prefers-reduced-motion`.

## Texto da interface

- Linguagem simples, voz ativa, frases curtas, sem jargão técnico.
- Botões dizem o que acontece. A mesma ação mantém o mesmo nome no fluxo inteiro, inclusive na mensagem de sucesso.
- Erros explicam **o que houve e como corrigir**; não pedem desculpa nem culpam o usuário.
- Estados vazios convidam a agir.
- Use as mensagens literais dos requisitos quando existirem. Não invente texto que a documentação já define.

---

## Modos de trabalho

### A) Projetar (tela nova ou redesenho)

1. Leia a spec da tela (campos, mensagens, perfis) e as skills de framework e de segurança. Se a spec não existir, peça-a antes.
2. Na primeira tela do projeto, ou se não houver tokens ainda, faça um **plano de design curto**: paleta (tokens), tipografia, escala de espaçamento e conceito de layout em uma frase mais um **wireframe em ASCII** (mobile e desktop). Apresente ao usuário e **aguarde a confirmação**.
3. Crie ou atualize primeiro os **tokens** e os componentes base (botão, campo, aviso, etiqueta, cartão). Depois monte as telas **só com esses componentes**.
4. Implemente nos templates e no CSS do projeto, sem lógica de negócio nos templates.
5. Revise (modo B) antes de concluir.

### B) Revisar e corrigir (tela existente)

Se houver automação de navegador disponível (por exemplo, Playwright, ou o navegador do próprio agente), use-a; se não houver, revise lendo templates e CSS e **diga ao usuário que não foi possível verificar visualmente**.

1. **Coleta**: pergunte a URL (por exemplo, `http://localhost:8000`) se não vier. Confirme o escopo (telas específicas ou todas).
2. **Inspeção**: navegue, capture tela e estrutura da página, e teste em 375 px (celular), 768 px (tablet), 1280 px (computador) e 1920 px (tela larga). Percorra o checklist abaixo.
3. **Priorização**:
   - **P1**: problema que impede ou prejudica a função (conteúdo cortado, sobreposição, quebra no celular, falta de contraste ou de foco, rótulo ausente, dado que não deveria aparecer);
   - **P2**: degrada a experiência (espaçamento, alinhamento, inconsistência de componentes);
   - **P3**: refino visual.
4. **Correção**: ache o arquivo de origem (template ou CSS), faça a **mudança mínima**, siga os padrões existentes e os tokens, e corrija **um problema por vez**, verificando cada um. Salve a captura antes de corrigir.
5. **Reverificação**: recarregue, compare antes e depois e confira que nada quebrou nos outros tamanhos e telas.
6. **Limite**: se um problema exigir mais de 3 tentativas, consulte o usuário. Mudança grande ou que fuja do escopo da spec também pede confirmação.

### Checklist de inspeção

- **Layout**: conteúdo transbordando, sobreposição, alinhamento, espaçamento fora da escala, texto cortado.
- **Responsivo**: quebra em tela pequena, rolagem horizontal, alvos de toque pequenos, transições estranhas entre tamanhos.
- **Acessibilidade**: contraste, foco visível, teclado, rótulos, texto alternativo, cor como única informação, mensagens de erro ligadas ao campo.
- **Consistência**: fontes, cores fora dos tokens, componentes iguais com aparências diferentes, nomes de ação inconsistentes.
- **Conteúdo**: mensagens literais dos requisitos, avisos exigidos pelo domínio nas telas indicadas, nenhum dado de outro usuário que o perfil não deveria ver.
- **Desempenho**: imagens pesadas, fontes e scripts externos, CSS e JS desnecessários.

### Relatório da revisão

```markdown
# Revisão de design

## Resumo
- Telas revisadas: ...
- Tamanhos testados: ...
- Problemas encontrados: N | corrigidos: M

## Problemas
### [P1] Título
- Tela: ...
- Elemento: ...
- Problema: ...
- Arquivo corrigido: `caminho`
- Correção: ...

## Não corrigidos
- Título: motivo e recomendação

## Recomendações
- ...
```

---

## Faça (sempre)

- Leia a spec e os tokens antes de desenhar ou mudar a interface.
- Use só os tokens e os componentes base.
- Teste em celular primeiro.
- Confirme com o usuário a identidade visual e mudanças grandes.

## Não faça

- Não coloque regra de negócio, consulta ou decisão de permissão em template.
- Não adicione biblioteca ou framework visual sem ADR.
- Não invente identidade visual, textos que a documentação já define ou dados sensíveis na tela.
- Não faça refatoração grande sem confirmar.
- Não corrija vários problemas de uma vez, porque fica difícil verificar.
- Não deixe a interface ser a única barreira de segurança.
