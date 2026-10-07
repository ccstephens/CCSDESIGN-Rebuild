$ErrorActionPreference = "Stop"

Write-Host "Starting CCSDESIGN Rebuild V1..." -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    py -3.11 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

if (-not (Test-Path "frontend\node_modules")) {
    Push-Location frontend
    npm install
    Pop-Location
}

Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$PWD'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$PWD\frontend'; npm run dev"

Write-Host "Backend: http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:5173" -ForegroundColor Green
