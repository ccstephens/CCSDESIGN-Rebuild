$ErrorActionPreference = "Stop"
Write-Host "Starting CCSDESIGN Rebuild..." -ForegroundColor Cyan

function Require-Command($Name,$Help) {
 if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
  Write-Host "Missing dependency: $Name" -ForegroundColor Red
  Write-Host $Help -ForegroundColor Yellow
  exit 1
 }
}

Require-Command "py" "Install Python 3.11."
Require-Command "npm" "Install Node.js 20 LTS or newer."
try { & py -3.11 --version | Out-Null } catch { Write-Host "Python 3.11 is required." -ForegroundColor Red; exit 1 }

if (-not (Test-Path ".venv")) { py -3.11 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

Push-Location frontend
try {
 if (-not (Test-Path "node_modules")) { npm install }
 npm run build
} finally { Pop-Location }

if (-not (Get-Command "meshroom_batch" -ErrorAction SilentlyContinue)) {
 Write-Host "Meshroom not detected: photo reconstruction will be disabled, but mesh import/repair remains available." -ForegroundColor Yellow
}

$url="http://127.0.0.1:8000"
Write-Host "Opening $url" -ForegroundColor Green
Start-Process $url
& .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
