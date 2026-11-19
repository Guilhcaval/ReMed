---
name: python-boas-praticas
description: Boas práticas de Python para o ReMed. Use sempre que for escrever, alterar ou revisar qualquer código Python do projeto (services, models, forms, views, comandos, testes, utilitários), mesmo que a tarefa pareça pequena.
---

# Boas práticas de Python no ReMed

Quando houver conflito, `docs/arquitetura.md` e as ADRs prevalecem sobre esta skill. Para código Django, leia também `.agents/skills/django-boas-praticas/SKILL.md`. Para segurança, `.agents/skills/seguranca-owasp/SKILL.md`.

Antes de escrever código, leia a spec da funcionalidade em `docs/specs/`. Não implemente nada que a spec não peça.

## Estilo e legibilidade

- Siga a PEP 8. Se o projeto adotar formatador ou linter (veja `docs/arquitetura.md` e a configuração do repositório), rode-o antes de concluir; não adicione ferramenta nova por conta própria.
- Código simples e explícito. Prefira funções curtas, com uma responsabilidade, a funções longas com várias.
- Nomes que dizem a intenção. Evite abreviações obscuras e nomes de uma letra fora de laços curtos.
- Siga o idioma dos nomes já usado no projeto. Na falta de padrão, use nomes do domínio em português sem acento (por exemplo, `doacao`, `solicitacao`, `ponto_de_coleta`), e termos técnicos do Python e do Django em inglês. Use os termos do documento de requisitos (doação, solicitação, correspondência, agendamento, retirada).
- Comentários e docstrings em português, e só quando explicam o **porquê**. O que o código já diz não precisa de comentário.
- Sem código morto, sem `print` de depuração e sem trechos comentados.

## Tipagem

- Use anotações de tipo em assinaturas de funções e métodos públicos, principalmente nos services.
- Prefira tipos explícitos a `Any`. Use `X | None` para valores opcionais, se a versão do Python do projeto permitir (confirme na arquitetura); caso contrário, `Optional[X]`.
- Retorne objetos de domínio ou tipos claros (modelos, `dataclass`), não dicionários anônimos.

## Dados e estruturas

- Para dados simples sem comportamento, use `dataclass`. Se for imutável, `frozen=True`.
- Para conjuntos fixos de valores (como status), use enumerações. Em modelos Django, use `TextChoices` (veja a skill de Django).
- Nunca use valores padrão mutáveis em parâmetros (`def f(x=[])`). Use `None` e crie dentro da função.
- Compare com `None` usando `is None` e `is not None`.
- Use f-strings para montar texto. Use `pathlib` para caminhos.

## Datas e valores

- Use datas e horas com fuso (`django.utils.timezone.now()`), nunca `datetime.now()` sem fuso, em código Django. O sistema compara validade com a data atual (RF004, RF006).
- Não use `float` para valores que exigem precisão exata.
- Regras de negócio com números (prazos, limites) ficam em constantes nomeadas ou em configuração, nunca soltas no código. Valores que o documento marca como "sugerido" ou deixa para a ata devem ser configuráveis e estar documentados na spec.

## Erros e exceções

- Capture a exceção mais específica possível. Nunca use `except:` vazio nem `pass` para esconder erro.
- Para erros de regra de negócio, levante exceções de domínio com mensagem clara (a mensagem do documento, quando houver). Quem converte a exceção em resposta ao usuário é a camada de apresentação.
- Não use exceções para controle de fluxo normal.
- Preserve a causa com `raise NovaExcecao(...) from erro` quando traduzir uma exceção.
- Falhe de forma segura: em dúvida, negue a operação.

## Funções e módulos

- Uma função faz uma coisa. Se precisa de "e" para descrever, divida.
- Evite efeitos colaterais escondidos. Funções que gravam dados deixam isso claro no nome (`cadastrar_`, `cancelar_`, `reservar_`).
- Evite parâmetros demais; agrupe em objeto quando fizer sentido.
- Imports no topo do arquivo, em três grupos (biblioteca padrão, terceiros, projeto), sem `import *`. Evite imports circulares movendo o que é comum para um módulo próprio.
- Não duplique regra: se duas funções repetem a mesma validação, extraia.

## Segurança em Python

- Não use `eval`, `exec`, `pickle` nem `subprocess` com `shell=True` em dados externos.
- Use `secrets` para valores secretos, nunca `random`.
- Não registre em log senhas, tokens, códigos de confirmação nem conteúdo de receitas.
- Segredos vêm de variáveis de ambiente, nunca do código.

## Registro (log)

- Use o módulo `logging`, não `print`.
- Mensagens objetivas, com o contexto necessário e sem dados sensíveis.

## Testes

- Todo comportamento novo tem teste. Corrigir um erro começa por um teste que o reproduz.
- Teste o comportamento, não a implementação. Um teste cobre um caso e tem nome que descreve o cenário.
- Cubra o caminho feliz, os erros e os **limites**: validade igual à data de hoje, quantidade zero, CPF duplicado, tentativas de login no limite.
- Não dependa de ordem entre testes nem de dados de outros testes.
- Não dependa de relógio, rede ou serviço externo real: substitua por dublê (por exemplo, a IA de leitura da embalagem e o webservice de CEP).
- Use a ferramenta de testes definida em `docs/arquitetura.md`; na falta, `python manage.py test`.

## Dependências

- Adicione uma dependência só quando necessária, e registre-a no arquivo de dependências do projeto com versão fixada.
- Confira nome, origem e manutenção do pacote antes de instalar.
- Mudança que afeta a arquitetura (por exemplo, trocar o algoritmo de hash de senha) exige ADR antes.

## Antes de concluir

1. Rode os testes e o formatador ou linter do projeto, se houver.
2. Confira se cada regra da spec tem teste.
3. Releia o diff procurando código morto, nomes ruins e regra duplicada.
4. Atualize `docs/state.md`.
