# ==============================================================================
# Script Cài đặt 1-Click Toàn bộ Công cụ Còn thiếu trên Windows 11
# ==============================================================================

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   BAT DAU CAI DAT CAC CONG CU ANTIGRAVITY CON THIEU" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Cai dat GitHub CLI
Write-Host "[1/5] Cai dat GitHub CLI..." -ForegroundColor Cyan
winget install --id GitHub.cli -e --silent --accept-package-agreements --accept-source-agreements

# 2. Cai dat Gitleaks (Quet secrets bao mat)
Write-Host "[2/5] Cai dat Gitleaks..." -ForegroundColor Cyan
winget install gitleaks -e --silent --accept-package-agreements --accept-source-agreements

# 3. Cai dat Bruno (API Client luu trong Git)
Write-Host "[3/5] Cai dat Bruno..." -ForegroundColor Cyan
winget install Usebruno.Bruno -e --silent --accept-package-agreements --accept-source-agreements

# 4. Cai dat DBeaver (Xem database)
Write-Host "[4/5] Cai dat DBeaver..." -ForegroundColor Cyan
winget install dbeaver.dbeaver -e --silent --accept-package-agreements --accept-source-agreements

# 5. Cai dat Ruff qua uv
Write-Host "[5/5] Cai dat Ruff Linter qua uv..." -ForegroundColor Cyan
uv tool install ruff

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "   HOAN TAT! HAY KHOI DONG LAI POWERSHELL DE CAP NHAT PATH!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
