# 0004. Gerenciar dependências com pip, ambiente virtual `.venv` e `requirements.txt` com versões fixadas

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF09, RS005

## Contexto

O projeto precisa de instalações reproduzíveis: quem clonar o repositório deve obter as mesmas versões de bibliotecas. O RS005 pede proteção contra o OWASP Top 10, e a edição de 2025 inclui as falhas na cadeia de suprimentos de software (A03). Por isso, as dependências precisam ser poucas, conhecidas e com versão controlada.

O repositório utiliza `.venv` local (fora do Git pelo `.gitignore`) e `requirements.txt` com todas as versões fixadas por `==`, inclusive as dependências indiretas (`asgiref`, `sqlparse`, `tzdata`).

## Direcionadores da decisão

- Instalação reproduzível em qualquer máquina.
- Ferramenta padrão do Python, sem instalação extra.
- Controle das dependências por segurança (RS005).

## Opções consideradas

1. pip com ambiente virtual `.venv` e `requirements.txt` com versões fixadas.
2. Poetry.
3. uv.

## Decisão

Opção 1. Regras que passam a valer:

- Cada desenvolvedor cria o ambiente virtual em `.venv/`, que não vai para o Git.
- Todas as dependências ficam no `requirements.txt`, com a versão fixada por `==`, inclusive as indiretas.
- Uma dependência só entra quando for necessária, depois de conferir nome, origem, manutenção e compatibilidade com o Python 3.14 (ADR 0003).
- Trocar de gerenciador exige uma nova ADR.

## Consequências

- Positivas:
  - Nada a instalar além do Python.
  - O `requirements.txt` mostra tudo o que o projeto usa.
- Negativas e custos:
  - O pip não gera um arquivo de bloqueio com hashes por padrão. As dependências indiretas precisam ser fixadas à mão quando mudam.
  - Não há separação entre dependências de produção e de desenvolvimento. Isso será tratado quando as ferramentas de teste e lint forem decididas.
- Impacto em specs e arquitetura:
  - Uma spec que precisar de biblioteca nova deve dizer qual é, e a biblioteca entra no `requirements.txt` com versão fixada.

## Como verificar

- Toda linha do `requirements.txt` usa `==`.
- `.venv/` está no `.gitignore`.
- Num ambiente limpo, `pip install -r requirements.txt` seguido de `pip check` termina sem erros.

## Notas

- A confirmar: a ferramenta de verificação de vulnerabilidades conhecidas (por exemplo, `pip-audit`) e quando ela roda. Isso fica junto da ADR de ferramentas de teste, formatação e lint.
