[CmdletBinding()]
param(
    [string]$TunnelId
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$tunnelExe = Join-Path $projectRoot '.local-tools/tunnel-client/tunnel-client.exe'
if (-not (Test-Path -LiteralPath $tunnelExe)) {
    throw 'Cliente oficial ausente. Instale o tunnel-client da OpenAI em .local-tools/tunnel-client antes de executar.'
}

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 10
    if ($health.status -ne 'ok') { throw 'Health check sem status ok.' }
} catch {
    throw 'Inicie a API na porta 8000 e o servidor MCP na porta 8001 antes de conectar o ChatGPT.'
}

if (-not $TunnelId) {
    Write-Host 'Crie ou consulte o tunel em https://platform.openai.com/settings/organization/tunnels'
    $TunnelId = Read-Host 'ID do tunel (tunnel_...)'
}
if ($TunnelId -notmatch '^tunnel_[A-Za-z0-9_-]+$') {
    throw 'ID de tunel invalido. Use o ID fornecido pela plataforma OpenAI.'
}

$previousRuntimeKey = $env:CONTROL_PLANE_API_KEY
$secureKey = $null
try {
    if (-not $env:CONTROL_PLANE_API_KEY) {
        Write-Host 'Use uma chave runtime OpenAI com permissoes Tunnels Read + Use. Nao use uma chave de administrador.'
        $secureKey = Read-Host 'Chave runtime (entrada oculta, nao sera salva)' -AsSecureString
        if ($secureKey.Length -eq 0) { throw 'A chave runtime e obrigatoria.' }
        $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        try {
            $env:CONTROL_PLANE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
        }
    }

    $connectionArgs = @(
        '--control-plane.tunnel-id', $TunnelId,
        '--control-plane.api-key', 'env:CONTROL_PLANE_API_KEY',
        '--mcp.server-url', 'http://127.0.0.1:8001/mcp',
        '--health.listen-addr', '127.0.0.1:8002'
    )
    & $tunnelExe doctor @connectionArgs --explain
    if ($LASTEXITCODE -ne 0) {
        throw 'O diagnostico do tunel falhou. Confira as permissoes e a associacao entre o tunel e seu workspace ChatGPT.'
    }
    Write-Host 'No ChatGPT, adicione um MCP personalizado com conexao Tunnel e selecione este mesmo ID.'
    Write-Host 'Mantenha este terminal aberto. Painel local: http://127.0.0.1:8002/ui'
    & $tunnelExe run @connectionArgs
    if ($LASTEXITCODE -ne 0) { throw 'O cliente de tunel encerrou com erro.' }
} finally {
    $env:CONTROL_PLANE_API_KEY = $previousRuntimeKey
    $previousRuntimeKey = $null
    if ($secureKey) { $secureKey.Dispose() }
}
