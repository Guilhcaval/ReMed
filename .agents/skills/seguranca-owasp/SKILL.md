---
name: seguranca-owasp
description: Segurança de aplicações web com base no OWASP Top 10:2025. Use ao criar ou revisar rotas, permissões por perfil, autenticação, sessões, formulários, upload de arquivos, consultas ao banco, operações concorrentes, geolocalização, integração com serviços externos ou de IA, tratamento de erros, logs, configurações ou dependências, e ao fazer revisões ou auditorias de segurança, mesmo que o usuário não diga "segurança" explicitamente.
---

# Segurança com o OWASP Top 10:2025

Referência: <https://top10.owasp.org/2025/>. Quando houver conflito, o documento de arquitetura e as ADRs do projeto prevalecem sobre esta skill. Esta lista é um ponto de partida para revisão, **não** uma garantia de que a aplicação está segura.

Os exemplos de código usam Django por ser comum, mas os princípios valem para qualquer stack web. Adapte os nomes de funções ao framework do projeto.

## Primeiro: entenda o que precisa ser protegido

Antes de revisar ou implementar, leia o PRD, as specs e os requisitos de segurança do projeto (se existirem). Identifique:

- **Dados sensíveis**: dados pessoais, saúde, financeiros, documentos enviados, localização.
- **Perfis e permissões**: quem pode ver e fazer o quê.
- **Operações críticas**: pagamento, reserva, exclusão, mudança de status, administração.
- **Integrações externas**: o que envia dados para fora e o que acontece se o serviço falhar.

Se os requisitos de segurança do projeto têm IDs, **mapeie cada um para a categoria OWASP** correspondente em uma tabela (requisito, perigo resumido, categoria OWASP, spec que o cobre) e revise com o usuário. Ao revisar uma spec, confira se cada requisito de segurança aplicável tem regra, critério de aceite e teste.

## A01: Controle de acesso quebrado

- Verifique no service (camada de regra de negócio) se o usuário tem direito ao **objeto**, e não apenas se está autenticado.
- Filtre pelo dono na própria consulta (por exemplo, "pedidos do cliente") e responda 404 para que ninguém descubra se o objeto de outra pessoa existe.
- Cada rota declara os perfis permitidos, e o service reconfere. A interface nunca é a única barreira.
- Defina **visibilidade de dados** por perfil: o que outros usuários nunca devem ver (contato, endereço, documentos). Teste isso explicitamente.
- Altere dados apenas com POST (ou PUT, PATCH, DELETE em APIs) e proteção contra CSRF. Não desative a proteção CSRF por conveniência.
- Valide redirecionamentos vindos do usuário (por exemplo, `url_has_allowed_host_and_scheme` no Django).
- Declare explicitamente os campos de cada formulário, para que ele não permita alterar `status`, `perfil`, `aprovado`, preço ou quantidade (mass assignment).
- O painel administrativo do framework não deve alterar por fora das regras de negócio os dados críticos (status, aprovação, verificação).
- Teste as rotas protegidas com visitante, dono, outro usuário e cada perfil que não deveria ter acesso.

## A02: Configuração insegura

- Leia segredos de variáveis de ambiente (chave secreta, credenciais do banco e de serviços externos). Nunca os coloque no código nem no Git. Mantenha um `.env.example` sem valores reais.
- Fora do desenvolvimento: modo debug desligado, hosts permitidos preenchidos, cookies seguros, HTTPS e HSTS. Use TLS 1.2 ou superior.
- Rode a verificação de deploy do framework antes de publicar (no Django, `python manage.py check --deploy`).
- Mantenha ativos os middlewares de segurança, CSRF e proteção contra clickjacking.
- Arquivos enviados por usuários não ficam em diretório público do servidor web.
- Remova contas, senhas e chaves padrão e desative recursos de depuração em produção.

## A03: Falhas na cadeia de suprimentos de software

- Adicione uma dependência só quando necessária e confira nome, origem e manutenção do pacote (cuidado com nomes parecidos).
- Fixe as versões em arquivo versionado e procure vulnerabilidades conhecidas (por exemplo, `pip-audit`, `npm audit`).
- Não execute scripts baixados sem ler o que fazem.
- Serviços externos (CEP, mapas, e-mail, IA, pagamentos) são dependências: registre quais dados enviam e o que acontece quando ficam indisponíveis.

## A04: Falhas criptográficas

- Use o sistema de senhas do framework. Não armazene nem compare senhas por conta própria. Se o requisito pedir um algoritmo específico (bcrypt, argon2), isso é decisão de ADR antes de implementar.
- **Dados sensíveis** devem ser criptografados em trânsito e, conforme o requisito, em repouso, com acesso restrito por perfil. Como será feito (disco, banco, serviço de arquivos) é decisão de ADR.
- Use `secrets` (Python) ou o equivalente do framework para gerar valores secretos: tokens de recuperação de senha, códigos de confirmação, links de uso único. Nunca `random`.
- Tokens de uso único têm validade curta e são invalidados após o uso.
- Não crie algoritmos próprios de criptografia nem de assinatura.

## A05: Injeção

- Prefira o ORM. Em SQL bruto, passe valores como parâmetros, sem interpolar texto.
- Mantenha o autoescape dos templates. Não use `safe`, `mark_safe` nem desative o escape em conteúdo enviado por usuários.
- Não use `eval`, `exec`, `pickle` nem `shell=True` com dados externos.
- Teste a exibição de conteúdo com `<script>` nos campos de texto livre.
- Nomes de arquivos enviados nunca são usados como caminho: gere o nome internamente.

## A06: Design inseguro

- Identifique abusos possíveis ainda na spec: quem pode fazer o quê, com que limite e o que acontece em caso de erro.
- Proteja invariantes **no banco** com constraints, além das validações no código: unicidade (documento, e-mail), quantidade nunca negativa, um recurso reservado para uma única operação por vez.
- Pense em regras de segurança do domínio e coloque-as nas specs com teste. Exemplos genéricos:
  - datas de validade obrigatórias e rotina que expira o que venceu;
  - limites de uso por usuário e canal de denúncia com suspensão;
  - itens que exigem aprovação de um perfil antes de aparecerem;
  - fluxos que exigem comprovação (documento) antes de liberar algo sensível;
  - comunicação entre usuários pela plataforma, sem expor contatos pessoais.
- Registre na spec e no PRD os **riscos aceitos** e as pendências.

## A07: Falhas de autenticação

- Use os formulários, funções de login e logout e validadores de senha do framework (defina mínimo de caracteres conforme o requisito).
- Encerre a sessão apenas com POST.
- Controles que frameworks costumam **não trazer prontos** e que exigem decisão de ADR: bloqueio por tentativas inválidas, autenticação em dois fatores, expiração de sessão por inatividade.
- Confirme o e-mail por link quando o requisito pedir. Links de recuperação de senha têm validade curta e uso único.
- **Enumeração de usuários**: no login, não revele se o usuário existe (mensagem única, como "e-mail ou senha incorretos"). Se o cadastro precisar dizer que um e-mail ou documento já existe, registre o risco como aceito ou mitigue com limite de tentativas.
- O perfil administrador só é atribuído por outro administrador. Defina como nasce o primeiro; se a fonte não diz, trate como questão em aberto.

## A08: Falhas de integridade de software ou dados

- Não desserialize dados não confiáveis com `pickle`.
- Grave pelos services, para que nenhum caminho ignore as regras. Por isso o painel administrativo não escreve nos modelos críticos.
- **Dados vindos de IA ou de serviço externo são sugestões**: o usuário confirma, campos de baixa confiança exigem confirmação, e o que não foi lido fica em branco.
- Registros de auditoria (entrega, verificação, aprovação) não podem ser apagados; correções geram novo registro com quem fez, data e hora.
- Não carregue scripts de CDN sem necessidade. Se precisar, use `integrity` (SRI).

## A09: Falhas de registro e alerta de segurança

- Registre eventos relevantes com o módulo de logging, sem depender de `print`.
- Eventos a registrar: logins (sucesso e falha), bloqueios, negações de acesso, mudanças de permissão, aprovações e suspensões, ações administrativas, denúncias, falhas de integração externa, e o histórico de quem fez o quê, quando.
- **Nunca registre**: senhas, tokens, códigos de confirmação, chaves de sessão, conteúdo de documentos sensíveis. Evite documentos pessoais completos em logs (use mascaramento).
- Neutralize quebras de linha em valores enviados por usuários antes de registrá-los (log injection).
- Defina quem é alertado e como, quando algo anormal acontece (muitas falhas de login, por exemplo).

## A10: Tratamento incorreto de condições excepcionais

- Capture a exceção mais específica. Não silencie erros com `except:` vazio nem com `pass`.
- Falhe de forma segura: em caso de erro, negue o acesso e não deixe a operação pela metade.
- **Operações transacionais**: reserva, agendamento, pagamento e entrega usam transação (`transaction.atomic()` no Django) e bloqueio de linha (`select_for_update()`) para evitar duplicidade. Em caso de falha, a operação é desfeita e o usuário é informado.
- A falha de um serviço externo (IA, CEP, e-mail) **não pode impedir** o fluxo principal: ofereça o caminho manual sem perda do que já foi digitado.
- Não mostre rastreamentos nem detalhes internos a usuários. Converta exceções de domínio em respostas HTTP na camada de entrada.
- Teste entradas inválidas, valores nos limites e recursos inexistentes.

## Pontos recorrentes em aplicações web

### Upload de arquivos

- Aceite só os formatos e tamanhos definidos pelo requisito. Valide pelo **conteúdo**, não só pela extensão.
- Gere o nome do arquivo internamente e guarde fora de diretório público.
- Sirva o arquivo por uma view que confira permissão.
- Defina a política de eliminação conforme a política de privacidade.
- Oriente o usuário a não enviar imagens com dados pessoais desnecessários.

### Geolocalização

- Peça consentimento explícito, ofereça alternativa (CEP, endereço) e permita revogar.
- Calcule distâncias no servidor e nunca exiba coordenadas exatas a outros usuários.
- Não guarde histórico de trajetos; só o necessário.

### Integração com IA ou serviço externo

- Informe o usuário de que o dado será enviado a terceiro, envie só o necessário e trate timeout e falha.
- Não envie dados do usuário além do indispensável.
- Identifique as respostas da IA como sugestões e exiba avisos de responsabilidade quando o domínio exigir (saúde, finanças, jurídico).

### Privacidade e proteção de dados

- Colete o mínimo necessário. Registre o consentimento (versão do documento aceito, data e hora).
- Dados sensíveis têm acesso restrito e política de retenção definida.
- Atenda pedidos de acesso, correção e eliminação ou anonimização conforme a lei aplicável ao projeto.
- Não afirme o conteúdo de leis além do que a fonte do projeto diz; dúvidas jurídicas vão para as questões em aberto.

## Decisões que normalmente precisam de ADR antes de implementar

Bloqueio por tentativas de login; algoritmo de hash de senha; 2FA; expiração de sessão por inatividade; armazenamento criptografado de arquivos; política de eliminação de dados; reserva transacional e bloqueio de linha; integração com IA ou serviço externo. Não implemente nenhuma delas sem ADR `aceita`.

## Ao revisar

Para cada problema, informe: categoria OWASP, requisito de segurança relacionado (quando houver), arquivo e linha, cenário de exploração e correção sugerida. Classifique a gravidade. **Não relate riscos hipotéticos como se fossem falhas confirmadas**: diferencie "confirmado", "provável" e "a verificar". Ao revisar uma spec, confira se cada requisito de segurança aplicável tem regra, critério de aceite e teste correspondentes.
