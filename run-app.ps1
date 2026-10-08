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

$url="http://127.0.0.1:8000"
$health="$url/api/health"
try {
 $existing=Invoke-RestMethod -Uri $health -TimeoutSec 2
 if ($existing.status -eq "ok") {
  Write-Host "CCSDESIGN Rebuild is already running. Opening it now." -ForegroundColor Green
  Start-Process $url
  exit 0
 }
} catch {}

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

$server=Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","backend.app.main:app","--host","127.0.0.1","--port","8000" -PassThru
$ready=$false
for ($i=0;$i -lt 30;$i++) {
 if ($server.HasExited) { break }
 try {
  $check=Invoke-RestMethod -Uri $health -TimeoutSec 2
  if ($check.status -eq "ok") { $ready=$true; break }
 } catch {}
 Start-Sleep -Milliseconds 500
}
if (-not $ready) {
 Write-Host "CCSDESIGN Rebuild did not start correctly." -ForegroundColor Red
 if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }
 exit 1
}
Write-Host "CCSDESIGN Rebuild is ready at $url" -ForegroundColor Green
Start-Process $url
Write-Host "Close this window or press Ctrl+C to stop the app." -ForegroundColor DarkGray
try { Wait-Process -Id $server.Id } finally { if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force } }
