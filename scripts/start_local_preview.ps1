$env:ENVIRONMENT = 'local'
$env:DATABASE_URL = 'sqlite:///./hxy_preview_20260810.db'
Set-Location $PSScriptRoot\..
& .venv\Scripts\python.exe scripts\setup_preview.py
& .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8010
