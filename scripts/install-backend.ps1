$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try {
            & python --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @("python")
            }
        } catch {
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            & py -3 --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @("py", "-3")
            }
        } catch {
        }
    }

    throw "Python was not found on PATH. Install Python 3.11+ and try again."
}

function New-Venv {
    param(
        [string[]]$PythonCommand,
        [string]$VenvDir
    )

    if ($PythonCommand.Length -eq 1) {
        & $PythonCommand[0] -m venv $VenvDir
    } else {
        & $PythonCommand[0] $PythonCommand[1] -m venv $VenvDir
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$venvDir = Join-Path $backendDir ".venv"
$pythonCommand = Get-PythonCommand

if (-not (Test-Path $venvDir)) {
    Write-Host "Creating backend virtual environment..."
    New-Venv -PythonCommand $pythonCommand -VenvDir $venvDir
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment was created, but $venvPython was not found."
}

Write-Host "Upgrading pip..."
& $venvPython -m pip install --upgrade pip

Write-Host "Installing backend requirements..."
& $venvPython -m pip install -r (Join-Path $backendDir "requirements.txt")
