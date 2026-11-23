# 0006. Usar JavaScript simples, sem framework de front-end

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF07, RNF08, RNF04, RNF03, RF001, RF005, RF015

## Contexto

As páginas são renderizadas no servidor (ADR 0001). Mesmo assim, algumas interações precisam de JavaScript no navegador:

- O botão "Mostrar" do campo de senha, presente nas telas.
- O preenchimento do endereço pelo CEP (RF001, RF005).
- A inclusão de outro horário ou outro responsável no cadastro do ponto de coleta (RF005).
- A localização do usuário, obtida com consentimento no navegador (RF015, RS010).
- Os componentes interativos do Bootstrap (ADR 0005).

O usuário pode estar em 3G/4G (RNF08), e páginas públicas e buscas devem responder em até 3 segundos (RNF04).

## Direcionadores da decisão

- Pouco JavaScript enviado ao navegador (RNF08, RNF04).
- Funcionamento nos navegadores do RNF07.
- Coerência com a renderização no servidor (ADR 0001).
- Menos dependências para manter (ADR 0004).

## Opções consideradas

1. JavaScript simples, sem framework.
2. htmx ou biblioteca parecida para atualizações parciais.
3. Framework de front-end (React, Vue ou parecido).
4. jQuery.

## Decisão

Opção 1. O htmx foi descartado porque as interações previstas no MVP (mostrar senha, preenchimento por CEP, campos dinâmicos de horário/responsável e geolocalização) são pontuais e locais no navegador, não justificando adicionar uma biblioteca externa nem criar endpoints de fragmentos HTML.

Regras que passam a valer:

- O JavaScript do projeto é escrito sem framework de front-end e sem jQuery, em arquivos estáticos do próprio projeto.
- O JavaScript do Bootstrap só é carregado nas páginas que usam um componente que precisa dele.
- Regras de negócio e validações que importam ficam no servidor (ADR 0001). O JavaScript só melhora a interação.
- Uma biblioteca de JavaScript só entra com uma nova ADR.

## Consequências

- Positivas:
  - Páginas leves, sem etapa de build de front-end.
  - Nenhuma dependência de JavaScript para atualizar.
- Negativas e custos:
  - Interações mais complexas, se surgirem (por exemplo, mapas ou listas que se atualizam sozinhas), dão mais trabalho sem uma biblioteca e podem pedir uma nova ADR.
  - Cada comportamento precisa ser testado à mão nos navegadores do RNF07 e com teclado (RNF03).
- Impacto em specs e arquitetura:
  - As specs devem dizer quais interações dependem de JavaScript e o que acontece quando ele falha ou quando o usuário nega a localização (o CEP é a alternativa, RF015).

## Como verificar

- O `requirements.txt` e o diretório `static/` não incluem framework de front-end nem jQuery.
- Os formulários continuam sendo validados no servidor quando o JavaScript está desligado.
- Os templates não carregam scripts de domínio externo (ADR 0005).

## Notas

- A decidir em outras ADRs: se a consulta de CEP é feita pelo navegador ou pelo servidor (RNF12) e a política de segurança de conteúdo (CSP), que pode proibir scripts inline.
