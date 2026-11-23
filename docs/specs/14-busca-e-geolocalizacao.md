# Spec 14 — Busca de Medicamentos e Geolocalização (RF015)

## 1. Cabeçalho

| Campo | Valor |
| --- | --- |
| **Número e título** | `14` — Busca de Medicamentos e Geolocalização (`RF015`) |
| **Status** | `aprovada` |
| **Requisitos de origem** | **Funcionais:** RF015 (Essencial — MVP, HU15). **Não funcionais:** RNF01, RNF02, RNF03, RNF04 (Importante — resposta em até 3 s no p95), RNF07 (Essencial), RNF08, RNF10, RNF12 (CEP/geolocalização). **Segurança:** RS002, RS010. |
| **Apps envolvidos** | `medicamentos` (principal: `BuscaMedicamentoService`, views/forms de busca pública e autenticada), `nucleo` (`CepService` — ADR 0018, `GeolocalizacaoService` — ADR 0017: *bounding box* + Haversine no PostgreSQL sem PostGIS, BrasilAPI + Nominatim com cache persistente e política de uso), `solicitacoes` (atalho para cadastrar solicitação quando não há resultado — RF013). |
| **Dependências de outras specs** | **[01-cadastro-de-usuario.md](01-cadastro-de-usuario.md) (`RF001` — `CepService` e `CacheCep`)**, **[02-autenticacao-e-controle-de-acesso.md](02-autenticacao-e-controle-de-acesso.md) (`RF002` — redirecionar visitante ao login para solicitar)**, **[04-gestao-de-usuarios-administrador.md](04-gestao-de-usuarios-administrador.md) (`RF004` — ocultação dinâmica de doações de doador suspenso/bloqueado)**, **[05-cadastro-de-ponto-de-coleta.md](05-cadastro-de-ponto-de-coleta.md) (`RF005`)**, **[08-cadastro-de-doacao.md](08-cadastro-de-doacao.md) (`RF008`)**, **[10-conferencia-e-aprovacao-de-validade.md](10-conferencia-e-aprovacao-de-validade.md) (`RF011` — rascunho)**, **[11-rotina-automatica-de-vencimento.md](11-rotina-automatica-de-vencimento.md) (`RF012` — rascunho)** e **[12-cadastro-de-solicitacao.md](12-cadastro-de-solicitacao.md) (`RF013` — rascunho)**. **Depende de specs ainda não escritas:** **RF016** (ação de solicitar/corresponder a partir do resultado) e **RF018** (revelação do local de retirada apenas após agendamento confirmado). |
| **ADRs relacionadas** | [0001](../adr/0001-django-mvt-com-camada-de-service.md), [0002](../adr/0002-postgresql-como-banco-de-dados.md), [0005](../adr/0005-bootstrap-hospedado-no-projeto.md), [0006](../adr/0006-javascript-simples-sem-framework.md), [0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md), [0018](../adr/0018-consulta-de-cep.md). |

---

## 2. Objetivo e escopo

Permitir que visitantes e usuários autenticados pesquisem medicamentos **`disponivel`** para doação utilizando filtros farmacêuticos e **geolocalização aproximada** (por consentimento explícito no navegador ou via CEP), ordenando por proximidade com cálculo de distância no servidor, preservando rigorosamente a privacidade do doador e do solicitante (RS002, RS010).

### Inclui

- Implantação do **`GeolocalizacaoService`** em `nucleo` ([ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md)):
  - Geocodificação aproximada por CEP usando **BrasilAPI CEP v2** como primário e **Nominatim (OpenStreetMap)** como *fallback*, **sempre com cache persistente em PostgreSQL (`CacheCep`)** respeitando a política de uso do Nominatim (`<= 1 req/s`, `User-Agent` identificando o projeto, sem *bulk* nem *autocomplete* — [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md));
  - Pré-filtro retangular (*bounding box* em `latitude`/`longitude` indexadas) seguido do cálculo de **distância Haversine no servidor** (PostgreSQL padrão, sem PostGIS/GDAL).
- Busca de doações com os **6 filtros do RF015**:
  1. Nome do medicamento ou princípio ativo;
  2. Forma farmacêutica (`FormaFarmaceutica`);
  3. Concentração/dosagem;
  4. Distância máxima (`km`);
  5. Validade mínima restante (`Date` — `"Válido pelo menos até"`, fiel ao RF015);
  6. Condição de conservação (`temperatura_ambiente` ou `refrigerado`).
- Obtenção da localização do usuário por **consentimento explícito no navegador** (`navigator.geolocation` via JS simples — ADR 0006) **ou CEP alternativo** (funciona sem JS), com **botão visível para limpar/revogar a localização usada na busca** (RS010). A última localização fica **apenas na sessão** (`request.session`), **nunca** em tabela de histórico de trajetos ([ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md)).
- Exibição estrita dos campos permitidos: nome, concentração, forma farmacêutica, quantidade disponível, data de validade, **bairro ou região aproximada e distância aproximada em faixas** (ex.: `"menos de 1 km"`, `"cerca de 2 km"`, `"cerca de 5 km"`, `"mais de 10 km"`, sem precisão exata para impedir que terceiros descubram o ponto de retirada antes do agendamento — RF018), condição de conservação e indicação de exigência de receita. **Nunca** exibe nome, contato, endereço do doador ou ponto de retirada (RS002, RF015 regra 2).
- Visibilidade rigorosa: somente doações `status = disponivel`, dentro da validade mínima vigente (RF012) e cujo doador esteja com `Usuario.status = ativo` (Spec `04`).
- Paginação de **10 resultados por página**, ordenação padrão do mais próximo ao mais distante, visualização resumida para visitantes (exigindo login para solicitar — RF002) e estado vazio com mensagem literal **`"Nenhum medicamento encontrado"`** + atalho para cadastrar solicitação (RF013).

### Não inclui

- Exibição de mapa interativo pesado ou rastreamento contínuo de localização (RS010, RNF08 — baixo consumo de dados em 3G/4G).
- Detalhamento do ponto de retirada ou início de conversa (liberados apenas nas specs de RF016, RF018 e RF019).

---

## 3. Atores e pré-condições

| Ator | Ações nesta spec | Pré-condições |
| --- | --- | --- |
| **Visitante (não autenticado)** | Pesquisar medicamentos disponíveis, informar CEP ou autorizar geolocalização na sessão e visualizar o resultado resumido. Ao acionar `"Solicitar"`, é redirecionado para login (RF002). | Nenhuma. |
| **Doador / Solicitante / Cuidador/Familiar** | Pesquisar medicamentos disponíveis com todos os filtros e iniciar solicitação/correspondência (para `Solicitante` e `Cuidador/Familiar`, RF013/RF016). | Conta ativa e autenticada (RF002). |

---

## 4. Fluxos

### 4.1 Fluxo principal — Busca por proximidade (navegador ou CEP)

1. O usuário acessa `medicamentos:busca` (`/medicamentos/`).
2. Opcionalmente informa um ou mais filtros (nome/princípio ativo, forma farmacêutica, concentração, distância máxima em km, validade mínima e conservação) e define sua referência de localização:
   - **Opção A (consentimento no navegador):** clica em `"Usar minha localização atual"` → JS simples solicita permissão ao navegador (`navigator.geolocation`) e envia coordenadas aproximadas (arredondadas para reduzir precisão — RS010) para `medicamentos:definir_localizacao` (`POST` com CSRF), que salva **somente em `request.session`** (jamais em banco);
   - **Opção B (CEP alternativo — funciona sem JS):** informa o CEP no campo de busca; o servidor consulta `CepService` / `GeolocalizacaoService` (usando `CacheCep`) e salva bairro/município/coordenadas aproximadas **somente em `request.session`**.
3. `BuscaMedicamentoService.buscar(filtros, localizacao_sessao, pagina)` executa no servidor:
   - Filtra `Doacao.status == disponivel`, `doador.status == ativo` (Spec `04`), `quantidade_disponivel > 0` e `data_validade >= hoje + validade_minima_restante_dias` (RF012);
   - Aplica filtros informados (busca case-insensitive/sem acento via `icontains` ou `unaccent` em `nome_medicamento` e `principio_ativo`, `forma_farmaceutica`, `concentracao_dosagem`, `data_validade >= filtro_validade`, `condicao_conservacao`);
   - Se houver localização na sessão: aplica pré-filtro *bounding box* (quando `distancia_max_km` informado), calcula distância **Haversine no servidor** usando as coordenadas aproximadas da doação (centroide do CEP do ponto de coleta escolhido quando houver, ou do CEP do doador quando sem ponto), filtra `<= distancia_max_km`, ordena **do mais próximo ao mais distante** e formata a exibição em **faixas aproximadas** (ex.: `"menos de 1 km"`, `"cerca de 2 km"`, `"cerca de 5 km"`, `"mais de 10 km"`) para não revelar nem permitir deduzir o ponto de retirada antes do RF018;
   - Se não houver localização na sessão: lista doações `disponivel` ordenadas por cadastro mais recente exibindo convite destacado para informar CEP ou ativar localização;
   - Pagina em **10 itens por página**.
4. Renderiza apenas os campos públicos permitidos (sem nome/contato/endereço do doador e sem revelar o ponto de retirada), com etiqueta de conservação (`Refrigerado` texto + cor) e indicação de receita (`Exige receita`).
5. Se visitante acionar `"Solicitar este medicamento"`, é redirecionado para `contas:login?next=...` (RF002).

### 4.2 Fluxos alternativos

- **FA-01 — Busca sem resultados:** exibe a mensagem literal **`"Nenhum medicamento encontrado"`** acompanhada de botão/link destacado **`"Cadastrar uma solicitação"`** apontando para `solicitacoes:criar` (RF013), pré-preenchendo os filtros buscados na query string (*acréscimo da especificação*) para que o usuário seja notificado quando surgir correspondência (RF016/RF017).
- **FA-02 — Revogação/limpeza de localização (RS010):** o usuário aciona `"Limpar minha localização"` (`POST` com CSRF em `medicamentos:limpar_localizacao`), removendo imediatamente as chaves de localização de `request.session`.
- **FA-03 — Busca sem localização definida:** exibe resultados disponíveis ordenados por mais recentes acompanhados de aviso/convite destacado para informar CEP ou permitir localização no navegador e ativar ordenação por proximidade.

### 4.3 Fluxos de exceção

- **FE-01 — Usuário recusa permissão de geolocalização no navegador:** interface informa de forma amigável que é possível informar apenas o **CEP** como alternativa (RF015 regra 1).
- **FE-02 — CEP inválido ou falha nos provedores externos (BrasilAPI e Nominatim indisponíveis):** `GeolocalizacaoService` trata timeout/erro sem quebrar a página, informa que não foi possível localizar o CEP naquele momento e permite buscar pelos demais filtros.

---

## 5. Regras de negócio

| ID | Regra | Origem / ADR / App |
| --- | --- | --- |
| **RN-14-01** | A localização do usuário é obtida apenas com **consentimento explícito no navegador** ou via **CEP** alternativo. A distância é calculada **no servidor** (*bounding box* + Haversine — [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md)), os resultados são ordenados por padrão **do mais próximo ao mais distante**, a localização fica **somente na sessão** (sem histórico de trajetos) e pode ser revogada/limpa a qualquer momento. | RF015 (regra 1), RS010, [ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md), [ADR 0018](../adr/0018-consulta-de-cep.md) • `nucleo`, `medicamentos` |
| **RN-14-02** | O resultado **nunca** exibe nome, contato ou endereço do doador (RS002). Mostra apenas **bairro ou região aproximada e distância aproximada em faixas** (ex.: `"menos de 1 km"`, `"cerca de 2 km"`, `"cerca de 5 km"`, `"mais de 10 km"`), impedindo dedução do ponto de retirada antes do agendamento confirmado (RF018). | RF015 (regra 2), RS002, RS010 • `medicamentos` |
| **RN-14-03** | Somente doações com **`status = disponivel`**, `quantidade_disponivel > 0`, dentro da validade mínima (RF012) e cujo doador possua **`Usuario.status = ativo`** (Spec `04`) aparecem na busca. | RF015 (regra 3), RF004, RF012 • `medicamentos` |
| **RN-14-04** | Visitantes sem login veem apenas o resultado resumido. Qualquer ação de solicitar exige autenticação (RF002). | RF015 (regra 4), RF002 • `medicamentos` |
| **RN-14-05** | Paginação fixa de **10 resultados por página**. | RF015 (regra 5), RNF04, RNF08 • `medicamentos` |
| **RN-14-06** | Quando não houver resultados, exibir exatamente **`"Nenhum medicamento encontrado"`** e a opção de cadastrar uma solicitação (RF013) para notificação futura (RF016/RF017). | RF015 (regra 6), RF013 • `medicamentos`, `solicitacoes` |

---

## 6. Modelo de dados lógico

Esta spec não cria tabelas de usuário ou histórico de localização (expressamente proibidas pelo RS010 / ADR 0017). Reutiliza:

- **`CacheCep`** (`nucleo`, Spec `01` / ADRs 0017 e 0018): armazena `cep`, `bairro`, `municipio`, `uf`, `latitude` (`Decimal(9,6)`, indexado) e `longitude` (`Decimal(9,6)`, indexado), evitando chamadas repetidas à BrasilAPI/Nominatim.
- **Campos de localização aproximada em `Doacao`** (`medicamentos`, indexados para *bounding box*): `regiao_bairro` (`String(100)`), `regiao_municipio` (`String(100)`), `regiao_uf` (`String(2)`), `latitude_aprox` (`Decimal(9,6)`, indexado) e `longitude_aprox` (`Decimal(9,6)`, indexado) — preenchidos no cadastro/edição da doação (RF008) a partir do `CacheCep` (usando o CEP do ponto de coleta escolhido quando houver ou do doador quando sem ponto), exibindo **apenas bairro/município e faixa aproximada de distância** sem expor endereço exato nem ponto de coleta.
- **Sessão (`request.session["busca_localizacao"]`):** dicionário efêmero `{origem: "gps"|"cep", cep?, rotulo_aproximado, lat, lon}`, apagado no logout ou em `medicamentos:limpar_localizacao`.

---

## 7. Divisão por camadas ([ADR 0001](../adr/0001-django-mvt-com-camada-de-service.md))

- **Views/Forms (`medicamentos`):** `MedicamentoBuscaView` + `MedicamentoBuscaForm` (`GET` — pública/autenticada), `DefinirLocalizacaoBuscaView` (`POST` com CSRF — salva localização na sessão), `LimparLocalizacaoBuscaView` (`POST` com CSRF — revoga localização da sessão).
- **Services:** `GeolocalizacaoService` (`nucleo` — `obter_coordenadas_por_cep`, `calcular_bounding_box`, `calcular_distancia_haversine_km`, respeitando cache e política de uso do Nominatim) e `BuscaMedicamentoService` (`medicamentos` — `buscar(filtros, localizacao, pagina)`).
- **Templates:** `templates/medicamentos/busca.html` (formulário de filtros responsivo *mobile first* com Bootstrap local, controle `"Usar minha localização"` em JS simples + campo CEP + botão `"Limpar localização"`, cartões leves para 3G/4G exibindo apenas campos permitidos, paginação de 10 itens e bloco `"Nenhum medicamento encontrado"` com CTA para RF013).
- **Rotas:** `medicamentos:busca` (`/medicamentos/`), `medicamentos:definir_localizacao` (`/medicamentos/localizacao/`), `medicamentos:limpar_localizacao` (`/medicamentos/localizacao/limpar/`).

---

## 8. Mensagens e validações

- Sem resultados (literal da fonte): **`"Nenhum medicamento encontrado"`**;
- Permissão de localização negada: `"Você pode informar seu CEP para ver os medicamentos mais próximos"`;
- CEP não localizado: `"Não foi possível localizar o CEP informado no momento. Você ainda pode buscar usando os outros filtros"`.

---

## 9. Segurança e privacidade

- **RS002 (OWASP A01/A04):** serializer/contexto da busca projeta explicitamente apenas os campos públicos do RF015 (nunca `doador`, `ponto_coleta` ou endereço completo) — validado por testes de regressão no HTML renderizado.
- **RS010 (OWASP A04/A05):** consentimento explícito para GPS, CEP alternativo, coordenadas arredondadas (~2 casas decimais ≈ 1 km ao salvar na sessão), distância calculada no servidor, zero persistência de histórico de trajetos e revogação em 1 clique.
- **Proteção contra abuso de API externa ([ADR 0017](../adr/0017-geolocalizacao-e-calculo-de-distancia.md)):** cache obrigatório em `CacheCep`, *rate limit* local para chamadas ao Nominatim (`<= 1 req/s`) e `User-Agent` próprio.

---

## 10. Requisitos não funcionais aplicáveis

- **RNF01–RNF03:** filtros claros, rótulos acessíveis, etiquetas `"Refrigerado"` e `"Exige receita"` em texto + cor (WCAG 2.1 AA).
- **RNF04 & RNF08:** resposta em até 3 s (p95) com paginação de 10 itens, índices em `(status, data_validade)` e `(latitude_aprox, longitude_aprox)`, HTML enxuto sem mapas pesados para 3G/4G.
- **RNF07 & RNF12:** *mobile first*, funciona sem JS via CEP e integra BrasilAPI/ViaCEP/Nominatim pelo servidor.

---

## 11. Critérios de aceite

1. **CA-14-01 (Ordenação por proximidade e cálculo no servidor — RN-14-01):** Dadas 3 doações `disponivel` em diferentes distâncias do CEP/localização da sessão, quando o usuário busca com distância máxima, então aparecem ordenadas da mais próxima à mais distante, excluindo as fora do raio.
2. **CA-14-02 (Privacidade estrita no resultado — RN-14-02):** A resposta HTML de `medicamentos:busca` (para visitante e para usuário autenticado) **nunca** contém nome, e-mail, telefone, endereço do doador nem nome/endereço do ponto de coleta escolhido na doação.
3. **CA-14-03 (Visibilidade estrita — RN-14-03):** Doações `em_analise`, `reservado`, `entregue`, `vencido`, `reprovado`, `cancelado`, vencidas no dia ou pertencentes a doador `suspenso`/`bloqueado` (Spec `04`) **nunca** aparecem na busca.
4. **CA-14-04 (Paginação, visitante e estado vazio — RN-14-04..RN-14-06):** Com 15 doações disponíveis, a página 1 retorna 10 itens e a página 2 retorna 5; visitante clicando em solicitar é redirecionado para login; busca sem correspondência exibe literalmente `"Nenhum medicamento encontrado"` e link para `solicitacoes:criar`.
5. **CA-14-05 (Consentimento revogável e zero histórico de trajetos — RN-14-01):** Ao acionar `medicamentos:limpar_localizacao`, os dados são apagados da sessão; nenhuma tabela do banco guarda coordenadas pessoais de buscas dos usuários.

---

## 12. Plano de testes

- **Unidade (`GeolocalizacaoService`, `BuscaMedicamentoService`):** cálculo Haversine com distâncias conhecidas; *bounding box* sem falso negativo nas bordas; cache em `CacheCep` evitando segunda chamada externa (com dublê de BrasilAPI/Nominatim); filtros combinados (nome/princípio ativo, forma, concentração, distância, validade, conservação); exclusão de doador suspenso/bloqueado e doações fora de `disponivel`.
- **Integração (Views/Privacidade):** paginação de 10 itens; verificação negativa no HTML garantindo ausência de dados pessoais do doador e do ponto de coleta; estado vazio com `"Nenhum medicamento encontrado"`; redirect de visitante ao tentar solicitar; definição e limpeza de localização na sessão via `POST` + CSRF.

---

## 13. Questões em aberto

Nenhuma questão em aberto bloqueante para esta spec no MVP. Todas as decisões (filtro `Date`, distância aproximada em faixas a partir do CEP do ponto escolhido ou do doador sem expor o ponto, e busca sem localização ordenando por mais recentes) estão fechadas.
