# Contratos da API — EP00

Esta é a base tipada das quatro frentes paralelas. React consome apenas a API REST do FastAPI; credenciais e integrações externas ficam no backend. Os serviços são injetados via `Depends` em `backend/app/core/dependencies.py`. Nesta etapa, todos os provedores são mocks locais. Os dados demonstrativos ficam em `backend/app/mocks/data/*.json`; `data.py` os carrega e valida com Pydantic, e `services.py` implementa os adaptadores mock.

## Convenções

- Base REST: `/api/v1`; Swagger: `/docs`; OpenAPI: `/openapi.json`.
- Preços são `Decimal` no Python e **strings com duas casas** no JSON, em BRL. Exemplo: `"8.90"`. Não usar float em contas monetárias.
- Quantidades e nutrientes são `Decimal` no Python e strings decimais no JSON. Unidades de ingrediente: `g`, `kg`, `ml`, `l`, `unit`. Conversões de xícaras e colheres ficam para a camada de normalização futura.
- `NutritionFacts.basis` explicita `per_100g`, `per_unit`, `per_serving` ou `recipe_total`. `reference_quantity` e `reference_unit` informam a referência exata. Dados mockados usam `estimated: true` e `source: "mock_ep00"`.
- `source: "mock_ep00"` em receitas, produtos e nutrição significa dado demonstrativo; preços e produtos **não são dados reais do iFood**.
- Erros de validação: HTTP 422 com `{"error":{"code":"validation_error","message":"Invalid request","details":[...]}}`. Erros de recurso/estado usam# Prompt Codex — EP00: Setup, Contratos e Mocks

## Contexto do projeto

Estamos desenvolvendo o **iFood Chef AI**, um projeto para o Hackathon SEMCOMP × iFood 2026.

Repositório: https://github.com/josegustavo14/hackathon-ifood

O objetivo é construir um agente de inteligência artificial capaz de transformar receitas e planos alimentares em compras no iFood.

### Exemplos de utilização

**Caso 1 — Receita**

O usuário solicita:

"Quero fazer uma lasanha à bolonhesa para quatro pessoas. Encontre uma receita, calcule os ingredientes, mostre as calorias e monte meu carrinho no iFood."

O sistema deverá:

1. Interpretar a solicitação com um LLM.
2. Buscar receitas na API de receitas.
3. Extrair e estruturar ingredientes e quantidades.
4. Ajustar as quantidades ao número de porções.
5. Consultar informações nutricionais.
6. Pesquisar os produtos no MCP do iFood.
7. Calcular embalagens e preços.
8. Apresentar uma proposta de carrinho.
9. Permitir que o usuário revise e autorize as alterações no carrinho.

**Caso 2 — Plano alimentar**

O usuário envia um PDF da nutricionista:

"Com base nesse plano, calcule os ingredientes necessários para sete dias e monte minha lista de compras."

O sistema extrai refeições, ingredientes, porções, frequência e alternativas do plano. Em seguida, consolida as quantidades e consulta os produtos disponíveis no iFood.

**Caso 3 — Modificação**

O usuário solicita:

"Já tenho farinha, ovos e leite. Remova esses ingredientes da compra."

O sistema deve atualizar a lista de ingredientes e recalcular a proposta de carrinho, sem modificar silenciosamente o carrinho real.

---

## 1. Arquitetura definida

Tecnologias:

- Backend: Python + FastAPI.
- Frontend: React + Vite.
- Schemas: Pydantic v2.
- LLM: provedor configurável, implementação posterior.
- Integração iFood: cliente MCP.
- Receitas: https://github.com/DenilsonRabelo/API-receitas
- Dados nutricionais: USDA FoodData Central e Open Food Facts.
- Comunicação: API REST JSON.
- Desenvolvimento: Git com módulos independentes.

Fluxo arquitetural:

```text
React
  |
  v
FastAPI
  |
  +-- Agent Service
  |     +-- LLM
  |     +-- Recipe Provider
  |     +-- PDF Parser
  |
  +-- Shopping Service
  |     +-- Ingredient Normalizer
  |     +-- Portion Calculator
  |     +-- Product Matcher
  |
  +-- Nutrition Service
  |     +-- USDA
  |     +-- Open Food Facts
  |
  +-- iFood Client
        |
        v
     MCP iFood
        +-- Discovery
        +-- Details
        +-- Cart
```

O frontend nunca deve acessar diretamente tokens do MCP, chaves de LLM ou outras credenciais privadas.

O backend será responsável por autenticação das integrações, coordenação do agente, validação de dados e comunicação com serviços externos.

### Autorização das tools MCP

A lista exata de scopes não é inferida pelos nomes das tools nem mantida como
regra de autorização no backend. `IFOOD_MCP_SCOPE` apenas encaminha ao fluxo
OAuth os scopes fornecidos pela configuração registrada do Agent. O consumer
MCP é a autoridade: `tools/list` informa as tools visíveis ao token e cada
`tools/call` pode responder `401`, `403` ou um erro MCP de autorização.

Não implementar operações reais do MCP nesta issue.

---

## 2. Organização da equipe

**Pessoa 1 — Leffeck: MCP iFood**

Responsável por:

- Autenticação e integração MCP.
- Pesquisa de mercados e produtos.
- Consulta de detalhes e preços.
- Criação e gerenciamento do carrinho.

Diretório principal:

`backend/app/integrations/ifood/`

**Pessoa 2 — Julia: Agente e Receitas**

Responsável por:

- Orquestração com LLM.
- API externa de receitas.
- Interpretação de mensagens.
- Extração estruturada de ingredientes.
- Processamento de PDFs alimentares.

Diretórios:

`backend/app/agent/`

`backend/app/integrations/recipes/`

**Pessoa 3 — José: Motor de Compras e Nutrição**

Responsável por:

- Normalização de ingredientes.
- Conversão de unidades.
- Ajuste de porções.
- Correspondência entre ingredientes e produtos.
- Otimização de embalagens.
- Cálculo de calorias e macronutrientes.
- Contratos compartilhados.

Diretórios:

`backend/app/shopping/`

`backend/app/nutrition/`

`backend/app/models/`

**Pessoa 4 — Diego: Frontend**

Responsável por:

- Interface React.
- Chat com o agente.
- Exibição de receitas.
- Upload e visualização de PDFs.
- Visualização de ingredientes, preços e nutrientes.
- Carrinho e confirmação.

Diretório:

`frontend/`

### Regra essencial

Todos devem conseguir desenvolver simultaneamente.

Os módulos precisam se comunicar por contratos tipados, não por estruturas JSON improvisadas.

Os contratos devem ser definidos nesta EP00 e utilizados pelos módulos reais nas próximas issues.

---

## 3. Objetivo desta tarefa — EP00

Implementar somente os seguintes entregáveis:

1. Estrutura inicial do projeto e configuração de desenvolvimento local.
2. Schemas compartilhados e endpoints REST.
3. Mocks funcionais que permitam o desenvolvimento paralelo.

Não implementar funcionalidades reais dos módulos.

Antes de modificar o repositório, verificar sua estrutura atual, dependências, arquivos e convenções. Preservar implementações existentes e adaptar esta proposta quando necessário, sem apagar trabalho prévio.

---

## 4. Estrutura de diretórios

Criar a seguinte estrutura, adaptando-a ao que já existir:

```text
hackathon-ifood/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── dependencies.py
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       ├── recipes.py
│   │   │       ├── agent.py
│   │   │       ├── nutrition.py
│   │   │       ├── shopping.py
│   │   │       └── cart.py
│   │   ├── models/
│   │   │   ├── recipe.py
│   │   │   ├── ingredient.py
│   │   │   ├── nutrition.py
│   │   │   ├── product.py
│   │   │   ├── shopping.py
│   │   │   ├── cart.py
│   │   │   └── agent.py
│   │   ├── agent/
│   │   ├── integrations/
│   │   │   ├── ifood/
│   │   │   └── recipes/
│   │   ├── shopping/
│   │   ├── nutrition/
│   │   └── mocks/
│   │       ├── recipes.py
│   │       ├── products.py
│   │       ├── nutrition.py
│   │       └── cart.py
│   ├── tests/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── types/
│   │   └── App.jsx
│   └── package.json
│
├── docs/
│   └── API_CONTRACTS.md
├── .env.example
├── .gitignore
└── README.md
```

Criar arquivos `__init__.py` quando necessários.

Evitar arquivos vazios desnecessários. Nos módulos futuros, usar apenas a estrutura mínima para permitir desenvolvimento posterior.

Se o frontend já estiver inicializado, preservar a configuração.

---

## 5. Schemas compartilhados

Utilizar Pydantic v2.

Criar contratos explícitos para as entidades abaixo.

### Ingredient

Representa um ingrediente necessário para uma receita ou plano alimentar.

Campos:

- `id`: string.
- `name`: string.
- `quantity`: Decimal ou equivalente de precisão adequada.
- `unit`: unidade padronizada.
- `optional`: boolean.
- `notes`: string opcional.

Unidades iniciais: `g`, `kg`, `ml`, `l`, `unit`.

Medidas culinárias não convertidas, como xícaras e colheres, deverão ser tratadas na camada de normalização futura. Não assumir equivalências universais.

### Recipe

Representa uma receita estruturada.

Campos:

- `id`: string.
- `name`: string.
- `description`: string opcional.
- `servings`: inteiro positivo.
- `ingredients`: lista de Ingredient.
- `instructions`: lista de strings.
- `preparation_time_minutes`: inteiro opcional.
- `source`: identificação da origem.
- `source_url`: URL opcional.

### NutritionFacts

Representa os dados nutricionais de um alimento ou receita.

Campos:

- `calories_kcal`: número.
- `protein_g`: número.
- `carbohydrates_g`: número.
- `fat_g`: número.
- `reference_quantity`: número.
- `reference_unit`: string.
- `source`: string.
- `estimated`: boolean.

Definir claramente se os dados são por 100 g, por unidade, por porção ou totais da receita.

Não preencher campos desconhecidos com valores inventados.

### ProductCandidate

Representa um produto retornado ou simulado do iFood.

Campos:

- `id`: string.
- `merchant_id`: string.
- `name`: string.
- `description`: string opcional.
- `price`: valor monetário preciso.
- `currency`: BRL.
- `package_quantity`: número opcional.
- `package_unit`: string opcional.
- `available`: boolean.
- `image_url`: URL opcional.
- `source`: string.

Utilizar Decimal no backend para preços e serialização consistente em strings decimais no JSON.

Não usar float para operações monetárias.

### ShoppingItem

Representa a escolha de compra para um ingrediente.

Campos:

- `ingredient`: Ingredient.
- `selected_product`: ProductCandidate opcional.
- `purchase_quantity`: inteiro não negativo.
- `total_price`: valor monetário.
- `status`: enum.

Status possíveis:

- `pending`
- `matched`
- `unavailable`
- `needs_review`

### ShoppingList

Campos:

- `id`: string.
- `recipe_id`: string opcional.
- `items`: lista de ShoppingItem.
- `estimated_subtotal`: valor monetário.
- `currency`: BRL.
- `unresolved_ingredients`: lista de ingredientes.
- `status`: enum.

### CartProposal

Representa uma proposta de carrinho, não necessariamente um carrinho já gravado no iFood.

Campos:

- `id`: string.
- `merchant_id`: string opcional.
- `items`: lista de itens selecionados.
- `estimated_subtotal`: valor monetário.
- `currency`: BRL.
- `requires_confirmation`: boolean.
- `status`: enum.

Status:

- `draft`
- `ready_for_review`
- `confirmed`
- `applied`
- `failed`

Nenhuma proposta poderá ser aplicada automaticamente apenas por ter sido gerada pelo agente.

### AgentRequest

Campos:

- `message`: string.
- `session_id`: string opcional.
- `context`: objeto opcional.

### AgentResponse

Campos:

- `session_id`: string.
- `message`: string.
- `status`: enum.
- `recipe`: Recipe opcional.
- `shopping_list`: ShoppingList opcional.
- `cart_proposal`: CartProposal opcional.
- `nutrition`: NutritionFacts opcional.

Status:

- `completed`
- `needs_input`
- `error`

### MealPlan

Criar também um contrato inicial para PDF alimentar.

Campos:

- `id`: string.
- `source_filename`: string.
- `days`: lista de dias.
- `meals`: lista de refeições ou estrutura equivalente.
- `extraction_warnings`: lista de strings.

Cada refeição deve permitir representar alimentos, quantidades, frequência e alternativas, evitando tratar opções mutuamente exclusivas como itens obrigatórios simultâneos.

Priorizar simplicidade e clareza. Não implementar um sistema nutricional complexo nesta etapa.

---

## 6. Endpoints REST compartilhados

Criar os seguintes endpoints sob `/api/v1`.

Todos devem possuir tipagem de request e response e aparecer corretamente no OpenAPI automático do FastAPI.

| Método | Endpoint | Responsabilidade |
|---|---|---|
| GET | `/health` | Estado do backend |
| GET | `/recipes/search?q=lasanha` | Pesquisa de receitas |
| GET | `/recipes/{recipe_id}` | Detalhes da receita |
| POST | `/agent/chat` | Interação com o agente |
| POST | `/meal-plans/parse` | Upload e interpretação de PDF |
| POST | `/nutrition/calculate` | Cálculo nutricional |
| POST | `/shopping/calculate` | Lista de compras e quantidades |
| POST | `/shopping/match` | Correspondência com produtos |
| POST | `/cart/preview` | Proposta de carrinho |
| POST | `/cart/apply` | Aplicação autorizada da proposta |

Na EP00, esses endpoints devem funcionar com mocks.

Não chamar APIs externas nem o MCP real.

O endpoint `/meal-plans/parse` deve aceitar multipart/form-data com arquivo PDF; na EP00, basta validar tipo e tamanho e devolver um plano alimentar mockado, deixando claro que não houve extração real.

O endpoint `/cart/apply` NÃO deve executar operações comerciais. No modo mock, apenas deve simular a transição após confirmação explícita no request. Não simular autorização ausente nem alegar que um carrinho real foi modificado.

Se necessário, ajustar a organização dos endpoints, desde que o contrato público fique documentado e consistente.

### Padrão de resposta

Os retornos devem ser JSON validado pelo Pydantic.

Usar HTTP status codes adequados:

- 200 para consultas e operações bem-sucedidas.
- 400 ou 422 para dados inválidos.
- 404 para recursos não encontrados.
- 409 para conflitos de estado, quando aplicável.
- 500 apenas para erros inesperados.

Definir um formato consistente para erros.

---

## 7. Mocks obrigatórios

Criar dados de exemplo plausíveis, sem dependências externas.

### Mock de receita

Lasanha à bolonhesa para quatro pessoas, com:

- Massa de lasanha.
- Carne moída.
- Molho de tomate.
- Muçarela.
- Cebola.
- Alho.

Incluir quantidades definidas e instruções de preparo.

### Mock de produtos

Criar produtos de supermercado fictícios associados à receita.

Exemplos:

- Massa de lasanha 500 g.
- Carne moída 500 g.
- Muçarela 200 g.
- Muçarela 500 g.
- Molho de tomate 300 g.

Adicionar preços fictícios, identificadores, quantidades, disponibilidade e merchant.

Deixar explícito que esses produtos e preços são demonstrativos, não dados reais do iFood.

### Mock nutricional

Criar dados ilustrativos de calorias, proteínas, carboidratos e gorduras para a receita e porções.

Identificar sempre os valores como estimados e provenientes de mock.

### Mock de plano alimentar

Criar um plano de exemplo contendo:

- Café da manhã.
- Almoço.
- Lanche.
- Jantar.

Incluir porções, ingredientes e pelo menos um caso de alternativa alimentar.

### Mock de carrinho

Criar uma proposta de carrinho com produtos da receita, subtotal e confirmação pendente.

O cenário principal deve demonstrar o fluxo:

`receita -> ingredientes -> lista de compras -> produtos -> carrinho`

Os mocks devem ser centralizados e reutilizados por todos os endpoints, evitando respostas inconsistentes.

---

## 8. Contratos de serviços internos

Além dos endpoints HTTP, estabelecer interfaces para que as implementações reais possam substituir os mocks.

Interfaces sugeridas:

```python
class RecipeProvider(Protocol):
    async def search(self, query: str): ...
    async def get_by_id(self, recipe_id: str): ...

class IFoodGateway(Protocol):
    async def search_products(self, query: str): ...
    async def get_product(self, product_id: str): ...
    async def get_cart(self): ...
    async def apply_cart(self, proposal): ...

class NutritionProvider(Protocol):
    async def get_nutrition(self, food_name: str): ...

class ShoppingEngine(Protocol):
    def calculate(self, recipe, servings: int): ...
    def match_products(self, shopping_list, products): ...
```

Ajustar as assinaturas para conter os tipos concretos, contexto de usuário e identificadores necessários.

O importante é permitir trocar implementações mockadas por implementações reais com alterações mínimas no restante do sistema.

Registrar as dependências no FastAPI com `Depends`, fábricas ou outra solução simples. Evitar frameworks de injeção de dependências desnecessários.

---

## 9. Configuração local

Preparar o projeto para executar localmente com comandos simples.

### Backend

Utilizar Python 3.11+ e FastAPI.

Exemplo esperado:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

O backend deve funcionar mesmo sem chave de LLM, USDA ou credenciais MCP, por meio de `MOCK_MODE=true`.

### Frontend

Utilizar React + Vite, aproveitando qualquer estrutura existente.

Exemplo:

```bash
cd frontend
npm install
npm run dev
```

Configurar CORS para o ambiente local.

### Variáveis de ambiente

Criar `.env.example` contendo apenas os nomes das variáveis, sem valores:

```env
MOCK_MODE=
API_HOST=
API_PORT=
FRONTEND_ORIGIN=
LLM_API_KEY=
LLM_MODEL=
USDA_API_KEY=
IFOOD_MCP_URL=
IFOOD_OAUTH_AUTHORIZE_URL=
IFOOD_OAUTH_REDIRECT_URI=
IFOOD_CLIENT_ID=
IFOOD_CLIENT_SECRET=
IFOOD_TOKEN_URL=
IFOOD_REVOKE_URL=
IFOOD_ACCESS_TOKEN=
IFOOD_SESSION_COOKIE_MAX_AGE_SECONDS=
IFOOD_MCP_SCOPE=
IFOOD_MCP_TIMEOUT_SECONDS=
RECIPES_API_URL=
```

Não colocar credenciais reais no repositório.

---

## 10. Documentação

Criar ou atualizar `docs/API_CONTRACTS.md`.

O documento deverá conter:

- Visão resumida da arquitetura.
- Lista de schemas e campos.
- Endpoints HTTP.
- Exemplos de request e response.
- Convenção monetária.
- Convenção de unidades.
- Comportamento em modo mock.
- Como integrar cada módulo real posteriormente.
- Responsável por cada diretório.

Atualizar o README existente com instruções de execução local, sem substituir desnecessariamente as informações já presentes.

Documentar que os contratos formam a base das quatro frentes paralelas.

---

## 11. Testes básicos

Criar testes automatizados com pytest para:

1. Inicialização do FastAPI.
2. Health check.
3. Pesquisa de receitas mockadas.
4. Retorno de uma receita por ID.
5. Validação dos principais schemas.
6. Serialização de preços e informações nutricionais.
7. Fluxo mockado de lista de compras e proposta de carrinho.
8. Rejeição de entrada inválida.
9. Garantia de que nenhuma operação real de checkout ocorre em modo mock.

Utilizar `TestClient` ou solução equivalente.

Os testes devem funcionar sem acesso à internet ou credenciais externas.

---

## 12. Restrições de implementação

- Não implementar o cliente MCP real.
- Não implementar chamadas reais a LLM.
- Não implementar a integração real da API de receitas.
- Não implementar cálculos nutricionais reais.
- Não implementar algoritmo avançado de otimização.
- Não implementar a interface final.
- Não persistir dados sensíveis.
- Não alterar arquivos desnecessariamente.
- Não adicionar banco de dados nesta etapa.
- Não criar microsserviços.
- Não adicionar Docker ou infraestrutura complexa, a menos que já existam no projeto.
- Não criar dependências circulares entre os módulos.
- Não realizar operações comerciais reais.

O objetivo é fornecer uma base **simples, testável, tipada e facilmente extensível**.

---

## 13. Critérios de aceite

A tarefa será concluída quando:

- [ ] A estrutura inicial estiver organizada.
- [ ] O backend FastAPI iniciar localmente.
- [ ] O frontend React iniciar localmente.
- [ ] Os schemas Pydantic estiverem definidos.
- [ ] Todos os endpoints planejados estiverem documentados.
- [ ] Os endpoints mockados retornarem respostas válidas.
- [ ] O Swagger estiver disponível em `/docs`.
- [ ] Os módulos possuírem interfaces para futuras integrações.
- [ ] O `.env.example` estiver disponível.
- [ ] O README explicar como executar o projeto.
- [ ] Os testes automatizados passarem.
- [ ] Nenhuma chave real ou dado sensível estiver versionado.

---

## 14. Instruções finais ao Codex

1. Inspecione o repositório existente.
2. Identifique arquivos e convenções já presentes.
3. Implemente a EP00 diretamente no projeto, preservando o código existente.
4. Priorize código simples e manutenção fácil.
5. Evite abstrações desnecessárias.
6. Mantenha a lógica dos mocks separada dos contratos.
7. Use tipagem clara em todas as interfaces.
8. Execute os testes disponíveis e corrija os erros encontrados.
9. Ao terminar, apresente:
   - Arquivos criados ou modificados.
   - Estrutura final do projeto.
   - Endpoints disponíveis.
   - Comandos para executar e testar.
   - Pendências reais para as próximas issues.

**Não implemente as issues das outras pessoas. O trabalho termina quando a infraestrutura, os contratos e os mocks estiverem prontos para os quatro integrantes desenvolverem em paralelo.**
 o mesmo envelope, com códigos como `http_404` e `http_409`. PDF grande usa 413.

## Schemas

| Schema | Campos |
|---|---|
| `Ingredient` | `id`, `name`, `quantity`, `unit`, `optional`, `notes` |
| `Recipe` | `id`, `name`, `description`, `servings`, `ingredients`, `instructions`, `preparation_time_minutes`, `source`, `source_url` |
| `NutritionFacts` | `calories_kcal`, `protein_g`, `carbohydrates_g`, `fat_g`, `reference_quantity`, `reference_unit`, `basis`, `source`, `estimated` |
| `ProductCandidate` | `id`, `merchant_id`, `name`, `description`, `price`, `currency`, `package_quantity`, `package_unit`, `available`, `image_url`, `source` |
| `ShoppingItem` | `ingredient`, `selected_product`, `purchase_quantity`, `total_price`, `status` (`pending`, `matched`, `unavailable`, `needs_review`) |
| `ShoppingList` | `id`, `recipe_id`, `items`, `estimated_subtotal`, `currency`, `unresolved_ingredients`, `status` (`pending`, `ready_for_review`, `needs_review`) |
| `CartProposal` | `id`, `merchant_id`, `items`, `estimated_subtotal`, `currency`, `requires_confirmation`, `status` (`draft`, `ready_for_review`, `confirmed`, `applied`, `failed`) |
| `AgentRequest` | `message`, `session_id`, `context` |
| `AgentResponse` | `session_id`, `message`, `status` (`completed`, `needs_input`, `error`), `recipe`, `shopping_list`, `cart_proposal`, `nutrition` |
| `MealPlan` | `id`, `source_filename`, `days`, `meals`, `extraction_warnings` |
| `Meal` | `day`, `name`, `frequency_per_week`, `ingredients`, `alternative_groups` |
| `MealAlternativeGroup` | `options` (duas ou mais `MealOption`), `choose` (padrão 1); opções não são somadas automaticamente |

## Endpoints

| Método | Rota | Request | Response mock |
|---|---|---|---|
| GET | `/health` | — | `{ "status": "ok", "mock_mode": true }` |
| GET | `/api/v1/recipes/search?q=lasanha` | query `q` | `Recipe[]` |
| GET | `/api/v1/recipes/{recipe_id}` | path ID | `Recipe`; 404 se ausente |
| POST | `/api/v1/agent/chat` | `AgentRequest` | `AgentResponse` com `needs_input` |
| POST | `/api/v1/meal-plans/parse` | multipart `file` PDF, até 10 MiB | `MealPlan` demonstrativo, com aviso de ausência de extração |
| POST | `/api/v1/nutrition/calculate` | `{"recipe_id":"mock-lasagna-bolognese","servings":4}` | `NutritionFacts` por porção |
| POST | `/api/v1/shopping/calculate` | `{"recipe_id":"mock-lasagna-bolognese","servings":4}` | `ShoppingList` com itens pendentes |
| POST | `/api/v1/shopping/match` | `{"shopping_list": <ShoppingList>, "merchant_id": null}` | `ShoppingList` com produtos mockados |
| POST | `/api/v1/cart/preview` | `{"shopping_list": <ShoppingList>}` | `CartProposal`; 409 se itens não resolvidos |
| POST | `/api/v1/cart/apply` | `{"proposal": <CartProposal>, "confirmed": true}` | `CartApplyResponse` com `mock_only: true`; 409 sem confirmação |
| GET | `/api/v1/ifood/addresses` | cookie de sessão OAuth | `AddressListResponse` |
| GET | `/api/v1/ifood/mcp/tools` | cookie de sessão OAuth | lista de tools e respectivos JSON Schemas |
| POST | `/api/v1/ifood/offers/search` | `SearchOffersRequest` | resultado bruto identificado como `ifood_searchOffers` |
| POST | `/api/v1/ifood/offers/browse` | `BrowseOffersRequest` | resultado bruto identificado como `ifood_browseOffers` |
| GET | `/api/v1/ifood/items/{item_id}` | `merchant_id` + `address_id` ou coordenadas | detalhes, preço base/promocional e disponibilidade validada |
| GET | `/api/v1/ifood/merchants/{merchant_id}` | `address_id` ou coordenadas | detalhes operacionais do estabelecimento |

### Consumer MCP do iFood

Todas as tools usam um único endpoint Streamable HTTP: `https://consumer-mcp.ifood.com.br/marketplace`.
Os domínios são identificados pelos nomes das tools, e não por URLs distintas. O fluxo de descoberta deve começar
com `ifood_listAddresses`; depois, `address_id` ou as coordenadas alimentam `ifood_browseOffers` e
`ifood_searchOffers`. O tipo padrão nessas rotas é `GROCERIES`.

`SearchOffersRequest` recebe `query`, `result_kind`, `merchant_type`, `refinements`, paginação e uma localização:
`address_id` ou o par `latitude`/`longitude`. `BrowseOffersRequest` recebe os mesmos campos, sem `query`, e exige
`merchant_type`. Na busca, `merchant_type` é opcional; na navegação é obrigatório. Quando recebe `address_id`, o backend consulta `ifood_listAddresses` e converte as coordenadas para
o objeto MCP obrigatório `userLocation`. `refinements.merchant_id` restringe a busca ao catálogo de um parceiro.

Os resultados paginados permanecem em `data`, preservando `results`, `facets`, `nextPageToken`, `hasMore` e
`agentHints`. Para busca de produtos usada pela lista de compras, o backend chama `ifood_searchOffers` com
`resultKind=ITEM` e valida cada candidato com `ifood_getItem` antes de convertê-lo em `ProductCandidate`.

`ItemDetailsResult.price` é o preço efetivo: usa `promotionalUnitPrice` quando presente e, caso contrário,
`unitPrice`. Os dois valores originais também são retornados. O schema do iFood não fornece booleano de estoque;
portanto, `available` significa que `getItem` confirmou o item atual para aquele `merchantId` e localização,
enquanto `ITEM_NOT_FOUND` resulta em `unavailable`. Outros erros não são convertidos em estado de estoque.

Exemplo de busca de produtos em supermercado:

```json
{
  "query": "leite integral",
  "result_kind": "ITEM",
  "merchant_type": "GROCERIES",
  "address_id": "UUID-RETORNADO-POR-LIST-ADDRESSES",
  "refinements": {
    "merchant_id": "UUID-DO-MERCADO",
    "max_item_price": "20.00",
    "only_open": true,
    "sort": "PRICE"
  },
  "page_size": 10
}
```

Exemplo de fluxo:

```bash
curl -s 'http://localhost:8000/api/v1/recipes/search?q=lasanha'
curl -s -X POST http://localhost:8000/api/v1/shopping/calculate -H 'Content-Type: application/json' -d '{"recipe_id":"mock-lasagna-bolognese","servings":4}'
curl -s -X POST http://localhost:8000/api/v1/nutrition/calculate -H 'Content-Type: application/json' -d '{"recipe_id":"mock-lasagna-bolognese","servings":4}'
```

O retorno de `/shopping/calculate` contém `"estimated_subtotal":"0.00"` e produtos nulos. Envie esse objeto em `shopping_list` para `/shopping/match`; a receita mockada para quatro porções retorna subtotal `"70.90"`. Envie o retorno para `/cart/preview`. A proposta tem `status: "ready_for_review"` e `requires_confirmation: true`. `/cart/apply` exige `confirmed: true` e responde `mock_only: true`; não chama o gateway nem modifica um carrinho real.

## Substituição dos mocks

- **Leffeck — `backend/app/integrations/ifood/`:** manter o adaptador do consumer MCP e validar os JSON Schemas retornados por `tools/list` no ambiente aprovado. Escopos MCP indicam permissões, não nomes de ferramentas. Checkout permanece fora deste escopo.
- **Julia — `backend/app/agent/` e `backend/app/integrations/recipes/`:** implementar agente, leitor de PDF e `RecipeProvider`. Substituir o endpoint mockado por serviços tipados sem alterar os schemas públicos.
- **José — `backend/app/shopping/`, `backend/app/nutrition/`, `backend/app/models/`:** implementar normalização, conversões com contexto, correspondência e `NutritionProvider`/`ShoppingEngine`. Preservar `Decimal` e bases nutricionais explícitas.
- **Diego — `frontend/`:** consumir a API REST; os tipos devem seguir `/openapi.json`. Não colocar segredos no bundle React.

`MOCK_MODE=false` habilita OAuth e chamadas ao consumer MCP nas rotas iFood. Os
tokens são persistidos criptografados em SQLite e sobrevivem a reinicializações do
backend. O estado PKCE pendente e os locks de refresh continuam locais ao processo;
por isso, use um único worker até adotar coordenação compartilhada para múltiplos
workers. Checkout continua fora deste escopo.
