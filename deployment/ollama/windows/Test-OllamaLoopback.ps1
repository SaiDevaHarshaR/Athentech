# Optional later staging test; read-only HTTP GET to loopback, does not send patient data.
[CmdletBinding()]
param([string]$Model='qwen3:4b')
$ErrorActionPreference='Stop'
if ($Model -notin @('qwen3:4b','qwen3:8b')) { throw 'Only approved models are supported.' }
$conns = Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue
if ($conns | Where-Object { $_.LocalAddress -notin @('127.0.0.1','::1') }) { throw 'Refusing test: Ollama listens beyond loopback.' }
try {
  $r = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 -Method Get
  $names = @($r.models | ForEach-Object { $_.name })
  if ($names -contains $Model) { Write-Host "READY: $Model exists on local Ollama."; exit 0 }
  Write-Warning "NOT READY: $Model is not downloaded. No download attempted."; exit 2
} catch {
  Write-Warning 'Ollama loopback check failed or service is unavailable. No configuration changed.'
  exit 3
}
