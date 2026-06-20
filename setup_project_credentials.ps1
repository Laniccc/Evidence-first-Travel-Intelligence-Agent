# Use GitHub credentials ONLY for this repository (other repos keep global creds).
#
# Method A (recommended): Git Credential Manager per-repo path
# Method B: Local credential file under .git/ (fully isolated from Windows Credential Manager)
#
# Usage:
#   .\setup_project_credentials.ps1              # Method A
#   .\setup_project_credentials.ps1 -UseLocalFile  # Method B
#   .\setup_project_credentials.ps1 -ClearOnly     # Clear this repo's cached cred only

param(
    [switch]$UseLocalFile,
    [switch]$ClearOnly,
    [switch]$ClearGlobalGithub
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$RepoSlug = "Laniccc/Evidence-first-Travel-Intelligence-Agent"
$DefaultRemote = "https://github.com/$RepoSlug.git"

$remote = git config --get remote.origin.url
if (-not $remote) {
    $remote = $DefaultRemote
    git remote add origin $remote 2>$null
    git remote set-url origin $remote 2>$null
}

if ($remote -match "^https://github\.com/") {
    $remote = $remote -replace "^https://github\.com/", "https://Laniccc@github.com/"
    git remote set-url origin $remote
    Write-Host "Remote set to: $remote" -ForegroundColor Cyan
}

function Clear-ProjectGitHubCredential {
    $list = cmdkey /list 2>&1 | Out-String
    $pathTargets = @(
        "LegacyGeneric:target=git:https://github.com/$RepoSlug",
        "LegacyGeneric:target=git:https://Laniccc@github.com/$RepoSlug"
    )
    $removed = $false
    foreach ($t in $pathTargets) {
        if ($list -match [regex]::Escape($t)) {
            cmdkey /delete:$t 2>$null
            Write-Host "Removed project credential: $t" -ForegroundColor Yellow
            $removed = $true
        }
    }
    if ($ClearGlobalGithub) {
        $hostTarget = "LegacyGeneric:target=git:https://github.com"
        if ($list -match [regex]::Escape($hostTarget)) {
            cmdkey /delete:$hostTarget 2>$null
            Write-Host "Removed global github.com credential (affects all HTTPS GitHub repos)." -ForegroundColor Yellow
            $removed = $true
        }
    }
    if (-not $removed) {
        Write-Host "No matching cached credential to remove (will prompt on next push if needed)." -ForegroundColor DarkGray
    }
}

Clear-ProjectGitHubCredential

if ($ClearOnly) {
    Write-Host "Cleared. Next: git push -u origin main (enter new PAT for this repo only)." -ForegroundColor Green
    exit 0
}

if ($UseLocalFile) {
    $credFile = Join-Path (Resolve-Path ".git").Path "credentials"
    git config --local --unset-all credential.helper 2>$null
    git config --local credential.helper "store --file=$credFile"
    git config --local --unset credential.https://github.com.useHttpPath 2>$null

    Write-Host ""
    Write-Host "Method B enabled: local file store" -ForegroundColor Green
    Write-Host "  File: $credFile"
    Write-Host ""
    Write-Host "Option 1 - Let git prompt once on push:" -ForegroundColor Cyan
    Write-Host "  git push -u origin main"
    Write-Host "  Username: Laniccc | Password: <PAT>"
    Write-Host ""
    Write-Host "Option 2 - Write file manually (one line):" -ForegroundColor Cyan
    Write-Host "  https://Laniccc:<YOUR_PAT>@github.com"
    Write-Host ""
} else {
    git config --local credential.https://github.com.useHttpPath true
    git config --local --unset-all credential.helper 2>$null

    Write-Host ""
    Write-Host "Method A enabled: per-repository credential (useHttpPath)" -ForegroundColor Green
    Write-Host "  Other GitHub repos will keep using your existing global login."
    Write-Host "  This repo will ask for (or use) a separate PAT on next push."
    Write-Host ""
    Write-Host "Next:" -ForegroundColor Cyan
    Write-Host "  git push -u origin main"
    Write-Host "  Username: Laniccc | Password: <paste PAT, NOT your GitHub login password>"
    Write-Host ""
}

Write-Host "Create PAT: https://github.com/settings/tokens (classic, scope: repo)" -ForegroundColor DarkGray
