<#
.SYNOPSIS
  Harvest real Oklahoma OSCN (Tulsa) civil judgments and run the screen.

.DESCRIPTION
  Run this on a Windows machine WITH open internet (not the sandboxed Claude
  web session, where oscn.net is blocked). It:
    1. sets up a Python venv + installs deps
    2. sweeps OSCN CJ ("civil relief more than $10,000") cases across several
       years, keeping only cases that have a judgment
    3. merges them into one records file
    4. ingests + screens -> screening/out/worklist.csv

  Eligibility is decided ONLY by the hard-coded rules in screening/rules.py
  (no eviction, amount > $20k, age 8-15y, dormant >=5y). This script just
  gathers REAL data and feeds it in. It never invents judgments.

.EXAMPLE
  .\screening\run_harvest.ps1
  .\screening\run_harvest.ps1 -County tulsa -Years 2011,2012,2013,2014,2015,2016 -End 2000
#>
param(
  [string]   $County = "tulsa",
  [int[]]    $Years  = @(2011,2012,2013,2014,2015,2016),
  [int]      $Start  = 1,
  [int]      $End    = 2000,
  [double]   $Delay  = 1.0
)

$ErrorActionPreference = "Stop"
# Run from the repo root regardless of where the script is invoked.
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "== Setting up Python environment ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { python -m venv .venv }
. .\.venv\Scripts\Activate.ps1
python -m pip install --quiet --upgrade pip
python -m pip install --quiet requests beautifulsoup4 pyyaml

New-Item -ItemType Directory -Force -Path "sample_data" | Out-Null
$yearFiles = @()

foreach ($y in $Years) {
  $outFile = "sample_data/oscn_${County}_$y.jsonl"
  Write-Host "== Harvesting $County $y  (CJ-$y-$Start .. CJ-$y-$End) ==" -ForegroundColor Cyan
  python screening/harvest_oscn.py `
    --county $County --year $y --start $Start --end $End `
    --only-judgments --delay $Delay `
    --out $outFile --cache-dir "sample_data/oscn_cache"
  if (Test-Path $outFile) { $yearFiles += $outFile }
}

# Merge per-year files into the one records file the screen ingests.
$records = "sample_data/oscn_${County}_records.jsonl"
if ($yearFiles.Count -eq 0) {
  Write-Host "No records harvested. Check network access to oscn.net." -ForegroundColor Red
  exit 1
}
Get-Content $yearFiles | Set-Content $records
$count = (Get-Content $records | Measure-Object -Line).Lines
Write-Host "== Merged $count judgment record(s) into $records ==" -ForegroundColor Green

Write-Host "== Ingesting + screening ==" -ForegroundColor Cyan
python -m screening.cli ingest --records $records
python -m screening.cli screen

Write-Host ""
Write-Host "Worklist: screening/out/worklist.csv" -ForegroundColor Green
Write-Host "If <10 candidates: rerun with more -Years or a larger -End." -ForegroundColor Yellow
Write-Host "Verify a few amounts against the live pages:" -ForegroundColor Yellow
Write-Host "  https://www.oscn.net/dockets/GetCaseInformation.aspx?db=$County&number=CJ-2014-123" -ForegroundColor Yellow
