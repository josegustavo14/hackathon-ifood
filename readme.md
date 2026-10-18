# iFood Chef AI

Base inicial do projeto para o **Hackathon SEMCOMP × iFood 2026**. A proposta é transformar receitas e planos alimentares em listas de compras e propostas de carrinho no iFood. Esta entrega é a **EP00**: estrutura, contratos e respostas demonstrativas para que as quatro frentes da equipe avancem em paralelo.

## O que funciona nesta etapa

- Backend FastAPI com schemas Pydantic v2, OpenAPI em `/openapi.json` e Swagger em `/docs`.
- Integração iFood consumer MCP com OAuth 2.0 + PKCE, renovação e revogação de tokens no backend.
- Descoberta de mercados/ofertas e consulta de item, preço, disponibilidade e estabelecimento via tools MCP.
- Endpoints REST de receita, agente, upload de PDF, nutrição, compras e carrinho.
- Dados fictícios em **JSON** em `backend/app/mocks/data/`, carregados e validados pelos schemas.
- Fluxo demonstrativo: receita → ingredientes → lista de compras → produtos fictícios → proposta de carrinho.
- Frontend React + Vite mínimo para iniciar o trabalho da interface.
- Testes automatizados do backend, sem internet ou credenciais.

A EP00 ainda usa mocks por padrão para LLM, receitas, nutrição e carrinho. Com `MOCK_MODE=false`, as rotas `/api/v1/ifood/*` usam o consumer MCP real; checkout continua desabilitado. O PDF é validado quanto a tipo, assinatura e tamanho, mas seu conteúdo não é extraído.

## Estrutura

```text
backend/
  app/
    api/v1/          rotas REST
    core/            configuração, interfaces e dependências FastAPI
    models/          contratos Pydantic compartilhados
    mocks/           adaptadores mock e fixtures em data/*.json
    agent/           espaço para agente e leitura de PDF
    integrations/    espaços para iFood e API de receitas
    shopping/        espaço para motor de compras
    nutrition/       espaço para cálculo nutricional
  tests/             testes da EP00
  requirements.txt
frontend/
  src/               base React e serviço de URL da API
  package.json
docs/API_CONTRACTS.md
.env.example
```

Consulte [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) para campos, unidades, estados, requests e responses completos.

## Requisitos e execução local

- Python **3.11+**
- Node.js e npm

Backend, a partir da raiz do repositório:

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
MOCK_MODE=true uvicorn app.main:app --reload
```

API mock: `http://localhost:8000`; Swagger: `http://localhost:8000/docs`; health check: `http://localhost:8000/health`. `MOCK_MODE=true` já é o padrão.

Para testar OAuth e o consumer MCP com a configuração de `.env` e callback em `localhost:8080`:

```bash
set -a
source .env
set +a
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host "$API_HOST" --port "$API_PORT" --reload
```

Abra `http://localhost:8080/api/v1/ifood/oauth/authorize`; depois do callback, use o Swagger em `http://localhost:8080/docs`. Tokens permanecem somente no backend e o navegador recebe um cookie de sessão HttpOnly.

Frontend, em outro terminal:

```bash
cd frontend
npm install
npm run dev
```

Interface: `http://localhost:5173`. A origem CORS padrão é essa URL. Para outra origem, configure `FRONTEND_ORIGIN`. O frontend só deve chamar o backend e nunca receber chaves privadas.

Para executar os testes, no ambiente virtual do backend:

```bash
cd backend
pytest -q
```

Para verificar o build do frontend: `cd frontend && npm run build`.

## Endpoints

| Método | Rota | Resposta nesta EP00 |
|---|---|---|
| GET | `/health` | estado do backend |
| GET | `/api/v1/recipes/search?q=lasanha` | lista de receitas mockadas |
| GET | `/api/v1/recipes/{recipe_id}` | receita ou 404 |
| POST | `/api/v1/agent/chat` | resposta demonstrativa |
| POST | `/api/v1/meal-plans/parse` | valida PDF multipart e retorna plano demonstrativo |
| POST | `/api/v1/nutrition/calculate` | nutrientes estimados por porção |
| POST | `/api/v1/shopping/calculate` | ingredientes e quantidades pendentes |
| POST | `/api/v1/shopping/match` | produtos fictícios e subtotal |
| POST | `/api/v1/cart/preview` | proposta para revisão |
| POST | `/api/v1/cart/apply` | transição simulada, só com confirmação explícita |
| GET | `/api/v1/ifood/addresses` | endereços da conta autenticada |
| GET | `/api/v1/ifood/mcp/tools` | tools e schemas expostos ao token atual |
| POST | `/api/v1/ifood/offers/search` | busca textual de mercados/produtos |
| POST | `/api/v1/ifood/offers/browse` | navegação de ofertas por tipo de estabelecimento |
| GET | `/api/v1/ifood/items/{item_id}` | detalhes, preço promocional e disponibilidade validada via `getItem` |
| GET | `/api/v1/ifood/merchants/{merchant_id}` | detalhes do estabelecimento |

Exemplo inicial:

```bash
curl 'http://localhost:8000/api/v1/recipes/search?q=lasanha'
curl -X POST 'http://localhost:8000/api/v1/shopping/calculate' \
  -H 'Content-Type: application/json' \
  -d '{"recipe_id":"mock-lasagna-bolognese","servings":4}'
```

Use a resposta de `/shopping/calculate` como `shopping_list` no body de `/shopping/match`; depois envie a lista retornada para `/cart/preview`. `/cart/apply` recebe `{"proposal": <CartProposal>, "confirmed": true}`. Os exemplos completos de contrato estão no Swagger e em `docs/API_CONTRACTS.md`.

## Dados e convenções

Os JSONs em `backend/app/mocks/data/` são a única fonte dos exemplos de receita, produtos, nutrição, plano alimentar, texto do agente e estado do carrinho. `data.py` lê os arquivos; `services.py` adapta os dados às interfaces do backend. `source: "mock_ep00"` identifica dados demonstrativos.

Dinheiro usa `Decimal` no Python e string com duas casas no JSON (`"8.90"`), sempre em BRL. Quantidades usam unidades `g`, `kg`, `ml`, `l` ou `unit`; medidas culinárias ainda não são convertidas. Informações nutricionais informam a base (`per_serving`, `recipe_total` etc.), origem e se são estimadas.

Use `.env.example` como lista de variáveis e mantenha os valores locais somente em `.env`, que não deve ser versionado. A integração real usa OAuth Authorization Code com PKCE e mantém `IFOOD_CLIENT_SECRET` exclusivamente no backend.

## Próximas frentes

| Responsável | Diretórios | Próxima implementação |
|---|---|---|
| Leffeck | `backend/app/integrations/ifood/` | autenticação MCP, descoberta de ofertas, detalhes, preços e disponibilidade |
| Julia | `backend/app/agent/`, `backend/app/integrations/recipes/` | agente, receitas externas e interpretação de PDF |
| José | `backend/app/shopping/`, `backend/app/nutrition/`, `backend/app/models/` | normalização, unidades, seleção de produtos e nutrição real |
| Diego | `frontend/` | interface, chat, upload, revisão e confirmação |

Os contratos em `backend/app/models/` e as interfaces em `backend/app/core/contracts.py` são a base comum das quatro frentes. Troque as fábricas em `backend/app/core/dependencies.py` ao integrar provedores reais. A proposta de carrinho deve continuar exigindo revisão e autorização explícita antes de qualquer operação comercial.
