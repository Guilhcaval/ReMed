# Spec 23 — Leitura da Embalagem por IA (RF009 — v2.0)

> [!IMPORTANT]
> **Pré-requisito arquitetural da v2.0:** conforme o [PRD](../prd/01-remed.md) (seção 5.4) e [arquitetura.md](../arquitetura.md), a escolha do **provedor de IA multimodal** (e eventual integração com base/API de medicamentos) exigirá uma **ADR própria antes da implementação na v2.0**, avaliando custo, latência (≤ 15 s — RNF04), contrato de privacidade/LGPD (não retenção nem treinamento com as imagens — RNF10) e compatibilidade com Python 3.14.

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `23` — Leitura da Embalagem por IA (`RF009` — **v2.0**) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF009 (Desejável — **v2.0**, HU09). **Não funcionais:** RNF01, RNF02, RNF03, RNF04 (Importante — resposta da IA em até **15 segundos**), RNF07, RNF08, RNF10 (Essencial — LGPD e aviso de envio a serviço externo), RNF12 (interoperabilidade — IA e avaliação de base/API de medicamentos), RNF13 (Essencial — IA só sugere), RNF14, RNF16. **Segurança:** RS001, RS002, RS009, RS013. |
| **Apps envolvidos** | `medicamentos` (principal: `LeituraEmbalagemIaService`, interface de provedor multimodal desacoplada, endpoint/fluxo auxiliar integrado ao cadastro do RF008), `nucleo` (`ArquivoService` — validação da foto antes do envio à IA), `auditoria` (`AuditoriaService` — registro de uso/falha sem dados pessoais). |
| **Dependências de outras specs** | **[06-envio-documentos-ponto-de-coleta.md](06-envio-documentos-ponto-de-coleta.md) (`RF006` — `ArquivoService`)**, **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008` — cadastro de doação e foto da embalagem)** e **[10-conferencia-e-aprovacao-de-validade.md](10-conferencia-e-aprovacao-de-validade.md) (`RF011` — conferência humana continua obrigatória)**. **Pendências externas:** Questão 9 do PRD (limite numérico de confiança para destacar campos — *"fase de detalhamento"*), Questão 8 (prazo de eliminação das imagens na Política de Privacidade) e ADR futura de provedor de IA multimodal (v2.0). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0004](../adr/0004-pip-venv-requirements-fixado.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0011](../adr/0011-historico-imutavel-e-auditoria.md), [0016](../adr/0016-armazenamento-seguro-de-arquivos.md) + **ADR futura de provedor de IA multimodal (v2.0)**. |

---

## 2. Objetivo e escopo

Agilizar o preenchimento do cadastro de doação (RF008) enviando a foto da embalagem (já validada e limpa de EXIF/GPS) a um modelo de **IA multimodal** que extrai e **sugere** nome do medicamento, princípio ativo e concentração, lote, data de validade e fabricante com nível de confiança (`0` a `1`) por campo, **mantendo sempre a decisão humana do doador** (RS009, RNF13), o fallback manual sem perda de dados e a conferência humana do RF011.

### Inclui

- Aviso prévio explícito de privacidade (LGPD — RF009 regra 6, RNF10): informa ao doador que a foto será enviada a um serviço externo de IA e orienta a **não fotografar etiquetas com dados pessoais** (ex.: nome do paciente/etiqueta de farmácia).
- Validação e saneamento da foto pelo `ArquivoService` (`JPG`/`PNG`, ≤ 5 MB, *magic bytes*, remoção de EXIF/GPS via `Pillow` e antimalware — ADR 0016) **antes** do envio ao provedor de IA.
- Chamada via interface desacoplada (`ProvedorIaEmbalagem`) com timeout rígido compatível com o limite de **15 segundos** (RNF04).
- Retorno estruturado de sugestões (`nome_medicamento`, `principio_ativo_e_concentracao`, `lote`, `data_validade`, `fabricante`) + `confianca` (`0.0` a `1.0`) por campo:
  - Todos os valores preenchidos vêm claramente identificados como **"Sugestão da IA — confira antes de salvar"** (RNF13, RS009);
  - Campos com confiança abaixo do limiar configurável **`0,80`** (`IA_CONFIANCA_MINIMA = 0.80` em `settings`) recebem destaque visual + textual exigindo confirmação manual;
  - **`data_validade` sugerida exige SEMPRE confirmação explícita do doador**, independentemente do nível de confiança (RF009 regra 2, RS009);
  - Campos que a IA não conseguir ler permanecem **em branco, sem estimativa/alucinação** (RF009 regra 2).
- **Fallback resiliente:** se o serviço externo de IA estiver indisponível, exceder 15 s ou falhar, o doador continua o preenchimento manual normalmente **sem perder nenhum campo já digitado** (RF009 regra 3, RS009).
- Limite configurável de **10 leituras por hora por doador** (`IA_LEITURAS_MAX_POR_HORA = 10` em `settings` — *acréscimo da especificação*, mantendo preenchimento manual sempre liberado).
- Gancho opcional para validação de nome/concentração/controle especial contra base/API oficial de medicamentos, a ser decidido em **ADR própria da v2.0** junto à escolha do provedor de IA (RF009 regra 4, RNF12).

### Não inclui

- Aprovação automática de doações pela IA (expressamente proibida — RS009, RNF13; toda doação continua nascendo `em_analise` e passando pelo RF011).
- Envio de receitas médicas (RF014) para qualquer serviço externo de IA (estritamente proibido — RNF10, RS002).
- Definição do provedor comercial/open-weight de IA (objeto de ADR específica na v2.0).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Doador** | Consentir com o envio da foto da embalagem à IA, acionar `"Ler dados da foto"`, conferir/corrigir os campos sugeridos (confirmando obrigatoriamente a validade) e salvar a doação (RF008). | Usuário autenticado com perfil `Doador`, foto da embalagem válida (`JPG`/`PNG`, ≤ 5 MB) selecionada no RF008. |
| **Sistema (provedor externo de IA)** | Analisar a imagem saneada e retornar JSON estruturado com campos extraídos e confiança (`0` a `1`) em até 15 segundos. | Provedor configurado em variáveis de ambiente (ADR futura da v2.0) e com contrato de não retenção/não treinamento LGPD. |

---

## 4. Fluxos

### 4.1 Fluxo principal — Sugestão assistida por IA no cadastro de doação

1. No formulário do RF008 (`medicamentos:doacao_criar`), o Doador visualiza o aviso de privacidade (RF009 regra 6 — não fotografar etiquetas com nome de paciente; envio da foto a serviço externo de IA) e anexa a foto da embalagem (`JPG`/`PNG`, ≤ 5 MB).
2. Aciona **"Preencher sugestões a partir da foto (IA)"** (ação opcional via `fetch` em JS simples da ADR 0006 ou `POST` progressivo sem perder campos já preenchidos).
3. `LeituraEmbalagemIaService.extrair_sugestoes(imagem_bytes, usuario)`:
   - Valida formato, tamanho, *magic bytes*, limpa EXIF/GPS (`Pillow`) e passa na interface antimalware (`ArquivoService` — ADR 0016) antes de qualquer chamada externa;
   - Invoca o adaptador do provedor de IA com timeout máximo (ex.: 12 s para cumprir SLA ponta a ponta ≤ 15 s — RNF04) e schema estrito proibindo estimativas quando ilegível;
   - Valida e normaliza a resposta JSON (`confianca` ∈ `[0.0, 1.0]`; campos ausentes/incertos viram `None`);
   - Registra evento resumido de telemetria/auditoria (`ia_embalagem.executada` — sucesso/latência/campos lidos, sem dados pessoais).
4. A interface preenche os campos disponíveis com etiqueta **"Sugestão da IA"**, destaca campos com confiança `< IA_CONFIANCA_MINIMA` e exibe confirmação obrigatória explícita para a **Data de validade** (RF009 regra 2).
5. O Doador confere/edita os dados e conclui o salvamento normal pelo `DoacaoService.cadastrar(...)` (RF008), mantendo o status inicial `em_analise` (RF011).

### 4.2 Fluxos de exceção

- **FE-01 — IA indisponível, erro HTTP ou timeout (> 15 s):** retorna aviso amigável (*"Não foi possível ler a embalagem automaticamente agora. Preencha os campos manualmente"*), mantendo intacto tudo o que o doador já digitou (RF009 regra 3).
- **FE-02 — Campo não lido pela IA:** devolvido como vazio (`""`), nunca preenchido com chute/valor padrão (RF009 regra 2).
- **FE-03 — Tentativa de salvar sem confirmar a data de validade sugerida ou campo de baixa confiança:** validação de formulário orienta o doador a revisar e confirmar manualmente.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-23-01** | A IA **apenas sugere** o preenchimento (nome, princípio ativo/concentração, lote, validade, fabricante + confiança `0` a `1`); **nunca decide** aprovação nem pula a conferência humana do RF011. | RF009 (regra 1), RS009, RNF13 • `medicamentos` |
| **RN-23-02** | Campos com confiança abaixo de **`0,80`** (`IA_CONFIANCA_MINIMA = 0.80` em `settings`) são destacados e exigem confirmação manual. A **data de validade sugerida deve ser sempre confirmada** pelo doador. Campos não lidos ficam em branco, sem estimativa. | RF009 (regra 2), RS009 • `medicamentos` |
| **RN-23-03** | Em falha ou indisponibilidade da IA (ou timeout de 15 s — RNF04), o doador preenche manualmente **sem perder os dados já digitados**. Limite de **10 leituras por hora por doador** (`IA_LEITURAS_MAX_POR_HORA = 10` em `settings` — *acréscimo da especificação*). | RF009 (regra 3), RNF04, RS009 • `medicamentos` |
| **RN-23-04** | Antes de enviar a foto à IA, o `ArquivoService` remove metadados EXIF/GPS e valida assinatura/tamanho/antimalware. O doador é informado previamente de que a foto vai a um serviço externo e orientado a não fotografar dados pessoais (LGPD — RNF10). As imagens servem exclusivamente à doação e seguem eliminação da Política de Privacidade. | RF009 (regras 5 e 6), RNF10, RNF16, RS002, RS013 • `medicamentos`, `nucleo` |
| **RN-23-05** | Escolha do provedor de IA multimodal e integração com base/API oficial de medicamentos (RF009 regra 4, RNF12, RS003) serão decididas em **ADR própria antes de iniciar a v2.0**. | RF009 (regra 4), RNF12, RS003 • `medicamentos` |

---

## 6. Modelo de dados lógico

Esta spec não exige persistir as respostas brutas da IA no banco (evitando retenção desnecessária — LGPD); caso seja útil auditar o uso de IA na conferência do RF011, pode adicionar em `Doacao` apenas o booleano `preenchido_com_auxilio_ia` (`Boolean`, padrão `False` — *acréscimo da especificação*) e registrar latência/status técnico em `RegistroAuditoria`.

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **View (`medicamentos`, restrita ao perfil `Doador`):** `DoacaoLerEmbalagemIaView` (`POST` com CSRF, `multipart/form-data`, rate-limitada por usuário — *acréscimo da especificação*, OWASP A04/custos).
- **Services (`LeituraEmbalagemIaService` + protocolo `ProvedorIaEmbalagem`):** validação/saneamento prévio via `ArquivoService`, invocação do provedor configurado, parsing estrito e *fallback* seguro.
- **Interface:** botão opcional `"Ler dados da foto com IA"` + quadro de aviso LGPD em `templates/medicamentos/doacao_form.html`, com destaque visual + textual de baixa confiança e checkbox de confirmação da validade via JS simples (ADR 0006).
- **Rota:** `medicamentos:doacao_ler_ia` (`/doacoes/ler-embalagem-ia/`).

---

## 8. Mensagens e validações

- Aviso prévio LGPD: `"A foto da embalagem será enviada a um serviço externo de IA apenas para sugerir os dados. Não fotografe etiquetas com nome de paciente ou outros dados pessoais."`;
- Indisponibilidade/timeout: `"Não foi possível ler a embalagem automaticamente no momento. Preencha os campos manualmente — nada do que você digitou foi perdido."`;
- Destaque de sugestão: `"Sugestão da IA — confira os dados e confirme especialmente a data de validade."`.

---

## 9. Segurança e privacidade

- **RS009 (OWASP A06/LLM):** saída validada por schema estrito (sem execução nem HTML), confiança explícita, confirmação obrigatória de validade, campos ilegíveis em branco e revisão humana mantida no RF011.
- **RNF10 & RS013:** remoção de EXIF/GPS antes do envio externo, aviso prévio de privacidade, proibição absoluta de enviar receitas médicas à IA, rate limit por usuário contra abuso de custo e chave de API exclusiva em variável de ambiente.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** avisos e destaques de baixa confiança nunca apenas por cor (texto + ícone, WCAG 2.1 AA).
- **RNF04:** timeout controlado garantindo resposta em até **15 segundos**.
- **RNF10, RNF12, RNF13, RNF16:** privacidade, interoperabilidade desacoplada, caráter estritamente sugestivo e validação de imagem.

---

## 11. Critérios de aceite

1. **CA-23-01 (Sugestão com destaque de baixa confiança e confirmação obrigatória de validade — RN-23-01, RN-23-02):** Com dublê de IA retornando lote com confiança `0.55` e validade com confiança `0.95`, o lote é destacado como baixa confiança e a data de validade ainda exige confirmação manual explícita antes de salvar; campo ilegível (`null`) permanece em branco.
2. **CA-23-02 (Fallback sem perda de dados — RN-23-03):** Simulando timeout (> 15 s) ou erro 503 do provedor de IA, a tela informa o erro de forma clara e preserva intactos os campos já preenchidos manualmente.
3. **CA-23-03 (Saneamento prévio e proteção de custo/acesso — RN-23-04):** A imagem enviada ao adaptador do provedor já está sem metadados EXIF/GPS; usuários sem perfil `Doador` recebem HTTP 403; excesso de chamadas respeita o limite por usuário.

---

## 12. Plano de testes

- **Unidade (`LeituraEmbalagemIaService` com dublê de `ProvedorIaEmbalagem`):** parsing de JSON válido, campo nulo ficando em branco, limiar de confiança, timeout/exceção devolvendo *fallback* limpo, remoção prévia de EXIF/GPS e rate limit.
- **Integração (View):** acesso restrito a `Doador`, CSRF obrigatório, exibição do aviso LGPD e da obrigação de confirmação da validade antes de persistir no RF008.

---

## 13. Questões em aberto

| # | Questão | Tipo / Origem | Impacto na implementação |
| --- | --- | --- | --- |
| 1 | **ADR de provedor de IA multimodal e base/API oficial de medicamentos (v2.0):** definir provedor, contrato LGPD, custo e integração oficial antes da v2.0. | Pré-requisito arquitetural da v2.0 | Não bloqueia o MVP nem a v1.1; obrigatório antes de iniciar a implementação da v2.0. |
| 2 | **Prazo de eliminação das imagens pela Política de Privacidade (Questão 8 do PRD):** ainda não definido. | Pendência externa (Cliente / Jurídico) | Seguirá a mesma rotina de retenção LGPD das fotos do RF008. |
