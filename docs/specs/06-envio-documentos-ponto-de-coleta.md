# Spec 06 — Envio de Documentos do Ponto de Coleta (RF006)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `06` — Envio de Documentos do Ponto de Coleta (`RF006`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF006 (Importante — **MVP ⬆**, HU06). **Não funcionais:** RNF01, RNF02, RNF03, RNF04, RNF07, RNF08, RNF14 (Essencial), RNF15, RNF16. **Segurança:** RS011, RS013. |
| **Apps envolvidos** | `pontos_coleta` (principal: `DocumentoPontoColeta`, `DocumentoPontoService`), `nucleo` (`TipoDocumentoPonto` em cadastro auxiliar, **`ArquivoService`** — validação, `Pillow >= 12.0`, interface antimalware, storage S3/privado, URL pré-assinada 60 s — e `ExecucaoRotina`), `auditoria` (`AuditoriaService` — registro de envio **e de leitura** de arquivos), `notificacoes` (`NotificacaoService` — aviso antes do vencimento). |
| **Dependências de outras specs** | **[01-cadastro-de-usuario.md](01-cadastro-de-usuario.md) (`RF001`)**, **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002`)**, **[03-notificacoes.md](03-notificacoes.md) (`RF017`)** e **[05-cadastro-de-ponto-de-coleta.md](05-cadastro-de-ponto-de-coleta.md) (`RF005`)**. Articula-se com **[07-aprovacao-ponto-de-coleta.md](07-aprovacao-ponto-de-coleta.md) (`RF007`)** (que aprova/reprova os documentos) e com **RF018** (ainda não escrita — tratamento de agendamentos futuros quando um documento vence e devolve o ponto a `pendente_aprovacao`). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0004](../adr/0004-pip-venv-requirements-fixado.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0010](../adr/0010-perfis-e-permissoes.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0014](../adr/0014-rotinas-agendadas.md), [0015](../adr/0015-notificacoes-email-e-plataforma.md), [0016](../adr/0016-armazenamento-seguro-de-arquivos.md), [0019](../adr/0019-hospedagem-implantacao-e-backup.md). |

---

## 2. Objetivo e escopo

Permitir que responsáveis com vínculo ativo em um ponto de coleta enviem, substituam (por versionamento) e acompanhem os documentos que comprovam a regularidade do estabelecimento (**licença de funcionamento** e **alvará sanitário**), introduzindo o **`ArquivoService`** em `nucleo` conforme a [ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md).

### Inclui

- Implantação do **`ArquivoService`** em `nucleo` ([ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md)): validação de tamanho (máx. **5 MB**), extensão e assinatura real (*magic bytes*) para `PDF`, `JPG` e `PNG`, reprocessamento de imagens via **`Pillow >= 12.0`** removendo metadados EXIF/GPS, **interface de scanner antimalware** no MVP (`clamd` ativado na implantação), gravação com **nome interno aleatório (UUID)** em Object Storage privado S3-compatível com SSE (`django-storages` + `boto3`, ou pasta privada em desenvolvimento), e entrega exclusiva por rota autenticada gerando **URL pré-assinada de 60 segundos** com registro obrigatório de envio e leitura na auditoria (RS013 solução 5).
- Entrada de `Pillow` (`>= 12.0`), `django-storages` e `boto3` no `requirements.txt` (fixados por `==` e validados no Python 3.14 — [ADR 0004](../adr/0004-pip-venv-requirements-fixado.md)).
- Cadastro auxiliar `TipoDocumentoPonto` em `nucleo` (`Licença de funcionamento` e `Alvará sanitário` como obrigatórios iniciais, extensível).
- Envio dos documentos obrigatórios como **Passo 2 contínuo** após o RF005, substituição (nova versão) de documento `reprovado` ou `vencido` mantendo o histórico imutável das versões anteriores (nunca há exclusão física).
- Rotina diária agendada (`manage.py verificar_documentos_pontos`, [ADR 0014](../adr/0014-rotinas-agendadas.md)) que: (a) notifica os responsáveis antes do vencimento (`documento_prestes_vencer`, RF017); e (b) marca documentos expirados como `vencido` e devolve o ponto para `pendente_aprovacao` (RF007).
- Consulta de documentos pelo responsável ativo do ponto e pesquisa pelo Administrador (`aprovacao_pontos_coleta` + 2FA) por **ponto de coleta, tipo, status e data de validade**.

### Não inclui

- Aprovação ou reprovação do documento e do ponto de coleta (Spec `07` — RF007).
- Ativação do daemon ClamAV (`clamd`) em desenvolvimento local (ativado na implantação — [ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md)).
- Exibição de documentos de pontos de coleta a doadores, solicitantes ou visitantes (expressamente proibida — RF006 regra 5, RS013).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Responsável com vínculo ativo no ponto** (`PontoColetaResponsavel.status == ativo`) | Enviar licença de funcionamento e alvará sanitário; acompanhar status/versões; enviar nova versão para documento `reprovado` ou `vencido`; visualizar seus próprios documentos enviados. | Ponto cadastrado (RF005), sessão autenticada (RF002) e vínculo **ativo** no ponto ([ADR 0010](../adr/0010-perfis-e-permissoes.md)). |
| **Administrador (`aprovacao_pontos_coleta`)** | Pesquisar documentos por ponto, tipo, status e validade e abrir os arquivos enviados (URL pré-assinada de 60 s) para análise (RF007). | Conta administrativa ativa com `aprovacao_pontos_coleta` e 2FA TOTP concluído. |
| **Sistema (rotina diária)** | Avisar responsáveis sobre documentos prestes a vencer e marcar documentos expirados como `vencido`, devolvendo o ponto a `pendente_aprovacao`. | Agendamento via [ADR 0014](../adr/0014-rotinas-agendadas.md). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Envio de documento obrigatório (Passo 2 após RF005)

1. O responsável ativo acessa a tela de documentação do ponto (`pontos_coleta:documentos`, aberta automaticamente ao salvar o RF005).
2. Seleciona o **Tipo de documento** (`Licença de funcionamento` ou `Alvará sanitário`), informa o **Número do documento**, a **Data de validade** (`dd/mm/aaaa`) e seleciona o **Arquivo** (`PDF`, `JPG` ou `PNG`, até 5 MB), acionando **Enviar documento** (`POST` com CSRF e `multipart/form-data`).
3. A view valida o formato inicial no `DocumentoPontoForm` e chama `DocumentoPontoService.enviar(...)`.
4. Dentro de `transaction.atomic()`, `DocumentoPontoService.enviar(...)`:
   - Valida vínculo ativo do ator no ponto (404 caso contrário);
   - Rejeita data de validade anterior à data atual (`"Documento vencido. Envie um documento válido"`);
   - Chama `ArquivoService.armazenar_privado(...)` (verifica ≤ 5 MB, extensão, *magic bytes*, remove EXIF/GPS em imagens via `Pillow`, chama a interface antimalware e grava com nome UUID no storage privado S3/local);
   - Cria nova versão de `DocumentoPontoColeta` com `versao` incremental (`1`, `2`, ...), `status = enviado` (ou `em_analise` quando ambos os documentos obrigatórios estiverem enviados, liberando o ponto na fila do RF007);
   - Registra `documento_ponto.enviado` (e `arquivo.enviado`) via `AuditoriaService`.
5. A view redireciona (PRG) exibindo `"Documento enviado com sucesso. O cadastro está em análise"`.

### 4.2 Fluxos alternativos

- **FA-01 — Substituição por nova versão (documento `reprovado` ou `vencido`):** o responsável ativo envia novo arquivo/validade para o mesmo tipo; o registro anterior **não é excluído** (permanece no histórico com quem enviou, data e hora), e o novo registro nasce com `versao = anterior + 1` e `status = enviado`/`em_analise`, recolocando o ponto na fila de análise do RF007.
- **FA-02 — Visualização segura do arquivo (`pontos_coleta:documento_baixar`):** responsável ativo do ponto ou Administrador com `aprovacao_pontos_coleta` (+ 2FA) solicita a visualização; `DocumentoPontoService.gerar_acesso_temporario(...)` confere permissão por objeto, registra `arquivo.acessado` na auditoria (RS013 solução 5) e redireciona para URL pré-assinada de **60 segundos** ([ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md)).
- **FA-03 — Rotina diária de vencimento de documentos (`manage.py verificar_documentos_pontos`):**
  1. Adquire `pg_try_advisory_lock` e registra execução em `ExecucaoRotina` ([ADR 0014](../adr/0014-rotinas-agendadas.md));
  2. Identifica documentos `aprovado` com vencimento próximo (**30 dias antes**, configurável via `PONTO_DOC_AVISO_VENCIMENTO_DIAS` em `settings`) ainda não avisados e dispara notificação `documento_prestes_vencer` aos responsáveis ativos (RF017);
  3. Identifica documentos `aprovado` com `data_validade < hoje` sem versão mais nova aprovada, muda o status do documento para `vencido`, devolve o `PontoColeta` (se `ativo`) para `pendente_aprovacao` aplicando o mesmo tratamento do RF007 regra 3 sobre agendamentos futuros (cancela agendamentos futuros mantendo a correspondência aceita/reservada e reiniciando o prazo de expiração da reserva da ADR 0013, com aviso às duas partes — RF018/RF017), grava auditoria e notifica os responsáveis ativos.

### 4.3 Fluxos de exceção

- **FE-01 — Formato inválido (ou extensão falsificada detectada por *magic bytes*):** rejeita exibindo `"Envie o arquivo em PDF, JPG ou PNG"`.
- **FE-02 — Arquivo acima de 5 MB:** rejeita exibindo `"O arquivo deve ter no máximo 5 MB"`.
- **FE-03 — Data de validade anterior à data atual:** rejeita exibindo `"Documento vencido. Envie um documento válido"`.
- **FE-04 — Scanner antimalware acusa ameaça ou falha (quando ativo na implantação):** rejeita o upload (*fail-closed*), não grava no storage e registra alerta/evento em log estruturado.
- **FE-05 — Doador, solicitante, ex-responsável inativo ou Admin sem `aprovacao_pontos_coleta` tenta acessar o documento:** recebe HTTP 404 (usuário comum/outro representante) ou HTTP 403 (Admin sem a função).

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-06-01** | Os tipos obrigatórios iniciais são **Licença de funcionamento** e **Alvará sanitário** (cadastro auxiliar `TipoDocumentoPonto` em `nucleo`, extensível). O ponto de coleta **só segue para análise do Administrador (RF007) após o envio dos documentos obrigatórios**. | RF006 (regra 1), RS011 • `nucleo`, `pontos_coleta` |
| **RN-06-02** | Todo arquivo enviado deve ter extensão e assinatura (*magic bytes*) verificadas (`PDF`, `JPG` ou `PNG`), tamanho máximo de **5 MB**, limpeza de EXIF/GPS em imagens (`Pillow >= 12.0`), passagem pela interface antimalware (`clamd` na implantação), nome interno aleatório (UUID) em storage privado criptografado (SSE) e acesso somente por link temporário de **60 segundos** autenticado. | RF006 (regra 2), RNF08, RNF16, RS013, [ADR 0016](../adr/0016-armazenamento-seguro-de-arquivos.md) • `nucleo`, `pontos_coleta` |
| **RN-06-03** | Não se aceita documento com data de validade anterior à data atual (`data_validade >= hoje` é aceito; `< hoje` exibe `"Documento vencido. Envie um documento válido"`). O representante é avisado **30 dias antes** do vencimento (`PONTO_DOC_AVISO_VENCIMENTO_DIAS` em `settings`, RF017). Vencido o prazo sem renovação aprovada, o documento passa a `vencido`, o ponto volta para `pendente_aprovacao` para nova análise (RF007) e eventuais agendamentos futuros seguem o tratamento do RF007 regra 3 (agendamentos cancelados mantendo a correspondência aceita/reservada, com reinício do prazo de expiração da reserva da ADR 0013 e aviso às partes — RF018/RF017). | RF006 (regra 3), RNF15, [ADR 0014](../adr/0014-rotinas-agendadas.md) • `pontos_coleta`, `correspondencias`, `notificacoes` |
| **RN-06-04** | Status válidos do documento: `enviado`, `em_analise`, `aprovado`, `reprovado` e `vencido`, sempre com histórico imutável (`AuditoriaService`). Aprovação e reprovação são registradas no RF007. | RF006 (regra 4), RNF14, [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `pontos_coleta`, `auditoria` |
| **RN-06-05** | Os documentos ficam visíveis **somente ao responsável ativo do ponto e ao Administrador com `aprovacao_pontos_coleta`** (+ 2FA), **nunca** a doadores ou solicitantes. Cada envio e cada leitura gera registro imutável na auditoria (quem, o quê, data e hora). | RF006 (regra 5), RS013 (soluções 4 e 5), [ADR 0010](../adr/0010-perfis-e-permissoes.md), [ADR 0011](../adr/0011-historico-imutavel-e-auditoria.md) • `pontos_coleta`, `auditoria` |
| **RN-06-06** | Documentos enviados **nunca são excluídos** (`on_delete=PROTECT`). A substituição de um documento `reprovado` ou `vencido` gera uma **nova versão** mantendo a anterior no histórico com autor, data e hora. | RF006 (Alteração, Exclusão), RNF14 • `pontos_coleta` |

---

## 6. Modelo de dados lógico

#### `TipoDocumentoPonto` (app `nucleo` — cadastro auxiliar populado por migração de dados)

| Campo | Tipo lógico | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `nome` | String (100, único) | Sim | Iniciais: `Licença de funcionamento` (`obrigatorio=True`), `Alvará sanitário` (`obrigatorio=True`). |
| `obrigatorio` | Boolean | Sim | |
| `ativo` | Boolean | Sim | |

#### `DocumentoPontoColeta` (app `pontos_coleta`)

| Campo | Tipo lógico | Obrigatório | Observação / constraints |
| --- | --- | --- | --- |
| `id` | Inteiro (PK) | Sim | |
| `ponto_coleta` | FK (`PontoColeta`, `PROTECT`, indexado) | Sim | |
| `tipo_documento` | FK (`TipoDocumentoPonto`, `PROTECT`) | Sim | |
| `versao` | PositiveInteger | Sim | Sequencial por `(ponto_coleta, tipo_documento)`; `UniqueConstraint(ponto_coleta, tipo_documento, versao)`. |
| `arquivo_chave` | String (255, único) | Sim | Chave aleatória UUID no storage privado (`pontos_coleta/<uuid>.<ext>`). |
| `mime_verificado` / `tamanho_bytes` | String (60) / PositiveInteger | Sim | `CheckConstraint(tamanho_bytes <= 5242880)`. |
| `numero_documento` | String (80) | Sim | |
| `data_validade` | Date (indexado) | Sim | |
| `status` | TextChoices (indexado) | Sim | `enviado`, `em_analise`, `aprovado`, `reprovado`, `vencido`. |
| `enviado_por` | FK (`Usuario`, `PROTECT`) | Sim | Responsável que enviou esta versão. |
| `enviado_em` | Datetime | Sim | |
| `aviso_vencimento_enviado_em` | Datetime, anulável | Não | Garante idempotência da rotina de aviso prévio (ADR 0014). |

### Status e transições

| Origem | Destino | Condição | Quem dispara |
| --- | --- | --- | --- |
| *(novo)* | `enviado` / `em_analise` | Upload válido (`PDF`/`JPG`/`PNG`, ≤ 5 MB, validade válida) | Responsável ativo (`RF006`) |
| `enviado` / `em_analise` | `aprovado` / `reprovado` | Decisão do Administrador | Administrador `aprovacao_pontos_coleta` (`RF007`) |
| `aprovado` | `vencido` | `data_validade < hoje` sem versão mais nova aprovada | Sistema — rotina diária (`RF006`) |

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms/Comandos:** `PontoDocumentoListaEnviarView` + `DocumentoPontoForm` (`pontos_coleta`, responsável ativo), `PontoDocumentoAcessarView` (`pontos_coleta`, responsável ativo ou `aprovacao_pontos_coleta` + 2FA — redireciona para URL pré-assinada 60 s), `AdminDocumentoListaView` (`pontos_coleta`, `aprovacao_pontos_coleta` + 2FA — pesquisa por ponto, tipo, status e validade) e comando `manage.py verificar_documentos_pontos` (`pontos_coleta`).
- **Services:** `ArquivoService` (`nucleo` — `armazenar_privado`, `gerar_url_temporaria`, interface `AntimalwareScanner`), `DocumentoPontoService` (`enviar`, `listar_do_ponto`, `gerar_acesso_temporario`, `pesquisar_admin`, `processar_vencimentos_diarios`).
- **Templates:** `templates/pontos_coleta/ponto_documentos.html` (indicador claro dos 2 documentos obrigatórios, histórico de versões, status em etiqueta texto+cor, formulário de envio/substituição com limite `5 MB` e formatos `PDF, JPG ou PNG` visíveis) e `templates/pontos_coleta/admin_documento_lista.html`.
- **Rotas:** `pontos_coleta:documentos` (`/pontos-coleta/<int:ponto_id>/documentos/`), `pontos_coleta:documento_acessar` (`/pontos-coleta/documentos/<int:doc_id>/acessar/`), `pontos_coleta:admin_documentos` (`/admin-remed/pontos-coleta/documentos/`).

---

## 8. Mensagens e validações

Textos literais exigidos pela fonte (RF006):

| Condição | Mensagem literal |
| --- | --- |
| Arquivo com formato ou assinatura (*magic bytes*) diferente de PDF, JPG ou PNG | `"Envie o arquivo em PDF, JPG ou PNG"` |
| Arquivo maior que 5 MB | `"O arquivo deve ter no máximo 5 MB"` |
| Data de validade anterior à data atual | `"Documento vencido. Envie um documento válido"` |
| Envio concluído com sucesso | `"Documento enviado com sucesso. O cadastro está em análise"` |

---

## 9. Segurança e privacidade

- **RS011 (OWASP A06/A09):** bloqueio de análise até envio dos 2 documentos obrigatórios; controle automático de vencimento devolvendo o ponto a `pendente_aprovacao`.
- **RS013 (OWASP A01/A04/A05/A08):** validação de conteúdo (*magic bytes* + `Pillow`), limpeza de EXIF/GPS, interface antimalware (*fail-closed* com `clamd` na implantação), nomes UUID fora de diretório público, SSE, URL pré-assinada de 60 s apenas após autorização por objeto/função e registro em `RegistroAuditoria` tanto no envio quanto em **cada leitura**.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** orientações claras de formato/tamanho e status em texto + cor (WCAG 2.1 AA).
- **RNF08 & RNF16:** storage privado criptografado compatível com escala horizontal, 5 MB, assinatura verificada, nome aleatório, link temporário autenticado.
- **RNF14 & RNF15:** histórico imutável de versões/envios/leituras; rotina diária com `pg_try_advisory_lock`, `ExecucaoRotina` e alerta em falha para `gestao_administradores`.

---

## 11. Critérios de aceite

1. **CA-06-01 (Envio válido e fila de análise — RN-06-01, RN-06-02):** Dado um ponto `pendente_aprovacao` e seu responsável ativo, quando envia licença de funcionamento e alvará sanitário válidos (PDF/JPG/PNG ≤ 5 MB, validade válida), então ambos são salvos com nomes UUID, EXIF removido em imagens, `"Documento enviado com sucesso. O cadastro está em análise"` é exibido, `RegistroAuditoria` grava o envio e o ponto fica elegível para análise no RF007.
2. **CA-06-02 (Validações literais — RF006 Mensagens):** Dado arquivo > 5 MB, arquivo `.exe` renomeado para `.pdf` (*magic bytes* inválido) ou data de validade anterior a hoje, então o envio é bloqueado exibindo respectivamente `"O arquivo deve ter no máximo 5 MB"`, `"Envie o arquivo em PDF, JPG ou PNG"` e `"Documento vencido. Envie um documento válido"`.
3. **CA-06-03 (Versionamento sem exclusão — RN-06-06):** Dado um documento `reprovado` ou `vencido`, quando o responsável envia nova versão, então a versão anterior é preservada intacta no histórico e a nova recebe `versao = anterior + 1`.
4. **CA-06-04 (Acesso restrito e auditoria de leitura — RN-06-05, ADR 0016):** Dado um documento enviado, quando um doador, solicitante ou representante de outro ponto acessa `pontos_coleta:documento_acessar`, recebe 404; quando um Admin sem `aprovacao_pontos_coleta` acessa, recebe 403; quando o responsável ativo ou Admin com `aprovacao_pontos_coleta` (+ 2FA) acessa, recebe redirect para URL pré-assinada de 60 s e `arquivo.acessado` é gravado na auditoria.
5. **CA-06-05 (Rotina diária de aviso e vencimento — RN-06-03, ADR 0014):** Dado um documento `aprovado` prestes a vencer, quando `verificar_documentos_pontos` roda, notifica os responsáveis uma única vez (idempotente); dado um documento com `data_validade < hoje`, marca o documento como `vencido`, devolve o ponto `ativo` para `pendente_aprovacao` e registra em `ExecucaoRotina`.

---

## 12. Plano de testes

- **Unidade (`ArquivoService`, `DocumentoPontoService`):** limite exato de 5 MB vs 5 MB + 1 byte; *magic bytes* válidos e falsificados (`.jpg`/`.png`/`.pdf`); remoção de EXIF/GPS com `Pillow`; dublê do scanner antimalware (limpo, infectado, erro *fail-closed*); geração de versão incremental; rotina `verificar_documentos_pontos` com relógio controlado e idempotência.
- **Integração (Views/Permissões):** upload pelo responsável ativo, 404 para outro usuário/vínculo inativo, 403 para Admin sem `aprovacao_pontos_coleta` ou sem 2FA, geração de URL pré-assinada 60 s + registro `arquivo.acessado` em `RegistroAuditoria`, e pesquisa administrativa por ponto/tipo/status/validade.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **Prazo de retenção/eliminação de documentos de pontos de coleta pela Política de Privacidade (LGPD — Questão 8 do PRD):** ainda não definido. | Pendência externa (Cliente / Jurídico) | Não bloqueia o MVP; documentos são preservados com `on_delete=PROTECT` até definição da política de retenção. |
