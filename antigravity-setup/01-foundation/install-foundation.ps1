# Script cai dat tu dong cac cong cu nen tang Windows 11
Write-Host "Dang cai dat GitHub CLI qua winget..." -ForegroundColor Cyan
winget install --id GitHub.cli -e --silent --accept-package-agreements --accept-source-agreements

Write-Host "Dang cai dat uv qua PowerShell..." -ForegroundColor Cyan
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

Write-Host "Hoan tat cai dat nen tang!" -ForegroundColor Green
