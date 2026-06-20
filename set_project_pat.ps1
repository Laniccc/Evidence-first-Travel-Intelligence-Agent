# Save a GitHub PAT for THIS repo only (.git/credentials). Does not print the token.
# Usage: .\set_project_pat.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$RepoSlug = "Laniccc/Evidence-first-Travel-Intelligence-Agent"
$credFile = Join-Path (Resolve-Path ".git").Path "credentials"

Write-Host "GitHub PAT setup (this repository only)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Create a CLASSIC token at:" -ForegroundColor Yellow
Write-Host "  https://github.com/settings/tokens"
Write-Host "Required scope: repo"
Write-Host ""
Write-Host "IMPORTANT: Password field must be the PAT (github_pat_... or ghp_...)," -ForegroundColor Red
Write-Host "             NOT your GitHub website login password."
Write-Host ""

$patSecure = Read-Host "Paste PAT (input hidden)" -AsSecureString
$pat = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($patSecure)
)
$patSecure.Dispose()

if ([string]::IsNullOrWhiteSpace($pat)) {
    throw "Empty PAT."
}
if ($pat -notmatch '^(ghp_|github_pat_)') {
    Write-Warning "Token does not look like a PAT (expected ghp_... or github_pat_...). Continue anyway."
}

$line = "https://Laniccc:$pat@github.com"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($credFile, $line, $utf8NoBom)

git config --local credential.helper "store --file=$credFile"
git config --local --unset credential.https://github.com.useHttpPath 2>$null
git remote set-url origin "https://Laniccc@github.com/$RepoSlug.git"

Write-Host ""
Write-Host "Saved to: $credFile" -ForegroundColor Green
Write-Host "Test with: git push -u origin main" -ForegroundColor Cyan
