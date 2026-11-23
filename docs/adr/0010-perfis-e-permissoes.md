# 0010. Modelar perfis de usuário final e permissões administrativas separadas por função

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RF001, RF002, RF004, RF005, RF006, RF007, RF011, RF012, RF014, RF017, RF021, RF022, RS002, RS015, RNF14

## Contexto

O controle de acesso do ReMed envolve dois grupos bem distintos de papéis, além de tensões explícitas nos requisitos:

1. **Perfis de usuário final (RF001, RF002, RF005):**
   - No cadastro (RF001, regra 5), o próprio usuário escolhe **um ou mais perfis** entre `Doador`, `Solicitante` e `Cuidador/Familiar` (acumuláveis).
   - O RF002 (regra 3) cita o perfil **"Ponto de coleta (representante da instituição)"** (RF005 e RF006), mas o RF001 não oferece essa opção no cadastro de pessoa física (Questão 15 do PRD). O RF005 (regra 7) define que o responsável deve ter cadastro de usuário (RF001) e ser vinculado à instituição, podendo haver mais de um responsável por ponto de coleta.
   - Todos os usuários autenticados recebem notificações (RF017) e podem registrar denúncias (RF021); visitantes sem login acessam apenas busca resumida (RF015), cadastro (RF001) e recuperação de senha (RF003).
2. **Funções administrativas (RF004, RF007, RF011, RF014, RF021, RF022, RS015):**
   - Os requisitos funcionais usam um único termo **"Administrador"** (e o RF011 menciona *"Administrador (ou responsável pela conferência)"*).
   - Porém, o **RS015 (solução 2)** exige **permissões administrativas separadas por função** (*aprovação de pontos de coleta, verificação de receitas, gestão de usuários e moderação*), concedidas apenas no mínimo necessário (Questão 19 do PRD).
   - Além disso, há um conflito direto na fonte (Questão 7 do PRD): o **RF004 (regra 5)** afirma que o Administrador **nunca vê receitas** (RF014) nem dados de saúde (RS002), enquanto o **RF014** lista `"Administrador (verificador)"` e o **RS015** cita o acesso a receitas.
   - O perfil Administrador só pode ser atribuído por outro Administrador, nunca a si mesmo, com *step-up* 2FA (RF004, ADR 0009), devendo existir sempre ao menos um Administrador ativo (RS015).

A [ADR 0007](0007-modelo-de-usuario-customizado.md) já definiu o model de usuário herdando de `AbstractBaseUser` e `PermissionsMixin` (disponibilizando `Group` e `Permission` nativos do Django), e a [ADR 0001](0001-django-mvt-com-camada-de-service.md) exige que a view declare quem pode acessar a rota e o service reconfira a permissão sobre o objeto (OWASP A01).

## Direcionadores da decisão

- Suportar múltiplos perfis acumuláveis para usuários finais (`Doador`, `Solicitante`, `Cuidador/Familiar`) autogerenciados no cadastro/perfil (RF001).
- Resolver o papel **"Ponto de coleta (representante da instituição)"** sem permitir que um representante acesse ou edite pontos de coleta de outras instituições (RF005, RF006, Questão 15 do PRD).
- Cumprir o **princípio do menor privilégio** e a **separação de permissões administrativas por função** exigida pelo RS015 (Questão 19 do PRD).
- Isolar o acesso a receitas (RF014, RS002) da gestão de usuários (RF004 regra 5), oferecendo solução técnica para a Questão 7 do PRD.
- Aplicar **negação por padrão** (*deny by default*) em duas camadas: rota na view e permissão por objeto no service (ADR 0001, OWASP A01).
- Evitar dependências externas desnecessárias (ADR 0004), reaproveitando o `PermissionsMixin` da ADR 0007.

## Opções consideradas

### 1. Perfis de uso no domínio + Grupos/Permissões nativos do Django (`PermissionsMixin`) para funções administrativas + checagem por objeto nos services (recomendada)

Separar claramente o que é **perfil de usuário final** do que é **permissão administrativa**:

- **Perfis de usuário final (domínio):**
  - `Doador`, `Solicitante` e `Cuidador/Familiar` modelados como campos/relação de domínio da conta (editáveis pelo próprio usuário, sempre com histórico — RNF14).
  - **Representante de ponto de coleta:** derivado do vínculo ativo do usuário na relação de responsáveis de um `PontoColeta` (RF005 regra 7). Qualquer usuário autenticado pode iniciar o cadastro de um ponto de coleta (RF005 pré-condição), tornando-se seu responsável inicial; alterações e envio de documentos (RF006) são autorizados apenas para os responsáveis vinculados **àquele** ponto.
- **Funções administrativas (`Group` e `Permission` do Django via `PermissionsMixin`):**
  - Qualquer usuário com ao menos uma permissão administrativa é tratado como conta administrativa e obrigado a usar **2FA TOTP** (ADR 0009).
  - Permissões funcionais distintas (agrupadas em grupos pré-definidos mantidos por migração/comando de inicialização), concedidas apenas no mínimo necessário (RS015):
    - `gestao_usuarios` (RF004 — nunca concede acesso a receitas);
    - `aprovacao_pontos_coleta` (RF007 e consulta de documentos do RF006);
    - `conferencia_doacoes` (RF011);
    - `verificacao_receitas` (RF014 — função isolada);
    - `moderacao_denuncias` (RF021 e consulta restrita de conversas/entregas vinculadas à denúncia);
    - `metricas_e_parametros` (RF022 e parâmetros do RF012);
    - `gestao_administradores` (atribuir/remover funções administrativas e reset de 2FA de outro Admin, com *step-up* 2FA — RF004 regra 4 e ADR 0009).
- **Verificação em duas camadas:** mixins declarativos na view (autenticação, status ativo, 2FA em rotas administrativas, perfil ou permissão exigida) + filtragem/checagem por objeto no service (dono da doação/solicitação, parte da correspondência/conversa ou responsável vinculado ao ponto de coleta).

- **Prós:**
  - Separa fisicamente perfis autoatribuíveis pelo usuário comum (RF001) de privilégios administrativos sensíveis (RS015), reduzindo o risco de escalação acidental de privilégio.
  - Reaproveita o `PermissionsMixin` já aceito na ADR 0007, sem adicionar bibliotecas externas (ADR 0004).
  - Atende integralmente ao RS015 e resolve na arquitetura o conflito da Questão 7 do PRD: quem tem `gestao_usuarios` não acessa receitas, pois `verificacao_receitas` é permissão separada.
  - Modela o representante de ponto de coleta de forma fiel ao RF005 (vínculo por estabelecimento, suportando múltiplos responsáveis e impedindo acesso cruzado entre instituições).
- **Contras:**
  - Mantém dois conceitos distintos de autorização no código (perfis de domínio para cidadãos vs. grupos/permissões do Django para funções administrativas).
  - Exige migração de dados (ou comando de sincronização) para criar e manter os grupos e permissões administrativas em todos os ambientes.

### 2. Unificar todos os perfis (inclusive `Doador`, `Solicitante` e `Cuidador/Familiar`) em `Group` / `Permission` do Django

Usar exclusivamente grupos e permissões do `django.contrib.auth` para todos os perfis do sistema, tanto de cidadãos quanto administrativos.

- **Prós:**
  - Um único mecanismo de verificação (`user.has_perm(...)` / `user.groups`) em todo o sistema.
- **Contras:**
  - Mistura no mesmo mecanismo perfis que o próprio visitante escolhe em tela pública (RF001) com privilégios administrativos sensíveis (RS015), aumentando o risco de bug de escalação de privilégio se uma view/form aceitar IDs de grupo sem filtro rigoroso.
  - Adiciona `JOIN` em tabelas de grupos até para checagens triviais de perfil de cidadão e dificulta o histórico específico de mudança de perfis do RF001.

### 3. Perfil único `Administrador` no MVP (sem separação por função) ou adoção de biblioteca externa de permissões por objeto (ex.: `django-guardian`)

Manter um único papel `Administrador` no MVP (deixando a separação do RS015 para depois) e/ou delegar permissões por objeto a uma biblioteca externa como `django-guardian`.

- **Prós:**
  - Um único papel `Administrador` reduz o trabalho inicial nas telas do RF004.
- **Contras:**
  - **Descumpre o RS015 (solução 2)** desde o MVP e agrava a Questão 7 do PRD (todo Administrador veria receitas, violando o RF004 regra 5).
  - Introduzir a separação por função depois do MVP obrigaria a refatorar mixins de views, services e testes de todas as funcionalidades administrativas.
  - Bibliotecas de permissão por objeto em tabela genérica (`django-guardian`) adicionam dependência externa e custo de consulta sem benefício real no ReMed, onde as regras por objeto são relacionamentos diretos de domínio (dono, participante da correspondência ou responsável vinculado ao ponto de coleta).

## Decisão

**Opção 1** — perfis de usuário final no domínio (`Doador`, `Solicitante`, `Cuidador/Familiar` + vínculo ativo de responsável por `PontoColeta`), **funções administrativas separadas via `Group`/`Permission` nativos do Django (`PermissionsMixin`)** e verificação em duas camadas (view + checagem por objeto no service).

Regras que passam a valer:

- **Perfis de usuário final (domínio):**
  - `Doador`, `Solicitante` e `Cuidador/Familiar` são acumuláveis e escolhidos/gerenciados pelo próprio usuário (RF001), sempre com registro de histórico (RNF14).
  - **Papel "Ponto de coleta" (Questão 15 do PRD):** decorre exclusivamente do **vínculo ativo** do usuário como responsável de um `PontoColeta` (RF005 regra 7), **sem checkbox no RF001**. Qualquer usuário autenticado pode cadastrar um ponto de coleta (RF005), tornando-se seu responsável inicial. O vínculo só concede acesso de gestão (RF005 e RF006) **enquanto estiver ativo**, e um ponto de coleta com status `pendente de aprovação` **não aparece** para doadores e solicitantes (RF005 regra 5).
- **8 funções administrativas separadas (RS015, Questão 19 do PRD, complementada pela [ADR 0011](0011-historico-imutavel-e-auditoria.md)):**
  - `gestao_usuarios` (RF004);
  - `aprovacao_pontos_coleta` (RF007 e consulta de documentos do RF006);
  - `conferencia_doacoes` (RF011);
  - `verificacao_receitas` (RF014);
  - `moderacao_denuncias` (RF021 e consulta restrita de conversas/entregas vinculadas à denúncia);
  - `metricas_e_parametros` (RF022 e parâmetros do RF012);
  - `gestao_administradores` (RF004 regra 4 — atribuir/remover funções administrativas e reset de 2FA de outro Admin, com *step-up* 2FA da ADR 0009);
  - `auditoria` (consulta somente leitura ao histórico imutável e aos registros de acesso, sem exibir receitas nem segredos — RNF14, RS015, [ADR 0011](0011-historico-imutavel-e-auditoria.md)).
- **Proibição técnica de acúmulo (`gestao_usuarios` × `verificacao_receitas`):** o sistema **proíbe tecnicamente** que uma mesma conta acumule as funções `gestao_usuarios` e `verificacao_receitas`, reforçando o RF004 (regra 5) e o RS015. Essa regra é aplicada no service de atribuição de permissões administrativas e verificada por testes automatizados.
- **Restrição de `is_superuser`:** `is_superuser` fica restrito exclusivamente ao **bootstrap inicial pelo terminal** (Questão 20 do PRD). Nas rotas da aplicação ReMed, valem **somente as funções explícitas**, sempre com **2FA obrigatório** (ADR 0009) — `is_superuser` não concede atalho nem ignora checagens de permissão ou de 2FA na aplicação.
- **Negação por padrão e checagem em duas camadas (ADR 0001, OWASP A01):** toda view protegida declara explicitamente o perfil de uso ou a função administrativa exigida; todo service que lê ou altera recurso de usuário ou instituição valida o vínculo na própria consulta, devolvendo "não encontrado" quando o recurso pertence a terceiros.
- **Proteção do último Administrador ativo:** a trava de "não remover o último Administrador ativo" (RF004 regra 4, RS015) aplica-se à função `gestao_administradores` (usuário ativo, com 2FA configurado). Nenhuma conta pode atribuir ou ampliar funções administrativas a si mesma pela interface.
- **Django Admin:** uso restrito; escrita desabilitada em models críticos cujas regras e históricos vivem nos services (ADR 0001).

## Consequências

- Positivas:
  - Atende ao RS015 desde o MVP sem dependências externas adicionais.
  - Mantém separação clara entre perfis autoatribuíveis (cidadão) e privilégios administrativos (com 2FA obrigatório).
  - Resolve tecnicamente o isolamento entre gestão de usuários (RF004) e verificação de receitas (RF014) por meio da proibição de acúmulo.
  - Garante rastreabilidade por pessoa física nas ações de pontos de coleta (RF005, RF006, RNF14) e elimina riscos de atalho por `is_superuser` na aplicação.
- Negativas e custos:
  - Exige criar e manter os 8 grupos/permissões administrativos por migração de dados ou comando idempotente.
  - A tela de gestão de usuários (RF004) precisará permitir selecionar quais funções administrativas estão sendo atribuídas ou removidas (em vez de um único checkbox "Administrador"), exibindo validação clara para a incompatibilidade entre `gestao_usuarios` e `verificacao_receitas`.
- Impacto em specs e arquitetura:
  - Condiciona diretamente as specs de **RF001**, **RF002**, **RF004**, **RF005**, **RF006**, **RF007**, **RF011**, **RF014**, **RF021** e **RF022**.
  - Cada spec deverá listar explicitamente qual perfil ou função administrativa acessa cada view e qual regra de vínculo o service valida.

## Como verificar

- Revisão de código e testes de view confirmam que toda rota protegida declara o perfil/função exigida e recusa visitante, usuário sem o perfil/função, `is_superuser` sem função explícita e Administrador sem 2FA concluído.
- Testes de service confirmam que um usuário não consegue ler nem alterar doações, solicitações, conversas ou documentos de ponto de coleta de terceiros, e que um vínculo de responsável **inativo** perde o acesso de gestão do ponto de coleta.
- Testes confirmam que pontos de coleta `pendente de aprovação` não aparecem nas listagens/buscas para doadores e solicitantes.
- Testes confirmam a proibição técnica de acumular `gestao_usuarios` e `verificacao_receitas` na mesma conta, e que um Administrador com `gestao_usuarios` não consegue acessar receitas (RF014).
- Testes confirmam que nenhum Administrador consegue atribuir funções administrativas a si mesmo e que o sistema impede remover `gestao_administradores` do último Administrador ativo.

## Notas

### Questão em aberto (a confirmar com o professor; não bloqueia esta ADR)

- **Quem exerce a verificação de receitas (Questões 6 e 7 do PRD):** o RF014 deixou em pendência da ata (prazo vencido em 10/11/2026) definir quem será o verificador de receitas. Esta ADR prepara a função isolada `verificacao_receitas` (proibida de acumular com `gestao_usuarios`), mas a definição organizacional de quem receberá essa função depende de confirmação com o professor/cliente.

### ADRs relacionadas

- [ADR 0001](0001-django-mvt-com-camada-de-service.md) (camada de service e separação view/service)
- [ADR 0004](0004-pip-venv-requirements-fixado.md) (sem dependências externas desnecessárias)
- [ADR 0007](0007-modelo-de-usuario-customizado.md) (modelo de usuário com `PermissionsMixin`)
- [ADR 0009](0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) (2FA TOTP obrigatório e *step-up* no RF004)
- [ADR 0011](0011-historico-imutavel-e-auditoria.md) (histórico imutável e auditoria — RNF14).
