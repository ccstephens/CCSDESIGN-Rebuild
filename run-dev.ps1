$ErrorActionPreference = "Stop"

Write-Host "CCSDESIGN Rebuild V1 startup check" -ForegroundColor Cyan

function Require-Command($Name, $Help) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "Missing dependency: $Name" -ForegroundColor Red
        Write-Host $Help -ForegroundColor Yellow
        exit 1
    }
}

Require-Command "py" "Install Python 3.11 and make sure the Python launcher is available."
Require-Command "npm" "Install Node.js 20 LTS or newer, which includes npm."

try {
    $pythonVersion = & py -3.11 --version 2>&1
    Write-Host "Python: $pythonVersion" -ForegroundColor DarkGray
} catch {
    Write-Host "Python 3.11 is required. Install it, then run this launcher again." -ForegroundColor Red
    exit 1
}

$nodeVersion = & node --version
$npmVersion = & npm --version
Write-Host "Node: $nodeVersion / npm: $npmVersion" -ForegroundColor DarkGray

if (-not (Get-Command "meshroom_batch" -ErrorAction SilentlyContinue)) {
    Write-Host "Meshroom is not on PATH. Mesh import/repair will work, but photo reconstruction will be unavailable." -ForegroundColor Yellow
} else {
    Write-Host "Meshroom/AliceVision detected." -ForegroundColor Green
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python environment..." -ForegroundColor Cyan
    py -3.11 -m venv .venv
}

Write-Host "Installing/updating backend dependencies..." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
    Push-Location frontend
    try { npm install } finally { Pop-Location }
}

Write-Host "Starting backend and frontend..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$PWD'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$PWD\frontend'; npm run dev"

Start-Sleep -Seconds 2
Write-Host "Backend API: http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "App:         http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "If photo reconstruction is disabled, install Meshroom/AliceVision and add meshroom_batch to PATH." -ForegroundColor DarkGray
