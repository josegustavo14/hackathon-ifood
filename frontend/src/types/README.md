Os tipos de API do frontend devem seguir `docs/API_CONTRACTS.md` e o OpenAPI em `/openapi.json`.

`api.d.ts` descreve os contratos consumidos pelo cliente JavaScript usando JSDoc em `services/api.js`. Mantenha os tipos sincronizados com os modelos Pydantic ao evoluir a API. Valores decimais são strings; o frontend apenas formata preços, e o backend calcula subtotais.
