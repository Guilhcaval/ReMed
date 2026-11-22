---
name: django-boas-praticas
description: Boas práticas de Django para qualquer projeto, com separação em camadas (model, form, service, view, template) e views baseadas em classe. Use sempre que for criar ou alterar models, migrações, forms, services, views, URLs, templates, admin, configurações ou testes de um projeto Django, mesmo para mudanças pequenas.
---

# Boas práticas de Django

Quando houver conflito, o documento de arquitetura e as ADRs do projeto prevalecem sobre esta skill. Leia também a skill de boas práticas de Python e, para rotas, permissões, autenticação, entrada de usuários, configurações ou dependências, a skill de segurança (OWASP).

Antes de escrever código, leia a spec da funcionalidade (se existir). Não implemente nada que a spec não peça.

## Decisões de arquitetura: confirme antes de seguir

Esta skill assume o padrão abaixo, que é recomendado, mas **confirme no documento de arquitetura ou nas ADRs** se o projeto o adota. Se o projeto decidiu outra coisa, siga o projeto.

- **MVT com camada de service**: toda regra de negócio e toda consulta ao ORM ficam em **services**.
- **Views baseadas em classe** que herdam de `django.views.View`, implementando só os métodos HTTP necessários. Mixins de acesso (como `LoginRequiredMixin`) são permitidos.
- **Services não recebem `request` e não retornam `HttpResponse`.**
- Banco de dados, versão do Python e do Django, e idioma/fuso: conforme a arquitetura.

Se o projeto ainda não tem essas decisões registradas, proponha-as ao usuário (ADR `proposta`); não as assuma em silêncio.

## Responsabilidade de cada camada

| Camada | Faz | Não faz |
| --- | --- | --- |
| Model | Define dados, relacionamentos, constraints, escolhas (status) | Regra de negócio, consulta com regra, envio de e-mail |
| Form | Valida formato e campos da entrada (documento válido, tamanho, tipo de arquivo) | Regra que envolve outras entidades ou estado do sistema |
| Service | Regra de negócio, consultas ao ORM, transações, permissões sobre objetos, histórico | Receber `request`, devolver resposta HTTP, renderizar |
| View | Ler a entrada (GET/POST), chamar form e service, traduzir exceções de domínio em resposta HTTP, redirecionar ou renderizar | Regra de negócio, consulta ao ORM |
| Template | Exibir dados | Lógica, consultas, decisões de permissão |

## Estrutura

- Organize em apps por contexto do domínio, com os nomes definidos na arquitetura. Não crie app novo sem justificar.
- Dentro de cada app, mantenha separados: `models.py`, `forms.py`, `services.py` (ou pacote `services/`), `views.py`, `urls.py`, `exceptions.py` e `tests/`.
- Siga o padrão de nomes dos services existentes (por exemplo, uma classe `<Entidade>Service` com os métodos de negócio, ou funções por caso de uso). Confirme na arquitetura.
- Use `app_name` e nomes de URL, e `reverse()` em vez de caminhos escritos à mão.

## Models

- O modelo descreve dados. Garanta invariantes **no banco** com constraints: `UniqueConstraint`, `CheckConstraint` (por exemplo, quantidade não negativa), chaves estrangeiras e índices nos campos de busca e filtro.
- Status como `TextChoices`, com todos os valores previstos nos requisitos.
- Quando os requisitos mandam **não excluir** registros e manter histórico, use `on_delete=PROTECT` onde a exclusão em cascata apagaria histórico, e altere o **status** em vez de apagar.
- Onde houver exigência de histórico (quem, o quê, quando), a forma de modelar (tabela própria, biblioteca) é decisão de ADR; não escolha por conta própria.
- Use `USE_TZ = True` e datas com fuso.
- Dê `__str__` útil, sem expor dado sensível. Evite `null=True` em campos de texto.
- Nada de regra de negócio em `save()`, em sinais (`signals`) ou em propriedades que consultam o banco. Se a regra precisa rodar, ela está num service.

## Migrações

- Gere com `makemigrations`, revise o arquivo e versione. Uma mudança lógica por migração.
- Nunca edite uma migração já aplicada em outro ambiente; crie outra.
- Migração de dados separada da migração de esquema.
- Confira que as constraints e os índices esperados aparecem no arquivo gerado.

## Services

- Recebem dados simples ou objetos de domínio (usuário, id, valores validados) e devolvem objetos de domínio. Nunca `request`, `HttpResponse` ou `form`.
- Toda regra de negócio da spec mora aqui, com a mensagem de erro definida pelos requisitos quando houver.
- Erros de regra viram **exceções de domínio** (`exceptions.py`): "não encontrado", "sem permissão", "regra violada". A view as traduz.
- A permissão sobre o objeto é verificada aqui, filtrando pelo dono na própria consulta. Responda como "não encontrado" para não revelar a existência do objeto de outra pessoa.
- **Operações dependentes usam `transaction.atomic()`.** Para reserva, agendamento, estoque e pagamento, use bloqueio de linha (`select_for_update()`) dentro da transação, para impedir duplicidade.
- Evite consultas N+1: use `select_related` e `prefetch_related`. Pagine listas conforme os requisitos.
- Rotinas automáticas (expirações, lembretes, virada de status por data) são **services**, chamados por um comando de gerenciamento. O agendador (cron, Celery, outro) é decisão de ADR.
- Envio de notificações e chamadas a serviços externos ficam em services dedicados, com tratamento de falha que não quebre o fluxo principal.

## Views

- Classe que herda de `View`; implemente só `get`, `post` etc. que a spec exige. Sem lógica nos métodos além de: ler entrada, validar com o form, chamar o service, traduzir exceção, responder.
- Alteração de dados só com POST e `{% csrf_token %}`. Após POST bem-sucedido, redirecione (padrão POST/Redirect/GET).
- Declare os mixins de acesso e os perfis permitidos na própria view. O service reconfere o direito sobre o objeto.
- Converta exceções de domínio em resposta HTTP (404, 403, mensagem de erro). Não mostre rastreamento nem detalhes internos.
- Sem consulta ao ORM em views.

## Forms

- Validam o formato dos campos: documentos com dígito verificador, CEP, tamanho de campos, tipo e tamanho de arquivos.
- Declare `Meta.fields` explicitamente. Nunca `fields = "__all__"` e nunca exponha `status`, `perfil`, `autor` ou campos controlados pelo sistema.
- As mensagens de validação seguem o texto definido pelos requisitos.

## Templates

- Sem lógica de negócio nem consultas. Mantenha o autoescape; não use `safe` em conteúdo de usuário.
- `{% csrf_token %}` em todo formulário POST.
- Siga a skill de UI/UX para acessibilidade, linguagem e responsividade.
- Não exiba dados que o perfil não pode ver.

## Admin do Django

- Use para consulta. Modelos críticos ficam **somente leitura** ou sem permissão de escrita, para que nenhuma alteração ignore os services. Alterações passam pelos services.

## Configurações

- Segredos e parâmetros por ambiente vêm de variáveis de ambiente; mantenha `.env.example` sem valores reais.
- `LANGUAGE_CODE` e fuso conforme a arquitetura; `USE_TZ = True`.
- Valores de regra que os requisitos deixam "sugeridos" ou pendentes (prazos, limites) ficam em configuração nomeada, não espalhados no código.
- Antes de qualquer deploy, rode `python manage.py check --deploy`.

## Testes

- Services: testes sem `request`, cobrindo regras, erros e limites (data igual a hoje, quantidade zero, valor duplicado).
- Views: teste com o cliente de teste, sempre com visitante, dono, outro usuário e cada perfil sem acesso.
- Concorrência (reserva dupla): teste com transações reais (`TransactionTestCase`); o comportamento transacional não funciona dentro da transação padrão do `TestCase`.
- Substitua serviços externos por dublês.
- Cada critério de aceite da spec tem ao menos um teste.

## Antes de concluir

1. Nenhum `request` em services; nenhuma consulta ao ORM em views ou templates.
2. Todas as regras da spec implementadas nos services e testadas.
3. Migrações geradas, revisadas e versionadas; constraints conferidas.
4. Perfis e visibilidade de dados testados.
5. `python manage.py check` e os testes passam.
6. Atualize o arquivo de estado do projeto (se existir) e, se uma decisão mudou, abra ou atualize a ADR.
