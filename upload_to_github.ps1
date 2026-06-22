# Upload project to GitHub: https://github.com/Laniccc/Evidence-first-Travel-Intelligence-Agent.git
# Usage:
#   .\upload_to_github.ps1
#   .\upload_to_github.ps1 -Message "feat: travel agent MVP"
#   .\upload_to_github.ps1 -DryRun

param(
    [string]$RemoteUrl = "https://github.com/Laniccc/Evidence-first-Travel-Intelligence-Agent.git",
    [string]$Branch = "main",
    [string]$Message = "init: Evidence-first Travel Intelligence Agent MVP",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Set-Location $ProjectRoot
Write-Host "Project: $ProjectRoot" -ForegroundColor Cyan

if (Test-Path "backend\.env") {
    Write-Warning "backend\.env exists locally and is ignored by git (will NOT be uploaded)."
}
if (Test-Path ".env") {
    Write-Warning ".env exists locally and is ignored by git (will NOT be uploaded)."
}

function Show-GitHub403Help {
    Write-Host ""
    Write-Host '=== GitHub 403: credential invalid or insufficient permission ===' -ForegroundColor Red
    Write-Host 'Git user is Laniccc, but cached Windows token cannot push to this repo.'
    Write-Host ""
    Write-Host 'Fix (HTTPS + Personal Access Token):'
    Write-Host '  1. Open https://github.com/settings/tokens -> Generate new token (classic)'
    Write-Host '  2. Enable repo scope, copy the token (shown once)'
    Write-Host '  3. Clear old credential and push again:'
    Write-Host '       cmdkey /delete:LegacyGeneric:target=git:https://github.com'
    Write-Host '       git push -u origin main'
    Write-Host '  4. When prompted: username Laniccc, password = PAT (not GitHub login password)'
    Write-Host ""
    Write-Host 'Or run: .\fix_github_auth.ps1' -ForegroundColor Yellow
    Write-Host ""
}

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitCommand)
    $cmd = "git " + ($GitCommand -join " ")
    if ($DryRun) {
        Write-Host ('[dry-run] ' + $cmd) -ForegroundColor DarkGray
        return
    }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & git @GitCommand 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
    $output | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            Write-Host $_.ToString()
        } else {
            Write-Host $_
        }
    }
    if ($exitCode -ne 0) {
        $text = ($output | Out-String)
        if ($text -match "403|Permission denied|Authentication failed") {
            Show-GitHub403Help
        }
        throw "git failed: $cmd (exit $exitCode)"
    }
}

function Invoke-GitCommit {
    param([string]$CommitMessage)
    if ($DryRun) {
        Write-Host ('[dry-run] git commit -m ' + $CommitMessage) -ForegroundColor DarkGray
        return
    }
    $msgFile = Join-Path $env:TEMP ("git-commit-msg-{0}.txt" -f [guid]::NewGuid().ToString("N"))
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($msgFile, $CommitMessage, $utf8NoBom)
        Invoke-Git commit -F $msgFile
    } finally {
        if (Test-Path $msgFile) {
            Remove-Item $msgFile -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-ForbiddenStagedPaths {
    param([string[]]$Paths)
    $blocked = @(
        @{ Pattern = '(^|/|\\)\.env$'; Label = '.env (secrets)' }
        @{ Pattern = '(^|/|\\)backend[/\\]\.env$'; Label = 'backend/.env (secrets)' }
        @{ Pattern = '(^|/|\\)\.npm-cache(/|\\|$)'; Label = '.npm-cache (npm download cache)' }
        @{ Pattern = '(^|/|\\)node_modules(/|\\|$)'; Label = 'node_modules' }
        @{ Pattern = '(^|/|\\)\.venv(/|\\|$)'; Label = '.venv (Python virtualenv)' }
        @{ Pattern = '(^|/|\\)target(/|\\|$)'; Label = 'target (Java build output)' }
        @{ Pattern = '(^|/|\\)__pycache__(/|\\|$)'; Label = '__pycache__' }
        @{ Pattern = '(^|/|\\)\.pytest_cache(/|\\|$)'; Label = '.pytest_cache' }
        @{ Pattern = '(^|/|\\)github-pat\.txt$'; Label = 'github-pat.txt (credentials)' }
        @{ Pattern = '(^|/|\\)debug_last_session\.md$'; Label = 'debug_last_session.md (local debug)' }
    )
    $hits = @()
    foreach ($p in $Paths) {
        $norm = ($p -replace '\\', '/').Trim()
        foreach ($rule in $blocked) {
            if ($norm -match $rule.Pattern) {
                $hits += [pscustomobject]@{ Path = $norm; Reason = $rule.Label }
                break
            }
        }
    }
    return ,$hits
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is not installed or not in PATH."
}

if (-not (Test-Path ".git")) {
    Write-Host "Initializing git repository..." -ForegroundColor Yellow
    Invoke-Git init
    Invoke-Git branch -M $Branch
}

$remotes = @()
if (-not $DryRun -and (Test-Path ".git")) {
    $remotes = @(git remote 2>$null)
}
if ($remotes -contains "origin") {
    Write-Host "Updating remote origin -> $RemoteUrl" -ForegroundColor Yellow
    Invoke-Git remote set-url origin $RemoteUrl
} else {
    Write-Host "Adding remote origin -> $RemoteUrl" -ForegroundColor Yellow
    Invoke-Git remote add origin $RemoteUrl
}

Invoke-Git add -A
Invoke-Git status

$hasChanges = $true
if (-not $DryRun) {
    $status = git status --porcelain
    if (-not $status) {
        Write-Host "No changes to commit." -ForegroundColor Green
        $hasChanges = $false
    } else {
        $stagedPaths = @(
            git diff --cached --name-only --diff-filter=AM 2>$null
        ) | Where-Object { $_ } | Select-Object -Unique
        $forbidden = Test-ForbiddenStagedPaths -Paths $stagedPaths
        if ($forbidden.Count -gt 0) {
            Write-Host ""
            Write-Host "=== Blocked: staged paths should stay local (check .gitignore) ===" -ForegroundColor Red
            $forbidden | Select-Object -First 20 | ForEach-Object {
                Write-Host ("  - {0}  ({1})" -f $_.Path, $_.Reason) -ForegroundColor Red
            }
            if ($forbidden.Count -gt 20) {
                Write-Host ("  ... and {0} more" -f ($forbidden.Count - 20)) -ForegroundColor Red
            }
            Write-Host ""
            Write-Host "Fix: update .gitignore, then run:" -ForegroundColor Yellow
            Write-Host "  git rm -r --cached <path>   # stop tracking without deleting local files" -ForegroundColor Yellow
            throw "Refusing to commit sensitive or cache artifacts. See messages above."
        }
    }
}

if ($hasChanges) {
    Invoke-GitCommit -CommitMessage $Message
}

Write-Host "Pushing to origin/$Branch ..." -ForegroundColor Cyan
Write-Host "If prompted, sign in to GitHub (HTTPS) or ensure SSH key is configured." -ForegroundColor DarkYellow

if ($DryRun) {
    Write-Host ('[dry-run] git push -u origin ' + $Branch) -ForegroundColor DarkGray
    Write-Host "Dry run complete. Re-run without -DryRun to upload." -ForegroundColor Green
    exit 0
}

Invoke-Git push -u origin $Branch

Write-Host "Done. Repository: $RemoteUrl" -ForegroundColor Green
