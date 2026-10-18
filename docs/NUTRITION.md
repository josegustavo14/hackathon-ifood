# Nutrição com USDA FoodData Central

## Configuração

No `.env` local, configure `NUTRITION_PROVIDER=usda` e `USDA_API_KEY` com sua chave FoodData Central. A chave fica apenas no backend. O `.env.example` nunca deve conter credenciais privadas.

Para experimentar, a chave pública `DEMO_KEY` funciona com dados reais, mas tem limites de **30 consultas/hora e 50/dia por IP**. Para uso contínuo, obtenha uma chave em [FoodData Central](https://fdc.nal.usda.gov/api-key-signup/). A [documentação oficial](https://fdc.nal.usda.gov/api-guide/) descreve os endpoints e limites. A aplicação informa erro quando a chave é rejeitada, a API fica indisponível ou o limite é atingido; não troca silenciosamente para valores mockados.

## Uso

- No chat, peça “quero macarrão e as calorias” ou, após receber uma receita, “e os macros?”.
- No modal da receita, ajuste as porções e clique em **Ver nutrição**. Alterar porções invalida o resultado anterior.
- O painel alterna entre valores por porção e receita inteira. **Ingredientes e fontes** mostra o peso utilizado e os nutrientes de cada ingrediente para a receita inteira.
- PDFs mostram o total semanal dos ingredientes obrigatórios, multiplicados pela frequência de cada refeição. Alternativas não escolhidas ficam de fora.
- Receitas RecipeNLG sem rendimento conhecido mostram apenas o total por lote, sem inventar uma quantidade de porções.

## Cálculo e rastreabilidade

A API consulta `/food/{fdcId}` do USDA, valida o ID e a descrição do registro, e usa valores por 100 g. A contribuição de cada ingrediente é `valor_por_100g × peso_em_gramas / 100`. O total é a soma antes do arredondamento; os valores por porção usam o total não arredondado dividido pelo número de porções. Valores monetários e nutrientes usam `Decimal` no backend.

Conversões de `kg` e `g` são exatas. Unidades de cebola, alho e ovo usam o peso de uma porção identificada no registro USDA. O ovo genérico assume tamanho grande (50 g comestíveis), informado em aviso. `ml` e `l` exigem densidade validada; medidas caseiras não são tratadas como uma unidade inteira do alimento. Quantidades desconhecidas ou ambíguas deixam o cálculo incompleto.

O mapeamento revisado em `backend/app/nutrition/usda_mappings.json` cobre massa seca, carne bovina moída, molho de tomate, creme de leite, muçarela, cebola, alho, arroz branco cru, peito de frango cru, ovo e azeite, incluindo aliases em português e inglês. Não há seleção automática do primeiro resultado de busca. Alimentos sem correspondência validada aparecem como pendentes. Creme de leite é aproximado pelo registro USDA de creme com 19,1% de gordura; a marca real pode variar. Massa e arroz usam o peso seco/cru, não o peso após cozinhar.

Calorias, proteínas, carboidratos e gorduras exigem cobertura de todos os ingredientes incluídos. Caso contrário, `status=incomplete`, `total=null` e `per_serving=null`; as contribuições conhecidas continuam visíveis como parciais. Fibras, açúcares, gorduras saturadas e sódio são opcionais: se algum ingrediente não tiver um desses valores, o campo agregado correspondente é `null`, nunca zero inventado. Ingredientes opcionais só entram com `include_optional=true`.

As fontes retornam ID USDA, descrição, nome do ingrediente, peso e nutrientes calculados. Os links levam ao registro usado. Os dados são estimativas da composição dos ingredientes; não medem perdas no cozimento, variação entre marcas ou peso final preparado.

Registros públicos são mantidos em cache por até 24 horas, limitado a 256 alimentos, na memória e em `backend/.data/usda_foods.sqlite3` (ignorado pelo Git). A validade começa na consulta original e não é renovada ao ler ou importar um registro. O cache sobrevive a reinícios, não armazena chaves nem receitas e não guarda erros de consulta. Registros repetidos são consultados uma vez por cálculo. Após expirar, o registro precisa ser atualizado pela API.

## Validação

`backend/tests/fixtures/usda_live_foods.json` contém os campos usados de registros reais consultados em 18/10/2026, preservando IDs e descrições. Os dados USDA são públicos ([guia e licença](https://fdc.nal.usda.gov/api-guide/)). Os testes usam esse snapshot para conferir decimais, calorias, macros e nutrientes adicionais da receita de macarrão, porções, rendimento desconhecido, cache e total semanal. A integração ativa também deve ser validada com a API real; testes automatizados não consomem a quota USDA.

Para a receita padrão de quatro porções, os registros consultados produzem **3.392 kcal no total e 848 kcal por porção**, usando 500 g de massa seca, 300 g de molho, 200 g de creme e 500 g de carne moída. Os avisos do cálculo identificam as aproximações utilizadas.
