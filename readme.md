# iFood Chef AI

Projeto do Hackathon SEMCOMP × iFood 2026. O backend FastAPI recebe receitas ou um PDF de plano alimentar, estrutura ingredientes, estima nutrição quando solicitada e prepara uma lista de compras para revisão. O frontend React + Vite conversa com o backend; chaves e tokens ficam no servidor.

## Estado atual

- **Receitas:** busca local opcional no dataset RecipeNLG, receita demonstrativa em JSON e geração de receita estruturada pelo LLM configurado. A receita retornada pelo agente pode ser aberta e usada nos endpoints de compras durante a vida do processo backend.
- **Plano alimentar:** upload de PDF de até 10 MiB, extração do texto, interpretação de refeições e alternativas e tentativa de cálculo nutricional dos itens obrigatórios extraídos. Alternativas sem escolha e frequência semanal não entram nessa soma.
- **Nutrição:** USDA FoodData Central com `NUTRITION_PROVIDER=usda` e chave; caso contrário, mock explícito. O chat só consulta nutrição quando o pedido é identificado como nutricional. Abrir uma receita não inicia o cálculo; há um botão **Ver nutrição**.
- **Compras:** motor determinístico para unidades, estoque, produtos compatíveis e combinações de embalagens. No modo real, a busca de ofertas usa os endpoints do iFood MCP e um endereço salvo escolhido pelo usuário.
- **Carrinho:** prévia local da proposta, sem alterar o iFood. No modo mock, `/cart/apply` simula a transição. No modo real, a confirmação explícita valida endereço, preços e disponibilidade novamente antes de chamar `createCart`. Isso cria um carrinho, sem finalizar pedido nem definir pagamento.

Os preços do mock são fictícios. Preços reais dependem da disponibilidade e da resposta do iFood. Frete desconhecido não entra no subtotal.

### Como o motor escolhe embalagens

Para cada ingrediente e estabelecimento, o motor procura uma combinação inteira de embalagens que cubra a quantidade líquida após o estoque doméstico:

```text
minimizar  Σ pᵢ xᵢ + F
sujeito a Σ qᵢ xᵢ ≥ Qₙₑcₑₛₛáᵣᵢₐ
           xᵢ ∈ ℤ≥0
```

`pᵢ` é o preço informado da embalagem, `qᵢ` sua quantidade útil, `xᵢ` o número de embalagens e `F` o frete. O frete só entra na comparação entre estabelecimentos quando é conhecido para todos eles; se não for, a comparação usa apenas o subtotal dos produtos e sinaliza a limitação. Produtos incompatíveis, indisponíveis ou com quantidade desconhecida são excluídos. Em empate de custo, o motor prefere menos excedente, depois menos embalagens e, por fim, IDs estáveis. A busca é exata para conjuntos pequenos; o fallback determinístico informa quando não há garantia de ótimo.

## Requisitos e execução

Python 3.11+ e Node.js compatível com Vite 7 (22.12+ ou 20.19+).

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Em outro terminal:

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

Abra `http://localhost:5173`. O backend serve Swagger em `http://localhost:8000/docs` e health check em `http://localhost:8000/health`. Sem `.env`, o backend inicia em modo mock. Para usar a configuração local, copie `.env.example` para `.env`, preencha apenas os valores necessários e execute a partir da raiz:

```bash
set -a
source .env
set +a
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host "$API_HOST" --port "$API_PORT" --reload
```

O frontend usa `http://localhost:8000/api/v1` por padrão. Para outra API, configure `VITE_API_BASE_URL` em `frontend/.env`; nunca coloque segredos em variáveis `VITE_`. Ajuste `FRONTEND_ORIGIN` no backend se a porta do frontend mudar.

## RecipeNLG

[RecipeNLG](https://github.com/Glorf/recipenlg) publica um dataset, não uma API de consulta. O [download oficial](https://recipenlg.cs.put.poznan.pl/dataset) exige aceite de termos que limitam o uso a pesquisa e educação sem fins comerciais. O projeto não baixa, distribui nem versiona o dataset. Confirme que seu uso atende aos termos antes de obtê-lo.

Coloque o ZIP baixado em `backend/.data/recipenlg/` (pasta ignorada pelo Git). O comando abaixo extrai `full_dataset.csv` nessa mesma pasta e gera o índice local:

```bash
cd backend
python -m app.integrations.recipes.index_recipes .data/recipenlg/NOME_DO_ARQUIVO.zip
```

O índice fica em `backend/.data/recipenlg.sqlite3`, ignorado pelo Git. Também é possível passar um CSV já extraído ao comando. Use `--index /outro/caminho/indice.sqlite3` e `RECIPENLG_INDEX_PATH` para mudar o local. A importação prioriza linhas `source=Gathered`. A busca retorna apenas receitas com pelo menos dois ingredientes e quantidades interpretáveis com segurança; medidas como xícaras, libras e embalagens sem conversão específica são descartadas, sem transformá-las em “unidades”. O dataset é majoritariamente em inglês. Com um LLM configurado, nomes de receitas e ingredientes são traduzidos ao abrir a receita; quantidades e instruções originais são preservadas. Quando não há rendimento informado, a API marca a receita como `recipenlg_batch`: `servings=1` significa **um lote completo**, não uma porção, e a interface não oferece nutrição por porção para ela.

Sem índice ou sem receita elegível, a busca mantém a receita demonstrativa; o agente pode recorrer à geração com o LLM. O índice local não contém credenciais, mas pode ocupar bastante espaço.

## Configuração de integrações

- `MOCK_MODE=true`: gateway iFood e carrinho simulados. Os JSONs de `backend/app/mocks/data/` são os dados de demonstração.
- `MOCK_MODE=false`: discovery, endereços e carrinho usam o iFood MCP. Para aplicar propostas reais, solicite também `mcp.cart.read mcp.cart.write` em `IFOOD_MCP_SCOPE`, além dos escopos de discovery e endereço. Autorize a conta em `/api/v1/ifood/oauth/authorize`; o callback configurado é `/api/v1/ifood/oauth/callback`. A aplicação guarda tokens criptografados em `backend/.data/ifood_oauth.sqlite3` e envia ao navegador somente um cookie HttpOnly. Em produção, defina `IFOOD_TOKEN_ENCRYPTION_KEY` independente.
- `LLM_PROVIDER=openai_compatible`, `LLM_API_KEY`, `LLM_MODEL` e `LLM_BASE_URL`: habilitam interpretação por LLM. Sem eles, o chat não gera novas receitas e o parser de plano usa o fallback determinístico. O LLM também classifica pedidos implícitos de nutrição; menções explícitas a calorias e macronutrientes são reconhecidas diretamente.
- `NUTRITION_PROVIDER=usda` e `USDA_API_KEY`: habilitam dados USDA estimados. Com `NUTRITION_PROVIDER=mock`, só a receita demonstrativa tem valores ilustrativos; receitas externas e PDFs retornam resultado nutricional incompleto, sem números inventados.

## Fluxos

1. Escolha uma receita na interface ou peça uma ao Chef. Ajuste porções e marque ingredientes que já possui.
2. Clique em **Montar minha lista de compras**. No modo real, selecione um endereço salvo quando houver mais de um; com um endereço, ele é usado diretamente. O backend pesquisa ofertas, verifica itens e calcula combinações dentro de um estabelecimento.
3. Revise itens, preços e ingredientes sem correspondência. Gere a prévia do carrinho. Ao marcar a confirmação e clicar em **Confirmar proposta**, o backend verifica novamente os produtos e cria o carrinho no iFood quando a sessão tem `createCart`. O checkout continua exclusivamente no iFood.
4. Para nutrição de uma receita, peça no chat ou clique em **Ver nutrição**. Ao enviar um PDF de plano alimentar, o backend tenta estimar os itens obrigatórios extraídos e avisa quando faltam dados.

Receitas geradas pelo LLM ficam em memória (até 256); reiniciar o backend ou usar múltiplos workers pode invalidar seus IDs. Reabra ou gere novamente a receita nesse caso. O PDF enviado não é persistido.

### Acesso por MCP

O servidor local em `backend/app/mcp_server/` expõe a API Chef AI para clientes MCP por stdio e Streamable HTTP, preservando os contratos e a confirmação explícita do carrinho. Não é uma implementação do MCP oficial do iFood.

Na pasta `backend`, instale com `.\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt`. Com o FastAPI rodando, execute `.\.venv\Scripts\python.exe -m app.mcp_server.smoke` para testar a conexão stdio. Consulte [docs/MCP.md](docs/MCP.md) para execução HTTP, Inspector, configuração de cliente, ferramentas e resultados dos testes.

## API principal

| Método | Rota | Função |
|---|---|---|
| GET | `/health` | estado do backend e modo mock |
| GET | `/api/v1/recipes/search?q=...` | pesquisa de receitas |
| GET | `/api/v1/recipes/{id}` | detalhes da receita |
| POST | `/api/v1/agent/chat` | receita e nutrição quando solicitada |
| POST | `/api/v1/meal-plans/parse` | interpretação de PDF e nutrição dos itens obrigatórios |
| POST | `/api/v1/nutrition/calculate` | estimativa nutricional por receita e porção |
| POST | `/api/v1/shopping/calculate` | ingredientes para compra |
| POST | `/api/v1/shopping/match` | correspondência e embalagens |
| POST | `/api/v1/shopping/plan` | planejamento estruturado independente do MCP |
| POST | `/api/v1/cart/preview` | prévia sem escrita no iFood |
| POST | `/api/v1/cart/apply` | simulação em modo mock; `createCart` após confirmação no modo real |
| GET | `/api/v1/ifood/addresses` | endereços salvos |
| GET | `/api/v1/ifood/mcp/tools` | ferramentas liberadas ao token atual |
| POST | `/api/v1/ifood/offers/search` | pesquisa de ofertas |

O contrato completo está no Swagger e em `docs/API_CONTRACTS.md`. Valores monetários usam `Decimal` no backend e strings decimais em BRL no JSON. Ingredientes usam `g`, `kg`, `ml`, `l` ou `unit`; conversões culinárias exigem equivalência confiável.

## Testes

```bash
backend/.venv/bin/pytest -q backend/tests
npm --prefix frontend test
npm --prefix frontend run build
```

Os testes automatizados usam mocks locais e não exigem internet ou credenciais. A validação das ofertas reais depende de uma conta iFood autorizada e da disponibilidade do MCP.

## Organização

- `backend/app/agent/` e `backend/app/integrations/recipes/`: agente, PDF e fontes de receita.
- `backend/app/nutrition/`: cálculo USDA.
- `backend/app/shopping/`: motor determinístico de compras.
- `backend/app/integrations/ifood/`: OAuth e cliente MCP.
- `backend/app/models/` e `backend/app/core/contracts.py`: contratos compartilhados.
- `frontend/`: interface e cliente REST.

O `createCart` foi identificado na sessão iFood autorizada, mas não foi executado durante a validação: os testes de escrita usam um gateway falso. A prévia local não indica que o carrinho real foi alterado. Frete, pagamento e envio do pedido não são feitos por este projeto.
