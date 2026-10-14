# Read-only preflight. No installation, no service restart, no secrets printed.
[CmdletBinding()]
param([int]$ExpectedApiPort = 8000)
$ErrorActionPreference = 'Continue'
Write-Host 'SAHASRA LOCAL AI - READ-ONLY HOST PREFLIGHT'
Write-Host ('Operating system: ' + [Environment]::OSVersion.VersionString)
$os = Get-CimInstance Win32_OperatingSystem
Write-Host ('Windows caption: ' + $os.Caption)
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor
Write-Host ('Total RAM GiB: ' + [math]::Round($cs.TotalPhysicalMemory / 1GB, 1))
Write-Host ('Free RAM GiB: ' + [math]::Round([double]$os.FreePhysicalMemory / 1MB, 1))
Write-Host ('Logical processors visible: ' + $cs.NumberOfLogicalProcessors)
Write-Host ('Physical cores reported: ' + (($cpu | Measure-Object -Property NumberOfCores -Sum).Sum))
Write-Host ('CPU: ' + (($cpu | Select-Object -First 1).Name))
foreach ($svcName in @('SahasraAIAgent','W3SVC')) {
  $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
  if ($svc) { Write-Host ("Service {0}: {1}" -f $svcName, $svc.Status) }
  else { Write-Host ("Service {0}: not found" -f $svcName) }
}
foreach ($port in @($ExpectedApiPort,11434)) {
  $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
  if (-not $listeners) { Write-Host ("Port {0}: no listener" -f $port) }
  else {
    foreach ($conn in $listeners) {
      Write-Host ("Port {0}: listener {1} (PID {2})" -f $port,$conn.LocalAddress,$conn.OwningProcess)
      if ($port -eq 11434 -and $conn.LocalAddress -notin @('127.0.0.1','::1')) {
        Write-Warning 'Ollama port is listening beyond loopback; DO NOT ENABLE LOCAL AI until fixed.'
      }
    }
  }
}
Write-Host 'Preflight complete. No settings changed.'
