# Spec 05 — Cadastro de Ponto de Coleta (Pessoa Jurídica) (RF005)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `05` — Cadastro de Ponto de Coleta (Pessoa Jurídica) (`RF005`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF005 (Importante — **MVP ⬆**, HU05). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF08, RNF11 (Essencial), RNF12, RNF14 (Essencial). **Segurança:** RS008, RS011. |
| **Apps envolvidos** | `pontos_coleta` (principal: `PontoColeta`, `HorarioFuncionamentoPonto`, `PontoColetaResponsavel`, `PontoColetaService`), `nucleo` (`TipoEstabelecimento` em cadastro auxiliar, `CepService` + `CacheCep` com coordenadas aproximadas, mixins de acesso), `auditoria` (`AuditoriaService`), `contas` (vinculação de responsáveis autenticados e função administrativa `aprovacao_pontos_coleta`). |
| **Dependências de outras specs** | **[01-cadastro-de-usuario.md](01-cadastro-de-usuario.md) (`RF001`)** (usuário cadastrado, `CepService`, `AuditoriaService`) e **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)** (usuário autenticado e mixins de permissão/2FA). Articula-se com as specs seguintes **[06 — RF006]** (envio de documentos obrigatórios) e **[07 — RF007]** (análise e aprovação pelo Administrador). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0007](../adr/0007-modelo-de-usuario-customizado.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md), [0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md), [0018](../adr/0018-consulta-de-cep.md). |

---

## 2. Objetivo e escopo

Permitir que representantes autenticados cadastrem e mantenham estabelecimentos (farmácias, postos de saúde, hospitais, clínicas, ONGs/instituições sociais e outros) como **pontos de coleta** — locais seguros e combinados para o encontro de retirada presencial de medicamentos entre doador e solicitante.

### Inclui

- Cadastro de pessoa jurídica (`PontoColeta`) por usuário pessoa física já autenticado (RF001 + RF002), sem criação de senha para a instituição ([ADR 0007](../adr/0007-modelo-de-usuario-customizado.md)).
- Tela **"Parceria ReMed — Cadastro de instituição / ponto de coleta"** fiel a [Cadastro Pessoa Jurídica.png](../prd/telas/Cadastro%20Pessoa%20Jur%C3%ADdica.png) e ao catálogo (RF005), incluindo aviso explícito de que o ponto de coleta é **apenas local de encontro para retirada, não local de guarda temporária de medicamentos**.
- Validação de **CNPJ** (dígitos verificadores e unicidade no PostgreSQL), cadastro auxiliar de **Tipo de estabelecimento**, endereço **público** preenchido pelo `CepService` (com coordenadas aproximadas do `CacheCep` para proximidade — [ADRs 0017 e 0018](../adr/0018-consulta-de-cep.md)), estrutura de **dias e horários de funcionamento para retirada** (com múltiplos blocos de horários, limitando agendamentos no RF018) e indicação de **refrigeração** (RF010).
- Fluxo em **dois passos contínuos** com o RF006: o Passo 1 (RF005) salva o ponto de coleta em `pendente_aprovacao` e redireciona imediatamente para o Passo 2 (Spec `06` — RF006) para envio dos documentos obrigatórios (licença de funcionamento e alvará sanitário com número e data de validade).
- Gestão de **responsáveis vinculados** (`PontoColetaResponsavel` — vínculo ativo dando acesso de gestão sem checkbox no RF001, suportando múltiplos responsáveis com conta ReMed já cadastrada mediante **convite que o outro usuário precisa aceitar** — [ADR 0010](../adr/0010-perfis-e-permissoes.md)).
- Todo ponto nasce automaticamente com status **`pendente_aprovacao`** (`"pendente de aprovação"`), **não aparecendo para doadores e solicitantes** até aprovação (RF006 + RF007).
- **Alteração** dos dados do ponto pelo responsável com vínculo ativo (exceto **CNPJ**, que **somente o Administrador com `aprovacao_pontos_coleta`** altera mediante motivo obrigatório) — sempre com histórico imutável (`AuditoriaService` — RNF14). Se o **endereço** de um ponto já `ativo` for alterado, o ponto **volta automaticamente para `pendente_aprovacao`** e os agendamentos futuros seguem o tratamento do RF007 (regra 3).
- **Inativação voluntária pelo representante** (*acréscimo da especificação, não consta no RF005*): o responsável ativo pode mudar seu próprio ponto para `inativo`, aplicando os mesmos efeitos do RF007 regra 3 (agendamentos futuros cancelados/remarcados com aviso às partes); a **reativação passa exclusivamente pelo Administrador** (RF007).
- **Pesquisa** de pontos de coleta por **CNPJ, razão social, nome fantasia, tipo de estabelecimento, município e status**, respeitando a visibilidade de cada perfil.
- Proibição de exclusão física (`on_delete=PROTECT` em retiradas e histórico).

### Não inclui

- Envio, validação, versionamento e controle de validade de licença de funcionamento e alvará sanitário (Spec `06` — RF006, com `ArquivoService` da ADR 0016; ver Questão 1 da seção 13 sobre encadeamento com a tela de cadastro).
- Análise, aprovação, reprovação, suspensão, inativação e revisão periódica pelo Administrador (Spec `07` — RF007).
- Guarda temporária de medicamentos pela instituição (não-objetivo desta versão — RF005 Observação, RNF11).
- Login por CNPJ (decidido na [ADR 0007](../adr/0007-modelo-de-usuario-customizado.md): acesso sempre pela conta de pessoa física do responsável).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Usuário autenticado (futuro representante da instituição)** | Cadastrar um novo ponto de coleta, tornando-se seu responsável ativo inicial. | Cadastro de usuário (RF001), `status = ativo` e e-mail confirmado (RF002). |
| **Responsável com vínculo ativo no ponto (`PontoColetaResponsavel.ativo = True`)** | Consultar seus pontos, alterar dados do ponto (exceto CNPJ) e gerenciar vínculos de responsáveis daquele ponto. | Sessão autenticada válida e vínculo **ativo** com o ponto alvo ([ADR 0010](../adr/0010-perfis-e-permissoes.md)). |
| **Administrador (`aprovacao_pontos_coleta`, ver Questão 3)** | Pesquisar pontos em qualquer status e alterar o **CNPJ** do ponto de coleta quando necessário (RF005 — Alteração). | Conta administrativa ativa com função explícita e 2FA TOTP concluído ([ADRs 0009 e 0010](../adr/0010-perfis-e-permissoes.md)). |
| **Doador / Solicitante / Visitante** | Consultar pontos de coleta **ativos** (para escolha na doação RF008 / agendamento RF018). | Apenas pontos com `status = ativo` são visíveis (RF005 regra 5). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Cadastro de ponto de coleta

1. O usuário autenticado acessa **"Parceria ReMed — Cadastro de instituição / ponto de coleta"** (`pontos_coleta:cadastrar`).
2. Visualiza o aviso de que o ponto será vinculado à sua conta ReMed autenticada (sem criar senha para a instituição) e seus dados de responsável (CPF, Nome, E-mail, Contato) exibidos como somente leitura com etiqueta `"Usuário vinculado · autenticado"`.
3. Preenche **Dados da instituição** (CNPJ, Razão Social, Nome Fantasia, Tipo de estabelecimento, E-mail institucional, Telefone), **Endereço do ponto de coleta** (CEP com preenchimento automático via `nucleo:cep_consultar`, Número e Complemento opcional), **Funcionamento e estrutura** (um ou mais blocos de dias de `Seg` a `Dom` com horários de `Abertura` e `Fechamento`, além de `"Possui refrigeração para medicamentos?"` Sim/Não) e **Observações** (opcional). Opcionalmente adiciona outros responsáveis já cadastrados no ReMed.
4. Aciona **Cadastrar ponto de coleta e enviar para aprovação** (`POST` com CSRF).
5. A view valida o formato no `PontoColetaCadastroForm` (e formset de horários) e chama `PontoColetaService.cadastrar(usuario_autenticado, dados)`.
6. Dentro de `transaction.atomic()`, `PontoColetaService.cadastrar(...)`:
   - Valida CNPJ (dígitos verificadores e unicidade no PostgreSQL);
   - Cria o `PontoColeta` com `status = pendente_aprovacao` e `data_cadastro` automática, salvando o endereço público e coordenadas aproximadas do `CacheCep` (se disponíveis — [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md));
   - Cria os registros de `HorarioFuncionamentoPonto` (validando `abertura < fechamento` e ausência de faixas sobrepostas no mesmo dia);
   - Cria o vínculo inicial ativo em `PontoColetaResponsavel` para o usuário autenticado (e eventuais responsáveis adicionais validados);
   - Registra `ponto_coleta.cadastrado` em `AuditoriaService` ([ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md)).
7. A view redireciona (PRG) para o detalhe do ponto / envio dos documentos obrigatórios (RF006), informando que o cadastro está `"Pendente de aprovação"` e só será ativado após o envio dos documentos (RF006) e aprovação do Administrador (RF007).

### 4.2 Fluxos alternativos

- **FA-01 — Preenchimento manual do endereço quando o webservice de CEP falha ([ADR 0018](../adr/0018-consulta-de-cep.md)):** libera edição manual de Logradouro, Bairro, Município e Estado sem perder os dados já digitados. O link `"Não sei meu CEP"` abre a busca oficial dos Correios em nova aba (`rel="noopener noreferrer"`).
- **FA-02 — Edição de dados pelo responsável ativo (`pontos_coleta:editar`):** responsável com vínculo ativo altera Razão Social, Nome Fantasia, Tipo de estabelecimento, E-mail, Telefone, Endereço, Horários, Refrigeração ou Observações. O campo **CNPJ** é exibido apenas para leitura e rejeitado pelo service se enviado alterado. Se o ponto estiver `ativo` e o **endereço** mudar, o ponto volta automaticamente para `pendente_aprovacao` (oculto de novas buscas) e os agendamentos futuros seguem o tratamento do RF007 (regra 3), com aviso às partes (RF017). A alteração é registrada em `AuditoriaService` (`ponto_coleta.alterado`, com nomes dos campos modificados).
- **FA-03 — Alteração de CNPJ pelo Administrador (`pontos_coleta:admin_alterar_cnpj`):** somente Administrador com função **`aprovacao_pontos_coleta`** (+ 2FA) e **motivo obrigatório** altera o CNPJ de um ponto (revalidando dígitos verificadores e unicidade) com registro em `AuditoriaService` (`ponto_coleta.cnpj_alterado`).
- **FA-04 — Gestão de responsáveis vinculados por convite (`pontos_coleta:responsaveis`):** responsável ativo do ponto pode enviar **convite** a outro usuário já cadastrado no ReMed (`status = ativo`, e-mail confirmado) criando `PontoColetaResponsavel` com `status = convite_pendente` e notificando o convidado (RF017); o vínculo só passa a `ativo` (concedendo acesso de gestão) quando o convidado **aceita o convite** (`pontos_coleta:convite_responder`). Um responsável ativo também pode inativar um vínculo existente, desde que permaneça **ao menos 1 responsável ativo** no ponto. Todo convite, aceite e desvínculo grava em `AuditoriaService`.
- **FA-05 — Inativação voluntária pelo representante (`pontos_coleta:inativar`, *acréscimo da especificação, não consta no RF005*):** responsável ativo pode inativar o próprio ponto (`status = inativo`), aplicando os mesmos efeitos do RF007 regra 3 (ocultação imediata e cancelamento/remarcação de agendamentos futuros com aviso às partes — RF018, RF017); a reativação depende exclusivamente de nova análise do Administrador (RF007).
- **FA-06 — Pesquisa de pontos de coleta:**
  - `pontos_coleta:meus_pontos` lista apenas os pontos onde `request.user` possui vínculo ativo (em qualquer status);
  - `pontos_coleta:lista_publica` (usada por doadores/solicitantes) lista **exclusivamente** pontos com `status = ativo`, filtráveis por nome fantasia, tipo de estabelecimento e município;
  - `pontos_coleta:admin_lista` (para `aprovacao_pontos_coleta` + 2FA) pesquisa por CNPJ, razão social, nome fantasia, tipo de estabelecimento, município e status.

### 4.3 Fluxos de exceção

- **FE-01 — Visitante não autenticado acessa a aba/rota de Pessoa Jurídica:** redirecionado para `contas:login` com orientação clara de que o representante precisa entrar na sua conta ReMed (ou criar conta de pessoa física primeiro — RF005 pré-condição).
- **FE-02 — CNPJ com dígitos verificadores inválidos ou já cadastrado:** rejeita com mensagem clara no campo CNPJ (`CnpjJaCadastrado` / erro de validação).
- **FE-03 — Horário inválido (`abertura >= fechamento`), nenhum dia selecionado ou sobreposição de horários no mesmo dia:** rejeita mantendo os dados preenchidos.
- **FE-04 — Usuário sem vínculo ativo (ou com vínculo inativo) tenta editar o ponto:** `PontoColetaService` filtra pelo vínculo ativo na própria consulta e lança `RecursoNaoEncontrado` (HTTP 404, OWASP A01).
- **FE-05 — Tentativa de remover/inativar o último responsável ativo do ponto:** `PontoColetaService` bloqueia com `RegraNegocioViolada` garantindo que o ponto nunca fique órfão.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-05-01** | O CNPJ é obrigatório, deve ter os dígitos verificadores validados (`xx.xxx.xxx/xxxx-xx` na interface, armazenado com 14 dígitos sem máscara) e ser **único** no banco de dados. | RF005 (regra 1), RS011, [ADR 0002](../adr/0002-postgresql-como-banco-de-dados.md) • `pontos_coleta` |
| **RN-05-02** | O **Tipo de estabelecimento** vem de cadastro auxiliar (`nucleo`), com as opções iniciais obrigatórias: `Farmácia`, `Posto/Unidade de Saúde`, `Hospital`, `Clínica`, `ONG/Instituição Social` e `Outros`. | RF005 (regra 2) • `nucleo`, `pontos_coleta` |
| **RN-05-03** | Os **dias e horários de funcionamento para retirada** são obrigatórios (ao menos 1 dia selecionado com `abertura < fechamento`, permitindo múltiplos blocos sem sobreposição no mesmo dia) e limitam as opções de data/horário no agendamento da retirada (RF018). | RF005 (regra 3) • `pontos_coleta` |
| **RN-05-04** | O campo **Possui refrigeração para medicamentos** (`Sim`/`Não`) é obrigatório e indica o ponto como adequado para retirada de medicamentos refrigerados (RF010). | RF005 (regra 4) • `pontos_coleta` |
| **RN-05-05** | Os status válidos são `pendente_aprovacao`, `ativo`, `suspenso` e `inativo`, sempre com histórico. Todo cadastro nasce **`pendente_aprovacao`**. **Somente pontos com status `ativo` aparecem para doadores e solicitantes**; a passagem para `ativo` depende do envio dos documentos obrigatórios (RF006) e da análise do Administrador (RF007). | RF005 (regra 5, Aprovação), RS011, [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `pontos_coleta` |
| **RN-05-06** | O endereço do ponto de coleta é preenchido automaticamente pelo CEP (`CepService` — [ADR 0018](../adr/0018-consulta-de-cep.md)), com edição de número e complemento (e fallback manual). Diferente do endereço de usuários, o **endereço do ponto de coleta é público** e suas coordenadas aproximadas são usadas na busca por proximidade (RF015, [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md)). | RF005 (regra 6), [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md), [ADR 0018](../adr/0018-consulta-de-cep.md) • `pontos_coleta`, `nucleo` |
| **RN-05-07** | Todo responsável pelo ponto de coleta deve ter conta de usuário cadastrada e ativa (RF001, RF002) e ser vinculado à instituição. Pode haver **mais de um responsável** por ponto (sempre restando ao menos 1 responsável ativo), vinculados por meio de **convite que o outro usuário precisa aceitar** (`status = convite_pendente` -> `ativo`). O acesso de gestão (RF005 e RF006) vale **somente enquanto o vínculo estiver `ativo`** ([ADR 0010](../adr/0010-perfis-e-permissoes.md)). | RF005 (regra 7, Pré-condição), [ADR 0010](../adr/0010-perfis-e-permissoes.md) • `pontos_coleta`, `contas`, `notificacoes` |
| **RN-05-08** | A alteração do cadastro é feita por responsável com vínculo ativo, **exceto o CNPJ**, que só pode ser alterado pelo Administrador com função **`aprovacao_pontos_coleta`** (+ 2FA) mediante **motivo obrigatório**. Alterar o **endereço** de um ponto já `ativo` devolve automaticamente o ponto para `pendente_aprovacao`, aplicando o tratamento do RF007 (regra 3) aos agendamentos futuros. Toda criação e alteração gera registro imutável em `AuditoriaService` (quem, o quê, data e hora — RNF14). | RF005 (Alteração), RF007 (regras 2 e 3), RS011, RNF14, [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `pontos_coleta`, `auditoria` |
| **RN-05-09** | **Não há exclusão física** de pontos de coleta (`on_delete=PROTECT` em vínculos de documentos e retiradas); o encerramento operacional ocorre apenas por mudança de status (`suspenso` ou `inativo`), preservando todo o histórico. O próprio responsável ativo pode inativar seu ponto (*acréscimo da especificação*), com os mesmos efeitos do RF007 regra 3; a reativação passa exclusivamente pelo Administrador (RF007). | RF005 (Exclusão), RF007 (regra 3), RNF14 • `pontos_coleta`, `correspondencias`, `notificacoes` |
| **RN-05-10** | O sistema exibe de forma visível que o ponto de coleta é **apenas local seguro de encontro para retirada**, não local de guarda temporária de medicamentos (RNF11). | RF005 (Observação), RNF11 • `pontos_coleta` |

---

## 6. Modelo de dados lógico

*(Nível lógico — sem código de models. Todas as datas/horas usam `USE_TZ = True`.)*

### 6.1 Entidades e campos

#### `TipoEstabelecimento` (app `nucleo` — cadastro auxiliar populado por migração de dados)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `nome` | String (80, único) | Sim | Valores iniciais: `Farmácia`, `Posto/Unidade de Saúde`, `Hospital`, `Clínica`, `ONG/Instituição Social`, `Outros`. |
| `ativo` | Boolean | Sim | Padrão `True`. |

#### `PontoColeta` (app `pontos_coleta`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | Referenciado com `on_delete=PROTECT` por documentos, doações e agendamentos. |
| `cnpj` | String (14, único) | Sim | 14 dígitos sem máscara; validado por dígito verificador; alteração restrita ao Administrador. `UniqueConstraint` no PostgreSQL. |
| `razao_social` | String (150) | Sim | |
| `nome_fantasia` | String (150, indexado) | Sim | |
| `tipo_estabelecimento` | FK (`TipoEstabelecimento`, `PROTECT`) | Sim | |
| `email` | EmailField (254) | Sim | E-mail institucional (público ou de contato do ponto). |
| `telefone` | String (11) | Sim | 10 ou 11 dígitos armazenados sem máscara (`(xx)xxxxx-xxxx` na interface). |
| `possui_refrigeracao` | Boolean | Sim | Indica aptidão para medicamentos refrigerados (RF010). |
| `observacoes` | Text | Não | Opcional. |
| `cep` | String (8) | Sim | 8 dígitos sem máscara. |
| `logradouro` / `numero` / `bairro` / `municipio` / `estado` | String | Sim | Endereço **público** (`estado` = UF de 2 letras; índice em `municipio`). |
| `complemento` | String (100) | Não | Opcional. |
| `latitude_aprox` / `longitude_aprox` | Decimal (anulável, indexados) | Não | Coordenadas obtidas do `CacheCep` / geocodificação para proximidade ([ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md)). |
| `status` | TextChoices (indexado) | Sim | `pendente_aprovacao`, `ativo`, `suspenso`, `inativo`. Padrão: `pendente_aprovacao`. |
| `criado_em` / `atualizado_em` | Datetime | Sim | `criado_em` cobre `Data do cadastro`. |

#### `HorarioFuncionamentoPonto` (app `pontos_coleta`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `ponto_coleta` | FK (`PontoColeta`, `CASCADE`) | Sim | |
| `dia_semana` | SmallInteger (0=Seg .. 6=Dom) | Sim | `CheckConstraint(0 <= dia_semana <= 6)`. |
| `hora_abertura` | Time (`hh:mm`) | Sim | |
| `hora_fechamento` | Time (`hh:mm`) | Sim | `CheckConstraint(hora_abertura < hora_fechamento)`. |

#### `PontoColetaResponsavel` (app `pontos_coleta`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `ponto_coleta` | FK (`PontoColeta`, `PROTECT`) | Sim | |
| `usuario` | FK (`Usuario`, `PROTECT`, indexado) | Sim | Usuário pessoa física com conta ativa (RF001). |
| `status` | TextChoices | Sim | `convite_pendente`, `ativo`, `recusado`, `inativo`. O responsável inicial nasce `ativo`; demais nascem `convite_pendente` e só obtêm acesso de gestão quando aceitam (`ativo` — [ADR 0010](../adr/0010-perfis-e-permissoes.md)). |
| `convidado_por` | FK (`Usuario`, `PROTECT`, anulável) | Não | Preenchido em vínculos criados por convite. |
| `vinculado_em` / `desvinculado_em` | Datetime | Sim / Não | Mantém histórico de vínculos. |

**Constraint:** `UniqueConstraint(fields=["ponto_coleta", "usuario"], condition=Q(status__in=["convite_pendente", "ativo"]))` (evita convite ou vínculo ativo duplicado para a mesma pessoa no mesmo ponto).

### 6.2 Status e transições (no escopo do RF005)

| Origem | Destino | Condição | Quem dispara |
| --- | --- | --- | --- |
| *(novo)* | `pendente_aprovacao` | Cadastro válido com CNPJ único, endereço, horários e responsável autenticado | Usuário autenticado (`RF005`) |
| `ativo` | `pendente_aprovacao` | Alteração de endereço de ponto já ativo pelo responsável (submete o novo endereço à reaprovação; agendamentos futuros seguem tratamento do RF007 regra 3) | Responsável ativo (`RF005`) |
| `ativo` / `pendente_aprovacao` | `inativo` | Inativação voluntária pelo responsável ativo (*acréscimo da especificação*, mesmos efeitos de cancelamento/aviso do RF007 regra 3; reativação exclusiva do Administrador) | Responsável ativo (`RF005`) |

*(As transições administrativas `pendente_aprovacao -> ativo / reprovado` e `ativo <-> suspenso / inativo`, bem como a reativação de ponto inativado, são especificadas na Spec `07` — RF007, condicionadas ao envio de documentos da Spec `06` — RF006.)*

### 6.3 Histórico obrigatório (RNF14 / [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md))

Eventos gravados via `AuditoriaService.registrar(...)`: `ponto_coleta.cadastrado`, `ponto_coleta.alterado` (lista de campos modificados), `ponto_coleta.remetido_reaprovacao` (quando altera endereço de ponto ativo), `ponto_coleta.inativado_responsavel`, `ponto_coleta.cnpj_alterado` (com motivo e ator Admin), `ponto_coleta.responsavel_convidado`, `ponto_coleta.responsavel_convite_aceito`, `ponto_coleta.responsavel_convite_recusado` e `ponto_coleta.responsavel_desvinculado`.

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

### 7.1 Camada de entrada (Views e Forms)

| Componente | App | Métodos | Acesso | Responsabilidade |
| --- | --- | --- | --- | --- |
| `PontoColetaCadastrarView` + `PontoColetaForm` + `HorarioFuncionamentoFormSet` | `pontos_coleta` | `GET`, `POST` | Autenticado (`ativo`, confirmado) | Renderiza o cadastro de instituição com os dados do responsável autenticado em somente leitura, valida formato, chama `PontoColetaService.cadastrar(...)` e redireciona (PRG) para o passo 2 (`pontos_coleta:documentos`, Spec 06). |
| `MeusPontosColetaView` | `pontos_coleta` | `GET` | Autenticado (`ativo`, confirmado) | Lista pontos onde o usuário possui vínculo `ativo` ou `convite_pendente` (em qualquer status do ponto). |
| `PontoColetaEditarView` + `PontoColetaEditarForm` | `pontos_coleta` | `GET`, `POST` | Responsável com vínculo ativo no ponto | Exibe CNPJ somente leitura (excluído de `Meta.fields`), valida formato, chama `PontoColetaService.atualizar(...)` e redireciona (PRG). |
| `PontoColetaInativarView` | `pontos_coleta` | `POST` | Responsável com vínculo ativo no ponto | *Acréscimo da especificação*: inativa voluntariamente o ponto (`status = inativo`) com confirmação explícita e CSRF, via `PontoColetaService.inativar_pelo_responsavel(...)`. |
| `PontoColetaResponsaveisView` + `ConvidarResponsavelForm` | `pontos_coleta` | `GET`, `POST` | Responsável com vínculo ativo no ponto | Lista responsáveis (`ativo` e `convite_pendente`) e permite enviar convite ou desvincular via `PontoColetaService`. |
| `PontoColetaConviteResponderView` | `pontos_coleta` | `POST` | Usuário convidado autenticado (`ativo`, confirmado) | Permite aceitar ou recusar convite pendente para ser responsável de um ponto via `PontoColetaService.responder_convite(...)`. |
| `PontoColetaListaPublicaView` + `PontoColetaFiltroPublicoForm` | `pontos_coleta` | `GET` | Público / Autenticado | Pesquisa apenas pontos com `status = ativo` (nome fantasia, tipo, município). |
| `AdminPontoColetaListaView` + `AdminPontoColetaFiltroForm` | `pontos_coleta` | `GET` | `aprovacao_pontos_coleta` (+ 2FA) | Pesquisa pontos em todos os status por CNPJ, razão social, nome fantasia, tipo, município e status. |
| `AdminPontoColetaAlterarCnpjView` + `AdminAlterarCnpjForm` | `pontos_coleta` | `POST` | `aprovacao_pontos_coleta` (+ 2FA) | Altera CNPJ com motivo obrigatório via `PontoColetaService.alterar_cnpj(...)`. |

### 7.2 Camada de regra de negócio (Services)

| Service e método | App | Transacional? | Entradas / saídas e regras aplicadas |
| --- | --- | --- | --- |
| `PontoColetaService.cadastrar(usuario, dados, horarios)` | `pontos_coleta` | **Sim** (`transaction.atomic`) | Aplica `RN-05-01` a `RN-05-08`: valida CNPJ único, cria `PontoColeta` (`pendente_aprovacao`), horários sem sobreposição, vínculo inicial `status = ativo` em `PontoColetaResponsavel`, obtém coordenadas aproximadas do `CacheCep` e grava `ponto_coleta.cadastrado` na auditoria. |
| `PontoColetaService.atualizar(ponto_id, usuario, dados, horarios)` | `pontos_coleta` | **Sim** (`transaction.atomic`) | Confere vínculo `status = ativo` do `usuario` na consulta (404 caso contrário), bloqueia mudança de CNPJ, valida horários, atualiza campos; se o ponto era `ativo` e o endereço mudou, retorna `status` para `pendente_aprovacao` (com tratamento de agendamentos futuros do RF007 regra 3 e aviso) e grava `ponto_coleta.alterado` / `ponto_coleta.remetido_reaprovacao` na auditoria. |
| `PontoColetaService.inativar_pelo_responsavel(ponto_id, usuario)` | `pontos_coleta` | **Sim** (`transaction.atomic` + `select_for_update`) | *Acréscimo da especificação*: confere vínculo `status = ativo`, altera `status` do ponto para `inativo`, aplica os mesmos efeitos de tratamento/aviso sobre agendamentos futuros do RF007 regra 3 e grava `ponto_coleta.inativado_responsavel` na auditoria. |
| `PontoColetaService.alterar_cnpj(ator, ponto_id, novo_cnpj, motivo)` | `pontos_coleta` | **Sim** (`transaction.atomic`) | Confere função `aprovacao_pontos_coleta` (+ 2FA), exige motivo obrigatório, valida dígitos e unicidade do novo CNPJ, atualiza e grava `ponto_coleta.cnpj_alterado` na auditoria. |
| `PontoColetaService.convidar_responsavel(ponto_id, ator, identificador_usuario)` / `responder_convite(convite_id, usuario, aceitar)` / `desvincular_responsavel(ponto_id, ator, responsavel_id)` | `pontos_coleta` | **Sim** (`transaction.atomic` + `select_for_update`) | Confere vínculo `status = ativo` do ator; ao convidar, exige conta `ativo` com e-mail confirmado, cria vínculo `convite_pendente` e notifica o convidado via `NotificacaoService`; o convidado ativa ou recusa explicitamente; ao desvincular, garante que reste ao menos 1 responsável `ativo` no ponto; grava cada evento na auditoria. |
| `PontoColetaService.pesquisar(ator, filtros, apenas_ativos=True)` | `pontos_coleta` | Não (leitura) | Aplica filtros de pesquisa do RF005 respeitando visibilidade (`status = ativo` para busca pública/usuários; todos os status apenas para `aprovacao_pontos_coleta`). |

### 7.3 Interface (Templates)

- **`templates/pontos_coleta/ponto_cadastrar.html`** (fiel a [Cadastro Pessoa Jurídica.png](../prd/telas/Cadastro%20Pessoa%20Jur%C3%ADdica.png)):
  - Logo ReMed, título **"Parceria ReMed"**, subtítulo **"Cadastro de instituição / ponto de coleta"** e abas (`"Pessoa Física · Doador / Solicitante"` e `"Pessoa Jurídica · Ponto de Coleta"` ativa).
  - Banner informativo: `"Cadastro com responsável autenticado: o ponto será vinculado à sua conta ReMed já cadastrada. Não é necessário criar uma senha para a instituição."`.
  - Seção **Dados da instituição** (`CNPJ *`, `Razão social *`, `Nome fantasia *`, `Tipo de estabelecimento *`, `E-mail institucional *`, `Telefone *`).
  - Seção **Endereço do ponto de coleta** (`CEP *` + `"Não sei meu CEP"`, `Logradouro *`, `Número *`, `Bairro *`, `Município *`, `Estado *`, `Complemento (opcional)`) + aviso verde `"O endereço do ponto de coleta é público e será exibido para orientar os encontros de retirada."`.
  - Seção **Funcionamento e estrutura**: caixas `Seg` a `Dom`, `Abertura *` e `Fechamento *` (`hh:mm`), `"+ Adicionar outro horário"` (JS simples — [ADR 0006](../adr/0006-javascript-simples-sem-framework.md)), rádio `"Possui refrigeração para medicamentos? *"` (`Sim`/`Não`) e aviso `"O ponto de coleta é apenas um local seguro de encontro para a retirada, não um local de guarda temporária de medicamentos."`.
  - Seção **Documentação e observações**: aviso indicando que o envio dos documentos obrigatórios ocorre imediatamente na etapa seguinte (fluxo contínuo de dois passos com o RF006) + `Observações (opcional)`.
  - Seção **Responsável pelo ponto de coleta**: cartão `"Sua conta ReMed"` com etiqueta `"Usuário vinculado · autenticado"` exibindo CPF, Nome, E-mail e Contato somente leitura + `"+ Adicionar outro responsável"` (`"Envia convite para uma conta ReMed já cadastrada; o vínculo só fica ativo após aceite"`).
  - Aviso `"Status inicial automático: Pendente de aprovação. O administrador analisará os documentos. O ponto de coleta só será ativado após a aprovação do cadastro."`, nota `"A data do cadastro é registrada automaticamente pelo sistema."`, botão primário **Cadastrar ponto de coleta e avançar para documentos** e link `"Voltar para minha conta"`.
- Demais templates: `ponto_meus.html` (inclui seção de convites pendentes com ações Aceitar/Recusar e ação de inativação voluntária com confirmação), `ponto_editar.html` (CNPJ somente leitura e aviso sobre reaprovação ao alterar endereço de ponto ativo), `ponto_responsaveis.html`, `ponto_lista_publica.html` e `admin_ponto_lista.html`.

### 7.4 Rotas

| Nome da URL | Caminho proposto | Propósito |
| --- | --- | --- |
| `pontos_coleta:cadastrar` | `/pontos-coleta/cadastrar/` | Exibir e processar cadastro de novo ponto de coleta (passo 1). |
| `pontos_coleta:meus_pontos` | `/pontos-coleta/meus/` | Listar pontos sob gestão e convites pendentes do usuário autenticado. |
| `pontos_coleta:editar` | `/pontos-coleta/<int:ponto_id>/editar/` | Editar dados do ponto (exceto CNPJ) pelo responsável ativo. |
| `pontos_coleta:inativar` | `/pontos-coleta/<int:ponto_id>/inativar/` | Inativação voluntária do ponto pelo responsável ativo (`POST` — *acréscimo da especificação*). |
| `pontos_coleta:responsaveis` | `/pontos-coleta/<int:ponto_id>/responsaveis/` | Gerenciar convites e vínculos de responsáveis do ponto. |
| `pontos_coleta:convite_responder` | `/pontos-coleta/convites/<int:convite_id>/responder/` | Aceitar ou recusar convite de responsabilidade (`POST`). |
| `pontos_coleta:lista_publica` | `/pontos-coleta/` | Consultar pontos de coleta **ativos**. |
| `pontos_coleta:admin_lista` | `/admin-remed/pontos-coleta/` | Pesquisa administrativa de pontos em qualquer status. |
| `pontos_coleta:admin_alterar_cnpj` | `/admin-remed/pontos-coleta/<int:ponto_id>/cnpj/` | Alteração de CNPJ restrita à função `aprovacao_pontos_coleta` (`POST`). |

---

## 8. Mensagens e validações

O catálogo do RF005 não traz tabela própria de textos literais; aplicam-se RNF01/RNF02 com consistência ao RF001:
- Campos obrigatórios vazios: `"Campo(s) obrigatório(s) não preenchido(s)"` destacando os campos;
- CNPJ inválido / horário inválido / formato incorreto: `"Campo preenchido incorretamente"` com instrução específica;
- CNPJ duplicado: `"CNPJ já cadastrado"`;
- Sucesso no passo 1 do cadastro: `"Ponto de coleta cadastrado com sucesso. Envie os documentos obrigatórios para análise."` (redirecionando imediatamente para o envio de documentos do RF006).
- Alteração de endereço de ponto ativo: `"Endereço atualizado. O ponto retornou para Pendente de aprovação até nova conferência do Administrador."`
- Inativação voluntária pelo responsável: `"Ponto de coleta inativado. Para reativá-lo futuramente, solicite reativação ao Administrador."`

---

## 9. Segurança e privacidade

| Requisito | Perigo resumido | Categoria OWASP 2025 | Controle aplicado nesta spec |
| --- | --- | --- | --- |
| **RS011** | Estabelecimento falso ou irregular aparecer para usuários | A01, A06, A09 | CNPJ validado e único no PostgreSQL; status inicial obrigatório `pendente_aprovacao`; ocultação estrita de pontos não `ativos` para doadores/solicitantes; CNPJ inalterável pelo representante; histórico imutável (`AuditoriaService`). |
| **RS008** | Encontro em local inseguro ou acesso cruzado entre instituições | A01, A06 | Priorização de pontos aprovados com endereço público claro e horários estruturados; checagem por objeto em `PontoColetaService` garantindo que um representante nunca veja nem edite ponto de outra instituição (404). |

---

## 10. Requisitos não funcionais aplicáveis

| ID | Exigência aplicada a esta spec |
| --- | --- |
| **RNF01–RNF03** | Formulário estruturado em seções claras, rótulos visíveis, dicas e conformidade WCAG 2.1 AA (inclusive blocos dinâmicos de horário operáveis por teclado). |
| **RNF04** | Pesquisa de pontos de coleta e consulta de CEP respondem em até 3 s (p95). |
| **RNF07–RNF08** | Layout responsivo (*mobile first*) com Bootstrap local e JS simples (funciona sem JS com ao menos um bloco de horário e preenchimento manual de endereço). |
| **RNF11** | Aviso explícito de que não há guarda temporária de medicamentos nesta versão. |
| **RNF12** | Integração com webservice de CEP (`CepService` — [ADR 0018](../adr/0018-consulta-de-cep.md)). |
| **RNF14** | Histórico imutável de criação, alterações, troca de CNPJ e vínculos de responsáveis em `RegistroAuditoria`. |

---

## 11. Critérios de aceite

1. **CA-05-01 (Cadastro válido nasce pendente e abre envio de documentos — RN-05-01..RN-05-07):** Dado um usuário autenticado (`ativo`, e-mail confirmado) que informa CNPJ válido inédito, razão social, nome fantasia, tipo de estabelecimento, contatos, endereço, ao menos um bloco de dia/horário válido e refrigeração, quando submete o cadastro, então o `PontoColeta` é criado com `status = pendente_aprovacao`, vínculo inicial `status = ativo` criado em `PontoColetaResponsavel`, evento `ponto_coleta.cadastrado` gravado na auditoria, o usuário é redirecionado para a etapa de envio de documentos (RF006) e o ponto **não aparece** em `pontos_coleta:lista_publica`.
2. **CA-05-02 (Unicidade e dígitos do CNPJ — RN-05-01):** Dado um CNPJ com dígito verificador inválido ou já cadastrado, quando o usuário submete, então o cadastro é rejeitado e nenhum registro é criado.
3. **CA-05-03 (Pré-condição de responsável autenticado — RF005):** Dado um visitante não autenticado acessando `pontos_coleta:cadastrar`, então é redirecionado para `contas:login`.
4. **CA-05-04 (Alteração por responsável ativo bloqueando CNPJ e reaprovação de endereço — RN-05-07, RN-05-08):** Dado um responsável com vínculo `status = ativo` editando seu ponto, quando salva, então os dados permitidos são atualizados, o CNPJ permanece inalterado (mesmo se adulterado no `POST`) e `ponto_coleta.alterado` é gravado na auditoria; se o ponto era `ativo` e o endereço foi alterado, o status volta a `pendente_aprovacao` (tratando agendamentos futuros conforme RF007 regra 3) e `ponto_coleta.remetido_reaprovacao` é gravado; se o vínculo estiver `convite_pendente`, `recusado` ou `inativo`, ou pertencer a outro usuário, recebe HTTP 404.
5. **CA-05-05 (Alteração de CNPJ exclusiva da função `aprovacao_pontos_coleta` — RN-05-08):** Dado um Administrador com `aprovacao_pontos_coleta` (+ 2FA) alterando o CNPJ com motivo obrigatório e novo CNPJ válido inédito, então o CNPJ é atualizado e `ponto_coleta.cnpj_alterado` é gravado na auditoria; qualquer outro perfil (ou Admin sem `aprovacao_pontos_coleta`) recebe HTTP 403.
6. **CA-05-06 (Convite de responsável e proteção contra ponto órfão — RN-05-07):** Dado um ponto de coleta com 1 responsável `ativo`, quando convida outro usuário `ativo` e confirmado, então o vínculo nasce `convite_pendente` (sem acesso de gestão ainda) e só passa a `ativo` após aceite explícito do convidado; enquanto houver apenas 1 responsável `ativo`, tentar desvinculá-lo é recusado; com 2 responsáveis `ativos`, um pode ser desvinculado e imediatamente perde acesso às telas de gestão do ponto.
7. **CA-05-07 (Pesquisa respeitando visibilidade — RN-05-05):** Dado um ponto `pendente_aprovacao` e um ponto `ativo`, quando um doador/solicitante pesquisa em `pontos_coleta:lista_publica`, então vê apenas o ponto `ativo`; quando o Administrador pesquisa em `pontos_coleta:admin_lista` filtrando por CNPJ, razão social, nome fantasia, tipo, município ou status, vê ambos.
8. **CA-05-08 (Inativação voluntária pelo responsável e proibição de exclusão física — RN-05-09, *acréscimo da especificação*):** Dado um responsável com vínculo `ativo` acionando `pontos_coleta:inativar` com confirmação e CSRF, então o ponto passa para `status = inativo` (aplicando os efeitos de RF007 regra 3 sobre agendamentos futuros), sai da lista pública e não pode ser reativado pelo responsável (apenas pelo Administrador no RF007); não há endpoint de exclusão física e `on_delete=PROTECT` impede exclusão em cascata no banco.

---

## 12. Plano de testes

*(Executor: `python manage.py test` contra PostgreSQL — [ADR 0012](../adr/0012-ferramentas-teste-formatacao-lint-e-seguranca.md). Sem código de aplicação.)*

### 12.1 Testes de unidade (Models, Forms e Services — sem `request`)

- Constraints PostgreSQL: `UniqueConstraint` em `cnpj`, `CheckConstraint` de `hora_abertura < hora_fechamento` e `0 <= dia_semana <= 6`, `UniqueConstraint` parcial em `PontoColetaResponsavel(ponto_coleta, usuario)` onde `status in ("convite_pendente", "ativo")`, `on_delete=PROTECT` e migração de dados dos 6 tipos iniciais em `TipoEstabelecimento`.
- Forms: validação de CNPJ válido/inválido (inclusive dígitos repetidos), horários sobrepostos ou invertidos, campos obrigatórios e exclusão de `cnpj` e `status` no `PontoColetaEditarForm`.
- `PontoColetaService`: criação atômica com status `pendente_aprovacao` + auditoria; edição bloqueando mudança de CNPJ, verificando vínculo `ativo` e retornando ponto `ativo` para `pendente_aprovacao` quando o endereço muda; inativação voluntária pelo responsável (*acréscimo da especificação*) com auditoria; alteração de CNPJ apenas por `aprovacao_pontos_coleta` com motivo obrigatório; convite de segundo responsável (recusando conta inativa/não confirmada, bloqueando gestão antes do aceite, ativando após aceite) e recusa ao desvincular o último responsável ativo; pesquisa respeitando `apenas_ativos`.

### 12.2 Testes de integração (Views, rotas e permissões)

- Visitante em `pontos_coleta:cadastrar`, `meus_pontos`, `editar`, `inativar`, `responsaveis` e `convite_responder` redirecionado para login.
- Usuário autenticado cadastra ponto, é redirecionado para o passo 2 de documentos (RF006), vê o ponto em `meus_pontos` como `"Pendente de aprovação"`, mas o ponto não aparece em `lista_publica`.
- Outro usuário (ou usuário com `convite_pendente`, ou ex-responsável com vínculo `inativo`) recebe HTTP 404 ao tentar acessar `editar`, `inativar` ou `responsaveis` de um ponto; após aceitar o convite em `convite_responder`, passa a acessar normalmente.
- `admin_lista` e `admin_alterar_cnpj` exigem função `aprovacao_pontos_coleta` + 2FA concluído (HTTP 403 para demais perfis, outros Admins sem a função e `is_superuser` sem função explícita).

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Guarda temporária de medicamentos pela instituição (RF005 Observação, RNF11):** fora de escopo nesta versão; depende de definição futura com o cliente e validação legal. | Restrição registrada na fonte (PRD seção 2.5) | Não bloqueia o MVP; o ponto permanece exclusivamente local seguro de encontro para retirada. |
