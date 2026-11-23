# 0017. Geolocalização aproximada e cálculo de distância no servidor

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RF015, RF016, RF001, RF005, RS002, RS010, RNF04, RNF12

## Contexto

A proximidade geográfica é central para a busca e para a correspondência no ReMed, mas envolve exigências rigorosas de privacidade:

- **RF015 (Essencial):** busca de medicamentos disponíveis ordenada do mais próximo ao mais distante, com filtro de distância máxima (km), exibindo apenas **bairro ou região aproximada e distância** — nunca endereço exato, nome ou coordenadas do doador (RS002). A localização do usuário é obtida por consentimento no navegador ou, como alternativa, informando o CEP.
- **RF016 (Essencial):** correspondência automática dentro do raio informado na solicitação (km), usando a proximidade como primeiro critério de desempate.
- **RS010:** perigo de a geolocalização revelar localização exata e hábitos de deslocamento. Soluções obrigatórias: (1) consentimento explícito e CEP como alternativa; (2) usar **localização aproximada** e **calcular a distância no servidor**, sem exibir coordenadas a outros usuários; (3) **não guardar histórico de trajetos**, apenas a última localização usada na busca; (4) permitir revogar o consentimento a qualquer momento.
- **RF001 e RF005:** o endereço do usuário serve apenas para geolocalização aproximada e nunca é exibido (RS002); o endereço do ponto de coleta é público e usado na busca por proximidade.
- **RNF04:** buscas devem responder em até **3 segundos (p95)** com até 500 usuários simultâneos.

## Direcionadores da decisão

- Calcular distâncias exclusivamente no servidor, sem expor coordenadas brutas de usuários no HTML ou em respostas (RS002, RS010).
- Garantir que não exista histórico de trajetos (RS010).
- Atender o tempo de resposta de até 3 segundos no p95 (RNF04) em buscas paginadas (10 por página, RF015).
- Manter simplicidade de instalação em desenvolvimento (Windows) e em produção, sem dependências nativas desnecessárias (ADRs 0002, 0004 e 0019).
- Tratar falhas de serviços externos de geocodificação sem bloquear o cadastro (RNF12).

## Opções consideradas

### Parte A — Armazenamento de coordenadas e cálculo de distância no PostgreSQL

#### G1. Colunas numéricas (`latitude`, `longitude`) no PostgreSQL padrão + *bounding box* indexado + fórmula de Haversine no servidor (recomendada para o MVP)

Armazenar coordenadas aproximadas em colunas `DecimalField` no PostgreSQL (sem exigir extensão PostGIS), indexadas com B-tree. Nas consultas de busca (RF015) e correspondência (RF016), o service aplica primeiro um pré-filtro retangular (*bounding box* em latitude/longitude, aproveitando o índice) e calcula a distância exata em km no PostgreSQL usando a fórmula de Haversine para filtrar pelo raio e ordenar por proximidade.

- **Prós:**
  - Funciona imediatamente em qualquer PostgreSQL padrão, **sem precisar instalar `PostGIS`, `GDAL`, `GEOS` e `PROJ`** no Windows de desenvolvimento nem na hospedagem (ADR 0019).
  - A precisão da fórmula de Haversine (erro inferior a 0,5% em raios urbanos) é mais do que suficiente para a exigência de **localização aproximada** (RS010).
  - Atende com folga o limite de 3 s (RNF04) na escala inicial do projeto e mantém caminho simples de migração para PostGIS se o volume crescer muito.
- **Contras:**
  - Não dispõe de índice espacial GiST nativo nem de operações geométricas avançadas (polígonos, rotas), exigindo montar o filtro de *bounding box* e a expressão Haversine no service.

#### G2. PostgreSQL com extensão PostGIS + GeoDjango (`PointField` / `Distance`)

Habilitar a extensão PostGIS no PostgreSQL (mencionada como possibilidade na ADR 0002) e usar `django.contrib.gis` com índice espacial GiST (`ST_DWithin`, `Distance`).

- **Prós:**
  - Solução espacial recomendada pela documentação oficial do GeoDjango, com índice GiST nativo e excelente escala para grandes bases geográficas.
- **Contras:**
  - Exige instalar e manter bibliotecas nativas (`GDAL`, `GEOS`, `PROJ`) no sistema operacional de cada desenvolvedor (especialmente trabalhoso no Windows) e garantir suporte a PostGIS na hospedagem escolhida (ADR 0019), adicionando complexidade acima do necessário para raios aproximados no MVP.

---

### Parte B — Geocodificação (obter coordenadas aproximadas a partir do CEP/endereço)

#### E1. Geocodificação aproximada por CEP com cache local no PostgreSQL (BrasilAPI CEP v2 + fallback Nominatim/OpenStreetMap) (recomendada)

Ao cadastrar ou atualizar endereço (RF001, RF005) ou buscar por CEP (RF015), o servidor obtém coordenadas aproximadas do CEP (aproveitando o cache de CEPs da [ADR 0018](0018-consulta-de-cep.md), onde a BrasilAPI v2 já retorna coordenadas quando disponíveis, com fallback para Nominatim/OpenStreetMap por município/bairro/CEP, respeitando política de uso e cache persistente).

- **Prós:**
  - Gratuito e sem necessidade de cartão/chave comercial no MVP.
  - Por geocodificar no nível do CEP/bairro (e não no número exato da residência), reforça nativamente a privacidade do endereço do usuário (RS002, RS010).
  - O cache persistente por CEP no PostgreSQL reduz drasticamente chamadas externas e melhora o tempo de resposta (RNF04).
- **Contras:**
  - Serviços gratuitos não oferecem SLA contratual; alguns CEPs podem não ter coordenadas retornadas, exigindo fallback pelo centróide de bairro/município ou tratamento gracioso na busca.

#### E2. API comercial de geocodificação (ex.: Google Maps Geocoding ou Mapbox)

- **Prós:**
  - Alta cobertura de endereços (inclusive para precisão de pontos de coleta públicos) e SLA comercial.
- **Contras:**
  - Exige conta paga/cartão de crédito, gestão de chave de API e controle de faturamento, além de enviar endereços de usuários a terceiro comercial (RNF10).

## Decisão

Adotadas as opções **G1** (colunas `latitude`/`longitude` no PostgreSQL padrão + *bounding box* indexado + Haversine no servidor) e **E1** (geocodificação aproximada por CEP via **BrasilAPI CEP v2** com fallback **Nominatim/OpenStreetMap** e **cache persistente obrigatório no PostgreSQL**), com a última localização da busca guardada **apenas na sessão do usuário**.

Regras que passam a valer:

- **Cálculo de distância no servidor (G1):** colunas numéricas `latitude` e `longitude` (`DecimalField`) indexadas no PostgreSQL padrão (sem PostGIS/GDAL), com pré-filtro por *bounding box* e cálculo da distância em km pela fórmula de Haversine no servidor/banco (RF015, RF016, RS010).
- **Geocodificação e política de uso do Nominatim (E1):**
  - Prioriza-se a coordenada aproximada retornada pela **BrasilAPI CEP v2** (reaproveitando o cache `CacheCep` da [ADR 0018](0018-consulta-de-cep.md)).
  - O **Nominatim** (`nominatim.openstreetmap.org`) atua apenas como fallback por CEP/bairro/município e **exige cache persistente obrigatório** no PostgreSQL para evitar consultas repetidas, cumprindo estritamente a **Nominatim Usage Policy** (*OpenStreetMap Foundation Operations Working Group*, `operations.osmfoundation.org/policies/nominatim/`):
    - limite absoluto de **1 requisição por segundo** (sem requisições paralelas automatizadas);
    - cabeçalho HTTP `User-Agent` próprio e identificável do ReMed (nunca o `User-Agent` genérico da biblioteca HTTP);
    - proibição de geocodificação em massa (*bulk*) e de *auto-complete* no navegador.
- **Localização aproximada para usuários (RS002, RS010):** coordenadas de usuários/doações são armazenadas com precisão reduzida (centróide do CEP ou arredondamento para ~2 casas decimais ≈ ~1,1 km) e nunca são enviadas ao template nem exibidas a terceiros — apenas bairro/região e distância aproximada (km).
- **Última localização de busca apenas na sessão (RS010):** a localização fornecida pelo navegador na busca (RF015) fica **somente na sessão HTTP do usuário** (que expira em 30 minutos de inatividade conforme a ADR 0009), sem persistência em tabela de usuário nem histórico de trajetos, sendo removida imediatamente se o usuário revogar o consentimento ou alternar para busca por CEP.
- **Ponto de coleta público (RF005):** o endereço do ponto de coleta é público, mas a associação de qual ponto foi escolhido para uma doação continua oculta na busca até o agendamento confirmado (RF015 regra 2, Questão 26 do PRD).
- **Degradação graciosa:** se a geocodificação externa falhar no cadastro, o endereço é salvo normalmente e a geocodificação pode ser preenchida posteriormente sem impedir o usuário de concluir o cadastro.

## Consequências

- Positivas:
  - Zero dependência de `GDAL`/`GEOS`/`PROJ` ou PostGIS no MVP, facilitando o desenvolvimento em Windows e a escolha de hospedagem.
  - Privacidade garantida por desenho (coordenadas aproximadas, cálculo no servidor, última localização apenas na sessão sem histórico de trajetos).
  - Cumprimento explícito da política de uso do Nominatim via cache persistente e controle de taxa.
- Negativas e custos:
  - Precisão limitada ao nível do CEP/bairro (adequada a usuários, mas pode gerar pequenas diferenças de distância para pontos de coleta em CEPs abrangentes).
  - Se o usuário ficar mais de 30 minutos inativo e a sessão expirar, precisará autorizar a localização ou informar o CEP novamente na próxima busca.
- Impacto em specs e arquitetura:
  - Condiciona as specs de **RF001**, **RF005**, **RF015** e **RF016**, e integra-se diretamente ao `CacheCep` da [ADR 0018](0018-consulta-de-cep.md).

## Como verificar

- Testes de busca (RF015) e correspondência (RF016) validam ordenação por distância crescente, filtro de raio máximo e desempate por solicitação mais antiga (RF016 regra 3).
- Testes de template/view confirmam que nenhuma resposta da busca expõe `latitude`, `longitude`, endereço ou contato do doador.
- Testes confirmam que a última localização de busca fica apenas na sessão (nunca gera histórico no banco) e é limpa ao revogar o consentimento.
- Testes do cliente de geocodificação (com dublês HTTP) confirmam leitura prévia do cache no PostgreSQL, envio de `User-Agent` identificável do ReMed nas chamadas ao Nominatim e respeito ao limite de taxa (<= 1 req/s).

## Notas

- **Referência de conformidade externa:** *Nominatim Usage Policy* — `operations.osmfoundation.org/policies/nominatim/` (OpenStreetMap Foundation).
- **ADRs relacionadas:** [ADR 0002](0002-postgresql-como-banco-de-dados.md), [ADR 0009](0009-sessao-bloqueio-tentativas-e-2fa-administrador.md) (expiração de sessão em 30 min), [ADR 0018](0018-consulta-de-cep.md) (`CacheCep` compartilhado) e [ADR 0019](0019-hospedagem-implantacao-e-backup.md).
