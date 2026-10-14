# READ-ONLY preflight: process ownership and localhost/public health routing.
$ErrorActionPreference = 'Continue'
Write-Host '=== Listeners for Sahasra port 8000 ==='
Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table
Write-Host '=== Python process executable and working command ==='
Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|uvicorn).*\.exe$' } |
  Select-Object ProcessId,ExecutablePath,CommandLine | Format-List
foreach ($url in @('http://127.0.0.1:8000/health','https://sahasraaiagent.athentech.in/health')) {
  Write-Host ('=== ' + $url + ' ===')
  try {
    $r = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    Write-Host ('HTTP ' + [int]$r.StatusCode)
    Write-Host ($r.Content | Out-String)
  } catch {
    if ($_.Exception.Response) {
      Write-Host ('HTTP ' + [int]$_.Exception.Response.StatusCode)
    } else {
      Write-Host $_.Exception.Message
    }
  }
}
Write-Host 'Read-only diagnostics finished. No processes or files changed.'
