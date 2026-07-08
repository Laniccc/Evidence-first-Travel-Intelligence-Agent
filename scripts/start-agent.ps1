<#
.SYNOPSIS
Start the Travel Intelligence Agent from the repository root.

.EXAMPLE
.\scripts\start-agent.ps1

.EXAMPLE
.\scripts\start-agent.ps1 -NoMcp -Port 8002

.EXAMPLE
.\scripts\start-agent.ps1 -AllowMcpFailure

.EXAMPLE
.\scripts\start-agent.ps1 -NoWeb

.EXAMPLE
.\scripts\start-agent.ps1 -WebOnly
#>

param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8001,
    [string]$WebHostName = "127.0.0.1",
    [int]$WebPort = 5173,
    [switch]$NoReload,
    [switch]$NoMcp,
    [switch]$NoWeb,
    [switch]$WebOnly,
    [switch]$WebViaGateway,
    [switch]$AllowMcpFailure,
    [switch]$AllowWebFailure,
    [switch]$IncludeWeatherMcp,
    [switch]$SkipCompileCheck,
    [switch]$SkipWebInstall
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$agentDir = Join-Path $repoRoot "apps\agent-python"
$webDir = Join-Path $repoRoot "apps\web"
$mainModule = Join-Path $agentDir "app\main.py"

function Test-CommandAvailable {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Test-HttpHealth {
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return @{ ok = $true; status = $r.StatusCode; body = $r.Content }
    } catch {
        return @{ ok = $false; status = $null; body = $_.Exception.Message }
    }
}

function Wait-HttpHealth {
    param(
        [string]$Url,
        [int]$TimeoutSec = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        $health = Test-HttpHealth $Url
        if ($health.ok) { return $health }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return Test-HttpHealth $Url
}

function Get-ListenerPid {
    param([int]$TargetPort)
    $line = netstat -ano | Select-String "127.0.0.1:$TargetPort\s+.*LISTENING" | Select-Object -First 1
    if (-not $line) { return $null }
    return [int](($line -split '\s+')[-1])
}

function Show-LogTail {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    Write-Host "[LOG] Last lines from $Path" -ForegroundColor DarkGray
    Get-Content $Path -Tail 30
}

function Start-WebDevServer {
    if ($NoWeb) {
        Write-Host "[--] Web startup skipped because -NoWeb was set." -ForegroundColor Yellow
        return
    }

    $packageJson = Join-Path $webDir "package.json"
    if (-not (Test-Path $packageJson)) {
        if ($AllowWebFailure) {
            Write-Host "[WARN] Web package.json not found, continuing because -AllowWebFailure was set: $packageJson" -ForegroundColor Yellow
            return
        }
        throw "Web package.json not found: $packageJson"
    }

    $webUrl = "http://$WebHostName`:$WebPort/"
    $webHealth = Test-HttpHealth $webUrl
    if ($webHealth.ok) {
        Write-Host "[OK] Web already running: $webUrl" -ForegroundColor Green
        return
    }

    $pidWeb = Get-ListenerPid $WebPort
    if ($pidWeb) {
        if ($AllowWebFailure) {
            Write-Host "[WARN] Web port $WebPort is occupied by PID $pidWeb but health failed; continuing because -AllowWebFailure was set." -ForegroundColor Yellow
            return
        }
        throw "Web port $WebPort is occupied by PID $pidWeb, but $webUrl did not respond. Stop that process or use -NoWeb."
    }

    $npmPath = Test-CommandAvailable @("npm.cmd", "npm")
    if (-not $npmPath) {
        if ($AllowWebFailure) {
            Write-Host "[WARN] npm not found; continuing because -AllowWebFailure was set." -ForegroundColor Yellow
            return
        }
        throw "npm was not found. Install Node.js LTS, then reopen PowerShell."
    }

    $nodeModules = Join-Path $webDir "node_modules"
    if (-not $SkipWebInstall -and -not (Test-Path $nodeModules)) {
        Write-Host "[..] apps/web/node_modules not found. Running npm install ..." -ForegroundColor Cyan
        Push-Location $webDir
        try {
            & $npmPath install
            if ($LASTEXITCODE -ne 0) {
                throw "npm install failed with exit code $LASTEXITCODE"
            }
        }
        finally {
            Pop-Location
        }
    }

    $logDir = Join-Path $repoRoot "logs\web"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $runnerPath = Join-Path $logDir "vite.runner.ps1"
    $stdoutPath = Join-Path $logDir "vite.out.log"
    $stderrPath = Join-Path $logDir "vite.err.log"

    $directAgentValue = if ($WebViaGateway) { "false" } else { "true" }
    $runner = @"
`$ErrorActionPreference = "Continue"
Set-Location "$webDir"
`$env:VITE_DIRECT_AGENT = "$directAgentValue"
`$env:VITE_AGENT_BASE_URL = "http://$HostName`:$Port"
& "$npmPath" run dev -- --host "$WebHostName" --port "$WebPort" --strictPort
"@
    Set-Content -Path $runnerPath -Value $runner -Encoding UTF8

    Write-Host "[..] Starting Web in background. Logs: $stdoutPath / $stderrPath" -ForegroundColor Cyan
    $webArgumentList = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
    Start-Process powershell `
        -WorkingDirectory $webDir `
        -WindowStyle Hidden `
        -ArgumentList $webArgumentList `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath | Out-Null

    $webHealth = Wait-HttpHealth $webUrl 45
    if ($webHealth.ok) {
        Write-Host "[OK] Web started: $webUrl" -ForegroundColor Green
        if ($WebViaGateway) {
            $gatewayHealth = Test-HttpHealth "http://127.0.0.1:8082/"
            if (-not $gatewayHealth.ok) {
                Write-Host "[WARN] api-java (:8082) is not reachable. The Web page can open, but queries may fail until the Gateway is started." -ForegroundColor Yellow
            }
        } else {
            Write-Host "[OK] Web query proxy mode: direct agent ($HostName`:$Port)" -ForegroundColor Green
        }
        return
    }

    Write-Host "[FAIL] Web did not become healthy: $($webHealth.body)" -ForegroundColor Red
    Show-LogTail $stdoutPath
    Show-LogTail $stderrPath
    if ($AllowWebFailure) {
        Write-Host "[WARN] Continuing because -AllowWebFailure was set." -ForegroundColor Yellow
        return
    }
    throw "Web failed to start within 45s. Check logs under $logDir."
}

if (-not (Test-Path $mainModule)) {
    throw "Cannot find Agent entrypoint: $mainModule"
}

if (-not (Test-Path (Join-Path $agentDir ".env")) -and (Test-Path (Join-Path $agentDir ".env.example"))) {
    Write-Host "[WARN] apps/agent-python/.env not found. Copying .env.example -> .env" -ForegroundColor Yellow
    Copy-Item (Join-Path $agentDir ".env.example") (Join-Path $agentDir ".env")
}

if ($WebOnly) {
    Start-WebDevServer
    return
}

if (-not $NoMcp) {
    $mcpScript = Join-Path $repoRoot "scripts\start-mcp-stack.ps1"
    if (Test-Path $mcpScript) {
        try {
            if ($IncludeWeatherMcp) {
                & $mcpScript -IncludeWeather
            } else {
                & $mcpScript
            }
        } catch {
            if (-not $AllowMcpFailure) {
                throw "MCP startup failed. Agent startup stopped because search evidence would be incomplete. Use -NoMcp for local-only debugging or -AllowMcpFailure to continue anyway. Details: $($_.Exception.Message)"
            }
            Write-Host "[WARN] MCP startup failed, continuing because -AllowMcpFailure was set: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } else {
        if (-not $AllowMcpFailure) {
            throw "MCP startup script not found: $mcpScript"
        }
        Write-Host "[WARN] MCP startup script not found, continuing because -AllowMcpFailure was set: $mcpScript" -ForegroundColor Yellow
    }
}

Start-WebDevServer

Push-Location $agentDir
try {
    $env:PYTHONPATH = (Get-Location).Path
    Write-Host "[OK] PYTHONPATH=$env:PYTHONPATH" -ForegroundColor Green

    if (-not $SkipCompileCheck) {
        Write-Host "[..] Checking Python imports with compileall ..." -ForegroundColor Cyan
        python -m compileall app -q
    }

    $uvicornArgs = @(
        "-m", "uvicorn",
        "app.main:app",
        "--host", $HostName,
        "--port", "$Port"
    )
    if (-not $NoReload) {
        $uvicornArgs += "--reload"
    }

    Write-Host "[OK] Starting Agent: http://$HostName`:$Port/agent/health" -ForegroundColor Green
    python @uvicornArgs
}
finally {
    Pop-Location
}
