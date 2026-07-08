<#
.SYNOPSIS
One-click startup for the Deep Research Agent Platform - all 3 services.

.DESCRIPTION
Starts MCP Search, Python Agent, Java Backend, and Vue Frontend in parallel.
All services run in background; logs written to logs/.
Press Ctrl+C to stop all services gracefully.

.EXAMPLE
.\scripts\start-all.ps1

.EXAMPLE
.\scripts\start-all.ps1 -NoFrontend

.EXAMPLE
.\scripts\start-all.ps1 -NoJava

.EXAMPLE
.\scripts\start-all.ps1 -AgentOnly
#>

param(
    [switch]$NoMcp,              # Skip MCP search stack
    [switch]$NoAgent,            # Skip Python agent
    [switch]$NoJava,             # Skip Java backend
    [switch]$NoFrontend,         # Skip Vue frontend
    [switch]$AgentOnly,          # Only start Python agent + MCP
    [switch]$SkipHealthCheck,    # Don't wait for health checks
    [int]$HealthTimeout = 120    # Max wait per service (seconds)
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

# ---- paths ----
$agentDir   = Join-Path $repoRoot "apps\agent-python"
$javaDir    = Join-Path $repoRoot "apps\api-java"
$webDir     = Join-Path $repoRoot "apps\web"
$logDir     = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# ---- ports ----
$MCP_PORT    = 3210
$AGENT_PORT  = 8001
$JAVA_PORT   = 8082
$WEB_PORT    = 3000

# ---- track background jobs for cleanup ----
$Script:bgJobs = @()
$Script:JavaGatewayExpected = $false

function Test-CommandAvailable {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Test-HttpHealth {
    param([string]$Url, [int]$TimeoutSec = 5)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return @{ ok = $true; status = $r.StatusCode; body = $r.Content }
    } catch {
        # Fallback: try localhost if 127.0.0.1 failed (Vite may bind IPv6)
        if ($Url -match '127\.0\.0\.1') {
            $altUrl = $Url -replace '127\.0\.0\.1', 'localhost'
            try {
                $r = Invoke-WebRequest -Uri $altUrl -UseBasicParsing -TimeoutSec $TimeoutSec
                return @{ ok = $true; status = $r.StatusCode; body = $r.Content }
            } catch { }
        }
        return @{ ok = $false; status = $null; body = $_.Exception.Message }
    }
}

function Wait-HttpHealth {
    param([string]$Url, [string]$Label, [int]$TimeoutSec)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $dots = 0
    do {
        $health = Test-HttpHealth $Url 3
        if ($health.ok) { return $health }
        $dots++
        if ($dots % 5 -eq 0) { Write-Host "   still waiting for $Label ..." -ForegroundColor DarkGray }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return Test-HttpHealth $Url 3
}

function Get-ListenerPid {
    param([int]$TargetPort)
    $line = netstat -ano | Select-String "127.0.0.1:$TargetPort\s+.*LISTENING" | Select-Object -First 1
    if (-not $line) { return $null }
    return [int](($line -split '\s+')[-1])
}

function Start-BackgroundProcess {
    param(
        [string]$Label,
        [string]$WorkingDir,
        [string]$ScriptBlock,
        [string]$LogName
    )
    $runnerPath = Join-Path $logDir "$LogName.runner.ps1"
    $stdoutPath = Join-Path $logDir "$LogName.out.log"
    $stderrPath = Join-Path $logDir "$LogName.err.log"

    Set-Content -Path $runnerPath -Value $ScriptBlock -Encoding UTF8

    Write-Host "[..] Starting $Label ..." -ForegroundColor Cyan
    Write-Host "     logs: $stdoutPath" -ForegroundColor DarkGray

    $proc = Start-Process powershell `
        -WorkingDirectory $WorkingDir `
        -WindowStyle Hidden `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`"" `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $Script:bgJobs += @{ Label = $Label; Proc = $proc; LogName = $LogName }

    return @{ stdout = $stdoutPath; stderr = $stderrPath; proc = $proc }
}

function Stop-AllServices {
    Write-Host ""
    Write-Host "=== Shutting down all services ===" -ForegroundColor Yellow
    foreach ($job in $Script:bgJobs) {
        $label = $job.Label
        $proc  = $job.Proc
        if ($proc -and -not $proc.HasExited) {
            Write-Host "[..] Stopping $label (PID $($proc.Id)) ..." -ForegroundColor Cyan
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $children = Get-WmiObject Win32_Process | Where-Object { $_.ParentProcessId -eq $proc.Id } | Select-Object -ExpandProperty ProcessId
            foreach ($cid in $children) {
                Stop-Process -Id $cid -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Get-ChildItem $logDir -Filter "*.runner.ps1" | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] All services stopped." -ForegroundColor Green
}

try {
    [Console]::TreatControlCAsInput = $false
} catch {}

# ─────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Deep Research Agent Platform                     " -ForegroundColor Cyan
Write-Host "  One-Click Startup                                " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$parts = @()
if (-not $NoMcp)                          { $parts += "MCP Search (:$MCP_PORT)" }
if (-not $NoAgent)                        { $parts += "Python Agent (:$AGENT_PORT)" }
if (-not $NoJava -and -not $AgentOnly)    { $parts += "Java Backend (:$JAVA_PORT)" }
if (-not $NoFrontend -and -not $AgentOnly){ $parts += "Vue Frontend (:$WEB_PORT)" }
Write-Host "Services: $($parts -join ' | ')" -ForegroundColor Green
Write-Host "Logs:     $logDir" -ForegroundColor DarkGray
Write-Host ""

# ─────────────────────────────────────────────────────────
# Phase 1: MCP Search Stack
# ─────────────────────────────────────────────────────────
if (-not $NoMcp) {
    Write-Host "--- MCP Search Stack ---" -ForegroundColor Cyan
    $mcpHealth = Test-HttpHealth "http://127.0.0.1:$MCP_PORT/health"
    if ($mcpHealth.ok) {
        Write-Host "[OK] MCP Search already running on :$MCP_PORT" -ForegroundColor Green
    } else {
        $mcpScript = Join-Path $repoRoot "scripts\start-mcp-stack.ps1"
        if (Test-Path $mcpScript) {
            & $mcpScript -StartupTimeoutSec ([Math]::Min($HealthTimeout, 120))
        } else {
            Write-Host "[WARN] MCP script not found, starting open-websearch directly..." -ForegroundColor Yellow
            $logs = Start-BackgroundProcess `
                -Label "MCP Search" `
                -WorkingDir $repoRoot `
                -LogName "mcp-search" `
                -ScriptBlock "`$env:DEFAULT_SEARCH_ENGINE='baidu'; `$env:ENABLE_CORS='true'; npx -y open-websearch@latest serve --port $MCP_PORT"
            if (-not $SkipHealthCheck) {
                $health = Wait-HttpHealth "http://127.0.0.1:$MCP_PORT/health" "MCP Search" $HealthTimeout
                if ($health.ok) { Write-Host "[OK] MCP Search started on :$MCP_PORT" -ForegroundColor Green }
                else { Write-Host "[FAIL] MCP Search health check timed out — check $($logs.stdout)" -ForegroundColor Red }
            }
        }
    }
}

# ─────────────────────────────────────────────────────────
# Phase 2: Python Agent
# ─────────────────────────────────────────────────────────
if (-not $NoAgent) {
    Write-Host "--- Python Agent ---" -ForegroundColor Cyan

    $agentHealth = Test-HttpHealth "http://127.0.0.1:$AGENT_PORT/agent/health"
    if ($agentHealth.ok) {
        Write-Host "[OK] Python Agent already running on :$AGENT_PORT" -ForegroundColor Green
    } else {
        $pid8001 = Get-ListenerPid $AGENT_PORT
        if ($pid8001) {
            Write-Host "[WARN] Port $AGENT_PORT occupied by PID $pid8001 but health check failed" -ForegroundColor Yellow
        }

        $envFile = Join-Path $agentDir ".env"
        if (-not (Test-Path $envFile) -and (Test-Path (Join-Path $agentDir ".env.example"))) {
            Write-Host "[WARN] .env not found, copying .env.example -> .env" -ForegroundColor Yellow
            Copy-Item (Join-Path $agentDir ".env.example") $envFile
        }

        $runnerBlock = @"
`$ErrorActionPreference = "Continue"
Set-Location "$agentDir"
`$env:PYTHONPATH = "$agentDir"
uvicorn app.main:app --host 127.0.0.1 --port $AGENT_PORT --reload
"@
        $logs = Start-BackgroundProcess `
            -Label "Python Agent" `
            -WorkingDir $agentDir `
            -LogName "python-agent" `
            -ScriptBlock $runnerBlock

        if (-not $SkipHealthCheck) {
            $health = Wait-HttpHealth "http://127.0.0.1:$AGENT_PORT/agent/health" "Python Agent" $HealthTimeout
            if ($health.ok) {
                Write-Host "[OK] Python Agent started: http://127.0.0.1:$AGENT_PORT/agent/health" -ForegroundColor Green
            } else {
                Write-Host "[FAIL] Python Agent health check failed — check $($logs.stdout)" -ForegroundColor Red
            }
        } else {
            Write-Host "[OK] Python Agent starting (health check skipped)" -ForegroundColor Green
        }
    }
}

# ─────────────────────────────────────────────────────────
# Phase 3: Java Backend
# ─────────────────────────────────────────────────────────
if (-not $NoJava -and -not $AgentOnly) {
    Write-Host "--- Java Backend ---" -ForegroundColor Cyan

    $javaHealth = Test-HttpHealth "http://127.0.0.1:$JAVA_PORT/api/health"
    if ($javaHealth.ok) {
        Write-Host "[OK] Java Backend already running on :$JAVA_PORT" -ForegroundColor Green
        $Script:JavaGatewayExpected = $true
    } else {
        $mvnCmd = Test-CommandAvailable @("mvn.cmd", "mvn")
        if (-not $mvnCmd) {
            Write-Host "[WARN] Maven not found - skipping Java backend" -ForegroundColor Yellow
            Write-Host "       Install Maven or use -NoJava to suppress this warning" -ForegroundColor DarkGray
        } elseif (-not (Test-Path (Join-Path $javaDir "pom.xml"))) {
            Write-Host "[WARN] pom.xml not found - skipping Java backend" -ForegroundColor Yellow
        } else {
            $runnerBlock = @"
`$ErrorActionPreference = "Continue"
Set-Location "$javaDir"
mvn spring-boot:run -q
"@
            $logs = Start-BackgroundProcess `
                -Label "Java Backend" `
                -WorkingDir $javaDir `
                -LogName "java-backend" `
                -ScriptBlock $runnerBlock
            $Script:JavaGatewayExpected = $true

            if (-not $SkipHealthCheck) {
                $health = Wait-HttpHealth "http://127.0.0.1:$JAVA_PORT/api/health" "Java Backend" $HealthTimeout
                if ($health.ok) {
                    Write-Host "[OK] Java Backend started: http://127.0.0.1:$JAVA_PORT/api/health" -ForegroundColor Green
                } else {
                    Write-Host "[WARN] Java Backend still starting (first run may take 60-120s)" -ForegroundColor Yellow
                    Write-Host "       Check logs: $($logs.stdout)" -ForegroundColor DarkGray
                }
            } else {
                Write-Host "[OK] Java Backend starting (health check skipped)" -ForegroundColor Green
            }
        }
    }
}

# ─────────────────────────────────────────────────────────
# Phase 4: Vue Frontend
# ─────────────────────────────────────────────────────────
if (-not $NoFrontend -and -not $AgentOnly) {
    Write-Host "--- Vue Frontend ---" -ForegroundColor Cyan

    $webHealth = Test-HttpHealth "http://127.0.0.1:$WEB_PORT"
    if ($webHealth.ok) {
        Write-Host "[OK] Vue Frontend already running on :$WEB_PORT" -ForegroundColor Green
    } else {
        $npmPath = Test-CommandAvailable @("npm.cmd", "npm")
        if (-not $npmPath) {
            Write-Host "[WARN] npm not found - skipping Vue frontend" -ForegroundColor Yellow
        } elseif (-not (Test-Path (Join-Path $webDir "package.json"))) {
            Write-Host "[WARN] package.json not found - skipping Vue frontend" -ForegroundColor Yellow
        } else {
            $nodeModules = Join-Path $webDir "node_modules"
            if (-not (Test-Path $nodeModules)) {
                Write-Host "[..] Installing npm dependencies ..." -ForegroundColor Cyan
                Push-Location $webDir
                try {
                    & $npmPath install
                    if ($LASTEXITCODE -ne 0) { throw "npm install failed (exit $LASTEXITCODE)" }
                } finally { Pop-Location }
            }

            $directAgentValue = if ((-not $Script:JavaGatewayExpected) -and (-not $NoAgent)) { "true" } else { "false" }
            $runnerBlock = @"
`$ErrorActionPreference = "Continue"
Set-Location "$webDir"
`$env:VITE_DIRECT_AGENT = "$directAgentValue"
`$env:VITE_AGENT_BASE_URL = "http://127.0.0.1:$AGENT_PORT"
`$env:VITE_API_BASE_URL = "http://127.0.0.1:$JAVA_PORT"
npx vite --port $WEB_PORT --host 127.0.0.1
"@
            $logs = Start-BackgroundProcess `
                -Label "Vue Frontend" `
                -WorkingDir $webDir `
                -LogName "vue-frontend" `
                -ScriptBlock $runnerBlock

            if (-not $SkipHealthCheck) {
                $health = Wait-HttpHealth "http://127.0.0.1:$WEB_PORT" "Vue Frontend" $HealthTimeout
                if ($health.ok) {
                    Write-Host "[OK] Vue Frontend started: http://127.0.0.1:$WEB_PORT" -ForegroundColor Green
                } else {
                    Write-Host "[WARN] Vue Frontend still starting - check $($logs.stdout)" -ForegroundColor Yellow
                }
            } else {
                Write-Host "[OK] Vue Frontend starting (health check skipped)" -ForegroundColor Green
            }
        }
    }
}

# ─────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Startup Complete                                 " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

if (-not $NoAgent) {
    $h = Test-HttpHealth "http://127.0.0.1:$AGENT_PORT/agent/health"
    $status = if ($h.ok) { "[OK]" } else { "[--]" }
    Write-Host "  $status  Python Agent    http://127.0.0.1:$AGENT_PORT/agent/health" -ForegroundColor $(if ($h.ok) { "Green" } else { "Yellow" })
}
if (-not $NoJava -and -not $AgentOnly) {
    $h = Test-HttpHealth "http://127.0.0.1:$JAVA_PORT/api/health"
    $status = if ($h.ok) { "[OK]" } else { "[--]" }
    Write-Host "  $status  Java Backend    http://127.0.0.1:$JAVA_PORT/api/health" -ForegroundColor $(if ($h.ok) { "Green" } else { "Yellow" })
}
if (-not $NoFrontend -and -not $AgentOnly) {
    $h = Test-HttpHealth "http://127.0.0.1:$WEB_PORT"
    $status = if ($h.ok) { "[OK]" } else { "[--]" }
    Write-Host "  $status  Vue Frontend    http://127.0.0.1:$WEB_PORT" -ForegroundColor $(if ($h.ok) { "Green" } else { "Yellow" })
}

Write-Host ""
Write-Host "Press Ctrl+C to stop all services and exit." -ForegroundColor Yellow
Write-Host ""

# ─────────────────────────────────────────────────────────
# Keep alive + crash monitor
# ─────────────────────────────────────────────────────────
try {
    while ($true) {
        Start-Sleep -Seconds 2
        foreach ($job in $Script:bgJobs) {
            if ($job.Proc.HasExited) {
                $code = $job.Proc.ExitCode
                if ($code -ne 0) {
                    Write-Host "[WARN] $($job.Label) exited with code $code" -ForegroundColor Yellow
                    $logFile = Join-Path $logDir "$($job.LogName).out.log"
                    Write-Host "       Check: $logFile" -ForegroundColor DarkGray
                }
            }
        }
    }
} finally {
    Stop-AllServices
}
