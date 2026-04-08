$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
$backendHost = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "127.0.0.1" }
$backendPort = if ($env:BACKEND_PORT) { [int]$env:BACKEND_PORT } else { 8000 }

function Get-ProcessCommandLine {
    param(
        [int]$ProcessId
    )

    try {
        return (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId").CommandLine
    } catch {
        return $null
    }
}

if (-not (Test-Path $venvPython)) {
    throw "Backend virtual environment not found. Run 'npm run backend:install' first."
}

$listener = Get-NetTCPConnection -LocalPort $backendPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1

if ($listener) {
    $commandLine = Get-ProcessCommandLine -ProcessId $listener.OwningProcess
    if ($commandLine -and $commandLine -like "*uvicorn*backend.main:app*") {
        Write-Host "Backend already running on http://$backendHost`:$backendPort (PID $($listener.OwningProcess))."
        exit 0
    }

    throw "Port $backendPort is already in use by PID $($listener.OwningProcess). Stop that process first or set BACKEND_PORT to a different value."
}

Set-Location $repoRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
& $venvPython -m uvicorn backend.main:app --reload --host $backendHost --port $backendPort
