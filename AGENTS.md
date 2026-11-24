# ReMed — Instruções do Projeto para Agentes

## 1. Sobre o projeto e mapa da documentação

O **ReMed** é uma aplicação web Django para doação e redistribuição responsável de medicamentos dentro da validade, conectando doadores, solicitantes/cuidadores, pontos de coleta e administradores sob requisitos de segurança sanitária e LGPD.

Antes de propor ou alterar qualquer funcionalidade, consulte a documentação oficial (não duplique regras no código nem invente requisitos):

- **PRD e catálogo de requisitos:** `docs/prd/01-remed.md` e `docs/prd/02-catalogo-requisitos.md`
- **Decisões de arquitetura (ADRs do MVP e da v1.1 aceitas (0001–0020); as da v2.0 ainda não foram escritas):** `docs/adr/README.md`
- **Mapa consolidado, apps, convenções e dependências:** `docs/arquitetura.md`
- **Especificações por requisito (Specs 01–23, todas aprovadas):** `docs/specs/` (MVP: `01` a `19`; v1.1: `20` a `22`; v2.0: `23`)

## 2. Hierarquia de decisão

Em caso de conflito, prevalece sempre a ordem:

**ADR (`docs/adr/`) > Spec (`docs/specs/`) > Código existente**

- Em caso de dúvida, conflito entre documentos ou comportamento não especificado, **pare e pergunte ao usuário** antes de implementar.
- Qualquer item que não conste no requisito da fonte deve ser marcado como **"acréscimo da especificação"** e perguntado antes de entrar no código.

## 3. Stack e arquitetura (resumo — detalhes em `docs/arquitetura.md`)

- **Runtime e banco:** Python `3.14`, Django `6.1.3`, PostgreSQL `18` (`psycopg` 3), variáveis de ambiente com `python-dotenv` (`.env.example`).
- **Padrão MVT com camada de service (ADR 0001):**
  - **Views:** apenas CBVs herdando de `django.views.View`, **sem consultas ao ORM** (`Model.objects`, `get_object_or_404`).
  - **Forms:** validação de formato com `Meta.fields` explícito.
  - **Services:** concentram regras de negócio, ORM, `transaction.atomic()`, `select_for_update()` em ordem fixa (ADR 0013), `AuditoriaService` (ADR 0011) e `NotificacaoService` (ADR 0015); **nunca recebem `request` nem `form`**.
  - **Models:** sem regra de negócio em `save()` e sem `signals`; usar `TextChoices`, `UniqueConstraint`, `CheckConstraint` e `on_delete=PROTECT` no histórico.
- **Front-end:** Bootstrap `5.3.9` hospedado em `static/vendor/bootstrap/` + `static/css/remed.css` (**zero CDN externa**, WCAG 2.1 AA) e JavaScript simples em `static/js/` (sem framework JS nem htmx).
- **Apps na raiz do projeto:** `core`, `nucleo`, `contas`, `auditoria`, `notificacoes`, `pontos_coleta`, `medicamentos`, `solicitacoes`, `correspondencias` (MVP) e `moderacao` (v1.1).

## 4. Comandos essenciais (Windows / PowerShell)

```powershell
# Ativar ambiente virtual
.\.venv\Scripts\Activate.ps1

# Lint e verificação de formatação (ADR 0012)
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .

# Auditoria de vulnerabilidades de dependências (ADR 0012)
.venv\Scripts\pip-audit.exe -r requirements.txt

# Checagem do Django e conexão com o PostgreSQL
.venv\Scripts\python.exe manage.py check --database default

# Testes automatizados em PostgreSQL (e cobertura opcional)
.venv\Scripts\python.exe manage.py test --verbosity=2
.venv\Scripts\coverage.exe run manage.py test && .venv\Scripts\coverage.exe report
```

## 5. Regras obrigatórias de trabalho

- **Uma etapa por vez:** implementar apenas a etapa autorizada do plano do MVP e parar ao final para revisão.
- **Aprovação prévia obrigatória:** sempre listar os comandos exatos e aguardar autorização explícita antes de rodar `pip install`, `makemigrations`, `migrate` ou qualquer comando que altere o banco de dados.
- **Primeira migração de usuário:** antes de gerar a primeira migração, mostrar o modelo `contas.Usuario` e esperar aprovação explícita do usuário.
- **Falhas e consistência do banco:** se um comando falhar ou o banco ficar inconsistente, pare e mostre o erro ao usuário; nunca apague migrações, tabelas ou bancos sem autorização.
- **Git:** **nunca** executar `git commit` (nem `git push`); o usuário faz os commits.
- **Segredos e `.env`:** **nunca** abrir, exibir ou registrar o conteúdo de `.env` (nem segredos/senhas); usar apenas `.env.example` como referência. Rodar `manage.py` e os testes lê o `.env` indiretamente, e isso é permitido; o que é proibido é abrir, exibir ou registrar o conteúdo do `.env`.
- **PostgreSQL:** **nunca** criar usuários, senhas ou bancos de dados no PostgreSQL.
- **Dependências:** adicionar somente pacotes previstos no plano (`docs/arquitetura.md`, seção 3.1), com versão fixada por `==` em `requirements.txt` (produção) ou `requirements-dev.txt` (desenvolvimento), e validar com `pip check`.
- **Escopo estrito:** não alterar arquivos fora do escopo da etapa atual; não implementar código fora das specs aprovadas.
- **Pendências externas do professor/cliente:** o agente **não decide** as pendências registradas em `docs/prd/01-remed.md` (seção 8) — em especial **Q4 a Q8, Q10 e Q14** (validade mínima restante, janela de refrigerados, verificador de receitas, política de privacidade/LGPD, critérios de aprovação de pontos e tela de login sem CNPJ). Manter os valores provisórios configuráveis documentados nas specs até confirmação formal.

## 6. Estado atual

- **Concluído:**
  - PRD, 20 ADRs aceitas (`0001`–`0020`), `docs/arquitetura.md` e 23 specs aprovadas (`01`–`23`).
  - **Etapa 0:** base `core/`, `.env.example`, `pyproject.toml`, `requirements-dev.txt`, Bootstrap `5.3.9` local, `templates/base.html`, `static/css/remed.css`, `.github/workflows/ci.yml` e conexão verificada com PostgreSQL `18.4`.
  - **Etapa 1:** base transversal (`nucleo`, `auditoria`, `contas` base com `AUTH_USER_MODEL = "contas.Usuario"`, 8 grupos administrativos, `notificacoes` outbox mínimo, trigger `BEFORE UPDATE OR DELETE` em `auditoria` no PostgreSQL e `argon2-cffi`).
  - **Etapa 2 (Spec 01 — RF001, Cadastro de Usuário):** `nucleo` (`validators.py`, `rate_limit.py`, `CepService` BrasilAPI + ViaCEP com cache, `mixins.py` e `CepConsultarView`), `contas` (`exceptions.py`, `UsuarioService`, `forms.py`, CBVs em `views.py`, `urls.py`), `notificacoes` (comando `manage.py despachar_emails` com advisory lock e `ExecucaoRotina`), templates acessíveis (cadastro fiel ao protótipo com logo `static/img/logo.png` e modais rascunho `1.0-rascunho`, confirmação de e-mail, reenvio sob limite 5/h, edição de perfil com CPF somente leitura e encerramento LGPD com ganchos no-op para etapas futuras), `static/js/cadastro.js` e suíte de testes automatizados em PostgreSQL cobrindo `CA-01-01` a `CA-01-18`.
  - **Etapa 3 (Spec 02 — RF002, Autenticação, Controle de Acesso e 2FA do Administrador):** `pyotp==2.12.1` + `segno==1.6.6` fixados em `requirements.txt`, `RegistroAcesso` `append-only` (trigger SQL `0004` + `identificador_hash` HMAC-SHA256 com chave dedicada `REMED_IDENTIFICADOR_HMAC_KEY`), `DispositivoTotp`, `CodigoRecuperacaoTotp`, `SessaoUsuario`, `EmailOuCpfBackend`, `SessaoService`, `AutenticacaoService` (bloqueio 15 min após 5 falhas unificando e-mail e CPF + limite secundário por IP), `TotpService` (QR SVG local em data URI, 8 códigos de recuperação em hash, anti-replay, step-up e reset por outro Admin com ≥ 2 Admins ativos), mixins declarativos completos (`PerfilObrigatorioMixin`, `ContaAdminPendente2faMixin`, `FuncaoAdminObrigatoriaMixin` sem atalho por `is_superuser`), comando `manage.py bootstrap_admin`, templates acessíveis (login fiel ao protótipo com `"E-mail ou CPF"` sem CNPJ, 2FA e aviso `"Esqueci minha senha"` em breve) e testes cobrindo `CA-02-01` a `CA-02-12`.
  - **Etapa 4 (Spec 03 — RF017, Notificações + Spec 04 — RF004, Gestão de Usuários pelo Administrador):** `NotificacaoService` completo (catálogo fechado para os 21 `TipoNotificacao` com bloqueio de PII/chaves proibidas e restrição de `local_retirada` ao pós-agendamento, `url_destino` estritamente interna, limite `20/h` para e-mails não críticos preservando plataforma e `seguranca_conta`, alerta operacional anti-loop em `despachar_emails` só na plataforma via `REMED_NOTIFICACAO_ALERTA_FALHAS_LOTE = 3`), context processor `contador_notificacoes` com 0 consultas ao banco para anônimos/inativos, central `/notificacoes/` com filtros, paginação e marcação via POST; `AcaoGestaoUsuario` (`0005` com `CheckConstraint` rejeitando motivo vazio/espaços + trigger SQL `append-only` `0006`), `GestaoUsuariosService` (visualização minimizada com CPF mascarado `mascarar_cpf`, alteração de status com motivo obrigatório, revogação imediata de sessões e gancho no-op `cancelador_operacoes_abertas`, atribuição das 8 funções sob *step-up* 2FA com bloqueio `gestao_usuarios` × `verificacao_receitas`, revogação de sessões sem 2FA ao atribuir primeira função administrativa e trava concorrente ordenada por `id` do último Administrador ativo sem deadlock), rotas separadas `/admin-remed/usuarios/` e 94 testes automatizados passando em PostgreSQL (`CA-03-01` a `CA-03-06` e `CA-04-01` a `CA-04-07`).
  - **Etapa 5 (Spec 05 — RF005 + Spec 06 — RF006 + Spec 07 — RF007, Pontos de Coleta e Armazenamento Privado):** `pillow==13.0.0` fixado em `requirements.txt`, `nucleo` (`TipoEstabelecimento` + `TipoDocumentoPonto` populados em `0003` com `reverse_code=noop`, `validar_cnpj`/`validar_telefone`, `ArquivoService` conforme ADR 0016 com limite 5 MB, *magic bytes* + `%%EOF` em PDF, remoção de EXIF/GPS e proteção contra *decompression bomb* via Pillow, interface `AntimalwareScanner` *fail-closed*, armazenamento local em `PRIVATE_STORAGE_ROOT` + rota assinada `TimestampSigner` 60 s `/arquivos/privados/<token>/` com anti-path-traversal, vínculo ao usuário, `nosniff`, `no-store` e `Content-Disposition: attachment`); novo app `pontos_coleta` (`PontoColeta`, `HorarioFuncionamentoPonto`, `PontoColetaResponsavel`, `DocumentoPontoColeta`, `AnalisePontoColeta` com `CheckConstraint` de motivo e trigger SQL `append-only` `0002`), `PontoColetaService`, `DocumentoPontoService` (versionamento sob `select_for_update()` no `PontoColeta`, limpeza física em rollback, rotina `manage.py verificar_documentos_pontos` idempotente com advisory lock e `ExecucaoRotina`), `AprovacaoPontoService` (checklist orientativo Q10, revisão periódica `180 dias` e gancho no-op `cancelador_agendamentos_futuros` com TODO para Spec 16), convite de responsável com resposta neutra anti-enumeração e notificação via `seguranca_conta`, barra global única em `nucleo/context_processors.py` + `templates/base.html` e testes cobrindo `CA-05-01` a `CA-07-05`.
  - **Etapa 6 (Specs 08, 09, 10, 11 e 14 — RF008, RF010, RF011, RF012 e RF015, Medicamentos / Oferta):** zero novas dependências Python; `nucleo` (`FormaFarmaceutica` em `0004` + 11 formas iniciais em `0005` com `reverse_code=noop`, `GeolocalizacaoService` com BrasilAPI + fallback Nominatim com `User-Agent`, rate limit `<= 1 req/s`, cache em `CacheCep`, *bounding box*, Haversine no servidor e faixas aproximadas); novo app `medicamentos` (`Doacao`, `FotoDoacao`, `DadosRefrigeracaoDoacao`, `ConferenciaDoacao`, `ParametroVencimento` singleton inicializado em `0002` com `30`/`15` dias provisórios Q4, `ExecucaoVencimento`, triggers SQL `append-only` `0003` em `ConferenciaDoacao` e `ExecucaoVencimento`); `RefrigeracaoService` (`REMED_REFRIGERADO_JANELA_MAX_MINUTOS = 120` provisório Q5), `DoacaoService` (cadastro `em_analise`, autodeclaração controle especial, 1–2 fotos JPG/PNG via `ArquivoService` sem EXIF/GPS, substituição de foto com remoção em `transaction.on_commit()`, transição `temperatura_ambiente <-> refrigerado`, cancelamento lógico e integração no encerramento LGPD em `contas/services.py`), `ConferenciaDoacaoService` (fila `conferencia_doacoes` + 2FA, `select_for_update()`, checklist Q4 e transição direta para `vencido`), `VencimentoService` + comando `manage.py verificar_vencimento_doacoes` (idempotente com `pg_try_advisory_lock`, orientação de descarte sanitário RNF11 em `DOACAO_VENCIDA`, alerta `gestao_administradores` e até 3 retentativas em `falha`/`parcial`, parâmetros editáveis por `metricas_e_parametros` + 2FA) e `BuscaMedicamentoService` (6 filtros via `icontains`, 10/página, projeção estrita sem PII/ponto/coordenadas e localização efêmera em `request.session`); rotas `/medicamentos/`, `/doacoes/*`, `/admin-remed/doacoes/conferencia/*` e `/admin-remed/vencimento/*`, barra global única atualizada (logo -> `/medicamentos/`, `Minhas doações` condicional a `perfil_doador`, `Continuar como visitante` ativado no login) e **150 testes automatizados** passando em PostgreSQL (`CA-08-01` a `CA-11-05` e `CA-14-01` a `CA-14-05`).
- **Próxima etapa:** **Etapa 7** — **Solicitações e Receitas (`solicitacoes`)**: Specs `12` (RF013) e `13` (RF014), mantendo isolada a função `verificacao_receitas` (Q6/Q7 do PRD) e a ausência estrutural do motivo de saúde (RS002).
