# 0001. Usar Django no padrão MVT, com camada de service e templates renderizados no servidor

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF07, RNF08, RNF06, RNF14, RNF09, RS005

## Contexto

O ReMed é uma aplicação web responsiva, aberta ao público e usada principalmente por formulários e listas: cadastros, doações, solicitações, busca, agendamento e telas do Administrador (RNF07). Os requisitos funcionais têm muitas regras numeradas: status com histórico, prazos, permissões por perfil e operações que não podem gerar reserva dupla. Essas regras precisam ficar num só lugar e poder ser testadas sem depender da camada web (RNF06, RNF14).

O público pode ter pouca familiaridade com tecnologia e usar 3G/4G, por isso o consumo de dados deve ser baixo (RNF01, RNF08). O RS005 pede proteção contra o OWASP Top 10 (CSRF, XSS e injeção de SQL).

O RNF09 (Desejável) pede uma API REST. O PRD coloca esse requisito na v2.0 ([01-remed.md](../prd/01-remed.md), seção 6.2).

O `requirements.txt` fixa o Django 6.1.3.

## Direcionadores da decisão

- Aplicação web responsiva, sem instalação obrigatória (RNF07).
- Pouco tráfego e poucas requisições para o usuário (RNF08).
- Regras de negócio centralizadas e testáveis, com transações nas operações de reserva, agendamento e entrega (RNF06).
- Histórico de alterações registrado de forma consistente, sem depender de cada tela (RNF14).
- Proteções nativas contra CSRF, XSS e injeção de SQL (RS005).
- Simplicidade para a equipe, num projeto acadêmico.

## Opções consideradas

1. Django MVT com camada de service e templates renderizados no servidor.
2. Django MVT sem camada de service (regras nas views, nos forms e nos models).
3. API REST em Django com um front-end SPA separado.

## Decisão

Opção 1. O projeto usa Django no padrão MVT. As páginas são renderizadas no servidor com os templates do Django, e as regras de negócio ficam numa camada de service.

Regras que passam a valer:

- **View:** classe que herda de `django.views.View` e implementa só os métodos HTTP necessários. Mixins de acesso, como o `LoginRequiredMixin`, são permitidos. A view lê a entrada, valida com o form, chama o service, converte as exceções de domínio em resposta HTTP e renderiza ou redireciona. Não tem regra de negócio nem acesso ao ORM.
- **Form:** valida o formato da entrada (CPF, CNPJ, CEP, tamanho e tipo de arquivo). Não valida regras que dependem de outras entidades ou do estado do sistema.
- **Service:** guarda as regras de negócio, as consultas ao ORM, as transações, a verificação de permissão sobre objetos e o registro de histórico. Não recebe `request` e não devolve `HttpResponse`.
- **Model:** define campos, relacionamentos, constraints e status, sem regra de negócio.
- **Template:** cuida só da apresentação, sem lógica de negócio nem consultas.
- Dados só mudam por POST, com token CSRF, seguido de redirecionamento (POST/Redirect/GET).

## Consequências

- Positivas:
  - As regras de cada RF ficam em services, que podem ser testados sem `request`.
  - CSRF, autoescape dos templates e ORM parametrizado vêm do framework (RS005).
  - Há um único projeto para construir, testar e implantar.
- Negativas e custos:
  - **O RNF09 (API REST) não é atendido por esta decisão.** Uma API, se necessária, será decidida em outra ADR. Hoje ela é candidata para a v2.0.
  - A camada de service exige disciplina e gera mais arquivos do que o Django "padrão".
  - O Admin do Django grava direto nos models. Suas ações precisam chamar os services ou ficar só para leitura nos models críticos.
  - Interações mais ricas, como o preenchimento pelo CEP e a geolocalização, dependem de JavaScript no navegador (ADR 0006).
- Impacto em specs e arquitetura:
  - Cada spec descreve as regras do RF em termos de services e as telas em termos de views e templates.
  - O documento de arquitetura, que será gerado de novo, deve descrever as camadas conforme esta ADR.

## Como verificar

- Revisão de código: nenhuma view nem template acessa o ORM, e nenhum service recebe `request` ou devolve resposta HTTP.
- Checagem simples no repositório: buscar `.objects.` nos arquivos de views e `request` nas assinaturas dos services.
- Testes de service rodam sem cliente HTTP. Testes de view usam o cliente de teste com cada perfil.

## Notas

- Banco de dados: [ADR 0002](0002-postgresql-como-banco-de-dados.md).
- Front-end: [ADR 0005](0005-bootstrap-hospedado-no-projeto.md) (CSS) e [ADR 0006](0006-javascript-simples-sem-framework.md) (JavaScript).
- Pendente: a ADR sobre a API REST (RNF09) e a divisão em apps por contexto do domínio.
