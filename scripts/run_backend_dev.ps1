$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
Set-Location $Backend
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_dev.py
