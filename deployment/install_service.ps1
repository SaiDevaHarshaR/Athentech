# =========================================================================
# Sahasra AI Agent — Windows Service installer (via NSSM)
#
# Run this in an Administrator PowerShell prompt, on the Windows Server
# that will actually run the API.
#
# What this does: wraps `python -m uvicorn main:app` as a real Windows
# Service, so it starts automatically on boot and restarts if it crashes
# — instead of dying whenever someone closes the terminal it was
# launched from.
#
# BEFORE RUNNING: download NSSM from https://nssm.cc/download (free,
# no installer — just an .exe) and fill in the 5 values below.
# =========================================================================

# ----- FILL THESE IN -----
$ServiceName = "SahasraAIAgent"
$ProjectPath = "__FILL_IN__"        # e.g. C:\inetpub\SahasraAIAgent  (where main.py lives)
$PythonExe   = "__FILL_IN__"        # e.g. C:\inetpub\SahasraAIAgent\venv\Scripts\python.exe
$NssmExe     = "__FILL_IN__"        # e.g. C:\Tools\nssm\nssm.exe
$ApiPort     = "8000"               # must match __API_PORT__ in deployment/iis-api-site/web.config
# --------------------------

if (-not (Test-Path $ProjectPath)) {
    Write-Error "ProjectPath does not exist: $ProjectPath — fix the path above and re-run."
    exit 1
}
if (-not (Test-Path $PythonExe)) {
    Write-Error "PythonExe does not exist: $PythonExe — fix the path above and re-run."
    exit 1
}
if (-not (Test-Path $NssmExe)) {
    Write-Error "NssmExe does not exist: $NssmExe — download NSSM from https://nssm.cc/download and fix the path above."
    exit 1
}

$LogsDir = Join-Path $ProjectPath "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir | Out-Null
}

Write-Host "Installing service '$ServiceName'..."
& $NssmExe install $ServiceName $PythonExe "-m uvicorn main:app --host 127.0.0.1 --port $ApiPort"
& $NssmExe set $ServiceName AppDirectory $ProjectPath
& $NssmExe set $ServiceName DisplayName "Sahasra AI Agent API"
& $NssmExe set $ServiceName Description "FastAPI backend for the Sahasra AI Agent chat widget and admin panel"
& $NssmExe set $ServiceName Start SERVICE_AUTO_START
& $NssmExe set $ServiceName AppStdout (Join-Path $LogsDir "service_stdout.log")
& $NssmExe set $ServiceName AppStderr (Join-Path $LogsDir "service_stderr.log")
& $NssmExe set $ServiceName AppRotateFiles 1
& $NssmExe set $ServiceName AppRotateOnline 1
& $NssmExe set $ServiceName AppRotateBytes 10485760
# ^ log rotation at 10MB, so these log files don't grow forever unwatched

Write-Host ""
Write-Host "Done. The service is installed but NOT started yet."
Write-Host "Before starting it, make sure .env exists in $ProjectPath with real values"
Write-Host "(see deployment/.env.production.template)."
Write-Host ""
Write-Host "Start it with:"
Write-Host "  nssm start $ServiceName"
Write-Host "or via Services.msc (look for 'Sahasra AI Agent API')"
Write-Host ""
Write-Host "Check logs at: $LogsDir"
