# 0018. Integrar consulta de CEP via proxy no servidor com cache no PostgreSQL e fallback

- Status: aceita
- Data: 2026-11-22
- Requisitos relacionados: RF001, RF005, RF015, RNF12, RNF04, RS002, RS005

## Contexto

A consulta de CEP por webservice externo (RNF12) é usada já no MVP em três fluxos:

- **RF001 (regra 8):** preenchimento automático de logradouro, bairro, município e estado pelo CEP no cadastro de usuário, mantendo número e complemento editáveis.
- **RF005 (regra 6):** preenchimento automático do endereço do ponto de coleta pelo CEP.
- **RF015 (regra 1):** CEP como alternativa à geolocalização do navegador na busca por proximidade.

Os serviços públicos gratuitos de CEP mais comuns no Brasil (**BrasilAPI** e **ViaCEP**) funcionam por HTTPS sem chave de API, mas **não oferecem SLA contratual** e proíbem varredura em massa (*crawling*), podendo bloquear IPs sob uso abusivo. Além disso, a [ADR 0006](0006-javascript-simples-sem-framework.md) usa JavaScript simples no navegador e o **RS005** recomenda política de segurança de conteúdo (CSP) restrita.

## Direcionadores da decisão

- Resiliência: se um webservice gratuito de CEP estiver lento ou fora do ar, o sistema deve tentar um fallback e, se ambos falharem, permitir preenchimento manual sem bloquear o cadastro.
- Redução de chamadas externas e respeito aos termos de uso dos serviços gratuitos (cache compartilhado por CEP e rate limit contra abuso).
- Baixo tempo de resposta nas telas públicas e de busca (RNF04) e baixo consumo de dados (RNF08).
- Privacidade e CSP: evitar expor o IP do usuário diretamente a terceiros e evitar abrir domínios externos em `connect-src`.
- Reaproveitamento do mesmo serviço e cache para a geocodificação aproximada por CEP da [ADR 0017](0017-geolocalizacao-e-calculo-de-distancia.md).

## Opções consideradas

### 1. Proxy no servidor Django (`CepService`) com cache no PostgreSQL + primário/fallback (BrasilAPI e ViaCEP) (recomendada)

O JavaScript simples da tela (ADR 0006) faz uma chamada `fetch` para um endpoint interno do próprio ReMed (ex.: `/enderecos/cep/<cep>/`, com validação de formato de 8 dígitos e limite de requisições por IP). O `CepService` consulta primeiro uma tabela `CacheCep` no PostgreSQL (TTL configurável, ex.: 30 dias); em *cache miss*, consulta o provedor primário (**BrasilAPI**) com timeout curto (ex.: 3 segundos) e, em caso de erro/timeout, faz fallback automático para o **ViaCEP**. Se ambos falharem, a resposta sinaliza indisponibilidade e a tela libera o preenchimento manual de logradouro, bairro, município e UF.

- **Prós:**
  - Fallback transparente entre dois serviços gratuitos sem SLA, reduzindo falhas perceptíveis ao usuário.
  - Cache persistente no PostgreSQL evita repetir consultas externas para o mesmo CEP, acelerando o atendimento e protegendo o IP do servidor contra bloqueios.
  - Mantém CSP restrita ao próprio domínio e não expõe o IP do usuário a serviços externos.
  - Centraliza a integração na camada de service (ADR 0001), permitindo reaproveitar o mesmo `CepService` no RF001, RF005 e RF015 (e aproveitar coordenadas aproximadas retornadas pela BrasilAPI v2 na ADR 0017).
- **Contras:**
  - Exige implementar um endpoint interno simples, uma tabela de cache e proteção contra abuso (*rate limit* por IP) para impedir terceiros de usar o ReMed como proxy de varredura de CEPs.
  - Exige cliente HTTP no servidor (biblioteca padrão `urllib.request` ou biblioteca dedicada como `httpx`).

### 2. Chamada direta do navegador (`fetch` em JavaScript) para ViaCEP ou BrasilAPI

O JavaScript da página de cadastro consulta diretamente `https://viacep.com.br/...` ou `https://brasilapi.com.br/...` no navegador do usuário.

- **Prós:**
  - Dispensa endpoint interno, cache de CEP no banco e cliente HTTP no backend para o preenchimento de formulário.
  - Distribui as requisições pelos IPs dos usuários finais.
- **Contras:**
  - Sem cache compartilhado entre usuários; expõe o IP do usuário ao terceiro e obriga a liberar domínios externos na CSP (`connect-src`).
  - Exige duplicar a lógica de consulta/fallback no servidor de qualquer forma para a busca por CEP no RF015 (cálculo de distância no servidor — RS010).

## Decisão

**Opção 1** — proxy no servidor Django (`CepService`) com cache persistente no PostgreSQL (`CacheCep`), provedor primário **BrasilAPI** e fallback **ViaCEP**, usando **`urllib.request` da biblioteca padrão do Python**.

Regras que passam a valer:

- **Endpoint interno e proteção contra abuso:** o JavaScript simples (ADR 0006) consulta um endpoint interno do próprio ReMed (ex.: `/enderecos/cep/<cep>/`), com validação de formato (8 dígitos) e *rate limit* por IP.
- **Cache persistente no PostgreSQL (`CacheCep`):** toda consulta verifica o cache antes de fazer requisição externa (TTL configurável em `settings`, ex.: 30 dias), armazenando logradouro, bairro, município, UF e, quando retornadas pela BrasilAPI v2, as coordenadas aproximadas usadas pela [ADR 0017](0017-geolocalizacao-e-calculo-de-distancia.md).
- **Ordem de provedores e degradação graciosa:** provedor primário **BrasilAPI** (timeout curto, ex.: 3 s) e fallback automático para **ViaCEP**. Se ambos falharem, retorna indisponibilidade e a tela libera preenchimento manual de logradouro, bairro, município e UF sem bloquear o cadastro.
- **Cliente HTTP sem dependência externa:** usar **`urllib.request` da biblioteca padrão do Python**, com timeout explícito e cabeçalho `User-Agent` identificável do ReMed — mantendo o `requirements.txt` enxuto (ADR 0004).

## Consequências

- Positivas:
  - Experiência consistente nos formulários do RF001, RF005 e na busca por CEP do RF015, mesmo quando um dos provedores gratuitos oscila.
  - Zero dependência externa adicionada ao `requirements.txt` (ADR 0004).
  - Reduz chamadas externas e integra-se diretamente ao cache de coordenadas aproximadas da [ADR 0017](0017-geolocalizacao-e-calculo-de-distancia.md).
- Negativas e custos:
  - Exige cuidar do rate limit no endpoint interno `/cep/<cep>/` para evitar abuso.
  - Como ambos os provedores são gratuitos sem SLA, caso o produto escale para alto volume comercial no futuro, será necessário avaliar serviço pago (ex.: API oficial dos Correios).
- Impacto em specs e arquitetura:
  - Condiciona as specs de **RF001**, **RF005** e **RF015** (e o link `"Não sei meu CEP"` listado na Questão 27 do PRD, que pode apontar para orientação ou busca oficial externa dos Correios).

## Como verificar

- Testes do `CepService` (com dublês HTTP) confirmam: retorno via cache sem chamada externa, acionamento do fallback ViaCEP quando a BrasilAPI falha ou dá timeout, normalização dos campos retornados, uso de `urllib.request` com timeout explícito e tratamento de CEP inexistente/inválido.
- Testes de view confirmam rejeição de CEP malformado, rate limit por IP e liberação do formulário para preenchimento manual quando os provedores estão indisponíveis.

## Notas

- **ADRs relacionadas:** [ADR 0004](0004-pip-venv-requirements-fixado.md) (sem dependências externas desnecessárias), [ADR 0006](0006-javascript-simples-sem-framework.md) (JavaScript simples) e [ADR 0017](0017-geolocalizacao-e-calculo-de-distancia.md) (`CacheCep` compartilhado com coordenadas aproximadas).
