---
name: seguranca-owasp
description: Segurança de aplicações com base no OWASP Top 10:2025, aplicada ao ReMed (Django, plataforma de doação e redistribuição de medicamentos). Use ao criar ou revisar rotas, permissões por perfil, autenticação, formulários, upload de fotos e receitas, consultas, reservas e agendamentos, geolocalização, integração de IA, tratamento de erros, configurações ou dependências, e ao fazer revisões de segurança.
---

# Segurança com o OWASP Top 10:2025 no ReMed

Referência: <https://top10.owasp.org/2025/>. Quando houver conflito, `docs/arquitetura.md` e as ADRs prevalecem sobre esta skill. Esta lista é um ponto de partida para revisão, não uma garantia de que a aplicação está segura.

O ReMed trata **dados pessoais e dados de saúde** (receitas, medicamentos solicitados) e organiza **encontros presenciais** entre pessoas. Os requisitos de segurança `RS001` a `RS011`, os RNF e o RF003 do catálogo (`docs/prd/02-catalogo-requisitos.md`) são a fonte do que precisa ser cumprido; esta skill diz como verificar.

## Mapa dos requisitos de segurança

Mapeamento proposto entre os RS do documento e as categorias OWASP. Revise com o usuário e complete a coluna "Spec" quando as specs existirem.

| RS | Perigo (resumo) | OWASP | Spec |
| --- | --- | --- | --- |
| RS001 | Medicamento vencido, adulterado ou violado chega ao solicitante | A06, A08 | |
| RS002 | Exposição de dados pessoais ou do motivo da necessidade de saúde | A01, A04, A06 | |
| RS003 | Entrega de medicamento sujeito a receita sem receita válida | A06, A01 | |
| RS004 | Perda de eficácia de medicamento refrigerado | A06 | |
| RS005 | Acesso indevido a contas | A07, A04, A02 | |
| RS006 | Uso indevido da plataforma (excesso de pedidos, revenda, perfis falsos) | A06, A09 | |
| RS007 | Reserva ou agendamento duplo do mesmo medicamento | A06, A10 | |
| RS008 | Riscos no encontro presencial (golpes, assédio, local inseguro) | A06, A01 | |
| RS009 | IA lê a embalagem incorretamente | A08, A06 | |
| RS010 | Geolocalização expõe localização e hábitos | A01, A06 | |
| RS011 | Ponto de coleta falso ou irregular | A06, A01, A09 | |

## A01: Controle de acesso quebrado

- Verifique no service se o usuário tem direito ao objeto, e não apenas se está autenticado.
- Filtre pelo dono na própria consulta (por exemplo, "doações do doador", "solicitações do solicitante") e responda 404 para que ninguém descubra se o objeto de outra pessoa existe.
- **Perfis do ReMed**: Visitante, Doador, Solicitante, Cuidador/Familiar, Representante do ponto de coleta e Administrador (RF003). Cada view declara os perfis permitidos, e o service reconfere.
- **Visibilidade de dados** (RS002, RS008, RF008): a busca e os resultados nunca exibem nome, contato ou endereço do doador, só localização aproximada e identificação reduzida. O local de retirada só é liberado às duas partes **após a confirmação do agendamento**. Telefone e e-mail nunca aparecem a outro usuário.
- **Receita** (RF012): visível apenas ao verificador, nunca ao doador. Teste explicitamente.
- Visitante sem login só acessa a busca resumida (RF008).
- Altere dados apenas com POST e `{% csrf_token %}`. Não use `csrf_exempt`.
- Valide redirecionamentos vindos do usuário com `url_has_allowed_host_and_scheme`.
- Declare os campos em `Meta.fields`, para que um formulário não permita alterar `status`, `perfil`, `aprovado` ou `quantidade disponível`.
- O Administrador do Django não altera status de doação, solicitação, reserva, verificação de receita nem aprovação de ponto de coleta por fora dos services.
- Teste as rotas protegidas com visitante, dono, outro usuário e cada perfil que não deveria ter acesso.

## A02: Configuração insegura

- Leia segredos de variáveis de ambiente, como `DJANGO_SECRET_KEY` e credenciais do banco e de serviços externos. Nunca os coloque no código nem no Git. Mantenha `.env.example` sem valores reais.
- Fora do desenvolvimento, use `DEBUG = False`, preencha `ALLOWED_HOSTS` e ative cookies seguros, HTTPS e HSTS. A comunicação deve usar TLS 1.2 ou superior (RS005).
- Rode `python manage.py check --deploy` antes de qualquer deploy.
- Mantenha os middlewares de segurança, CSRF e clickjacking.
- Arquivos enviados (fotos e receitas) não ficam em diretório público do servidor web.

## A03: Falhas na cadeia de suprimentos de software

- Adicione uma dependência só quando for necessária e confira nome, origem e manutenção do pacote.
- Fixe as versões em um arquivo versionado e procure vulnerabilidades conhecidas, por exemplo com `pip-audit`.
- Não execute scripts baixados sem antes ler o que fazem.
- Serviços externos previstos (consulta de CEP, mapas e geolocalização, e-mail, IA e base de medicamentos, RNF12) são dependências: registre quais dados enviam e o que acontece quando ficam indisponíveis.

## A04: Falhas criptográficas

- Use o sistema de senhas do Django (`create_user`, `set_password`). Não armazene nem compare senhas por conta própria.
- O RS005 pede hash com bcrypt ou argon2, e o padrão do Django é PBKDF2. O Django suporta configurar outros algoritmos em `PASSWORD_HASHERS`, mas isso exige pacote adicional. **Decisão pendente: registrar em ADR antes de implementar.**
- **Dados sensíveis** (RS002, RF012, RNF08, RNF10): receitas e dados pessoais devem ser criptografados no armazenamento, com acesso restrito por perfil. Como será feito (disco, banco ou serviço de arquivos) é **decisão pendente de ADR**.
- Use `secrets` ou `django.utils.crypto` para gerar valores secretos, nunca `random`. Isso vale para o link de recuperação de senha (validade de 1 hora e uso único, RF003) e para o código de confirmação da entrega (RF011, RS008).
- Não crie algoritmos próprios de criptografia nem de assinatura.

## A05: Injeção

- Prefira o ORM. Em SQL bruto, passe valores como parâmetros, sem interpolar texto.
- Mantenha o autoescape. Não use `safe`, `mark_safe` nem `autoescape off` em conteúdo enviado por usuários (observações, mensagens da plataforma, denúncias).
- Não use `eval`, `exec`, `pickle` nem `shell=True` com dados externos.
- Teste a exibição de conteúdo com `<script>` nos campos de texto livre.
- Nomes de arquivos enviados nunca são usados como caminho: gere o nome internamente.

## A06: Design inseguro

- Identifique abusos possíveis ainda na spec: quem pode fazer o quê, com que limite e o que acontece em caso de erro.
- Proteja invariantes no banco com constraints, além das validações no código: CPF, CNPJ e e-mail únicos; quantidade disponível nunca negativa; uma doação reservada para uma única correspondência por vez (RS007).
- Regras do domínio que são de segurança, e devem estar nas specs com teste:
  - validade obrigatória, sem data anterior à atual, e rotina diária que marca como vencida e cancela reservas (RS001, RF006);
  - medicamentos de controle especial bloqueados até a definição do fluxo (RS003, RF012);
  - refrigerado exige condição de conservação e ciência do solicitante (RS004, RF013);
  - limites de solicitações abertas e canal de denúncia com suspensão (RS006); o valor do limite está pendente no documento;
  - retirada priorizando pontos de coleta aprovados, e comunicação por mensagens da plataforma sem expor contato (RS008);
  - ponto de coleta só aparece após aprovação do Administrador (RS011).
- Registre na spec e no PRD os riscos aceitos e as pendências (por exemplo, o motivo da necessidade de saúde nunca é coletado, RS002).

## A07: Falhas de autenticação

- Use `AuthenticationForm`, `login()`, `logout()` e os validadores de senha do Django (mínimo de 8 caracteres, RF001).
- Encerre a sessão apenas com POST.
- **Requisitos do documento** (RF003, RS005):
  - bloqueio temporário após 5 tentativas inválidas em 15 minutos, com aviso ao usuário;
  - sessão expira após 30 minutos de inatividade;
  - link de recuperação de senha com validade de 1 hora e uso único;
  - autenticação em dois fatores obrigatória para o Administrador;
  - CPF e e-mail únicos, e e-mail confirmado por link (RS006).
- O Django **não traz pronto** o bloqueio por tentativas nem o 2FA. O mecanismo de cada um é **decisão pendente de ADR**.
- Expiração por inatividade com o Django exige configuração explícita da sessão (por exemplo, `SESSION_COOKIE_AGE` combinado com renovação a cada requisição). Confirme a abordagem na ADR.
- **Risco a registrar**: o documento manda exibir "CPF já cadastrado" e "E-mail já cadastrado" (RF001), o que permite descobrir quem tem conta. No login, não revele se o usuário existe (a mensagem "E-mail/CPF ou senha incorretos" já faz isso). No cadastro, registre o risco como aceito ou mitigue com limite de tentativas.
- O perfil Administrador só é atribuído por outro Administrador (RF001); o documento não diz como nasce o primeiro. Trate como questão em aberto.

## A08: Falhas de integridade de software ou dados

- Não desserialize dados não confiáveis com `pickle`.
- Grave pelos services, para que nenhum caminho ignore as regras. Por isso o Admin do Django não escreve nos modelos de domínio.
- **Integridade da informação do medicamento** (RS001, RS009): a foto da embalagem fica vinculada à doação para conferência e retirada. Os dados sugeridos pela IA são **sugestões**: o usuário confirma, campos de baixa confiança exigem confirmação, a validade é sempre confirmada, e o que a IA não lê fica em branco.
- Registros de entrega e de verificação não podem ser apagados; correções geram novo registro com quem fez, data e hora (RF011).
- Não carregue scripts de CDN sem necessidade. Se precisar, use `integrity` (SRI).

## A09: Falhas de registro e alerta de segurança

- Registre eventos relevantes com o módulo de logging, sem depender de `print`.
- **O documento exige** registrar todos os acessos (sucesso e falha) com data, hora e identificação do usuário (RF003), histórico de quem, o quê, data e hora nas operações (RS006, RS011), e todas as notificações enviadas (RF009).
- Eventos a registrar: falhas e bloqueios de login, negações de acesso, aprovações e suspensões de ponto de coleta, verificações de receita, denúncias, falhas de integração externa.
- **Nunca registre**: senhas, tokens, códigos de confirmação, chaves de sessão, conteúdo de receitas. Evite CPF completo em logs de aplicação (use mascaramento); isso é recomendação, não requisito do documento.
- Neutralize quebras de linha em valores enviados por usuários antes de registrá-los.

## A10: Tratamento incorreto de condições excepcionais

- Capture a exceção mais específica. Não silencie erros com `except:` vazio nem com `pass`.
- Falhe de forma segura: em caso de erro, negue o acesso e não deixe a operação pela metade.
- **Operações transacionais obrigatórias** (RNF06, RS007): reserva, agendamento e entrega (RF009 a RF011) usam `transaction.atomic()` nos services e bloqueio de linha para evitar reserva dupla. Em caso de falha, a operação é desfeita e o usuário é informado.
- A falha da IA (RF005) ou de qualquer serviço externo **não pode impedir** o fluxo principal: o cadastro manual continua disponível sem perda do que já foi digitado.
- Não mostre rastreamentos nem detalhes internos a visitantes. Converta exceções de domínio em respostas HTTP na view.
- Teste entradas inválidas, valores nos limites e recursos inexistentes.

## Pontos específicos do ReMed

### Upload de fotos e receitas (RF004, RF007, RF012, RNF08)

- Aceite só os formatos do documento (fotos: JPG ou PNG; receitas: JPG, PNG ou PDF) e no máximo 5 MB. Valide pelo conteúdo, não só pela extensão.
- Gere o nome do arquivo internamente e guarde fora de diretório público.
- Sirva o arquivo por uma view que confira permissão (receita só ao verificador).
- Defina a eliminação conforme a política de privacidade (prazo ainda pendente no documento).
- Oriente o doador a não fotografar dados pessoais na embalagem (RF005).

### Geolocalização (RF008, RS010)

- Peça consentimento explícito, ofereça o CEP como alternativa e permita revogar o consentimento.
- Calcule a distância no servidor e nunca exiba coordenadas a outros usuários.
- Não guarde histórico de trajetos; só a última localização usada na busca.

### Integração de IA externa (RF005, RS009, RNF10, RNF13)

- A foto é enviada a um serviço externo: informe o doador, envie só o necessário e trate timeout e falha.
- Não envie dados do usuário além da imagem.
- Identifique os dados da IA como sugestões e exiba o aviso de que a plataforma não substitui avaliação médica ou farmacêutica.

### Privacidade (RNF10)

- Colete o mínimo necessário. Registre o consentimento (versão do documento aceito, data e hora).
- Receitas são dado sensível. Atenda pedidos de acesso, correção e eliminação ou anonimização conforme o documento.
- Não afirme o conteúdo de leis além do que o documento diz; dúvidas jurídicas vão para as questões em aberto.

## Decisões que precisam de ADR antes de implementar

Bloqueio por tentativas de login; algoritmo de hash de senha; 2FA do Administrador; sessão por inatividade; armazenamento criptografado de arquivos; política de eliminação de dados; reserva transacional e bloqueio de linha; integração de IA externa. Não implemente nenhuma delas sem ADR `aceita`.

## Ao revisar

Para cada problema, informe a categoria OWASP, o RS relacionado (quando houver), o arquivo e a linha, o cenário de exploração e a correção. Não relate riscos hipotéticos como se fossem falhas confirmadas. Ao revisar uma spec, confira se cada RS aplicável tem regra, critério de aceite e teste correspondentes.
