---
name: ui-ux-design
description: Projeta e revisa a interface do ReMed (UI/UX) com visual moderno, minimalista e agradável, seguindo princípios de usabilidade e acessibilidade. Use sempre que for criar ou alterar templates, CSS, telas, formulários, componentes, mensagens de interface, navegação ou layout, ou quando o usuário pedir para "melhorar o visual", "revisar a UI", "corrigir o layout" ou "achar problemas de design", mesmo que ele não diga "design" explicitamente.
---

# UI/UX do ReMed

Quando houver conflito, `docs/arquitetura.md`, as ADRs e a spec da tela prevalecem sobre esta skill. Esta skill cuida da **aparência e da usabilidade**; ela nunca muda regra de negócio. Se uma melhoria de design exigir mudar comportamento, isso vira alteração de spec.

## Contexto do produto

- **ReMed**: plataforma web de doação e redistribuição de medicamentos não vencidos. A interface lida com saúde, dados pessoais e encontros presenciais, então precisa transmitir **confiança, clareza e cuidado**.
- **Público**: inclui pessoas com pouca familiaridade com tecnologia (RNF01) e usuários em celular com conexão 3G ou 4G e baixo consumo de dados (RNF08).
- **Requisitos que condicionam o design** (catálogo em `docs/prd/02-catalogo-requisitos.md`):
  - interface intuitiva, linguagem simples, dicas nos botões, botões de ajuda e glossário (RNF01);
  - mensagens de erro claras, com o motivo e como corrigir (RNF02);
  - acessibilidade **WCAG 2.1 nível AA**: contraste, navegação por teclado e texto alternativo (RNF03);
  - aplicação web responsiva, **mobile first**, nas duas últimas versões de Chrome, Edge, Firefox e Safari, em computadores, Android e iOS (RNF07);
  - páginas públicas e buscas respondendo em até 3 s no percentil 95 (RNF04).
- **Tecnologia**: o front é renderizado pelo Django (templates, MVT). Não adicione framework de CSS, biblioteca de componentes, framework JavaScript nem ícones externos sem ADR `aceita`. Siga o que `docs/arquitetura.md` definir para CSS.

## Identidade visual

- A identidade vem dos **mockups do documento** (cadastro, ponto de coleta e login), descritos no catálogo: cartão centralizado sobre fundo claro, logotipo com cruz verde e o nome "ReMed", slogan "Conectando cuidado, compartilhando saúde", botão primário em azul escuro, avisos informativos em verde claro, campos com rótulo e texto de ajuda, abas "Pessoa Física" e "Pessoa Jurídica".
- Os valores exatos (hex) não estão no documento. Se não existirem em `docs/` ou no CSS, **proponha** uma paleta de 4 a 6 tokens nomeados, derivada dos mockups, e **peça confirmação** antes de aplicar. Nunca invente a identidade visual em silêncio.
- Uma única cor de destaque. A cor semântica (sucesso, aviso, erro, informação) tem papel próprio e nunca é decorativa.

## Princípios de design

1. **Minimalismo com função**: cada elemento existe para ajudar o usuário a entender ou agir. Corte o que for decoração.
2. **Hierarquia clara**: uma ação principal por tela, bem visível; ações secundárias discretas.
3. **Espaço em branco generoso**: agrupe por proximidade, separe por espaço antes de usar linhas ou caixas.
4. **Consistência**: o mesmo componente se parece e se comporta igual em todo o sistema. Uma ação mantém o mesmo nome em todo o fluxo.
5. **Ousadia em um só lugar**: deixe um elemento ser o mais marcante da tela e mantenha o resto quieto.
6. **Confiança**: informações de saúde e de encontro exigem clareza, avisos visíveis e nenhum visual "chamativo".

### Evite

- Gradientes decorativos, sombras em tudo, cartões idênticos para qualquer conteúdo e o mesmo raio de borda em todos os elementos sem relação com a hierarquia.
- Rótulos em caixa alta acima de todo título, numeração de passos quando o conteúdo não é uma sequência, ícones sem texto em ações importantes.
- Animações de entrada em cada seção e efeitos em todo `hover`.
- Mais de duas famílias de fonte.

## Design tokens

Centralize em **um** arquivo CSS, com variáveis (`:root`), e use só os tokens no restante do CSS. Nada de cores, tamanhos ou espaçamentos soltos.

- **Cores**: primária, texto, texto secundário, fundo, superfície, borda, e as semânticas (sucesso, aviso, erro, informação), cada uma com par fundo e texto que atenda ao contraste.
- **Tipografia**: fontes do sistema ou uma única família hospedada no projeto (evita requisições externas e economiza dados, RNF08). Tamanho base de pelo menos 16 px, altura de linha em torno de 1,5, linhas de texto com no máximo cerca de 75 caracteres. Escala de tamanhos definida (por exemplo, base, grande, título 1, título 2).
- **Espaçamento**: escala fixa (por exemplo, múltiplos de 4 ou 8 px).
- **Forma**: raios de borda e sombras em poucos níveis, ligados à hierarquia.
- **Camadas** (`z-index`): poucos níveis nomeados.

## Regras de usabilidade

Aplique as heurísticas de Nielsen:

1. **Visibilidade do estado do sistema**: mostre carregando, salvo, erro e sucesso.
2. **Linguagem do usuário**: termos do documento (doação, solicitação, ponto de coleta), sem jargão técnico. Explique "princípio ativo", "validade" e "receita" com dica ou glossário (RNF01).
3. **Controle e liberdade**: dá para voltar, cancelar e corrigir.
4. **Consistência e padrões**.
5. **Prevenção de erros**: campos com o tipo certo, máscaras, validação ao sair do campo e confirmação antes de ações irreversíveis.
6. **Reconhecer em vez de lembrar**: opções visíveis, valores padrão sensatos, CEP preenchendo o endereço.
7. **Eficiência**: poucos passos, atalhos de teclado nativos.
8. **Design estético e minimalista**.
9. **Ajudar a reconhecer e corrigir erros**: diga o que houve e como resolver.
10. **Ajuda e documentação**: botões de ajuda e glossário (RNF01).

Também: ações frequentes ao alcance do polegar no celular, poucas opções por tela, agrupamento de campos longos em seções.

## Padrões de interface do ReMed

### Formulários (cadastros, doação, solicitação)

- Rótulo **sempre visível** acima do campo (o texto de exemplo não substitui o rótulo). Marque os obrigatórios e mostre o texto de ajuda (por exemplo, "Informe um CPF válido e ainda não cadastrado").
- Agrupe em seções com título (por exemplo, "Dados pessoais", "Como você quer usar o ReMed?", "Seu endereço").
- Use os tipos e atributos certos (`type`, `inputmode`, `autocomplete`) e preencha o endereço pelo CEP.
- Mensagens de validação **literais do catálogo** ("Campo(s) obrigatório(s) não preenchido(s)", "CPF já cadastrado"), junto do campo e de um resumo no topo quando houver vários.
- Ao errar, **mantenha o que o usuário digitou**.
- Senha com opção "Mostrar" e a regra (mínimo de 8 caracteres) à vista.
- Envio de arquivo (foto da embalagem, receita) com formato e tamanho aceitos informados (até 5 MB), pré-visualização e erro claro.
- Um único botão primário por formulário, com texto que diz o que acontece ("Cadastrar doação"), não "Enviar".

### Estados de tela

Toda tela de dados define: carregando, vazio, erro e sucesso. O estado vazio convida a agir; por exemplo, na busca, "Nenhum medicamento encontrado" com a opção de cadastrar uma solicitação (RF008).

### Status e etiquetas

Doações, solicitações, correspondências e agendamentos têm status (catálogo). Mostre como etiqueta com **texto e cor**, nunca só cor, usando os status exatos do catálogo.

### Busca e resultados (RF008)

Filtros claros, resultados paginados (10 por página), cada resultado com nome, concentração, forma, quantidade, validade, bairro ou região, distância, condição de conservação e indicação de receita. **Nunca** exiba nome, contato ou endereço do doador (RS002). O local de retirada só aparece após a confirmação do agendamento.

### Informações críticas de segurança

- Exiba o aviso de que a **plataforma não substitui avaliação médica ou farmacêutica** nas telas de doação, solicitação e retirada (RNF13), visível e sem ruído.
- Dados sugeridos pela IA (RF005) aparecem **identificados como sugestão**, editáveis, com os campos de baixa confiança destacados e a validade sempre para confirmar.
- Medicamento refrigerado: destaque a condição de conservação e a orientação de transporte (RF013).
- Retirada: oriente a priorizar pontos de coleta (RS008).
- Ações irreversíveis ou de risco (cancelar, recusar medicamento, encerrar conta) pedem confirmação com texto claro sobre a consequência.

### Navegação

Simples e igual para o mesmo perfil. Mostre ao usuário só o que o perfil dele pode fazer (Doador, Solicitante, Cuidador/Familiar, Representante do ponto de coleta, Administrador). A interface nunca é a única barreira de permissão: o service confere.

## Acessibilidade (WCAG 2.1 AA, RNF03)

- HTML semântico: `lang="pt-BR"`, marcos (`header`, `nav`, `main`, `footer`), títulos em ordem, listas e tabelas reais.
- Contraste mínimo de 4,5:1 para texto comum e 3:1 para texto grande, ícones e bordas de componentes. Verifique os pares do tema.
- **Foco visível** em todo elemento interativo e navegação completa por teclado, com ordem lógica e link para pular ao conteúdo.
- Não dependa só de cor para transmitir informação (status, erro, obrigatório).
- Todo campo com rótulo associado. Erros ligados ao campo (`aria-describedby`) e anunciados (`aria-live`).
- Texto alternativo em imagens com significado, e vazio em imagens decorativas.
- Alvos de toque com pelo menos 44 px.
- Ampliação a 200% sem perda de conteúdo. Respeite `prefers-reduced-motion`.

## Responsivo e desempenho

- **Mobile first**: projete a partir de 375 px e amplie. Defina os pontos de quebra como tokens.
- Sem rolagem horizontal. Imagens e tabelas se adaptam à largura.
- CSS enxuto, JavaScript mínimo e com melhoria progressiva: o fluxo principal funciona sem depender dele.
- Imagens otimizadas, com dimensões declaradas e carregamento tardio quando fora da tela. Nada de fontes ou scripts externos desnecessários (RNF04, RNF08).

## Movimento

Só quando ajuda: confirmar uma ação, mostrar o que mudou, indicar carregamento. Duração curta, sem animação decorativa nem de entrada automática, e desligada com `prefers-reduced-motion`.

## Texto da interface

- Português simples, voz ativa, frases curtas, sem jargão técnico.
- Botões dizem o que acontece ("Cadastrar doação", "Confirmar retirada"). A mesma ação mantém o mesmo nome no fluxo inteiro, inclusive na mensagem de sucesso.
- Erros explicam **o que houve e como corrigir**; não pedem desculpa nem culpam o usuário.
- Estados vazios convidam a agir.
- Use as mensagens literais do catálogo quando existirem. Não invente texto que o documento já define.

---

## Modos de trabalho

### A) Projetar (tela nova ou redesenho)

1. Leia a spec da tela (campos, mensagens, perfis) e as skills de Django e de segurança. Se a spec não existir, peça-a antes.
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
- **Conteúdo**: mensagens literais do catálogo, aviso de que não substitui avaliação médica ou farmacêutica nas telas exigidas, nenhum dado pessoal do doador na busca.
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
- Não invente identidade visual, textos que o documento já define ou dados sensíveis na tela.
- Não faça refatoração grande sem confirmar.
- Não corrija vários problemas de uma vez, porque fica difícil verificar.
- Não deixe a interface ser a única barreira de segurança.
