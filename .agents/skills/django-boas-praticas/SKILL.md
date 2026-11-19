---
name: django-boas-praticas
description: Boas práticas de Django para o ReMed, com MVT, camada de service e views baseadas em classe. Use sempre que for criar ou alterar models, migrações, forms, services, views, URLs, templates, admin, configurações ou testes do projeto Django, mesmo para mudanças pequenas.
---

# Boas práticas de Django no ReMed

Quando houver conflito, `docs/arquitetura.md` e as ADRs (`docs/adr/`) prevalecem sobre esta skill. Leia também `.agents/skills/python-boas-praticas/SKILL.md` e, para rotas, permissões, autenticação, entrada de usuários, configurações ou dependências, `.agents/skills/seguranca-owasp/SKILL.md`.

Antes de escrever código, leia a spec da funcionalidade em `docs/specs/`. Não implemente nada que a spec não peça.

## Regras de arquitetura (decididas)

- O projeto segue **MVT**. Toda regra de negócio e toda consulta ao ORM ficam nos **services**.
- Toda view é uma **classe que herda de `django.views.View`** e implementa só os métodos HTTP necessários. Mixins de acesso, como `LoginRequiredMixin`, são permitidos.
- **Services não recebem `request` e não retornam `HttpResponse`.**
- O banco é **PostgreSQL**.

## Responsabilidade de cada camada

| Camada | Faz | Não faz |
| --- | --- | --- |
| Model | Define dados, relacionamentos, constraints, escolhas (status) | Regra de negócio, consulta com regra, envio de e-mail |
| Form | Valida formato e campos da entrada (CPF válido, tamanho, tipo de arquivo) | Regra que envolve outras entidades ou estado do sistema |
| Service | Regra de negócio, consultas ao ORM, transações, permissões sobre objetos, histórico | Receber `request`, devolver resposta HTTP, renderizar |
| View | Ler a entrada (GET/POST), chamar form e service, traduzir exceções de domínio em resposta HTTP, redirecionar ou renderizar | Regra de negócio, consulta ao ORM |
| Template | Exibir dados | Lógica, consultas, decisões de permissão |

## Estrutura

- Organize em apps por contexto do domínio, com os nomes definidos em `docs/arquitetura.md`. Não crie app novo sem justificar na arquitetura.
- Dentro de cada app, mantenha separados: `models.py`, `forms.py`, `services.py` (ou pacote `services/`), `views.py`, `urls.py`, `exceptions.py` e `tests/`.
- Siga o padrão de nomes dos services já existentes (no exemplo de referência, uma classe `<Entidade>Service` com os métodos de negócio). Confirme em `docs/arquitetura.md`.
- Use `app_name` e nomes de URL, e `reverse()` em vez de caminhos escritos à mão.

## Models

- Modelo descreve dados. Garanta invariantes no banco com constraints: `UniqueConstraint` (CPF, CNPJ, e-mail), `CheckConstraint` (quantidade não negativa), chaves estrangeiras e índices nos campos de busca e filtro.
- Status como `TextChoices`, com todos os valores que o catálogo de requisitos lista (por exemplo, os status de doação, solicitação e agendamento).
- O documento manda **não excluir** vários registros (doações, solicitações, pontos de coleta, entregas) e manter histórico. Use `on_delete=PROTECT` onde a exclusão em cascata apagaria histórico, e altere o **status** em vez de apagar.
- Registre quem, o quê, data e hora onde o documento exige histórico. Como isso será modelado (tabela de histórico, biblioteca) é decisão de ADR; não escolha por conta própria.
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
- Toda regra de negócio do catálogo e da spec mora aqui, com a mensagem de erro do documento quando houver.
- Erros de regra viram **exceções de domínio** (`exceptions.py`), como "objeto não encontrado", "sem permissão", "regra violada". A view as traduz.
- Permissão sobre o objeto é verificada aqui, filtrando pelo dono na própria consulta. Responda como "não encontrado" para não revelar que o objeto de outra pessoa existe.
- **Operações dependentes usam `transaction.atomic()`.** Para reserva, agendamento e entrega (RF009 a RF011, RNF06, RS007), use bloqueio de linha (`select_for_update()`) dentro da transação, para impedir reserva dupla.
- Evite consultas N+1: use `select_related` e `prefetch_related`. Pagine listas conforme o documento (por exemplo, 10 registros por página na busca, RF008).
- Rotinas automáticas (por exemplo, validade diária do RF006, expirações do RF007 e RF009, lembretes) são **services**, chamados por um comando de gerenciamento. O agendador é decisão de ADR.
- Envio de notificações e chamadas a serviços externos (CEP, IA, e-mail) ficam em services dedicados, com tratamento de falha que não quebre o fluxo principal.

## Views

- Classe que herda de `View`; implemente só `get`, `post` etc. que a spec exige. Sem lógica nos métodos além de: ler entrada, validar com o form, chamar o service, traduzir exceção, responder.
- Alteração de dados só com POST e `{% csrf_token %}`. Após POST bem-sucedido, redirecione (padrão POST/Redirect/GET).
- Declare os mixins de acesso e os perfis permitidos na própria view (Doador, Solicitante, Cuidador/Familiar, Representante do ponto de coleta, Administrador). O service reconfere o direito sobre o objeto.
- Converta exceções de domínio em resposta HTTP (404, 403, mensagem de erro). Não mostre rastreamento nem detalhes internos.
- Sem consulta ao ORM em views.

## Forms

- Validam o formato dos campos: CPF e CNPJ com dígito verificador, CEP, tamanho de campos, tipo e tamanho de arquivos.
- Declare `Meta.fields` explicitamente. Nunca `fields = "__all__"` e nunca exponha `status`, `perfil`, `autor` ou quantidade disponível.
- As mensagens de validação vêm literais do catálogo (por exemplo, "Campo(s) obrigatório(s) não preenchido(s)").

## Templates

- Sem lógica de negócio nem consultas. Mantenha o autoescape; não use `safe` em conteúdo de usuário.
- `{% csrf_token %}` em todo formulário POST.
- Interface em português do Brasil, linguagem simples (RNF01), mensagens de erro claras (RNF02), acessibilidade WCAG 2.1 AA com rótulos, contraste, navegação por teclado e texto alternativo (RNF03), e layout responsivo mobile first (RNF07).
- Exiba o aviso de que a plataforma não substitui avaliação médica ou farmacêutica onde o documento exige (RNF13).
- Não exiba dados que o perfil não pode ver (por exemplo, contato ou endereço do doador na busca, RS002).

## Admin do Django

- Use para consulta. Modelos de domínio ficam **somente leitura** ou sem permissão de escrita, para que nenhuma alteração ignore os services. Alterações passam pelos services.

## Configurações

- Segredos e parâmetros por ambiente vêm de variáveis de ambiente; mantenha `.env.example` sem valores reais.
- `LANGUAGE_CODE` e fuso conforme a arquitetura; `USE_TZ = True`.
- Valores de regra que o documento deixa "sugeridos" ou pendentes (prazos, limites) ficam em configuração nomeada, não espalhados no código.
- Antes de qualquer deploy, rode `python manage.py check --deploy`.

## Testes

- Services: testes sem `request`, cobrindo regras, erros e limites (validade igual a hoje, quantidade zero, CPF duplicado).
- Views: teste com o cliente de teste, sempre com visitante, dono, outro usuário e cada perfil sem acesso.
- Concorrência (reserva dupla): teste com transações reais (`TransactionTestCase`); o teste de comportamento transacional não funciona dentro da transação padrão do `TestCase`.
- Substitua serviços externos por dublês.
- Cada critério de aceite da spec tem ao menos um teste.

## Antes de concluir

1. Nenhum `request` em services; nenhuma consulta ao ORM em views ou templates.
2. Todas as regras da spec implementadas nos services e testadas.
3. Migrações geradas, revisadas e versionadas; constraints conferidas.
4. Perfis e visibilidade de dados testados.
5. `python manage.py check` e os testes passam.
6. Atualize `docs/state.md` e, se uma decisão mudou, abra ou atualize a ADR.
