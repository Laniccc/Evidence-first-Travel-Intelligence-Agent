# Clone vendor repos + install deps + sync crawler .env paths.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$CrawlerRoot = Join-Path $Root "external\crawlers"
$Vendor = Join-Path $CrawlerRoot "vendors"
New-Item -ItemType Directory -Force -Path $Vendor | Out-Null

$CtripVendor = Join-Path $Vendor "CtripSpider"
$DpVendor = Join-Path $Vendor "dianping-crawler"

if (-not (Test-Path $CtripVendor)) {
    git clone https://github.com/aglorice/CtripSpider.git $CtripVendor
}
if (-not (Test-Path $DpVendor)) {
    git clone https://github.com/crazyboycjr/dianping-crawler.git $DpVendor
}

Write-Host "Installing CtripSpider Python dependencies..."
pip install requests beautifulsoup4 lxml fake-useragent rich pandas openpyxl -q

$EnvFile = Join-Path $Root "apps\agent-python\.env"
$RelCtrip = "../../external/crawlers/ctrip"
$RelDp = "../../external/crawlers/dianping"

function Set-EnvLine {
    param([string]$Path, [string]$Key, [string]$Value)
    if (-not (Test-Path $Path)) { return }
    $lines = Get-Content $Path -Encoding UTF8
    $found = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match "^$([regex]::Escape($Key))=") {
            $found = $true
            "$Key=$Value"
        } else { $line }
    }
    if (-not $found) { $newLines += "$Key=$Value" }
    Set-Content -Path $Path -Value $newLines -Encoding UTF8
}

if (Test-Path $EnvFile) {
    Set-EnvLine $EnvFile "CTRIP_SPIDER_ROOT" $RelCtrip
    Set-EnvLine $EnvFile "DIANPING_CRAWLER_ROOT" $RelDp
    Set-EnvLine $EnvFile "ENABLE_NEARBY_PLATFORM_CRAWLERS" "true"
    Write-Host "Updated $EnvFile"
}

Write-Host ""
Write-Host "Adapter roots:"
Write-Host "  CTRIP_SPIDER_ROOT=$(Join-Path $CrawlerRoot 'ctrip')"
Write-Host "  DIANPING_CRAWLER_ROOT=$(Join-Path $CrawlerRoot 'dianping')"
