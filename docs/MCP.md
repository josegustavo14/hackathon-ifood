# MCP do iFood Chef AI

Servidor MCP local que conecta clientes e agentes à **nossa API REST FastAPI**. Não é o MCP oficial do iFood e não implementa autenticação, checkout ou integração comercial do iFood. O frontend continua consumindo REST normalmente.

```text
Cliente MCP → stdio ou Streamable HTTP → app.mcp_server → FastAPI → serviços existentes
```

A implementação usa o [SDK oficial Python MCP, linha v1](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x), limitada a `>=1.28,<2` em um arquivo de dependências opcional. Versão usada na validação: **1.30.0**, Python 3.13. Os contratos de entrada/saída são os modelos Pydantic do backend, incluindo o contrato atual `NutritionCalculation`.

## Instalação e API

Requisitos: Python 3.11+ e acesso ao registro de pacotes na primeira instalação. No PowerShell, a partir da raiz do repositório:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt
$env:MOCK_MODE = 'true'
$env:NUTRITION_PROVIDER = 'mock'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Se `.venv` já existir, reutilize-a e apenas instale as dependências. Mantenha a API rodando. O frontend não precisa estar aberto para usar MCP. Confira a API em `http://127.0.0.1:8000/health`.

## Teste rápido: stdio

Em um segundo terminal, na pasta `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server.smoke
```

Esse comando abre o servidor como subprocesso, realiza o handshake MCP e testa descoberta, receita, nutrição, compras, produtos, proposta, chat, PDF, recurso e prompt. Confirma que aplicar sem autorização é bloqueado. **Não aplica o carrinho**, nem mesmo o mock.

Resultado esperado (demais campos foram omitidos aqui):

```json
{
  "ok": true,
  "transport": "stdio",
  "tools": 10,
  "subtotal": "70.90",
  "confirmation_without_consent": "blocked",
  "cart_applied": false
}
```

O teste exige backend em modo mock e a receita demonstrativa disponível. Para API em outra origem, acrescente `--api-url http://127.0.0.1:OUTRA_PORTA`. O processo retorna código 1 se falhar.

Para iniciar só o servidor stdio:

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server
```

Ele fica aguardando mensagens JSON-RPC do cliente; isso não abre página no navegador. `stdout` é reservado ao protocolo; logs vão para `stderr`. Use Ctrl+C para encerrar um processo iniciado manualmente.

## Conexão por HTTP e Inspector

Com a API rodando, em outro terminal na pasta `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server --transport streamable-http --port 8001
```

Endpoint: **`http://127.0.0.1:8001/mcp`**. O servidor fica restrito a `127.0.0.1`, usa HTTP stateless e respostas JSON. Não é uma página HTML; abrir a URL diretamente no navegador não testa o handshake.

Em um terceiro terminal, na pasta `backend`, teste:

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server.smoke --url http://127.0.0.1:8001/mcp
```

Para testar manualmente pelo [MCP Inspector oficial](https://github.com/modelcontextprotocol/inspector), com Node.js compatível com a versão instalada do Inspector:

```powershell
npx.cmd -y @modelcontextprotocol/inspector
```

Abra o endereço fornecido pelo Inspector, escolha **Streamable HTTP**, informe `http://127.0.0.1:8001/mcp` e conecte. Em **Tools**, liste as ferramentas e execute `health` com `{}` e `search_recipes` com `{"query":"lasanha"}`.

Para o fluxo completo, use o conteúdo dos resultados estruturados em sequência:

1. `search_recipes`: `{"query":"lasanha"}`. A lista fica no campo `result` da resposta estruturada.
2. `get_recipe`: `{"recipe_id":"mock-lasagna-bolognese"}`.
3. `calculate_nutrition`: `{"recipe_id":"mock-lasagna-bolognese","servings":4}`. Confira `total`, `per_serving`, `status` e `warnings`.
4. `calculate_shopping`: `{"recipe_id":"mock-lasagna-bolognese","servings":4,"pantry_ingredient_ids":[]}`.
5. `match_products`: `{"shopping_list": <objeto do passo 4>}`.
6. `preview_cart`: `{"shopping_list": <objeto do passo 5>}`. Confira produtos, embalagens e subtotal.
7. `apply_cart`: `{"proposal": <objeto do passo 6>,"confirmed":false}` deve produzir um erro MCP sem chamar `/cart/apply`.
8. Apenas após revisar e autorizar, envie a mesma proposta com `"confirmed":true`. No modo mock, o resultado contém `mock_only:true`, status `applied` e mensagem de simulação.

Os trechos com `<objeto ...>` são instruções para colar o JSON correspondente; não são JSON literal válido.

## Configuração de um cliente MCP por stdio

### ChatGPT com servidor local

O cliente oficial Secure MCP Tunnel foi instalado neste computador em `.local-tools/tunnel-client/tunnel-client.exe`, com verificação do SHA256 publicado na release oficial. Os binários estão ignorados pelo Git; o checkout em outro computador exige instalar o cliente novamente.

Com a API na porta 8000 e o MCP na porta 8001, execute a partir da raiz:

```powershell
powershell.exe -NoProfile -File .\dev\connect-chatgpt.ps1
```

O script pede o `tunnel_id` criado em https://platform.openai.com/settings/organization/tunnels e uma chave runtime com permissões **Tunnels Read + Use**. A chave é recebida como entrada oculta, enviada ao cliente por variável de ambiente apenas durante a execução e não é gravada em arquivo. Não informe uma chave de administrador. Se a política local bloquear scripts, execute os comandos do cliente oficial manualmente em vez de alterar a política do computador.

Depois do diagnóstico bem-sucedido, o cliente fica rodando neste terminal. No ChatGPT, adicione um MCP personalizado e selecione conexão **Tunnel**, usando o mesmo ID e a associação ao workspace correto. O painel local fica em `http://127.0.0.1:8002/ui`. A conexão ao ChatGPT só está concluída depois que uma ferramenta, como `health`, for chamada por ele com sucesso. Instalar o binário e testar o MCP local não estabelece essa conexão de conta.

Referência: [Secure MCP Tunnel — documentação oficial](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

### Exemplo genérico de cliente stdio

Exemplo genérico para clientes que aceitam `mcpServers` em JSON. Ajuste o diretório absoluto para o local do seu checkout. A localização desse arquivo depende do cliente.

```json
{
  "mcpServers": {
    "ifood-chef-ai": {
      "command": "C:/CAMINHO/hackathon-ifood/backend/.venv/Scripts/python.exe",
      "args": ["-m", "app.mcp_server"],
      "cwd": "C:/CAMINHO/hackathon-ifood/backend",
      "env": {
        "CHEF_API_URL": "http://127.0.0.1:8000",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

Use caminhos com `/` ou escape barras como `\\` em JSON. O cliente inicia o processo stdio; não inicie uma cópia manual para esse cliente. A API precisa estar acessível à máquina onde o processo MCP roda. Esta configuração é apenas um exemplo; nenhum cliente ou plugin foi instalado/configurado automaticamente.

## Ferramentas e contratos

| Ferramenta | Entrada principal | Saída |
|---|---|---|
| `health` | nenhuma | estado da API e `mock_mode` |
| `search_recipes` | `query` | `Recipe[]`, em `result` |
| `get_recipe` | `recipe_id` | `Recipe` |
| `calculate_nutrition` | `recipe_id`, `servings`, `include_optional` | `NutritionCalculation` |
| `calculate_shopping` | `recipe_id`, `servings`, `pantry_ingredient_ids` | `ShoppingList` pendente, sem os IDs excluídos |
| `match_products` | `shopping_list`, `merchant_id` opcional | `ShoppingList` com correspondências |
| `preview_cart` | `shopping_list` | `CartProposal`, sem aplicação |
| `apply_cart` | `proposal`, `confirmed` booleano estrito, padrão `false` | `CartApplyResponse` |
| `chat` | `message`, `session_id`, `context` opcionais | `AgentResponse` |
| `parse_meal_plan` | `filename`, `pdf_base64` | `MealPlan` |

Recurso: **`chef://guide`**, com fluxo, contratos e limitações. Prompt: **`prepare_recipe`**, com `dish` e `servings`.

Porções: inteiros de 1 a 1000. IDs de receita: letras ASCII, números, `_` e `-`, até 200 caracteres. IDs desconhecidos da despensa geram erro para evitar exclusões silenciosas por digitação. Dinheiro e quantidades preservam a serialização decimal do backend. O SDK também disponibiliza conteúdo textual para clientes sem suporte a resultados estruturados.

Para testar o PDF, gere o base64 localmente e envie os valores como argumentos da ferramenta:

```powershell
$pdfBytes = [System.IO.File]::ReadAllBytes((Resolve-Path '.\plano.pdf'))
$pdfBase64 = [Convert]::ToBase64String($pdfBytes)
@{ filename = 'plano.pdf'; pdf_base64 = $pdfBase64 } | ConvertTo-Json -Compress
```

O MCP aceita apenas nome simples `.pdf`, base64 válido, assinatura `%PDF-` e no máximo 10 MiB decodificados. Não aceita caminhos locais nem busca URLs de arquivo. O backend extrai o texto do PDF e interpreta o plano com o provedor configurado; PDFs inválidos ou sem texto retornam erro. O base64 completo pode exceder os limites de contexto de alguns clientes; prefira PDFs pequenos para testes manuais.

## Configuração e limites

- `CHEF_API_URL`: origem da API, padrão `http://127.0.0.1:8000`. Não acrescente `/api/v1`. Também aceita `--api-url`, com prioridade sobre a variável.
- `--transport`: `stdio` por padrão ou `streamable-http`.
- `--port`: porta MCP HTTP, padrão 8001. O backend usa outra porta (8000).
- Timeout HTTP de 30 segundos, sem repetição automática de requisições, redirecionamentos ou proxies herdados do ambiente.
- O servidor lê variáveis do processo; não carrega automaticamente o `.env` da raiz. `MOCK_MODE` e `NUTRITION_PROVIDER` são configurações do processo FastAPI.
- Falhas HTTP, indisponibilidade, timeout e respostas fora do contrato se tornam erros de ferramenta MCP (`isError:true`). Logs internos não são incluídos nas respostas de conexão/timeout.
- O serviço HTTP é local e **não tem autenticação própria**. Para publicar externamente, é necessário implementar autenticação/autorização MCP e políticas por usuário. Não publicar essa configuração local por túnel ou bind público.
- `confirmed:true` deve ser enviado pelo cliente somente após consentimento humano. É uma validação de intenção, não uma prova criptográfica nem um sistema de autenticação. A ferramenta é marcada como operação que altera estado para permitir confirmação pelo cliente MCP.
- O MCP não adiciona persistência nem uma sessão comercial. Uma proposta `applied` é rejeitada; o backend mock não mantém um registro durável para impedir o reenvio de uma cópia antiga `ready_for_review`. Integração comercial futura exige idempotência e autorização no backend.

## Testes automatizados e revisão

Na pasta `backend`, após instalar `requirements-mcp.txt`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_mcp.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Validação realizada nesta entrega:

- **13 testes MCP passando**: handshake/descoberta, schemas, recurso/prompt, fluxo completo com decimais, nutrição atual, porções/despensa, confirmação ausente/falsa/tipo incorreto, aplicação mock, proposta já aplicada, chat/sessão, PDF inválido, erros HTTP, timeout, conexão e contrato inválido.
- **111 testes totais do backend passando**. Há um aviso de depreciação já emitido pela combinação Starlette/httpx do projeto.
- O cliente smoke usa um PDF válido com texto para exercitar o parser atual. Execute os comandos stdio e HTTP acima com a API em modo mock; os smoke tests não aplicam propostas.
- O adaptador MCP reutiliza os contratos da API integrada. A interface mantém os modais da main e os fluxos de seleção de produtos, nutrição e checkout da integracao-final.

Os testes MCP são opcionais e ficam ignorados quando o SDK não está instalado. A suíte existente continua executável com `requirements.txt`.

## Solução de problemas

- **`No module named mcp`**: use o Python de `.venv` e instale `requirements-mcp.txt`.
- **`No module named app`**: execute a partir de `backend` ou ajuste `cwd` no cliente.
- **Erro de conexão à API**: confira `/health` e a origem `CHEF_API_URL`; MCP não inicia o FastAPI automaticamente.
- **Porta ocupada**: use outra porta em `--port` e atualize a URL do cliente. API e MCP precisam de portas diferentes.
- **HTTP 503**: o backend está com integrações ainda indisponíveis, por exemplo nutrição USDA sem chave configurada. Para a demonstração, inicie o backend com os valores do primeiro comando.
- **Servidor stdio sem mostrar uma página**: comportamento normal; teste pelo cliente smoke ou por um cliente MCP.
- **Alterou o código**: reinicie o processo MCP e reconecte o cliente; o comando MCP não usa autoreload.
