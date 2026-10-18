# Motor de compras

`DeterministicShoppingEngine` recebe receitas, estoque doméstico e produtos estruturados. Não acessa LLM, USDA nem MCP. O endpoint `POST /api/v1/shopping/plan` usa exatamente esses dados; o chamador é responsável por obter produtos e preços atuais. Os endpoints EP00 `/shopping/calculate` e `/shopping/match` continuam disponíveis com o catálogo mockado.

## Exemplo

```json
{
  "recipes": [
    {"id": "r1", "servings": 4, "target_servings": 4, "ingredients": [
      {"id": "cheese-1", "name": "Muçarela", "quantity": "300", "unit": "g"}
    ]},
    {"id": "r2", "servings": 2, "target_servings": 2, "ingredients": [
      {"id": "cheese-2", "name": "Muçarela", "quantity": "400", "unit": "g"}
    ]}
  ],
  "stock": [{"name": "Muçarela", "quantity": "200", "unit": "g"}],
  "products": [
    {"id": "a", "merchant_id": "mercado", "name": "Muçarela 200 g", "price": "9.00", "package_quantity": "200", "package_unit": "g", "available": true, "source": "catalog"},
    {"id": "b", "merchant_id": "mercado", "name": "Muçarela 300 g", "price": "13.00", "package_quantity": "300", "package_unit": "g", "available": true, "source": "catalog"}
  ]
}
```

O requisito líquido é 500 g. A seleção exata é 1 embalagem de 200 g e 1 de 300 g, por R$ 22,00. A resposta inclui necessidade original, estoque elegível e usado, necessidade líquida, seleções, quantidade comprada, sobra, custo, status e motivo. Dinheiro e quantidades são `Decimal` no backend e strings no JSON.

## Regras

- `g`/`kg` e `ml`/`l` usam conversão direta. `unit` só é compatível com `unit`. `cup`, `tablespoon` e `teaspoon` exigem uma regra em `conversions` com nome exato do ingrediente, fator e origem informada. Sem regra, o item fica `needs_review`.
- Nomes são normalizados apenas em maiúsculas/minúsculas, acentos e espaços. Sinônimos exigem `aliases` explícitos. Unidades ou categorias incompatíveis não são consolidadas. Restrições em `required_tags` são verificadas nos produtos e no estoque; dados ausentes não passam por essa verificação. Uma troca fora do nome ou da categoria exige `authorized_product_ids`; disponibilidade, unidade e tags continuam obrigatórias.
- Produtos precisam estar disponíveis, ter embalagem e unidade compatível. A comparação por nome é conservadora: só aceita o nome do ingrediente seguido da medida da embalagem. `merchant_id` limita a busca a um mercado. Sem ele, o motor avalia cada mercado isoladamente e escolhe o plano com mais itens resolvidos; entre planos equivalentes, aplica custo, sobra, número de embalagens e ID estável. Nunca mistura mercados em um carrinho.
- Para até oito produtos e no máximo `100_000` combinações de contagens, a busca exaustiva minimiza, nesta ordem: preço, sobra, número de embalagens e IDs. Para espaços maiores, compara soluções de uma embalagem por tipo individualmente; sinaliza `optimal: false` e `deterministic_fallback_not_proven_optimal`. Não afirma ótimo não demonstrado.
- `delivery_fees` é opcional e contém valores conhecidos por mercado. O frete não entra em `estimated_subtotal`. `estimated_total` só existe quando o frete do mercado escolhido foi informado. Se faltar frete para algum mercado comparado, a escolha entre mercados considera apenas produtos, retorna um aviso e marca o plano global como não comprovadamente ótimo.
- Quantidade desconhecida, conversão não verificada e produto sem correspondência permanecem não resolvidos. Ingredientes opcionais ficam fora do cálculo, salvo com `include_optional: true`.

O retorno detalhado de `/shopping/plan` é próprio do motor. O fluxo EP00 de carrinho usa `ShoppingList`; em `/shopping/match`, uma combinação mista é representada por um `ShoppingItem` por produto, mantendo o subtotal e permitindo criar uma proposta mockada. Nenhuma rota aplica um carrinho real.

## Testar

```bash
cd backend
.venv/bin/pytest -q
```
