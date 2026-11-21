# Starts the PS05-X API (port 8000) and web app (port 3000) in two PowerShell windows.
# Prerequisites: apps/api/.env (copy from .env.example and set DEMO_*_PASSWORD), pip + npm installs done.
$root = Split-Path -Parent $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\apps\api'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\apps\web'; npm run dev -- --port 3000"
Start-Sleep -Seconds 6
Start-Process "http://localhost:3000"
Write-Host "API:  http://localhost:8000/docs"
Write-Host "Web:  http://localhost:3000"
