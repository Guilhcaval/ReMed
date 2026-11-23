# Catálogo de requisitos — ReMed

Transcrição fiel do **Documento de Requisitos ReMed** (43 páginas, gerado em 21/11/2026). Este catálogo substitui a consulta ao documento original, que não fica no repositório. Visão de produto, fases e questões em aberto: [01-remed.md](01-remed.md).

Não foram transcritas: a seção 2.1, que só tem texto-modelo; a contagem de pontos de função, incompleta (só o total não ajustado: 485 PF); e as referências.

## Convenções da fonte

- **Identificação:** `[nome da subseção. identificador]`, por exemplo `[Recuperação de senha. RF003]`. Os IDs começam em `RF001`, `RNF01` e `RS001` e seguem incrementando.
- **Prioridades:**
  - **Essencial:** sem ele o sistema não entra em funcionamento. Tem de ser implementado.
  - **Importante:** sem ele o sistema funciona, mas de forma não satisfatória. Deve ser implementado, mas o sistema pode ser implantado sem ele.
  - **Desejável:** não compromete as funções básicas. Pode ficar para versões posteriores.
- **Módulos:**
  - Acesso e usuários: RF001 a RF004.
  - Pontos de coleta: RF005 a RF007.
  - Doação de medicamentos: RF008 a RF012.
  - Solicitação de medicamentos: RF013 e RF014.
  - Busca, correspondência e retirada: RF015 a RF020.
  - Moderação e métricas: RF021 e RF022.
- Os números entre colchetes depois de um campo (por exemplo `[1]`) indicam a regra numerada correspondente.

---

## 1. Requisitos funcionais

### RF001 — Cadastro de Usuário

- **Descrição:** cadastro dos usuários da plataforma (doador, solicitante ou cuidador/familiar). O sistema é aberto ao público: basta o cadastro para doar ou solicitar medicamentos.
- **Usuários:** Visitante (futuro doador, solicitante ou cuidador/familiar).
- **Prioridade:** Essencial.

**Campos — Cadastro de Usuário**

| Campo | Tipo | Formato / observação |
| --- | --- | --- |
| Nome completo | String | Mín. 3 e máx. 120 caracteres |
| CPF | String | xxx.xxx.xxx-xx [1] |
| Data de nascimento | Date | xx/xx/xxxx [2] |
| E-mail | String | [3] |
| Celular | String | (xx)xxxxx-xxxx |
| Senha | String | [4] |
| Perfil de uso | Integer | [5] |
| Aceite dos Termos de Uso e Política de Privacidade | Boolean | [6] |
| Data do cadastro | Date | xx/xx/xxxx |
| Status | Integer | [7] |

**Campos — Endereço:** CEP (String, xxxxx-xxx) [8]; Logradouro, Número, Bairro, Município, Estado e Complemento (String).

**Regras**
1. O CPF deve ter os dígitos validados e ser único no sistema.
2. Cadastro só para maiores de 18 anos. Menores de idade são representados por um cuidador/familiar.
3. O e-mail deve ser único. Depois do cadastro, um link de confirmação é enviado ao endereço informado.
4. Senha com no mínimo 8 caracteres, guardada como hash, nunca em texto aberto (RS005).
5. Perfil de uso: Doador, Solicitante ou Cuidador/Familiar. Um usuário pode acumular mais de um perfil. O perfil Administrador só pode ser dado por outro Administrador (RF004).
6. O aceite é obrigatório. São registrados a versão do documento aceito, a data e a hora. A política de privacidade e o consentimento serão definidos em pendência da ata (RNF10).
7. Status: ativo, inativo, suspenso ou bloqueado, sempre com histórico. A alteração do status pelo Administrador está no RF004.
8. O CEP preenche os campos automaticamente (webservice), com edição de número e complemento. O endereço só serve para a geolocalização aproximada (RF015) e não é exibido a outros usuários (RS002).

**Mensagens:** campos obrigatórios vazios: "Campo(s) obrigatório(s) não preenchido(s)", destacando os campos • campos incorretos: "Campo preenchido incorretamente" • "CPF já cadastrado" • "E-mail já cadastrado" • sucesso: "Cadastro realizado com sucesso".

**Alteração:** feita pelo próprio usuário, exceto o CPF, que não pode ser mudado depois do cadastro. Sempre com histórico (quem, o quê, data e hora).

**Exclusão:** o usuário pode pedir o encerramento da conta. Os dados pessoais são eliminados ou anonimizados conforme a LGPD (RNF10), mantendo só os registros de doações e entregas, de forma anônima, para as métricas (RF022). O prazo será definido na política de privacidade.

**Tela "Criar conta · ReMed — Cadastro de pessoa física"** ([imagem](<telas/Cadastro Pessoa Física.png>)):
- Duas abas: "Pessoa Física · Doador / Solicitante" (selecionada) e "Pessoa Jurídica · Ponto de Coleta".
- Seção **Dados pessoais**: "Os campos com * são obrigatórios". Campos:
  - Nome completo* ("De 3 a 120 caracteres").
  - CPF* ("Informe um CPF válido e ainda não cadastrado").
  - Data de nascimento* ("Cadastro para maiores de 18 anos"), com o aviso "Menores de 18 anos devem ser representados por um cuidador ou familiar".
  - E-mail* ("Use um e-mail não cadastrado. Enviaremos a confirmação").
  - Celular*.
  - Senha*, com botão "Mostrar" ("Use no mínimo 8 caracteres").
- Seção **Como você quer usar o ReMed?**: "Selecione um ou mais perfis", com caixas de seleção Doador, Solicitante e Cuidador/Familiar.
- Seção **Seu endereço**: CEP* com o link "Não sei meu CEP"; Logradouro*, Bairro* e Município* ("Preenchido pelo CEP"); Número*; Estado* (UF); Complemento (opcional).
  - Aviso: "Seu endereço é usado apenas para localização aproximada e não será exibido a outros usuários".
- Caixa "Li e aceito os Termos de Uso e a Política de Privacidade.*". Nota: "A data do cadastro é registrada automaticamente pelo sistema".
- Botão **Cadastrar usuário** e o link "Já tem uma conta? Entrar".
- Rodapé: "ReMed · Conectando cuidado, compartilhando saúde".

### RF002 — Autenticação e Controle de Acesso

- **Descrição:** acesso seguro ao sistema (login, bloqueio por tentativas inválidas e expiração da sessão) e controle dos perfis de acesso. A recuperação de senha está no RF003.
- **Usuários:** Doador, Solicitante, Cuidador/Familiar e Administrador.
- **Prioridade:** Essencial.

**Campos — Login:** E-mail ou CPF (String); Senha (String).

**Regras**
1. Depois de 5 tentativas de login inválidas em 15 minutos, a conta é bloqueada temporariamente e o usuário é informado (RS005).
2. A sessão expira após 30 minutos de inatividade.
3. Perfis de acesso:
   - Doador: RF008, RF009, RF010, RF016, RF018, RF019, RF020.
   - Solicitante/Cuidador: RF013, RF014, RF016, RF018, RF019, RF020.
   - Ponto de coleta (representante da instituição): RF005, RF006.
   - Administrador: RF004, RF007, RF011, RF014, RF021, RF022.
   - Todos os perfis autenticados recebem notificações (RF017) e podem registrar denúncias (RF021).
   - Visitantes sem login só podem consultar a busca resumida (RF015) e iniciar a recuperação de senha (RF003).
4. O acesso do Administrador exige autenticação em dois fatores.
5. Todos os acessos (sucesso e falha) são registrados com data, hora e identificação do usuário.

**Mensagens:** login inválido: "E-mail/CPF ou senha incorretos" • conta bloqueada: "Muitas tentativas. Tente novamente mais tarde".

**Tela "Entrar no ReMed"** ([imagem](<telas/Login ReMed.png>)):
- Subtítulo "Acesse sua conta para continuar".
- Campos: "E-mail, CPF ou CNPJ" e Senha, com botão "Mostrar".
- Link "Esqueci minha senha", botão **Entrar** e o link "Ainda não tem uma conta? Criar conta".
- Link "Continuar como visitante", com o quadro "Consulte o resumo dos medicamentos disponíveis. Para doar ou solicitar, entre na sua conta".
- Observação: a tela aceita CNPJ, o que diverge do campo "E-mail ou CPF" deste requisito.

### RF003 — Recuperação de Senha

- **Descrição:** permite que o usuário que esqueceu a senha defina uma nova, de forma segura, por um link enviado ao e-mail cadastrado.
- **Usuários:** Doador, Solicitante, Cuidador/Familiar, Representante da instituição e Administrador (qualquer usuário cadastrado).
- **Pré-condição:** usuário cadastrado (RF001) com e-mail confirmado.
- **Prioridade:** Importante.

**Campos — Solicitação de recuperação:** E-mail (String) [1]; Data e hora da solicitação (Datetime, xx/xx/xxxx xx:xx).

**Campos — Redefinição de senha:** Link de recuperação (token) (String) [2]; Nova senha (String) [3]; Confirmação da nova senha (String); Data e hora da redefinição (Datetime, xx/xx/xxxx xx:xx).

**Regras**
1. A resposta à solicitação é sempre a mesma, exista ou não o e-mail informado, para não revelar quais e-mails estão cadastrados (RS012). O link só é enviado ao e-mail cadastrado do usuário.
2. O link vale 1 hora e é de uso único. Uma nova solicitação invalida o link anterior. O token é gerado de forma aleatória e guardado só como hash (RS012).
3. A nova senha segue as regras do RF001, é guardada como hash e não pode ser igual à senha atual (RS005).
4. Depois da redefinição, as sessões ativas do usuário são encerradas e ele é avisado por e-mail de que a senha foi alterada (RF017).
5. Há limite de solicitações por e-mail e por endereço IP em um período (sugerido: 5 por hora), para evitar uso indevido (RS012). Todas as solicitações e redefinições (sucesso e falha) são registradas com data, hora e identificação do usuário (RF002).

**Mensagens:** solicitação enviada: "Se o e-mail estiver cadastrado, você receberá as instruções para redefinir a senha" • link inválido ou expirado: "Link inválido ou expirado. Solicite uma nova recuperação" • senha fora do padrão: "Campo preenchido incorretamente" • sucesso: "Senha alterada com sucesso".

### RF004 — Gestão de Usuários pelo Administrador

- **Descrição:** gestão dos usuários pelo Administrador: consulta, alteração de status (ativar, inativar, suspender e bloquear) e atribuição do perfil Administrador.
- **Usuários:** Administrador.
- **Pré-condição:** usuário logado com perfil Administrador, com autenticação em dois fatores (RF002).
- **Prioridade:** Importante.

**Campos — Consulta de Usuários:** Nome ou CPF parcial (String); E-mail (String); Perfil de uso (Integer); Status (Integer); Período de cadastro (Date, início e fim).

**Campos — Gestão do Usuário:** Usuário (Integer, identificador); Ação (Integer) [1]; Novo status (Integer) [2]; Motivo (String) [3]; Perfil atribuído (Integer) [4]; Responsável pela ação (String); Data e hora da ação (Datetime, xx/xx/xxxx xx:xx).

**Regras**
1. Ações permitidas: consultar o cadastro, alterar o status (ativar, inativar, suspender, bloquear e desbloquear) e atribuir ou remover o perfil Administrador. O Administrador não altera os dados pessoais do usuário nem o CPF (RF001).
2. Os status seguem o RF001: ativo, inativo, suspenso ou bloqueado. Usuário suspenso ou bloqueado não consegue autenticar (RF002). Suas doações "disponíveis" saem da busca e suas reservas e agendamentos em aberto são cancelados, com aviso à outra parte (RF017).
3. O motivo é obrigatório para suspender ou bloquear e é informado ao usuário. A suspensão pode decorrer da análise de uma denúncia (RF021).
4. O perfil Administrador só pode ser dado por outro Administrador, nunca a si mesmo, e exige autenticação em dois fatores (RF002). Deve existir sempre ao menos um Administrador ativo (RS015).
5. O Administrador vê só os dados necessários à gestão (nome, CPF parcialmente oculto, e-mail, perfil e status), nunca receitas (RF014) nem outros dados de saúde (RS002).

**Mensagens:** motivo não informado: "Informe o motivo da suspensão ou do bloqueio" • remoção do último Administrador: "Não é possível remover o último Administrador ativo" • sucesso: "Status do usuário alterado com sucesso".

**Alteração:** o status e o perfil podem ser alterados de novo pelo Administrador, sempre com histórico (quem, o quê, data e hora) (RNF14).

**Exclusão:** o Administrador não exclui usuários. O encerramento da conta é pedido pelo próprio usuário (RF001).

**Pesquisa:** por nome, CPF, e-mail, perfil de uso, status e período de cadastro.

### RF005 — Cadastro de Ponto de Coleta (Pessoa Jurídica)

- **Descrição:** cadastro de pessoas jurídicas (farmácias, postos de saúde, hospitais, clínicas e instituições sociais) que servirão de ponto de coleta, isto é, local seguro e combinado para a retirada dos medicamentos pelo solicitante. O envio dos documentos está no RF006 e a análise pelo Administrador, no RF007.
- **Usuários:** Representante da instituição e Administrador.
- **Pré-condição:** responsável com cadastro de usuário (RF001) e autenticado (RF002).
- **Prioridade:** Importante.

**Campos — Cadastro do Ponto de Coleta**

| Campo | Tipo | Formato / observação |
| --- | --- | --- |
| CNPJ | String | xx.xxx.xxx/xxxx-xx [1] |
| Razão Social | String | |
| Nome Fantasia | String | |
| Tipo de estabelecimento | Integer | [2] |
| E-mail | String | |
| Telefone | String | (xx)xxxxx-xxxx |
| Dias e horários de funcionamento para retirada | String | [3] |
| Possui refrigeração para medicamentos | Boolean | [4] |
| Observações | String | |
| Data do cadastro | Date | xx/xx/xxxx |
| Status | Integer | [5] |

**Campos — Endereço do Ponto de Coleta:** CEP (String, xxxxx-xxx) [6]; Logradouro, Número, Bairro, Município, Estado e Complemento (String).

**Campos — Responsável pelo Ponto de Coleta:** CPF (String, xxx.xxx.xxx-xx) [7]; Nome (String); E-mail (String); Contato (String, (xx)xxxxx-xxxx).

**Regras**
1. O CNPJ deve ter os dígitos validados e ser único no sistema.
2. Opções: farmácia, posto/unidade de saúde, hospital, clínica, organização não governamental/instituição social e outros. A lista é mantida em cadastro auxiliar.
3. Os horários informados limitam as opções de data e horário no agendamento da retirada (RF018).
4. A informação indica o ponto como adequado a medicamentos refrigerados (RF010).
5. Status: pendente de aprovação, ativo, suspenso ou inativo. Só pontos "ativos" aparecem para doadores e solicitantes. Sempre com histórico. A passagem de "pendente de aprovação" para "ativo" depende do envio dos documentos (RF006) e da análise do Administrador (RF007).
6. O CEP preenche os campos automaticamente (webservice), com edição de número e complemento. Diferente do endereço de usuários, o endereço do ponto de coleta é público e é usado na busca por proximidade (RF015).
7. O responsável deve ter cadastro de usuário (RF001) e ser vinculado à instituição. Pode haver mais de um responsável por ponto de coleta.

**Aprovação:** todo cadastro nasce "pendente de aprovação" e só é ativado após o envio dos documentos (RF006) e a análise do Administrador (RF007), que também pode suspender ou inativar o ponto.

**Alteração:** feita pelo responsável da instituição, exceto o CNPJ, que só o Administrador altera. Sempre com histórico (quem, o quê, data e hora).

**Exclusão:** não há exclusão. O ponto muda de status (suspenso ou inativo), mantendo o histórico, inclusive das retiradas já feitas nele.

**Pesquisa:** por CNPJ, razão social, nome fantasia, tipo de estabelecimento, município e status.

**Observação:** nesta versão o ponto de coleta é só o local do encontro entre doador e solicitante. A guarda temporária de medicamentos pela instituição não está prevista e depende de definição com o cliente e de validação legal (RNF11).

**Tela "Parceria ReMed — Cadastro de instituição / ponto de coleta"** ([imagem](<telas/Cadastro Pessoa Jurídica.png>)):
- Aba "Pessoa Jurídica · Ponto de Coleta" selecionada.
- Aviso "Cadastro com responsável autenticado: o ponto será vinculado à sua conta ReMed já cadastrada. Não é necessário criar uma senha para a instituição".
- Seção **Dados da instituição**: CNPJ* ("Informe um CNPJ válido e ainda não cadastrado"), Razão social*, Nome fantasia*, Tipo de estabelecimento* (opções: Farmácia · Posto/Unidade de Saúde · Hospital · Clínica · ONG/Instituição Social · Outros), E-mail institucional* e Telefone*.
- Seção **Endereço do ponto de coleta**: CEP* com "Não sei meu CEP", Logradouro*, Número*, Bairro*, Município*, Estado* e Complemento (opcional).
  - Aviso: "O endereço do ponto de coleta é público e será exibido para orientar os encontros de retirada".
- Seção **Funcionamento e estrutura**:
  - Dias de funcionamento para retirada*, com caixas de Seg a Dom.
  - Abertura* e Fechamento* (hh:mm). "O horário informado vale para os dias selecionados", com o link "+ Adicionar outro horário".
  - "Possui refrigeração para medicamentos?*" (Sim/Não).
  - Aviso: "O ponto de coleta é apenas um local seguro de encontro para a retirada, não um local de guarda temporária de medicamentos".
- Seção **Documentação e observações**: "Anexe a licença de funcionamento / alvará sanitário para análise.*", com área de envio ("PDF, JPG ou PNG · Máximo de 5 MB por arquivo") e Observações (opcional).
- Seção **Responsável pelo ponto de coleta**: dados da conta autenticada (CPF, Nome, E-mail, Contato), só para leitura, com a etiqueta "Usuário vinculado · autenticado". Link "+ Adicionar outro responsável" ("Deve ter uma conta ReMed já cadastrada").
- Aviso "Status inicial automático: Pendente de aprovação. O administrador analisará os documentos. O ponto de coleta só será ativado após a aprovação do cadastro".
- Botão **Cadastrar ponto de coleta e enviar para aprovação** e o link "Voltar para minha conta".

### RF006 — Envio de Documentos do Ponto de Coleta

- **Descrição:** envio, substituição e acompanhamento dos documentos que comprovam a regularidade do estabelecimento (licença de funcionamento e alvará sanitário).
- **Usuários:** Representante da instituição e Administrador (consulta).
- **Pré-condição:** ponto de coleta cadastrado (RF005) e responsável autenticado (RF002).
- **Prioridade:** Importante.

**Campos — Envio do Documento:** Ponto de coleta (Integer, identificador); Tipo de documento (Integer) [1]; Arquivo (File, PDF, JPG ou PNG, máx. 5 MB) [2]; Número do documento (String); Data de validade do documento (Date, xx/xx/xxxx) [3]; Data e hora do envio (Datetime, xx/xx/xxxx xx:xx); Status do documento (Integer) [4].

**Regras**
1. Opções: licença de funcionamento e alvará sanitário, ambos obrigatórios. Outros tipos podem ser incluídos em cadastro auxiliar. O cadastro só segue para análise (RF007) depois do envio dos documentos obrigatórios.
2. O arquivo deve ser legível e ficar vinculado à instituição, para consulta posterior pelo Administrador (RS011). O tipo e o conteúdo do arquivo são verificados antes do aceite (RS013, RNF16).
3. Não se aceita documento com validade anterior à data atual. O representante é avisado antes do vencimento (RF017). Vencido o prazo sem renovação, o ponto volta a ficar pendente de nova análise (RF007).
4. Status: enviado, em análise, aprovado, reprovado ou vencido. A aprovação ou reprovação é registrada pelo Administrador no RF007. Sempre com histórico.
5. Os documentos ficam visíveis só ao responsável pelo ponto e ao Administrador, nunca a doadores ou solicitantes (RS013).

**Mensagens:** formato inválido: "Envie o arquivo em PDF, JPG ou PNG" • arquivo acima do limite: "O arquivo deve ter no máximo 5 MB" • documento vencido: "Documento vencido. Envie um documento válido" • sucesso: "Documento enviado com sucesso. O cadastro está em análise".

**Alteração:** o representante pode enviar uma nova versão de um documento reprovado ou vencido. A versão anterior fica no histórico, com quem enviou, data e hora.

**Exclusão:** documentos enviados não são excluídos. A substituição gera uma nova versão.

**Pesquisa:** o Administrador consulta por ponto de coleta, tipo, status e data de validade.

### RF007 — Aprovação do Ponto de Coleta

- **Descrição:** análise, aprovação ou reprovação e acompanhamento da situação dos pontos de coleta pelo Administrador, para que só estabelecimentos regulares sejam exibidos.
- **Usuários:** Administrador.
- **Pré-condição:** Administrador logado com dois fatores (RF002); ponto com status "pendente de aprovação" (RF005) e documentos enviados (RF006).
- **Prioridade:** Importante.

**Campos — Análise do Cadastro:** Ponto de coleta (Integer, identificador); Resultado (Integer) [1]; Motivo da reprovação ou da pendência (String) [2]; Responsável pela análise (String); Data e hora da análise (Datetime, xx/xx/xxxx xx:xx).

**Campos — Alteração de Situação:** Novo status (Integer) [3]; Motivo (String).

**Regras**
1. Resultado: aprovado, reprovado ou pendente de documentação.
   - Aprovado: o status passa a "ativo" e o ponto pode ser escolhido nas doações (RF008) e exibido nos agendamentos (RF018).
   - Reprovado ou pendente: o ponto continua oculto e o representante é orientado a corrigir ou reenviar os documentos (RF006).
2. O motivo é obrigatório e é informado ao representante (RF017). Os critérios de aprovação (CNPJ ativo e compatível com o tipo de estabelecimento, documentos legíveis e dentro da validade, endereço conferido) serão definidos no detalhamento do cadastro.
3. Um ponto "ativo" pode ser suspenso ou inativado pelo Administrador (por exemplo, por denúncia — RF021 — ou documento vencido) e reativado após nova análise. Ponto suspenso ou inativo deixa de ser exibido, e os agendamentos futuros nele são cancelados ou remarcados, com aviso às partes (RF018 e RF017).
4. Deve haver revisão periódica dos pontos ativos, incluindo a conferência dos documentos vencidos (RS011).
5. Histórico com quem analisou, resultado, motivo, data e hora. O registro não pode ser apagado (RNF14).

**Mensagens:** motivo não informado: "Informe o motivo da reprovação ou da suspensão" • sucesso: "Situação do ponto de coleta atualizada com sucesso".

**Pesquisa:** lista por status (pendente de aprovação, ativo, suspenso ou inativo), tipo de estabelecimento, município e CNPJ.

### RF008 — Cadastro de Doação de Medicamento

- **Descrição:** cadastro dos medicamentos não vencidos oferecidos para doação. A doação também pode ser feita por alguém que deseja ajudar.
- **Usuários:** Doador.
- **Pré-condição:** usuário logado com perfil Doador.
- **Prioridade:** Essencial.

**Campos — Cadastro da Doação**

| Campo | Tipo | Formato / observação |
| --- | --- | --- |
| Nome do medicamento (comercial ou genérico) | String | Máx. 150 caracteres |
| Princípio ativo | String | |
| Concentração/dosagem | String | Ex.: 500 mg |
| Forma farmacêutica | Integer | [1] |
| Quantidade | Integer | Unidades |
| Fabricante | String | |
| Lote | String | |
| Data de validade | Date | xx/xx/xxxx [2] |
| Embalagem íntegra | Boolean | [3] |
| Foto da embalagem (frente e validade/lote) | Image | JPG ou PNG, máx. 5 MB [4] |
| Condição de conservação | Integer | [5] |
| Sujeito a receita | Boolean | [6] |
| Ponto de coleta para retirada | Integer | [7] |
| Observações | String | |
| Data do cadastro | Date | xx/xx/xxxx |
| Status | Integer | [8] |

**Regras**
1. A lista de formas farmacêuticas (comprimido, cápsula, xarope, injetável, pomada, colírio etc.) é mantida em cadastro auxiliar.
2. A validade é o principal ponto de atenção. É obrigatória e não se aceita data anterior à atual. A validade mínima restante será definida na pendência de critérios de conferência (RF011).
3. Só embalagens íntegras são aceitas. Se o doador marcar "não", o cadastro é bloqueado com mensagem explicativa.
4. A foto é obrigatória e fica vinculada à doação para a conferência (RF011) e a retirada (RF020). Pode ser usada a leitura automática por IA (RF009).
5. Opções: temperatura ambiente ou refrigerado. Se refrigerado, aplica-se o RF010.
6. Se "sim", aplica-se o RF014.
7. Escolhido, de preferência, entre os pontos de coleta cadastrados e ativos (RF005). Se não houver ponto próximo, outro local seguro pode ser combinado no agendamento (RF018). A residência do doador não deve ser sugerida por padrão (RS008).
8. Status: em análise, disponível, reservado, entregue, vencido, reprovado ou cancelado. Sempre com histórico. A mudança para "vencido" é feita automaticamente pela rotina do RF012.

**Aviso obrigatório:** ao salvar, o sistema mostra que a plataforma não substitui avaliação médica ou farmacêutica (RNF13).

**Alteração:** permitida ao doador enquanto o status for "em análise" ou "disponível". Se validade, lote ou quantidade mudarem, a doação volta para "em análise". Histórico com quem alterou, o quê, data e hora.

**Exclusão:** não há exclusão. O doador pode cancelar a doação (status "cancelado") enquanto ela não for entregue, mantendo o histórico.

**Pesquisa:** o doador consulta suas doações por medicamento, status e período.

### RF009 — Leitura da Embalagem por IA

- **Descrição:** lê a foto da embalagem enviada no RF008 com um modelo de IA multimodal (análise da imagem e extração dos dados) e sugere o preenchimento automático dos campos da doação.
- **Usuários:** Doador e Sistema.
- **Pré-condição:** foto da embalagem anexada no cadastro da doação (RF008).
- **Prioridade:** Desejável.

**Entrada:** Foto da embalagem (Image, JPG ou PNG, máx. 5 MB).

**Saída (sugestão de preenchimento):** Nome do medicamento (String); Princípio ativo e concentração (String); Lote (String); Data de validade (Date); Fabricante (String); Nível de confiança de cada campo (Float, 0 a 1) [1].

**Regras**
1. Os dados sugeridos são exibidos ao doador para conferência e edição antes de salvar. A IA só sugere, não decide (RS009, RNF13).
2. Campos de baixa confiança são destacados e exigem confirmação manual. O limite será definido na fase de detalhamento do cadastro. A data de validade sugerida sempre deve ser confirmada pelo doador. Campos que a IA não conseguir ler ficam em branco, sem estimativa.
3. Se a IA estiver indisponível ou falhar, o doador preenche manualmente, sem perder o que já digitou.
4. Deve ser avaliada uma eventual integração com bases de dados ou API de medicamentos, para validar nome e concentração (RNF12).
5. As imagens só servem à doação e são eliminadas conforme a política de privacidade (RNF10).
6. A foto vai para um serviço externo de IA. O doador é informado disso e orientado a não fotografar etiquetas com dados pessoais (por exemplo, nome do paciente), conforme a LGPD (RNF10).

### RF010 — Gestão de Medicamentos Refrigerados

- **Descrição:** trata os medicamentos que exigem refrigeração, como a insulina, garantindo transporte e conservação apropriados.
- **Usuários:** Doador, Solicitante e Cuidador/Familiar.
- **Pré-condição:** doação cadastrada com conservação "refrigerado" (RF008).
- **Prioridade:** Essencial.

**Campos — Controle de conservação:** Condição de conservação (Integer, refrigerado); Faixa de temperatura indicada na bula (String) [1]; Declaração do doador de conservação adequada (Boolean) [2]; Ciência do solicitante sobre o transporte (Boolean) [3]; Janela de retirada (Time, xx:xx a xx:xx) [4].

**Regras**
1. Em geral entre 2 °C e 8 °C. A informação da bula prevalece.
2. O doador declara que o medicamento foi mantido refrigerado até o cadastro e que será mantido até a retirada.
3. O solicitante recebe a orientação de transporte (ex.: bolsa térmica) e confirma ciência antes do agendamento (RS004).
4. A retirada ocorre em janela curta, no mesmo dia, em ponto de coleta com refrigeração, quando possível (RF005 e RF018). O limite de tempo será definido em pendência da ata (prazo 10/11/2026).
5. Na retirada, o solicitante confere a conservação e pode recusar o medicamento (RF020).
6. Refrigerados sem informação de conservação são rejeitados no cadastro (RF008).

### RF011 — Conferência e Aprovação de Validade

- **Descrição:** confere a validade e a integridade do medicamento antes de disponibilizá-lo. A retirada automática dos vencidos está no RF012.
- **Usuários:** Administrador (ou responsável pela conferência).
- **Pré-condição:** doação com status "em análise".
- **Prioridade:** Essencial.

**Campos — Conferência da Doação:** Doação (Integer, identificador); Resultado (Integer, aprovada ou reprovada); Motivo da reprovação (String) [1]; Responsável pela conferência (String); Data e hora da conferência (Datetime, xx/xx/xxxx xx:xx).

**Regras**
1. Toda doação nasce "em análise" e só passa a "disponível" depois de aprovada. Se reprovada, o motivo é obrigatório e informado ao doador. O doador é informado do resultado (RF017).
2. Os critérios de conferência e de comprovação da validade (validade mínima restante, uso da foto, conferência manual ou automática) serão definidos em pendência da ata (prazo 03/11/2026).
3. O solicitante pode recusar o medicamento na retirada se a validade divergir do cadastro (RF020).
4. Histórico com quem conferiu, resultado, data e hora.

### RF012 — Rotina Automática de Vencimento

- **Descrição:** verifica automaticamente a validade das doações, retira da plataforma os medicamentos vencidos ou abaixo da validade mínima, cancela as reservas e avisa os envolvidos.
- **Usuários:** Sistema. Doador e Solicitante (notificados).
- **Pré-condição:** doações com status "em análise", "disponível" ou "reservado" (RF008).
- **Prioridade:** Essencial.

**Campos — Parâmetros da Rotina:** Validade mínima restante (Integer, dias) [1]; Antecedência do aviso de vencimento (Integer, dias) [2].

**Campos — Execução da Rotina:** Data e hora da execução (Datetime, xx/xx/xxxx xx:xx) [3]; Doações verificadas (Integer); Doações marcadas como vencidas (Integer); Reservas e agendamentos cancelados (Integer); Notificações enviadas (Integer); Resultado da execução (Integer) [4].

**Regras**
1. A validade mínima restante será definida na pendência de critérios de conferência (RF011). Doações com validade expirada, ou abaixo desse mínimo, passam a "vencido".
2. O aviso de "doação prestes a vencer" vai ao doador com antecedência configurável (sugerido: 15 dias) (RF017).
3. A rotina roda automaticamente uma vez por dia, em horário de menor uso (RNF15). A validade também é conferida na reserva (RF016) e no agendamento (RF018), para que uma doação que venceu no mesmo dia não seja reservada.
4. Resultado: sucesso, parcial ou falha. Cada execução é registrada. Em caso de falha, o Administrador é alertado e a rotina roda de novo (RNF15).
5. A doação "vencida" sai da busca (RF015), tem reservas e agendamentos cancelados, a solicitação vinculada volta a "aberta" e doador e solicitante são notificados (RF017), com orientação de descarte conforme a legislação sanitária (RNF11).
6. A doação vencida não pode voltar a "disponível". A quantidade vencida entra no RF022 (medicamentos vencidos antes da entrega). Esta rotina responde ao perigo do RS001.

**Alteração:** o Administrador pode alterar os parâmetros, com registro de quem alterou, o quê, data e hora.

### RF013 — Cadastro de Solicitação de Medicamento

- **Descrição:** cadastro da necessidade de um medicamento. O pedido pode ser feito pelo próprio beneficiário ou por um cuidador/familiar.
- **Usuários:** Solicitante e Cuidador/Familiar.
- **Pré-condição:** usuário logado com perfil Solicitante ou Cuidador/Familiar.
- **Prioridade:** Essencial.

**Campos — Cadastro da Solicitação:** Medicamento, nome ou princípio ativo (String); Concentração/dosagem (String); Quantidade necessária (Integer); Pedido em nome de terceiro (Boolean) [1]; Pessoa que fará a retirada (String) [1]; Receita (File, JPG, PNG ou PDF, máx. 5 MB) [2]; Raio de busca para retirada (Integer, km); Disponibilidade de dias e horários (String); Data do cadastro (Date, xx/xx/xxxx); Status (Integer) [3].

**Regras**
1. Se o pedido for feito por cuidador/familiar, deve ser informado quem fará a retirada. Os dados do beneficiário são limitados ao mínimo necessário.
2. Obrigatória quando o medicamento é sujeito a receita (RF014). O arquivo é tratado como dado sensível (RS002).
3. Status: aberta, correspondida, agendada, atendida, cancelada ou expirada. Sempre com histórico.
4. A plataforma não coleta, não exibe e não compartilha o motivo da necessidade de saúde (RS002).
5. Deve existir um limite de solicitações abertas por usuário, para evitar uso indevido (RS006). O valor será definido no detalhamento.
6. A solicitação sem correspondência expira após um prazo configurável (sugerido: 30 dias) e o usuário é notificado (RF017) para renová-la ou cancelá-la.

**Alteração:** o solicitante pode alterar ou cancelar enquanto o status for "aberta" ou "correspondida".

**Exclusão:** não há exclusão. A solicitação é cancelada (status), mantendo o histórico.

**Pesquisa:** o solicitante consulta suas solicitações por medicamento, status e período.

### RF014 — Fluxo para Medicamentos Sujeitos a Receita

- **Descrição:** exige e verifica a receita válida antes da correspondência e da retirada de medicamentos sujeitos a receita.
- **Usuários:** Solicitante, Cuidador/Familiar e Administrador (verificador).
- **Pré-condição:** solicitação de medicamento sujeito a receita (RF013).
- **Prioridade:** Essencial.

**Campos — Verificação da Receita:** Solicitação (Integer, identificador); Receita (File, JPG, PNG ou PDF) [1]; Data de emissão da receita (Date); Status da verificação (Integer) [2]; Responsável pela verificação (String) [3]; Observação (String); Data e hora da verificação (Datetime).

**Regras**
1. A receita deve conter o medicamento, a data de emissão, o profissional prescritor e a assinatura. A prescrição de controle especial fica bloqueada até a definição do fluxo (RS003).
2. Status: pendente, válida ou inválida. A correspondência de um medicamento sujeito a receita só ocorre com a receita "válida" (RF016).
3. Quem verificará a documentação será definido em pendência da ata (prazo 10/11/2026).
4. A receita é dado sensível: guardada criptografada, visível só ao verificador, nunca ao doador, e excluída após o prazo da política de privacidade (RNF10).
5. Na retirada, quem retira deve ser a pessoa informada na solicitação (RF013).
6. O sistema não substitui avaliação médica ou farmacêutica (RNF13).

### RF015 — Busca de Medicamentos e Geolocalização

- **Descrição:** busca de medicamentos disponíveis para doação, com geolocalização para priorizar as opções mais próximas.
- **Usuários:** Visitante, Doador, Solicitante e Cuidador/Familiar.
- **Prioridade:** Essencial.

**Filtros:** Nome do medicamento ou princípio ativo (String); Forma farmacêutica (Integer); Concentração/dosagem (String); Distância máxima (Integer, km) [1]; Validade mínima restante (Date); Condição de conservação (Integer, ambiente ou refrigerado).

**Resultado exibido:**
- Nome, concentração, forma farmacêutica e quantidade.
- Data de validade.
- Bairro ou região aproximada e distância [2].
- Condição de conservação e indicação de exigência de receita.

**Regras**
1. A localização é obtida com o consentimento do usuário no navegador ou dispositivo. Como alternativa, o usuário informa o CEP. Por padrão, os resultados vão do mais próximo ao mais distante (RS010).
2. O resultado nunca mostra nome, contato ou endereço do doador (RS002). O ponto de retirada só é revelado depois do agendamento (RF018).
3. Só doações com status "disponível" aparecem.
4. Visitantes sem login veem só o resultado resumido. Para solicitar, é preciso estar logado (RF002).
5. Resultados paginados, 10 por página.
6. Sem resultados, aparece "Nenhum medicamento encontrado" e a opção de cadastrar uma solicitação (RF013), para ser notificado quando surgir uma correspondência (RF016 e RF017).

**Pesquisa:** por nome, princípio ativo, forma farmacêutica, concentração, distância, validade e condição de conservação.

### RF016 — Correspondência entre Oferta e Necessidade

- **Descrição:** cruza automaticamente as doações disponíveis com as solicitações abertas e controla o aceite das duas partes e a reserva da doação. Os envolvidos são avisados conforme o RF017.
- **Usuários:** Sistema, Doador e Solicitante.
- **Pré-condição:** existir doação "disponível" e solicitação "aberta".
- **Prioridade:** Essencial.

**Campos — Correspondência:** Doação (Integer, identificador); Solicitação (Integer, identificador); Distância calculada (Float, km); Status (Integer) [1]; Data e hora (Datetime, xx/xx/xxxx xx:xx).

**Regras**
1. Status: pendente de aceite, aceita, recusada ou expirada.
2. Há correspondência quando coincidem princípio ativo, concentração e forma farmacêutica, dentro do raio informado na solicitação, respeitando as regras de receita (RF014) e de refrigerados (RF010).
3. Com várias solicitações para uma doação, a prioridade é da proximidade (RF015). Em caso de empate, da solicitação mais antiga.
4. A correspondência exige o aceite de doador e solicitante em prazo configurável (sugerido: 48 horas). Vencido o prazo, a doação volta a "disponível" e a solicitação a "aberta". Os envolvidos são avisados da nova correspondência, do aceite e do fim do prazo (RF017).
5. Ao aceitar, a doação passa a "reservada" para uma única correspondência por vez (RS007).

### RF017 — Notificações

- **Descrição:** avisa os usuários, por e-mail e na plataforma, sobre os eventos relevantes de cada fluxo (correspondência, agendamento, vencimento, aprovação de pontos de coleta, mensagens, segurança da conta etc.) e registra todos os envios.
- **Usuários:** Sistema (emissor). Doador, Solicitante, Cuidador/Familiar, Representante da instituição e Administrador (destinatários).
- **Pré-condição:** ocorrência de um evento relevante em outro requisito funcional.
- **Prioridade:** Essencial.

**Campos — Notificação:** Destinatário (Integer, identificador do usuário); Tipo (Integer) [1]; Canal (Integer, e-mail e notificação na plataforma) [2]; Mensagem (String) [3]; Status de envio (Integer) [4]; Data e hora de envio (Datetime, xx/xx/xxxx xx:xx); Data e hora de leitura (Datetime, xx/xx/xxxx xx:xx) [5].

**Regras**
1. Tipos:
   - Nova correspondência, aceite e agendamento confirmado, alterado ou cancelado (RF016, RF018).
   - Lembrete 24 horas antes da retirada (RF018).
   - Doação prestes a vencer e doação vencida (RF012).
   - Nova mensagem (RF019).
   - Resultado da análise do ponto de coleta e documento prestes a vencer (RF007, RF006).
   - Solicitação prestes a expirar (RF013).
   - Resultado de denúncia (RF021).
   - Segurança da conta, como senha alterada, suspensão ou bloqueio (RF003, RF004).
2. E-mail e notificação na plataforma são obrigatórios. Outros canais (SMS ou aplicativo de mensagens) são desejáveis.
3. As notificações não podem conter dados pessoais, o motivo da necessidade nem o texto das mensagens trocadas (RS002, RS014). O endereço do local de retirada só é informado após a confirmação do agendamento (RF018).
4. Status: pendente, enviada, lida ou falha. Se o envio falhar, são feitas até 3 novas tentativas, sem impedir a notificação na plataforma nem a operação que a originou (RNF15). Todas as notificações são registradas.
5. As notificações na plataforma ficam numa lista com indicação de lida ou não lida e são mantidas pelo prazo da política de privacidade (RNF10). As notificações de segurança da conta não podem ser desativadas.

**Pesquisa:** o usuário consulta suas notificações por tipo, status e período.

### RF018 — Agendamento da Retirada

- **Descrição:** agendamento da retirada entre doador e solicitante, evitando desencontros. A retirada tende a ocorrer em local combinado ou instituição, sem logística de entrega obrigatória.
- **Usuários:** Doador, Solicitante e Cuidador/Familiar.
- **Pré-condição:** correspondência aceita pelas duas partes (RF016).
- **Prioridade:** Essencial.

**Campos — Agendamento:** Correspondência (Integer, identificador); Data da retirada (Date, xx/xx/xxxx); Horário (Time, xx:xx); Ponto de coleta ou local combinado (String) [1]; Pessoa que fará a retirada (String); Status (Integer) [2].

**Regras**
1. O doador propõe data, horário e local, e o solicitante confirma ou sugere outra opção. Os detalhes são combinados por mensagens na plataforma (RF019), sem revelar telefone ou e-mail (RS008).
2. Status: proposto, confirmado, reagendado, cancelado, retirado ou não compareceu. Sempre com histórico.
3. O endereço do local só é liberado às duas partes após a confirmação (RS002). Os pontos de coleta cadastrados (RF005) têm prioridade, respeitando o horário de funcionamento de cada um (RS008).
4. Reagendar e cancelar é permitido até um prazo antes do horário (sugerido: 2 horas), com notificação à outra parte (RF017).
5. Se, 24 horas após o horário marcado, não houver confirmação de retirada, o status passa a "não compareceu", a reserva é desfeita e o medicamento volta a "disponível".
6. Para refrigerados, vale a janela curta do RF010.

### RF019 — Mensagens dentro da Plataforma

- **Descrição:** troca de mensagens de texto entre doador e solicitante na plataforma, para combinar a retirada sem que um conheça o telefone, o e-mail ou o endereço do outro.
- **Usuários:** Doador, Solicitante e Cuidador/Familiar (partes da correspondência). Administrador (consulta em caso de denúncia).
- **Pré-condição:** correspondência aceita pelas duas partes (RF016).
- **Prioridade:** Importante.

**Campos — Mensagem:** Correspondência (Integer, identificador); Remetente (Integer, identificador do usuário); Texto (String, máx. 500 caracteres) [1]; Data e hora do envio (Datetime, xx/xx/xxxx xx:xx); Status (Integer) [2].

**Regras**
1. Só texto, sem anexos nem links. O sistema detecta e bloqueia (ou alerta sobre) telefone, e-mail, endereço, links e pedidos de pagamento (RS014). As partes são identificadas de forma reduzida, sem nome completo (RS002).
2. Status: enviada ou lida. O destinatário recebe aviso de nova mensagem, sem o conteúdo (RF017).
3. A conversa fica ativa entre o aceite da correspondência (RF016) e a confirmação da entrega ou o cancelamento do agendamento (RF020 e RF018). Depois, fica só para leitura.
4. Mensagens não podem ser editadas nem apagadas. O histórico fica acessível só às duas partes e, quando há denúncia (RF021), ao Administrador, limitado ao necessário para a análise (RNF10).
5. Cada parte pode bloquear a outra e denunciar a conversa (RF021). A confirmação do agendamento continua no RF018, e não por mensagem (RS008).

**Mensagens:** mensagem vazia: "Digite uma mensagem" • conteúdo não permitido: "Não é permitido compartilhar telefone, e-mail, endereço ou links" • conversa encerrada: "Esta conversa foi encerrada".

**Pesquisa:** o usuário consulta suas conversas por correspondência e período.

### RF020 — Confirmação de Retirada e Entrega

- **Descrição:** registra a efetiva entrega do medicamento ao solicitante, base da principal métrica do sistema.
- **Usuários:** Doador, Solicitante e Cuidador/Familiar.
- **Pré-condição:** agendamento confirmado (RF018).
- **Prioridade:** Essencial.

**Campos — Confirmação da Entrega:** Agendamento (Integer, identificador); Código de confirmação (String) [1]; Quantidade entregue (Integer); Conferência de validade e embalagem (Boolean) [2]; Data e hora da entrega (Datetime, xx/xx/xxxx xx:xx); Avaliação ou denúncia (String, opcional) [3].

**Regras**
1. Um código é gerado ao confirmar o agendamento e enviado só ao solicitante. Ele é informado no ato da retirada para validar a entrega (RS008).
2. Na retirada, o solicitante confere validade, lote e integridade da embalagem com a foto cadastrada. Pode recusar o medicamento, informando o motivo, e ele volta a "disponível" ou "reprovado".
3. Qualquer usuário pode registrar uma avaliação ou denúncia, tratada e analisada pelo Administrador conforme o RF021 (RS006).
4. A entrega pode ser parcial. A quantidade disponível da doação é atualizada e, ao zerar, o status passa a "entregue".
5. A confirmação muda o status da solicitação para "atendida" e o do agendamento para "retirado", e alimenta o RF022.
6. O registro da entrega não pode ser apagado. Correções geram novo registro com quem fez, data e hora.

### RF021 — Denúncia e Moderação

- **Descrição:** registro de denúncias pelos usuários e análise e decisão do Administrador (moderação), para combater uso indevido, medicamentos com problemas, golpes e estabelecimentos irregulares.
- **Usuários:** Doador, Solicitante, Cuidador/Familiar e Representante da instituição (denunciantes). Administrador (moderador).
- **Pré-condição:** usuário logado (RF002). Para a análise, Administrador logado.
- **Prioridade:** Importante.

**Campos — Registro da Denúncia:** Objeto da denúncia (Integer) [1]; Identificador do objeto (Integer); Motivo (Integer) [2]; Descrição (String, máx. 500 caracteres); Data e hora do registro (Datetime, xx/xx/xxxx xx:xx); Status (Integer) [3].

**Campos — Análise da Denúncia:** Decisão (Integer) [4]; Justificativa (String); Responsável pela análise (String); Data e hora da análise (Datetime, xx/xx/xxxx xx:xx).

**Regras**
1. A denúncia pode ser registrada nas telas de doação (RF008), solicitação (RF013), conversa (RF019), ponto de coleta (RF005) e confirmação de retirada (RF020). O objeto pode ser um usuário, doação, solicitação, conversa, ponto de coleta ou retirada.
2. Motivos: medicamento com validade ou embalagem divergente, tentativa de golpe ou cobrança, assédio ou comportamento inadequado, perfil falso, revenda ou acúmulo de medicamentos, ponto de coleta irregular e outros (RS006, RS008, RS011).
3. Status: aberta, em análise, procedente ou improcedente. O prazo de análise é configurável (sugerido: 3 dias úteis). Denúncias que envolvam risco à saúde, como medicamento adulterado, têm prioridade, e a doação sai da busca preventivamente até a decisão (RS001).
4. Decisões possíveis: arquivar, advertir o usuário, retirar a doação, suspender ou bloquear o usuário (RF004) ou suspender o ponto de coleta (RF007). Decisões que envolvam suspensão exigem justificativa informada ao usuário (RF017).
5. A identidade do denunciante não é revelada ao denunciado. O denunciante é informado do resultado (RF017).
6. Na análise, o Administrador pode consultar o histórico da conversa (RF019) e os registros da conferência (RF011) e da entrega (RF020) ligados à denúncia, limitado ao necessário (RNF10, RS002, RS015).
7. Deve existir limite de denúncias por usuário em um período. Denúncias de má-fé reiteradas podem levar à suspensão do denunciante (RS006).
8. Histórico com quem denunciou, quem analisou, a decisão, data e hora. As denúncias não podem ser apagadas (RNF14).

**Mensagens:** descrição vazia: "Descreva o motivo da denúncia" • sucesso: "Denúncia registrada. Você será avisado do resultado".

**Pesquisa:** o Administrador busca denúncias por status, motivo, objeto e período. O denunciante consulta as suas.

### RF022 — Relatório de Métricas de Entregas

- **Descrição:** apresenta os indicadores de desempenho do sistema. A principal métrica é a quantidade de medicamentos efetivamente entregues.
- **Usuários:** Administrador.
- **Pré-condição:** usuário logado com perfil Administrador.
- **Prioridade:** Importante.

**Indicadores**
- Quantidade de medicamentos efetivamente entregues (principal).
- Quantidade de doações cadastradas e de solicitações atendidas.
- Taxa de atendimento: solicitações atendidas ÷ solicitações abertas.
- Tempo médio entre o cadastro da doação e a entrega.
- Quantidade de medicamentos vencidos antes da entrega.
- Quantidade de agendamentos com não comparecimento.
- Quantidade de pontos de coleta ativos por região.
- Quantidade de denúncias registradas e procedentes.

**Filtros:** Período (Date, início e fim); Região, município ou bairro (String); Medicamento ou forma farmacêutica (String).

**Regras**
1. Dados em tabela e gráfico, exportáveis em CSV ou PDF.
2. Só dados agregados e anônimos, sem dados pessoais ou de saúde (RS002).
3. Indicadores calculados a partir dos registros do RF020 (entregas), RF018 (não comparecimentos), RF011 e RF012 (validade e vencimento), RF005 e RF007 (pontos de coleta) e RF021 (denúncias).

---

## 2. Requisitos não funcionais

| ID | Tipo | Descrição | Prioridade |
| --- | --- | --- | --- |
| RNF01 | Produto – facilidade de uso | Interface intuitiva, com linguagem simples e direta, dicas (hint) nos botões, botões de ajuda e glossário (ex.: princípio ativo, validade, receita), facilitando o uso por pessoas com pouca familiaridade com tecnologia. | Importante |
| RNF02 | Produto – facilidade de uso | Mensagens de erro claras quando uma ação não pode ser realizada, indicando o motivo e como corrigir. | Importante |
| RNF03 | Produto – facilidade de uso | A interface segue as diretrizes de acessibilidade WCAG 2.1 nível AA (contraste, navegação por teclado e textos alternativos em imagens). | Importante |
| RNF04 | Produto – desempenho | Páginas públicas e buscas (RF015) respondem em até 3 segundos (percentil 95) com até 500 usuários simultâneos. A leitura da embalagem por IA (RF009) retorna em até 15 segundos. | Importante |
| RNF05 | Produto – confiabilidade | Disponibilidade mínima de 99% ao mês, com backup diário automático (retenção mínima de 30 dias) e restauração testada periodicamente. | Importante |
| RNF06 | Produto – confiabilidade | Reserva, agendamento e entrega (RF016, RF018 e RF020) são transacionais, sem permitir que o mesmo medicamento seja reservado para duas solicitações. Em caso de falha, a operação é desfeita e o usuário é informado. | Essencial |
| RNF07 | Produto – portabilidade | Aplicação web responsiva (mobile first), funcionando nas duas últimas versões de Chrome, Edge, Firefox e Safari, em computadores, Android e iOS, sem instalação obrigatória. | Essencial |
| RNF08 | Produto – espaço | **Servidor:** hospedagem em nuvem com escalabilidade horizontal, mínimo de 2 vCPU, 4 GB de RAM e 50 GB SSD no ambiente inicial. Fotos e receitas em armazenamento de arquivos criptografado, limitadas a 5 MB (JPG, PNG ou PDF). **Usuário:** qualquer dispositivo com navegador atualizado e internet (3G/4G ou superior), com baixo consumo de dados. | Importante |
| RNF09 | Organizacional – implementação | Desenvolvimento com controle de versão (Git), API REST e banco de dados relacional, mantendo a rastreabilidade dos requisitos (RF, RNF e RS) e a documentação técnica atualizada. | Desejável |
| RNF10 | Externo – legal (privacidade) | Conformidade com a LGPD (Lei nº 13.709/2018): coleta do mínimo necessário, Termos de Uso e Política de Privacidade visíveis, consentimento registrado, dados de saúde (receitas) tratados como sensíveis e atendimento a pedidos de acesso, correção e eliminação ou anonimização. | Essencial |
| RNF11 | Externo – legal (sanitário) | Respeitar a legislação sanitária de medicamentos (ANVISA), incluindo a Portaria SVS/MS nº 344/1998 para medicamentos de controle especial. A viabilidade jurídica da redistribuição entre particulares deve ser validada antes da implantação. | Essencial |
| RNF12 | Externo – interoperabilidade | Integração com serviços externos: consulta de CEP (webservice), mapas e geolocalização, envio de e-mail e, se aprovada a avaliação, IA de leitura de imagens e bases ou API de medicamentos. | Importante |
| RNF13 | Externo – ético | O sistema não substitui avaliação médica ou farmacêutica e exibe esse aviso nas telas de doação, solicitação e retirada. Dados extraídos por IA são identificados como sugestões a confirmar pelo usuário. | Essencial |
| RNF14 | Produto – confiabilidade | Toda operação que altere dados (cadastros, status, aprovações, reservas, entregas, denúncias e ações administrativas) gera um registro de histórico imutável (quem, o quê, data e hora), mantido pelo prazo da política de privacidade (RNF10), acessível só ao Administrador e que não pode ser alterado nem apagado (RF001, RF002, RF004, RF007, RF011, RF020 e RF021). | Essencial |
| RNF15 | Produto – confiabilidade | As rotinas automáticas (vencimento das doações, RF012; expiração de solicitações, RF013; expiração de reservas e prazos de aceite, RF016) rodam por agendador, com registro de cada execução e alerta ao Administrador em caso de falha. Notificações (RF017) são enviadas em até 5 minutos após o evento, com até 3 novas tentativas em caso de falha, sem bloquear a operação do usuário. | Importante |
| RNF16 | Produto – segurança | Todo arquivo enviado (fotos de embalagem, receitas e documentos de pontos de coleta, RF008, RF013 e RF006) tem tipo e assinatura verificados (JPG, PNG ou PDF), tamanho máximo de 5 MB, varredura antimalware, nome interno aleatório e acesso só por link temporário e autenticado, sem URL pública direta. | Importante |

---

## 3. Requisitos de segurança

### RS001
**Perigo:** no RF008, RF011 e RF012, um medicamento vencido, com validade adulterada ou com embalagem violada pode ser cadastrado, disponibilizado e entregue ao solicitante, pondo a saúde dele em risco.
**Soluções:**
1. Data de validade e foto da embalagem obrigatórias, rejeitando validade anterior à data atual.
2. Validade mínima restante, a ser definida na pendência de critérios de conferência.
3. Rotina automática diária que muda para "vencido" as doações expiradas, retira-as da busca e cancela as reservas (RF012).
4. O solicitante confere validade, lote e embalagem na retirada, com direito de recusa (RF020).

### RS002
**Perigo:** no RF001, RF013, RF015, RF016, RF017 e RF019, dados pessoais de doadores e solicitantes, ou o motivo da necessidade de saúde, podem ser expostos a outros usuários em buscas, notificações ou agendamentos.
**Soluções:**
1. O motivo da necessidade de saúde não é coletado nem exibido.
2. Só são exibidos a localização aproximada e uma identificação reduzida (sem nome completo, contato ou endereço).
3. O ponto de retirada só é liberado às duas partes após a confirmação do agendamento.
4. Receitas e dados pessoais são criptografados, com acesso restrito por perfil.
5. Definir a política de privacidade e o consentimento, conforme a LGPD.

### RS003
**Perigo:** no RF014, um medicamento sujeito a receita, principalmente de controle especial, pode ser entregue sem receita válida ou a quem não é o beneficiário.
**Soluções:**
1. A receita é anexada e verificada antes da correspondência (RF016).
2. Medicamentos de controle especial ficam bloqueados até a definição do fluxo e a validação jurídica (RNF11).
3. A identidade de quem retira é conferida na retirada, com base no que foi informado na solicitação.
4. Cada verificação é registrada (quem, quando e resultado).

### RS004
**Perigo:** no RF010, um medicamento refrigerado, como a insulina, pode perder eficácia ou segurança se a refrigeração for interrompida durante o armazenamento, o transporte ou a retirada.
**Soluções:**
1. Condição de conservação obrigatória, com declaração de ciência do doador.
2. O solicitante recebe a orientação de transporte e confirma ciência antes do agendamento.
3. Retirada em janela curta, de preferência em local com refrigeração.
4. Na retirada, a conservação é conferida, com direito de recusa.

### RS005
**Perigo:** no RF001, RF002 e RF003, contas podem ser acessadas indevidamente (senhas fracas ou vazadas, tentativas repetidas), permitindo ações em nome de outra pessoa.
**Soluções:**
1. Senhas com no mínimo 8 caracteres, guardadas com hash (bcrypt ou argon2).
2. Bloqueio temporário da conta após 5 tentativas inválidas em 15 minutos.
3. Sessões que expiram por inatividade e toda a comunicação em TLS 1.2 ou superior.
4. Autenticação em dois fatores para o perfil Administrador.
5. Proteção contra as falhas do OWASP Top 10 (CSRF, XSS, injeção de SQL).

### RS006
**Perigo:** no RF013, RF016, RF020 e RF021, a plataforma pode ser usada de forma indevida (solicitações em excesso, acúmulo ou revenda de medicamentos, perfis falsos), desviando-se da sua finalidade.
**Soluções:**
1. CPF único e e-mail confirmado.
2. Limites de solicitações abertas simultâneas e de quantidade por período.
3. Termos de Uso proibindo a comercialização, canal de denúncia (RF021) e suspensão de usuários pelo Administrador (RF004).
4. Histórico de todas as operações (quem, o quê, data e hora).

### RS007
**Perigo:** no RF008, RF016 e RF018, um mesmo medicamento pode ser reservado ou agendado ao mesmo tempo para mais de uma solicitação, gerando desencontros e registros inconsistentes.
**Soluções:**
1. Ao aceitar a correspondência, a doação passa a "reservada" numa operação única e transacional (RNF06).
2. A reserva expira se o agendamento não for confirmado no prazo, voltando a "disponível".
3. A quantidade disponível é atualizada a cada reserva ou entrega parcial.
4. As partes são notificadas de qualquer mudança de status.

### RS008
**Perigo:** no RF018, RF019 e RF020, o encontro presencial para a retirada pode expor doador e solicitante a riscos, como golpes, assédio ou local inseguro.
**Soluções:**
1. Priorizar a retirada em pontos de coleta cadastrados e aprovados (RF005), evitando residências.
2. Comunicação por mensagens da plataforma (RF019), sem expor telefone ou e-mail.
3. Entrega validada por um código de confirmação enviado ao solicitante.
4. Canal de denúncia (RF021) e possibilidade de bloquear usuários.

### RS009
**Perigo:** no RF009, a IA pode ler a embalagem errado (ex.: validade ou concentração), preenchendo o cadastro com informação incorreta.
**Soluções:**
1. Dados extraídos exibidos para conferência e edição antes de salvar.
2. Campos de baixa confiança destacados, exigindo confirmação manual.
3. Foto vinculada à doação, para a conferência (RF011) e a retirada (RF020).
4. A falha da IA não impede o cadastro manual.
5. Campos que a IA não conseguir ler ficam em branco, sem estimativa, e a validade sempre é confirmada pelo doador.
6. O doador é informado de que a foto vai para um serviço externo de IA e orientado a não fotografar dados pessoais, conforme a LGPD.

### RS010
**Perigo:** no RF015, a geolocalização pode revelar a localização exata e os hábitos de deslocamento dos usuários.
**Soluções:**
1. Pedir consentimento explícito e permitir o CEP como alternativa.
2. Usar localização aproximada e calcular a distância no servidor, sem exibir coordenadas a outros usuários.
3. Não guardar histórico de trajetos, só a última localização usada na busca.
4. O usuário pode revogar o consentimento a qualquer momento.

### RS011
**Perigo:** no RF005, RF006 e RF007, um estabelecimento falso ou irregular pode ser cadastrado como ponto de coleta, levando doadores e solicitantes a se encontrarem em local inadequado ou inseguro.
**Soluções:**
1. CNPJ validado e único, e documentos (licença de funcionamento e alvará sanitário) obrigatórios (RF006).
2. O ponto só é exibido após aprovação do Administrador (status "ativo") (RF007).
3. Revisão periódica dos cadastros e suspensão imediata em caso de denúncia.
4. Histórico de todas as aprovações, alterações e suspensões (quem, o quê, data e hora).

### RS012
**Perigo:** no RF003, a recuperação de senha pode ser usada para descobrir quais e-mails estão cadastrados ou para tomar a conta de outra pessoa (links interceptados, reutilizados ou gerados em excesso).
**Soluções:**
1. Resposta sempre igual, exista ou não o e-mail cadastrado.
2. Link com validade de 1 hora e uso único, gerado de forma aleatória e guardado só como hash. Uma nova solicitação invalida o link anterior.
3. Limite de solicitações por e-mail e por endereço IP em um período.
4. Depois da redefinição, as sessões ativas são encerradas e o usuário é avisado por e-mail (RF017).

### RS013
**Perigo:** no RF008, RF013, RF014 e RF006, os arquivos enviados (fotos de embalagem, receitas e documentos de estabelecimentos) podem conter código malicioso, ser adulterados ou ser acessados por quem não deveria.
**Soluções:**
1. Validar tipo, extensão e assinatura do arquivo, com limite de 5 MB e rejeição de formatos não permitidos (RNF16).
2. Varredura antimalware de todo arquivo antes de disponibilizá-lo.
3. Armazenamento criptografado, com nome interno aleatório e fora de diretório público.
4. Acesso por link temporário e autenticado, conforme o perfil: receitas só ao verificador, documentos de pontos de coleta só ao Administrador e ao responsável.
5. Registro de cada envio e acesso a arquivo (quem, o quê, data e hora).

### RS014
**Perigo:** no RF019 e no RF017, mensagens e notificações podem ser usadas para golpes, assédio, divulgação de dados pessoais (telefone, e-mail, endereço) ou links maliciosos, inclusive para levar a conversa para fora da plataforma.
**Soluções:**
1. Mensagens só de texto, sem anexos nem links, com tamanho limitado.
2. Detectar e bloquear, ou alertar sobre, telefone, e-mail, endereço, links e pedidos de pagamento no texto.
3. Conversa ativa só entre o aceite da correspondência e a conclusão ou o cancelamento da retirada, com possibilidade de bloquear o outro usuário e denunciar (RF021).
4. Notificações sem dados pessoais nem texto das mensagens, enviadas só do domínio oficial do sistema, com limite de envio por usuário.

### RS015
**Perigo:** no RF004, RF007 e RF021, as contas de Administrador, por terem amplos poderes (aprovar pontos de coleta, suspender usuários e acessar receitas e documentos), podem ser usadas de forma indevida ou invadidas, gerando aprovações fraudulentas, suspensões injustas ou vazamento de dados.
**Soluções:**
1. Autenticação em dois fatores para o Administrador (RF002). O perfil só é dado por outro Administrador, nunca a si mesmo.
2. Permissões administrativas separadas por função (aprovação de pontos de coleta, verificação de receitas, gestão de usuários e moderação), concedidas só no mínimo necessário.
3. Registro imutável de toda ação administrativa (quem, o quê, data e hora) (RNF14), com revisão periódica desses registros.
4. Suspensões, bloqueios e reprovações exigem motivo registrado e informado ao usuário.

---

## 4. Matrizes

### 4.1 Matriz de avaliação de risco

| Probabilidade \ Gravidade | Catastrófico (1) | Crítico (2) | Marginal (3) | Insignificante (4) |
| --- | --- | --- | --- | --- |
| Frequente (A) | | | | |
| Provável (B) | | | RS005, RS009 | |
| Ocasional (C) | RS001 | RS002, RS004, RS012 | RS006, RS014 | |
| Remoto (D) | RS003 | RS008, RS011, RS013, RS015 | RS007, RS010 | |
| Improvável (E) | | | | |
| Eliminado (F) | | | | |

### 4.2 Matriz de rastreabilidade — requisitos funcionais

D = o requisito da linha depende do requisito da coluna. R = existe algum relacionamento entre os requisitos.

| | 001 | 002 | 003 | 004 | 005 | 006 | 007 | 008 | 009 | 010 | 011 | 012 | 013 | 014 | 015 | 016 | 017 | 018 | 019 | 020 | 021 | 022 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **RF001** | | | | | | | | | | | | | | | | | | | | | | |
| **RF002** | D | | R | | | | | | | | | | | | | | | | | | | R |
| **RF003** | D | R | | | | | | | | | | | | | | | R | | | | | |
| **RF004** | D | D | | | | | | | | | | | | | | | R | | | | R | |
| **RF005** | D | D | | | | | | R | | R | | | | | | | | R | | | | |
| **RF006** | | D | | | D | | R | | | | | | | | | | R | | | | | |
| **RF007** | | D | | | D | R | | | | | | | | | | | R | R | | | R | R |
| **RF008** | | D | | | R | | | | | | | | R | R | | | | | | | R | |
| **RF009** | | | | | | | | D | | | R | | | | | | | | | | | |
| **RF010** | | | | | R | | | D | | | | | | R | | | | R | | R | | |
| **RF011** | | | | | | | | D | R | | | | | R | | | R | | | | | R |
| **RF012** | | | | | | | | D | | | D | | | | R | R | R | R | | | | R |
| **RF013** | | D | | | | | | R | | | | | | | R | | R | | | | | |
| **RF014** | | | | | | | | R | | R | R | | D | | | R | | | | | | |
| **RF015** | | | | | | | | D | | | D | R | R | | | R | | | | | | |
| **RF016** | | | | | | | | D | | | D | R | D | R | R | | R | | | | | |
| **RF017** | D | | R | R | | R | R | | | | R | R | R | | | R | | R | R | | R | |
| **RF018** | | | | | R | | R | | | R | | R | | | | D | R | | R | | R | R |
| **RF019** | | | | | | | | | | | | | | | | D | R | R | | R | R | |
| **RF020** | | | | | | | | | | R | | | | | | | | D | R | | R | |
| **RF021** | | D | | R | | | R | R | | | | | | | | | R | R | R | R | | R |
| **RF022** | | R | | | | | R | | | | R | R | | | | | | R | | D | R | |

Matriz reproduzida exatamente como consta na fonte. Os relacionamentos R são recíprocos; a dependência (D) tem um só sentido, da linha para a coluna.
