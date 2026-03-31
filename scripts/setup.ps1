$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-WorkingPythonVersion {
    if (Test-Command "python") {
        try {
            $pythonVersion = & python --version 2>&1
            if ($LASTEXITCODE -eq 0) {
                return @{
                    Command = "python"
                    Version = "$pythonVersion"
                }
            }
        } catch {
        }
    }

    if (Test-Command "py") {
        try {
            $pyVersion = & py -3 --version 2>&1
            if ($LASTEXITCODE -eq 0) {
                return @{
                    Command = "py -3"
                    Version = "$pyVersion"
                }
            }
        } catch {
        }
    }

    return $null
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot "frontend"

Write-Step "Checking prerequisites"
$hasNode = Test-Command "node"
$hasNpm = Test-Command "npm"
$pythonInfo = Get-WorkingPythonVersion

if (-not $hasNode -or -not $hasNpm) {
    throw "Node.js and npm are required. Install Node.js 20+ and rerun this script."
}

Write-Host "Node: $(node --version)"
Write-Host "npm:  $(npm --version)"

if ($pythonInfo) {
    Write-Host "$($pythonInfo.Command): $($pythonInfo.Version)"
} else {
    Write-Warning "Python was not found on PATH. Backend setup will be skipped until Python 3.11+ is installed."
}

Write-Step "Installing frontend dependencies"
npm install --prefix $frontendDir

if ($pythonInfo) {
    Write-Step "Installing backend dependencies"
    & (Join-Path $PSScriptRoot "install-backend.ps1")
} else {
    Write-Step "Backend install skipped"
    Write-Host "Install Python 3.11+ from https://www.python.org/downloads/windows/ and ensure 'Add python.exe to PATH' is enabled."
    Write-Host "Then run: npm run backend:install"
}

Write-Step "Setup complete"
Write-Host "Frontend: npm run frontend:dev"
Write-Host "Backend:  npm run backend:dev"
