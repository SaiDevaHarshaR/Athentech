# Deploy changed files with backup, rollback and service health check.
param(
  [string]$AppDir = 'D:\Websites\P441-SahasraAiAgent\SahasraAiAgent',
  [string]$ServiceName = 'SahasraAIAgent',
  [string]$HealthUrl = 'https://api.athentech.in/health'
)
$ErrorActionPreference = 'Stop'
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $kit 'app'
if (-not (Test-Path $AppDir)) { throw "AppDir missing: $AppDir" }
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) { throw 'nssm missing' }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $AppDir "backup_$stamp"
New-Item -Path $backup -ItemType Directory -Force | Out-Null
$files = @(Get-ChildItem $src -Recurse -File | Where-Object { $_.Extension -notin @('.pyc') })
$manifest = @()
foreach ($f in $files) {
  $rel = $f.FullName.Substring($src.Length + 1)
  $dst = Join-Path $AppDir $rel
  # Existing finance pins are client-specific policy. Never silently overwrite them.
  if ($rel -like 'config\clients\*.json' -and (Test-Path $dst)) {
    Write-Host "Existing client pin kept: $rel"
    continue
  }
  $exists = Test-Path $dst
  if ($exists) {
    $safe = Join-Path $backup $rel
    New-Item -ItemType Directory -Path (Split-Path $safe) -Force | Out-Null
    Copy-Item $dst $safe -Force
  }
  $manifest += [pscustomobject]@{path=$rel; existed=$exists}
}
$manifest | ConvertTo-Json | Set-Content (Join-Path $backup 'manifest.json') -Encoding UTF8
$backup | Set-Content (Join-Path $AppDir 'last_backup.txt') -Encoding UTF8
try {
  foreach ($item in $manifest) {
    $dst = Join-Path $AppDir $item.path
    New-Item -ItemType Directory -Path (Split-Path $dst) -Force | Out-Null
    Copy-Item (Join-Path $src $item.path) $dst -Force
  }
  $py = Join-Path $AppDir '.venv\Scripts\python.exe'
  if (-not (Test-Path $py)) { $py = 'python' }
  foreach ($item in $manifest) {
    if ($item.path -notlike '*.py') { continue }
    & $py -m py_compile (Join-Path $AppDir $item.path)
    if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $($item.path)" }
  }
  & nssm restart $ServiceName | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Service restart failed' }
  $healthy = $false
  for ($i=0; $i -lt 12; $i++) {
    Start-Sleep -Seconds 3
    try {
      $resp = Invoke-WebRequest $HealthUrl -UseBasicParsing -TimeoutSec 5
      if ([int]$resp.StatusCode -eq 200) { $healthy=$true; break }
    } catch {}
  }
  if (-not $healthy) { throw 'Service health check failed' }
  Write-Host 'DEPLOY FINISHED. Run verify_live_exports.py for each client and compare with baseline.'
} catch {
  Write-Warning "Deploy failed: $_"
  & (Join-Path $kit 'rollback_update.ps1') -AppDir $AppDir -ServiceName $ServiceName
  throw
}
