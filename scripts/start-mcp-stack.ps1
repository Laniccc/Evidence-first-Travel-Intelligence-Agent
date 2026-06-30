<#
.SYNOPSIS
Start HTTP MCP services required by the Agent.

.EXAMPLE
.\scripts\start-mcp-stack.ps1

.EXAMPLE
.\scripts\start-mcp-stack.ps1 -StatusOnly

.EXAMPLE
.\scripts\start-mcp-stack.ps1 -IncludeWeather
#>

param(
    [switch]$IncludeWeather,
    [switch]$StatusOnly,
    [switch]$KillStalePort,
    [int]$StartupTimeoutSec = 45
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$npmCache = "$env:USERPROFILE\.npm-cache"
$logDir = Join-Path $repoRoot "logs\mcp"
New-Item -ItemType Directory -Force -Path $npmCache | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$env:npm_config_cache = $npmCache

function Test-CommandAvailable {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Test-McpHealth {
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return @{ ok = $true; body = $r.Content }
    } catch {
        return @{ ok = $false; body = $_.Exception.Message }
    }
}

function Wait-McpHealth {
    param(
        [string]$Url,
        [int]$TimeoutSec
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        $health = Test-McpHealth $Url
        if ($health.ok) { return $health }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return Test-McpHealth $Url
}

function Get-ListenerPid {
    param([int]$Port)
    $line = netstat -ano | Select-String "127.0.0.1:$Port\s+.*LISTENING" | Select-Object -First 1
    if (-not $line) { return $null }
    return [int](($line -split '\s+')[-1])
}

function Read-AgentEnvValue {
    param([string]$Key, [string]$Default = "")
    $envVal = [Environment]::GetEnvironmentVariable($Key)
    if ($envVal) { return $envVal }
    $envFile = Join-Path $repoRoot "apps\agent-python\.env"
    if (-not (Test-Path $envFile)) { return $Default }
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
    if (-not $line) { return $Default }
    return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

function Show-LogTail {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    Write-Host "[LOG] Last lines from $Path" -ForegroundColor DarkGray
    Get-Content $Path -Tail 30
}

function Start-McpDaemon {
    param(
        [string]$Name,
        [string]$Command
    )
    $runnerPath = Join-Path $logDir "$Name.runner.ps1"
    $stdoutPath = Join-Path $logDir "$Name.out.log"
    $stderrPath = Join-Path $logDir "$Name.err.log"

    $runner = @"
`$ErrorActionPreference = "Continue"
`$env:npm_config_cache = "$npmCache"
$Command
"@
    Set-Content -Path $runnerPath -Value $runner -Encoding UTF8

    Write-Host "[..] Starting $Name in background. Logs: $stdoutPath / $stderrPath" -ForegroundColor Cyan
    $argumentList = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
    Start-Process powershell `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -ArgumentList $argumentList `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath | Out-Null

    return @{ stdout = $stdoutPath; stderr = $stderrPath }
}

Write-Host "=== MCP HTTP stack ===" -ForegroundColor Cyan

$npxPath = Test-CommandAvailable @("npx.cmd", "npx")
if (-not $npxPath) {
    throw "npx was not found. Install Node.js LTS, then reopen PowerShell. If npm has EPERM issues, run: `$env:npm_config_cache=`"`$env:USERPROFILE\.npm-cache`""
}
Write-Host "[OK] npx found: $npxPath" -ForegroundColor Green

$searchEngine = Read-AgentEnvValue "MCP_SEARCH_DEFAULT_ENGINE" "baidu"
$searchUseProxy = (Read-AgentEnvValue "MCP_SEARCH_USE_PROXY" "false").ToLower() -in @("true", "1", "yes")
$searchProxyUrl = Read-AgentEnvValue "MCP_SEARCH_PROXY_URL" "http://127.0.0.1:7890"
$proxyEnv = if ($searchUseProxy) {
    "`$env:USE_PROXY='true'; `$env:PROXY_URL='$searchProxyUrl';"
} else {
    "`$env:USE_PROXY='false';"
}

# open-webSearch :3210
$searchHealth = Test-McpHealth "http://127.0.0.1:3210/health"
if ($searchHealth.ok) {
    Write-Host "[OK] open-webSearch already running on :3210" -ForegroundColor Green
} elseif ($StatusOnly) {
    Write-Host "[--] open-webSearch not running on :3210" -ForegroundColor Yellow
} else {
    $pid3210 = Get-ListenerPid 3210
    if ($pid3210) {
        if ($KillStalePort) {
            Write-Host "[WARN] Port 3210 is occupied by PID $pid3210 and health failed. Stopping it because -KillStalePort was set." -ForegroundColor Yellow
            Stop-Process -Id $pid3210 -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
        } else {
            throw "Port 3210 is occupied by PID $pid3210, but http://127.0.0.1:3210/health failed. Stop that process or rerun with -KillStalePort."
        }
    }

    $logs = Start-McpDaemon "open-websearch" @"
`$env:DEFAULT_SEARCH_ENGINE='$searchEngine'
`$env:ENABLE_CORS='true'
$proxyEnv
npx -y open-websearch@latest serve
"@
    $searchHealth = Wait-McpHealth "http://127.0.0.1:3210/health" $StartupTimeoutSec
    if ($searchHealth.ok) {
        Write-Host "[OK] open-webSearch started on :3210" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] open-webSearch did not become healthy: $($searchHealth.body)" -ForegroundColor Red
        Show-LogTail $logs.stdout
        Show-LogTail $logs.stderr
        throw "open-webSearch failed to start within ${StartupTimeoutSec}s. Check logs under $logDir. Common causes: first-run npm download blocked, proxy not configured, or package install failure."
    }
}

# Open-Meteo :3000, optional
if ($IncludeWeather) {
    $meteoHealth = Test-McpHealth "http://127.0.0.1:3000/mcp"
    if ($meteoHealth.ok) {
        Write-Host "[OK] Open-Meteo MCP already reachable on :3000" -ForegroundColor Green
    } elseif ($StatusOnly) {
        Write-Host "[--] Open-Meteo not running on :3000" -ForegroundColor Yellow
    } else {
        $logs = Start-McpDaemon "open-meteo" @"
`$env:TRANSPORT='http'
`$env:PORT='3000'
npx -y open-meteo-mcp-server
"@
        $meteoHealth = Wait-McpHealth "http://127.0.0.1:3000/mcp" $StartupTimeoutSec
        if ($meteoHealth.ok) {
            Write-Host "[OK] Open-Meteo MCP started on :3000" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Open-Meteo MCP did not become healthy: $($meteoHealth.body)" -ForegroundColor Red
            Show-LogTail $logs.stdout
            Show-LogTail $logs.stderr
            throw "Open-Meteo MCP failed to start within ${StartupTimeoutSec}s. Check logs under $logDir."
        }
    }
}

Write-Host ""
Write-Host "stdio MCP (browser/osm/wikipedia/wikidata/sqlite): no separate start; Agent calls npx/uvx on first use." -ForegroundColor DarkGray
Write-Host "If you changed .env, restart the Agent." -ForegroundColor DarkGray
