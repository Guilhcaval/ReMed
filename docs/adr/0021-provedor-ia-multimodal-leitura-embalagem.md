# 0021. Integrar leitura da embalagem por IA multimodal via adaptador HTTP na biblioteca padrão

- Status: aceita
- Data: 2026-11-24
- Requisitos relacionados: RF009, RF008, RF011, RNF04, RNF08, RNF10, RNF12, RNF13, RNF14, RNF16, RS002, RS009, RS013

## Contexto

O **RF009 (Leitura da Embalagem por IA)** auxilia o doador no preenchimento do cadastro de doação ([RF008](../specs/08-cadastro-de-doacao.md)) extraindo sugestões de nome do medicamento, princípio ativo, concentração/dosagem, lote, data de validade e fabricante a partir da foto da embalagem, com nível de confiança (`0` a `1`) por campo.

Essa integração envolve forças sensíveis que exigem decisão arquitetural explícita:

- **Privacidade e LGPD (RNF10, RS002, RS013):** a foto será enviada a um serviço externo de IA; metadados EXIF/GPS e dados do usuário não podem vazar, receitas médicas (RF014) nunca podem ser enviadas à IA, e respostas brutas não devem ser retidas no banco.
- **Segurança sanitária e integridade (RS009, RNF13, RF011):** a IA apenas sugere dados editáveis; campos de baixa confiança exigem confirmação manual, a data de validade sugerida sempre precisa ser confirmada pelo doador, campos ilegíveis permanecem em branco sem estimativa, e toda doação continua passando pela conferência humana (RF011).
- **Desempenho e resiliência (RNF04, RF009 regra 3):** resposta em até **15 segundos** e fallback gracioso sem perda de dados quando a IA estiver sem chave configurada, fora do ar ou lenta.
- **Enxugamento de dependências (ADR 0003, ADR 0004):** evitar SDKs pesados de provedores comerciais com alta frequência de quebra ou vulnerabilidades em Python 3.14.

## Direcionadores da decisão

- Manter zero dependências externas adicionais em `requirements.txt` (ADR 0004) e compatibilidade imediata com Python 3.14 (ADR 0003).
- Evitar aprisionamento a um único fornecedor comercial (*vendor lock-in*) suportando múltiplos provedores multimodais configuráveis por variáveis de ambiente (ADR 0020).
- Garantir remoção prévia de EXIF/GPS e validação de conteúdo via `ArquivoService` (ADR 0016) **antes** de qualquer envio externo e sem gravar arquivos órfãos em disco.
- Garantir SLA ponta a ponta ≤ 15 s (RNF04) por meio de timeout rígido e fallback manual transparente.
- Impedir abuso de custo e vazamento de segredos/PII em logs ou auditoria (OWASP A04, A08, A09, A10).

## Opções consideradas

### 1. Protocolo interno `ProvedorIaEmbalagem` com adaptadores HTTP via `urllib.request` (stdlib) para `gemini` e `openai_compat` (escolhida)

A camada de service (`LeituraEmbalagemIaService`) valida e saneia a imagem em memória via `ArquivoService`, aplica limite de taxa por usuário (`10/h`) e aciona um adaptador desacoplado implementado sobre `urllib.request` da biblioteca padrão do Python, selecionado exclusivamente por variáveis de ambiente (`REMED_IA_PROVEDOR`, `REMED_IA_API_KEY`, `REMED_IA_MODELO`, `REMED_IA_ENDPOINT`). Quando não configurado, utiliza `ProvedorIaDesativado`, acionando o fallback manual sem realizar chamadas de rede.

- **Prós:**
  - Zero novos pacotes em `requirements.txt`, mantendo auditoria `pip-audit` limpa e compatibilidade nativa com Python 3.14.
  - Suporta tanto a API REST multimodal do **Google Gemini** (`gemini-2.5-flash` e sucessores, com chave via cabeçalho `x-goog-api-key`) quanto qualquer API compatível com **OpenAI Chat Completions multimodal** (`openai_compat`, incluindo OpenAI, Groq, OpenRouter e servidores locais como Ollama/vLLM).
  - Facilita testes automatizados 100% determinísticos e offline por injeção de dublê do protocolo `ProvedorIaEmbalagem` ou mock do `urlopen`.
- **Contras:**
  - Exige manutenção manual do pequeno contrato JSON/HTTP de cada adaptador caso os provedores alterem seus endpoints REST no futuro.

### 2. Instalar SDK oficial de um único provedor (ex.: `google-genai` ou `openai`)

- **Prós:**
  - Tipagem e helpers prontos do fornecedor escolhido.
- **Contras:**
  - Adiciona dezenas de subdependências transitivas (`httpx`, `pydantic`, `anyio` etc.) ao `requirements.txt`, aumenta a superfície de `pip-audit` e acopla o projeto a um único fornecedor.

## Decisão

**Opção 1** — integrar a leitura da embalagem por IA multimodal (RF009) por meio do protocolo `ProvedorIaEmbalagem` e adaptadores HTTP sobre **`urllib.request` da biblioteca padrão do Python**, com suporte configurável a **`gemini`** e **`openai_compat`** e modo padrão desativado (`REMED_IA_PROVEDOR=""`, `REMED_IA_API_KEY=""`).

Regras que passam a valer:

- **Saneamento obrigatório prévio em memória (ADR 0016 / RNF10):** antes de qualquer envio externo, `ArquivoService.validar_e_sanitizar_imagem` valida extensão/assinatura (`JPG`/`PNG`, ≤ 5 MB), reprocessa a imagem via Pillow removendo 100% dos metadados EXIF/GPS e executa o `AntimalwareScanner` em modo *fail-closed*, sem gravar arquivos em disco.
- **Isolamento estrito de dados (RNF10 / RS002):** nenhum dado pessoal do usuário é enviado ao provedor de IA; receitas médicas (RF014) são terminantemente proibidas de utilizar este serviço; respostas brutas da IA não são persistidas no banco.
- **Configuração e segurança de transporte (ADR 0020 / OWASP A02/A09):** credenciais existem apenas em variáveis de ambiente (`REMED_IA_API_KEY`), nunca em código, logs ou auditoria; em `gemini`, a chave vai exclusivamente no cabeçalho `x-goog-api-key` (nunca em query string); fora de `DEBUG`, apenas endpoints `https://` são aceitos; a leitura do corpo HTTP é limitada a 64 KB.
- **Timeout, limiar de confiança e rate limit (RNF04 / RS009):** timeout configurável com padrão `REMED_IA_TIMEOUT_SEGUNDOS = 12` (teto ≤ 14 s para cumprir SLA ≤ 15 s); limiar configurável `REMED_IA_CONFIANCA_MINIMA = 0.80` (provisório — Questão 9 do PRD); limite configurável de `REMED_IA_LEITURAS_MAX_POR_HORA = 10` por doador.
- **Sugestão editável e confirmação humana (RS009 / RNF13):** a resposta é validada por schema estrito (campos ilegíveis ou datas ambíguas retornam em branco); campos com confiança `< 0.80` recebem destaque visual + textual e confirmação obrigatória; **a data de validade sugerida exige sempre confirmação explícita do doador** (validada também no servidor em `DoacaoCadastroForm`); toda doação segue nascendo `em_analise` (RF011).
- **Telemetria sem PII (ADR 0011 / RNF14):** cada tentativa de leitura e o uso de auxílio de IA no cadastro são registrados em `RegistroAuditoria` contendo apenas status técnico, provedor, latência e nomes dos campos sugeridos (sem PII, imagem ou chave).

## Consequências

- **Positivas:**
  - Antecipa o RF009 com segurança sanitária, privacidade LGPD e experiência fluida (reutilizando diretamente a foto principal `foto_1` no cadastro de doação).
  - Zero novas dependências externas e zero alterações de esquema/migrações no banco de dados.
  - Ambiente sem chave configurada opera de forma transparente com fallback manual gracioso.
- **Negativas e custos:**
  - Em implantação produtiva, será necessário contratar plano/API com termo formal de **não retenção e não treinamento** das imagens enviadas (RNF10 / Questão 8 do PRD).
  - A validação opcional contra base/API oficial de medicamentos (RF009 regra 4 / RNF12) permanece como evolução futura desacoplada.
- **Impacto em specs e arquitetura:**
  - Atende integralmente a [Spec 23 — Leitura da Embalagem por IA](../specs/23-leitura-embalagem-por-ia.md) e integra-se à [Spec 08](../specs/08-cadastro-de-doacao.md) sem alterar o fluxo de conferência humana da [Spec 10](../specs/10-conferencia-e-aprovacao-de-validade.md).

## Como verificar

- Testes unitários de `LeituraEmbalagemIaService` com dublês offline confirmam: remoção prévia de EXIF/GPS antes do envio ao provedor, rejeição de arquivos inválidos/maliciosos, tratamento de campos nulos e datas ambíguas em branco, destaque de baixa confiança (`< 0.80`), confirmação obrigatória da validade, rate limit (`10/h`), fallback gracioso em ausência de chave/timeout/HTTP 503 e ausência de PII/API key em logs e `RegistroAuditoria`.
- Testes dos adaptadores HTTP (`ProvedorIaGemini` e `ProvedorIaOpenAiCompat`) com `urlopen` mockado validam cabeçalhos (`x-goog-api-key` fora da URL), timeout rígido e exigência de HTTPS com `DEBUG=False`.
- Testes de integração de `DoacaoLerEmbalagemIaView` e `DoacaoCriarView` validam restrição ao perfil `Doador`, CSRF, aviso LGPD literal, bloqueio server-side sem confirmação de validade/baixa confiança e criação da doação sempre em status `em_analise`.

## Notas

- **ADRs relacionadas:** [ADR 0001](0001-django-mvt-com-camada-de-service.md), [ADR 0004](0004-pip-venv-requirements-fixado.md), [ADR 0006](0006-javascript-simples-sem-framework.md), [ADR 0011](0011-historico-imutavel-e-auditoria.md), [ADR 0016](0016-armazenamento-seguro-de-arquivos.md), [ADR 0018](0018-consulta-de-cep.md) e [ADR 0020](0020-configuracao-variaveis-ambiente-python-dotenv.md).
- **Spec relacionada:** [23-leitura-embalagem-por-ia.md](../specs/23-leitura-embalagem-por-ia.md).
- **Pendências externas preservadas:** Questão 8 do PRD (prazos da Política de Privacidade) e Questão 9 do PRD (confirmação do limiar numérico de confiança provisório `0.80`).
