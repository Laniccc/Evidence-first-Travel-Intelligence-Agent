# 一键启动需要「单独挂起」的 MCP HTTP 服务（stdio 类由 Agent 在首次调用时自动 npx 拉起）
# 用法:
#   .\scripts\start-mcp-stack.ps1
#   .\scripts\start-mcp-stack.ps1 -IncludeWeather
#   .\scripts\start-mcp-stack.ps1 -StatusOnly

param(
    [switch]$IncludeWeather,
    [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"
$npmCache = "$env:USERPROFILE\.npm-cache"
New-Item -ItemType Directory -Force -Path $npmCache | Out-Null
$env:npm_config_cache = $npmCache

function Test-McpHealth {
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return @{ ok = $true; body = $r.Content }
    } catch {
        return @{ ok = $false; body = $_.Exception.Message }
    }
}

function Get-ListenerPid {
    param([int]$Port)
    $line = netstat -ano | Select-String "127.0.0.1:$Port\s+.*LISTENING"
    if (-not $line) { return $null }
    return [int](($line -split '\s+')[-1])
}

function Start-DaemonWindow {
    param(
        [string]$Title,
        [string]$Command
    )
    Write-Host "Starting $Title ..."
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "`$env:npm_config_cache='$npmCache'; $Command"
    ) | Out-Null
}

Write-Host "=== MCP HTTP stack ===" -ForegroundColor Cyan

# --- open-webSearch :3210 ---
$searchHealth = Test-McpHealth "http://127.0.0.1:3210/health"
if ($searchHealth.ok) {
    Write-Host "[OK] open-webSearch already running on :3210" -ForegroundColor Green
} elseif ($StatusOnly) {
    Write-Host "[--] open-webSearch not running on :3210" -ForegroundColor Yellow
} else {
    $pid3210 = Get-ListenerPid 3210
    if ($pid3210) {
        Write-Host "[WARN] Port 3210 in use (PID $pid3210) but health failed — stopping stale process." -ForegroundColor Yellow
        Stop-Process -Id $pid3210 -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    Start-DaemonWindow "open-webSearch" @"
`$env:DEFAULT_SEARCH_ENGINE='baidu'; `$env:ENABLE_CORS='true'; `$env:USE_PROXY='false'; npx -y open-websearch@latest serve
"@
        Start-Sleep -Seconds 8
        $searchHealth = Test-McpHealth "http://127.0.0.1:3210/health"
        if ($searchHealth.ok) {
            Write-Host "[OK] open-webSearch started" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] open-webSearch did not become healthy: $($searchHealth.body)" -ForegroundColor Red
        }
}

# --- Open-Meteo :3000 (optional) ---
if ($IncludeWeather) {
    $meteoHealth = Test-McpHealth "http://127.0.0.1:3000/mcp"
    if ($meteoHealth.ok) {
        Write-Host "[OK] Open-Meteo MCP already reachable on :3000" -ForegroundColor Green
    } elseif ($StatusOnly) {
        Write-Host "[--] Open-Meteo not running on :3000" -ForegroundColor Yellow
    } else {
        Start-DaemonWindow "Open-Meteo MCP" @"
`$env:TRANSPORT='http'; `$env:PORT='3000'; npx -y open-meteo-mcp-server
"@
        Write-Host "[..] Open-Meteo starting in new window (may take a minute)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "stdio MCP (browser/osm/wikipedia/wikidata/sqlite): no separate start — Agent calls npx/uvx on first use." -ForegroundColor DarkGray
Write-Host "Requires Node.js (node/npx). Install: https://nodejs.org/ (LTS)." -ForegroundColor DarkGray
Write-Host "Then restart agent-python (uvicorn) if you changed .env." -ForegroundColor DarkGray
