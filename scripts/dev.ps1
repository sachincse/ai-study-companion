# Start backend + frontend dev servers on Windows (PowerShell).
#   .\scripts\dev.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path "$root\.env")) {
  Copy-Item "$root\.env.example" "$root\.env"
  $secret = python -c "import secrets; print(secrets.token_urlsafe(48))"
  (Get-Content "$root\.env") -replace '^SECRET_KEY=.*$', "SECRET_KEY=$secret" | Set-Content "$root\.env"
  Write-Host "Created .env from .env.example (with a fresh SECRET_KEY) - add an API key (or use Ollama) before chatting." -ForegroundColor Yellow
}
if (-not (Test-Path "$root\backend\.venv")) {
  python -m venv "$root\backend\.venv"
  & "$root\backend\.venv\Scripts\python.exe" -m pip install -r "$root\backend\requirements-dev.txt"
}
if (-not (Test-Path "$root\frontend\node_modules")) {
  Push-Location "$root\frontend"; npm install; Pop-Location
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"
Write-Host "Backend: http://localhost:8000/api/docs   Frontend: http://localhost:5173" -ForegroundColor Green
