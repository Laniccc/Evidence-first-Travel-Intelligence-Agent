# Clone optional external crawler repos and print recommended .env commands.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$External = Join-Path $Root "external"
New-Item -ItemType Directory -Force -Path $External | Out-Null

$Ctrip = Join-Path $External "CtripSpider"
$Dp = Join-Path $External "dianping-crawler"

if (-not (Test-Path $Ctrip)) {
    git clone https://github.com/aglorice/CtripSpider.git $Ctrip
}
if (-not (Test-Path $Dp)) {
    git clone https://github.com/crazyboycjr/dianping-crawler.git $Dp
}

$CliCtrip = (Resolve-Path (Join-Path $Root "scripts\crawlers\ctrip_cli.py")).Path
$CliDp = (Resolve-Path (Join-Path $Root "scripts\crawlers\dianping_cli.py")).Path

Write-Host "Recommended .env (apps/agent-python):"
Write-Host "CTRIP_SPIDER_ROOT=$Ctrip"
Write-Host "DIANPING_CRAWLER_ROOT=$Dp"
Write-Host "CTRIP_CRAWLER_COMMAND=python `"$CliCtrip`" --place `"{place}`" --city `"{city}`" --mode {mode}"
Write-Host "DIANPING_CRAWLER_COMMAND=python `"$CliDp`" --place `"{place}`" --city `"{city}`" --mode review"
Write-Host "DIANPING_SPIDER_COMMAND=python `"$CliDp`" --place `"{place}`" --city `"{city}`" --mode nearby"
