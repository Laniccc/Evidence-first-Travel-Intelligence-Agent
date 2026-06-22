# Verify MCP upstream tool names against running daemons.
# Usage: .\scripts\verify-mcp-tools.ps1
# Requires: Python venv with agent-python deps; Node for stdio servers on first call.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$AgentDir = Join-Path $Root "apps\agent-python"

$npmCache = "$env:USERPROFILE\.npm-cache"
New-Item -ItemType Directory -Force -Path $npmCache | Out-Null
$env:npm_config_cache = $npmCache

Push-Location $AgentDir
try {
    if (Test-Path ".\.venv\Scripts\python.exe") {
        $py = ".\.venv\Scripts\python.exe"
    } else {
        $py = "python"
    }
    & $py (Join-Path $Root "scripts\verify_mcp_tools.py")
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
