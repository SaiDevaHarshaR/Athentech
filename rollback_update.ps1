param(
  [string]$AppDir = 'D:\Websites\P441-SahasraAiAgent\SahasraAiAgent',
  [string]$ServiceName = 'SahasraAIAgent'
)
$ErrorActionPreference = 'Stop'
$backup = (Get-Content (Join-Path $AppDir 'last_backup.txt') -Raw).Trim()
$manifestPath = Join-Path $backup 'manifest.json'
if (-not (Test-Path $manifestPath)) { throw "Backup manifest missing: $manifestPath" }
$manifest = @(Get-Content $manifestPath -Raw | ConvertFrom-Json)
foreach ($item in $manifest) {
  $dst = Join-Path $AppDir $item.path
  if ($item.existed) {
    $saved = Join-Path $backup $item.path
    New-Item -ItemType Directory -Path (Split-Path $dst) -Force | Out-Null
    Copy-Item $saved $dst -Force
  } elseif (Test-Path $dst) {
    Remove-Item $dst -Force
  }
}
& nssm restart $ServiceName | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Rollback copied files but restart failed' }
Write-Host "ROLLBACK COMPLETE from $backup"
