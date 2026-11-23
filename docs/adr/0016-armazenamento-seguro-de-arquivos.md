# 0016. Armazenamento seguro de arquivos, validação, antimalware e acesso temporário

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RNF08, RNF16, RS013, RS002, RNF10, RF006, RF008, RF013, RF014

## Contexto

Três fluxos do MVP recebem upload de arquivos enviados pelos usuários (todos limitados a **5 MB**):

1. **Documentos de ponto de coleta (RF006 — MVP ⬆):** licença de funcionamento e alvará sanitário (`PDF`, `JPG` ou `PNG`), visíveis apenas ao responsável ativo do ponto e ao Administrador com função `aprovacao_pontos_coleta` (ADR 0010). Não são excluídos (substituição gera nova versão).
2. **Fotos da embalagem do medicamento (RF008 — MVP):** `JPG` ou `PNG`, vinculadas à doação para conferência (RF011) e retirada (RF020), e no futuro enviadas ao serviço de IA (RF009 — v2.0).
3. **Receitas médicas (RF013, RF014 — MVP):** `JPG`, `PNG` ou `PDF`, classificadas como **dado pessoal sensível de saúde** (LGPD — RNF10, RS002): guardadas criptografadas, visíveis apenas à função `verificacao_receitas` (ADR 0010), nunca ao doador nem ao gestor de usuários, e excluídas após o prazo da política de privacidade (Questão 8 do PRD).

Os requisitos não funcionais e de segurança impõem salvaguardas rígidas:

- **RNF08:** armazenamento de arquivos **criptografado**, compatível com servidor em nuvem com **escalabilidade horizontal** (o que inviabiliza disco local isolado em múltiplas instâncias).
- **RNF16 e RS013:** todo arquivo enviado deve ter **tipo, extensão e assinatura (*magic bytes*) verificados** (`JPG`, `PNG` ou `PDF`), limite de 5 MB, **varredura antimalware** antes de ser disponibilizado, **nome interno aleatório** fora de diretório público, **acesso somente por link temporário e autenticado** (sem URL pública direta) e **registro de cada envio e acesso** (quem, o quê, data e hora — ADR 0011).

## Direcionadores da decisão

- Compatibilidade com escalabilidade horizontal (RNF08) e armazenamento criptografado em repouso.
- Validação real de conteúdo (assinatura/*magic bytes*, não apenas extensão ou `Content-Type`) e varredura antimalware antes de disponibilizar o arquivo (RNF16, RS013).
- Nenhuma URL pública permanente; controle rigoroso de acesso por perfil/objeto (ADR 0010) e auditoria obrigatória de envio e leitura (ADR 0011, RS013).
- Proteção contra vazamento de privacidade em imagens (por exemplo, metadados EXIF/GPS de fotos de embalagem — RS002, RS010).
- Manter desenvolvimento local simples, com a mesma interface de `ArquivoService` (ADR 0001).

## Opções consideradas

### 1. Object Storage privado compatível com S3 (`django-storages` + `boto3`, criptografia server-side) + validação de assinatura (`Pillow` 12+ e magic bytes) + ClamAV (`clamd`) + rota autenticada no Django (recomendada)

Em produção, os arquivos ficam em bucket privado S3-compatível com criptografia em repouso habilitada e sem acesso público, identificados apenas por chaves aleatórias (`<categoria>/<uuid>.<ext>`). Em desenvolvimento local, um backend de storage em pasta privada (fora de `static/` e sem rota pública) ou MinIO local implementa a mesma interface de `STORAGES` do Django.

- **Upload (sempre passando pelo `ArquivoService`, já que o limite é 5 MB):**
  1. Valida tamanho (`<= 5 MB`), extensão e assinatura real (*magic bytes*) para `JPG`, `PNG` ou `PDF`.
  2. Para imagens (`JPG`/`PNG`), valida e reprocessa via `Pillow` (`>= 12.0`, com suporte oficial ao Python 3.14), removendo metadados EXIF/GPS (RS002, RS010).
  3. Executa varredura *in-stream* via daemon **ClamAV (`clamd`)** antes de gravar no bucket; se detectado malware ou erro de varredura, rejeita o upload (*fail-closed*).
  4. Grava no bucket privado com nome aleatório e registra o evento de envio na auditoria (ADR 0011).
- **Download/visualização:**
  - O usuário acessa uma rota autenticada do Django; o `ArquivoService` verifica perfil e vínculo com o objeto (ADR 0010), registra a leitura na auditoria (RS013 solução 5 / ADR 0011) e entrega o arquivo por **URL pré-assinada curta** (ex.: 60 s) ou por **stream autenticado pelo Django** (obrigatório caso haja criptografia adicional em nível de aplicação para receitas), sempre com `X-Content-Type-Options: nosniff` e `Cache-Control: no-store`.

- **Prós:**
  - Compatível com escalabilidade horizontal (RNF08) e independente do sistema de arquivos da instância web.
  - Separa fisicamente arquivos privados do servidor web, eliminando risco de acesso direto por URL previsível (RS013).
  - Remoção de EXIF via `Pillow` elimina vazamento acidental de coordenadas GPS nas fotos de embalagem.
  - Ponto único no `ArquivoService` garante autorização por objeto (ADR 0010) e auditoria de leitura (RS013 / ADR 0011).
- **Contras:**
  - Exige provisionar bucket S3-compatível e serviço/sidecar `clamd` na hospedagem (ClamAV consome memória relevante para a base de assinaturas — atenção aos 4 GB mínimos do RNF08).
  - Introduz dependências externas (`django-storages`, `boto3`, `Pillow >= 12.0`, `clamd`) na implementação dos requisitos com upload (RF006, RF008, RF014 — ADR 0004).

### 2. Volume de disco privado compartilhado (NFS/EFS ou disco local) + `X-Accel-Redirect` (Nginx) + ClamAV local

Salvar arquivos em diretório privado fora da raiz pública e delegar o envio de bytes ao Nginx via cabeçalho `X-Accel-Redirect` após autorização e auditoria no Django.

- **Prós:**
  - Dispensa `django-storages`/`boto3` e provedor de Object Storage; baixo custo em servidor único (VPS).
- **Contras:**
  - Disco local **não suporta escalabilidade horizontal** (RNF08); exigir NFS/EFS aumenta complexidade de infraestrutura.
  - Criptografia em repouso e backups de 30 dias (RNF05) dependem de configuração manual do volume.

### 3. Armazenar arquivos como `BinaryField` no PostgreSQL

- **Prós:**
  - Transações e backups unificados no banco de dados.
- **Contras:**
  - Infla rapidamente o PostgreSQL e os backups diários de 30 dias (RNF05), degrada o cache de memória do banco e não é adequado para grandes volumes de arquivos de até 5 MB.

## Decisão

**Opção 1** — Object Storage privado compatível com S3 (`django-storages` + `boto3`), validação rigorosa no upload, interface de antimalware no MVP com `clamd` ativado na implantação, criptografia gerenciada (SSE) + controle de acesso estrito e entrega por URL pré-assinada de 60 segundos.

Regras que passam a valer:

- **Armazenamento em produção:** bucket privado S3-compatível via `django-storages` + `boto3`, sem acesso público, com **criptografia em repouso gerenciada pelo storage (SSE)** — **sem criptografia adicional em nível de aplicação** para receitas (protegidas por SSE, isolamento do bucket privado, controle de acesso estrito da função `verificacao_receitas` da ADR 0010 e auditoria de leitura da ADR 0011). Em desenvolvimento local, `FileSystemStorage` em pasta privada fora de `static/` e sem rota pública.
- **Validação rigorosa no MVP:** todo arquivo passa pelo `ArquivoService` (limite de **5 MB**, extensão permitida conforme o requisito, verificação de assinatura/*magic bytes* para `JPG`, `PNG` ou `PDF`, e reprocessamento de imagens via **`Pillow >= 12.0`** para validar integridade e remover metadados EXIF/GPS — RS002, RS010).
- **Antimalware em duas etapas (RNF16 — "Importante", Questão 17 do PRD):** no **MVP**, implementa-se a **interface do scanner antimalware** no `ArquivoService` (com implementação *no-op* configurável em desenvolvimento e testes via dublê) junto com a validação rigorosa acima; na **implantação**, ativa-se o daemon **ClamAV (`clamd`)** em modo *fail-closed* (rejeitando uploads se detectado malware ou falha do scanner).
- **Nomes aleatórios e entrega por URL pré-assinada de 60 segundos:** arquivos são gravados com chave interna aleatória (`<categoria>/<uuid>.<ext>`), fora de diretório público. Todo download/visualização passa por rota autenticada no Django, onde o `ArquivoService` valida permissão por perfil e vínculo de objeto (ADR 0010), registra o acesso na auditoria imutável (RS013 solução 5, ADR 0011) e redireciona para uma **URL pré-assinada válida por 60 segundos** (configurável em `settings`), com `Content-Disposition` seguro e cabeçalhos contra *sniffing* (`X-Content-Type-Options: nosniff`).
- **Entrada de dependências no `requirements.txt` (ADR 0004):** `Pillow`, `django-storages`, `boto3` e `clamd` **não** são instalados agora; entram com versões fixadas por `==` (e dependências indiretas) apenas na implementação das specs com upload (RF006/RF008) e da implantação.

## Consequências

- Positivas:
  - Atende RNF08, RNF16, RS013 e RS002 com suporte nativo a escalabilidade horizontal e sem sobrecarregar a aplicação web com streaming de bytes.
  - Garante controle de acesso centralizado e trilha de auditoria de envio e leitura de arquivos.
  - Desacoplar a ativação do `clamd` para a implantação evita peso operacional no desenvolvimento local mantendo o contrato pronto no `ArquivoService`.
- Negativas e custos:
  - A URL pré-assinada de 60 segundos é portátil durante sua curta janela de validade caso compartilhada pelo usuário autorizado (mitigado pela expiração de 60 s e pelo registro de auditoria de quem solicitou o acesso).
  - Na implantação em produção, o serviço `clamd` exigirá alocação de RAM adequada (considerar no dimensionamento da ADR 0019).
  - A exclusão definitiva de receitas e fotos após o prazo da política de privacidade (RNF10, Questão 8 do PRD) exigirá rotina agendada coordenada entre banco e storage (ADR 0014).
- Impacto em specs e arquitetura:
  - Condiciona as specs de **RF006**, **RF008**, **RF013**, **RF014** e (na v2.0) **RF009**.

## Como verificar

- Testes rejeitam arquivos acima de 5 MB, extensões não permitidas e arquivos com extensão renomeada cuja assinatura (*magic bytes*) não corresponda a `JPG`, `PNG` ou `PDF`.
- Teste confirma que metadados EXIF/GPS são removidos de imagens enviadas.
- Teste com dublê da interface antimalware confirma rejeição de arquivo infectado e comportamento *fail-closed* quando o scanner está ativo e indisponível (e teste com assinatura EICAR na integração do `clamd` na implantação).
- Testes confirmam que o nome salvo no storage é aleatório, que não existe URL pública direta, que o redirecionamento gera URL pré-assinada com expiração de 60 s e que todo envio e leitura exige perfil/vínculo autorizado (ADR 0010) e gera registro na auditoria (ADR 0011).

## Notas

- **Armazenamento local em desenvolvimento e testes:** em desenvolvimento local, o `ArquivoService` usa `FileSystemStorage` sobre `PRIVATE_STORAGE_ROOT` (`private_media/`, fora de `static/`, no `.gitignore` e sem rota `MEDIA_URL` pública), emitindo link temporário de 60 segundos via token assinado (`django.core.signing.TimestampSigner`) entregue por `FileResponse` com `X-Content-Type-Options: nosniff` e `Cache-Control: no-store`. Nos testes automatizados (`manage.py test`), usa-se diretório temporário isolado por teste (`@override_settings(PRIVATE_STORAGE_ROOT=...)`), testando o adaptador S3 por contrato/dublê. Com isso, na Etapa 5 (RF006/RF008) entra no `requirements.txt` apenas `Pillow >= 12.0`; `django-storages` e `boto3` entram na Etapa 9 (empacotamento/implantação) junto à configuração real do bucket S3.
- **Fonte da compatibilidade do Pillow com Python 3.14:** notas de lançamento oficiais do **Pillow 12.0.0** (lançado em 15/10/2025, `pillow.readthedocs.io`), que anunciam suporte oficial ao **Python 3.14** (removendo suporte ao Python 3.9). A versão exata será validada no `.venv` antes de entrar no `requirements.txt` (ADR 0004).
- **ADRs relacionadas:** [ADR 0004](0004-pip-venv-requirements-fixado.md), [ADR 0010](0010-perfis-e-permissoes.md), [ADR 0011](0011-historico-imutavel-e-auditoria.md), [ADR 0014](0014-rotinas-agendadas.md) e [ADR 0019](0019-hospedagem-implantacao-e-backup.md).
