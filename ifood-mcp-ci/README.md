# Testes automatizados do iFood MCP

Esta pasta e independente dos projetos `backend` e `frontend`. Ela reutiliza,
sem modificar, o OAuth Authorization Code + PKCE, o armazenamento criptografado
e o cliente Streamable HTTP MCP existentes no produto.

## O que roda

- `contract`: sem rede, valida `initialize`, `notifications/initialized`,
  `tools/call`, Bearer token, `Mcp-Session-Id`, IDs JSON-RPC, erros, refresh,
  persistencia do token rotacionado e ausencia de secrets na saida;
- `live`: executa um smoke test no endpoint real. Uma resposta autorizada de
  `tools/list` ou um HTTP 403 explicito sao aceitos; ambos comprovam alcance do
  MCP e aplicacao do limite OAuth. Erros de rede, protocolo, HTTP 401 e 5xx
  continuam falhando.

O smoke test nao exige uma identidade permanente nem chama tools com dados de
producao. A validacao detalhada de inicializacao, sessao, Bearer token, chamada
de tool, refresh e erros permanece na camada contratual sem rede.

## Execucao local

```bash
python -m pip install -r ifood-mcp-ci/requirements.txt
python -m pytest -c ifood-mcp-ci/pytest.ini ifood-mcp-ci/mcp_tests -m contract \
  --junitxml=ifood-mcp-ci/reports/contract.xml
```

Os testes `live` exigem uma autorizacao real previamente criada pelo produto.
Eles nunca abrem navegador e nunca usam `client_credentials`.

No GitHub, os testes contratuais rodam em todo push para `main`. A camada `live`
nao roda em pushes nem por agendamento: ela exige `Run workflow` com a opcao
`Run read-only tests against the real iFood MCP` marcada. Essa protecao evita
consultas acidentais quando a unica autorizacao disponivel pertence a producao.

## Ambiente protegido do GitHub

Crie o environment `ifood-mcp-test`, configure aprovadores quando disponivel,
restrinja quem pode administra-lo e defina:

| Tipo | Nome | Conteudo |
| --- | --- | --- |
| Variable | `IFOOD_MCP_URL` | URL HTTPS do MCP |
| Variable | `IFOOD_TOKEN_URL` | URL HTTPS oficial de refresh OAuth Consumer |
| Variable | `IFOOD_OAUTH_REDIRECT_URI` | Redirect URI registrado pelo produto |
| Secret | `IFOOD_CLIENT_ID` | Client ID do OAuth Consumer |
| Secret | `IFOOD_CLIENT_SECRET` | Client secret do OAuth Consumer |
| Secret | `IFOOD_TOKEN_ENCRYPTION_KEY` | Mesma chave usada para criptografar o store |
| Secret | `IFOOD_TEST_SESSION_ID` | ID opaco da sessao do usuario de teste |
| Secret | `IFOOD_CI_TOKEN_STORE_B64` | SQLite criptografado, codificado em base64 |

O SQLite inicial deve ser gerado pelo fluxo OAuth do produto, usando uma conta
dedicada a testes e apenas os escopos necessarios. Se, excepcionalmente, a demo
usar uma conta de producao, mantenha apenas os casos de leitura fornecidos nesta
suite, execute manualmente uma unica vez e revogue a autorizacao depois de obter
as evidencias. O workflow restaura esse seed somente na primeira execucao.
Depois, o arquivo criptografado atualizado e mantido no cache privado do
Actions, preservando a rotacao do refresh token.

Nunca use o banco de producao, cookies de uma pessoa, um access token manual ou
o endpoint Merchant `authentication/v1.0/oauth/token` em automacoes recorrentes.
Se nao houver conta dedicada, a execucao manual deve ter autorizacao explicita
do responsavel pela conta. Se o cache expirar ou o refresh token for revogado,
autorize novamente a conta e substitua o secret `IFOOD_CI_TOKEN_STORE_B64`.

## Primeira execucao no GitHub

1. Faça commit da pasta `ifood-mcp-ci/` e do workflow na branch.
2. Abra o pull request e integre a branch em `main`.
3. Crie o environment e cadastre as variables e secrets da tabela acima.
4. Em **Actions > iFood MCP endpoint tests > Run workflow**, marque a opcao de
   execucao real e confirme.
5. Baixe `ifood-mcp-contract-report` e `ifood-mcp-live-report` como evidencia.
6. Se uma conta de producao foi usada, revogue a autorizacao e remova os secrets
   e caches do workflow depois de salvar a evidencia.
