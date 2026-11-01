# ==============================================================================
# Script Kiểm tra Trạng thái 30 Công cụ Antigravity trên Windows 11
# ==============================================================================

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   KIEM TRA MOI TRUONG 30 CONG CU ANTIGRAVITY (WINDOWS 11)" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$tools = @(
    # Nhom 1: Nen tang
    @{ Name = "Git"; Cmd = "git"; Args = "--version"; Group = "01. Nen tang & Workflow"; Install = "winget install --id Git.Git -e" },
    @{ Name = "Node.js"; Cmd = "node"; Args = "-v"; Group = "01. Nen tang & Workflow"; Install = "winget install OpenJS.NodeJS.LTS -e" },
    @{ Name = "npm"; Cmd = "npm"; Args = "-v"; Group = "01. Nen tang & Workflow"; Install = "Di kem Node.js LTS" },
    @{ Name = "Python"; Cmd = "python"; Args = "--version"; Group = "01. Nen tang & Workflow"; Install = "winget install Python.Python.3.11 -e" },
    @{ Name = "uv"; Cmd = "uv"; Args = "--version"; Group = "01. Nen tang & Workflow"; Install = "irm https://astral.sh/uv/install.ps1 | iex" },
    @{ Name = "GitHub CLI"; Cmd = "gh"; Args = "--version"; Group = "01. Nen tang & Workflow"; Install = "winget install --id GitHub.cli -e" },
    @{ Name = "Docker"; Cmd = "docker"; Args = "--version"; Group = "01. Nen tang & Workflow"; Install = "winget install Docker.DockerDesktop -e" },

    # Nhom 4: Chat luong ma nguon
    @{ Name = "Ruff (Python Lint/Format)"; Cmd = "ruff"; Args = "--version"; Group = "04. Chat luong ma nguon"; Install = "uv tool install ruff" },
    @{ Name = "pytest (Python Test)"; Cmd = "pytest"; Args = "--version"; Group = "04. Chat luong ma nguon"; Install = "uv pip install pytest" },
    @{ Name = "ESLint"; Cmd = "npx"; Args = "eslint -v"; Group = "04. Chat luong ma nguon"; Install = "npm install --save-dev eslint" },
    @{ Name = "Prettier"; Cmd = "npx"; Args = "prettier -v"; Group = "04. Chat luong ma nguon"; Install = "npm install --save-dev prettier" },
    @{ Name = "Gitleaks"; Cmd = "gitleaks"; Args = "version"; Group = "04. Chat luong ma nguon"; Install = "winget install gitleaks -e" },

    # Nhom 5: Quan sat & Nang suat
    @{ Name = "Repomix"; Cmd = "npx"; Args = "repomix --version"; Group = "05. Quan sat & Nang suat"; Install = "npx repomix" },
    @{ Name = "Postman"; Cmd = "postman"; Args = ""; Group = "05. Quan sat & Nang suat"; Install = "winget install Postman.Postman -e" },
    @{ Name = "Bruno"; Cmd = "bruno"; Args = ""; Group = "05. Quan sat & Nang suat"; Install = "winget install Usebruno.Bruno -e" },
    @{ Name = "DBeaver"; Cmd = "dbeaver"; Args = ""; Group = "05. Quan sat & Nang suat"; Install = "winget install dbeaver.dbeaver -e" }
)

$installedCount = 0
$totalCheckable = $tools.Count

$currentGroup = ""
foreach ($item in $tools) {
    if ($item.Group -ne $currentGroup) {
        $currentGroup = $item.Group
        Write-Host ""
        Write-Host "[$currentGroup]" -ForegroundColor Magenta
        Write-Host "----------------------------------------------------------------------" -ForegroundColor DarkGray
    }

    $name = $item.Name.PadRight(30)
    $cmd = $item.Cmd
    $found = $false
    $versionOutput = ""

    # Kiem tra xem command co trong PATH khong
    $commandExists = Get-Command $cmd -ErrorAction SilentlyContinue

    if ($commandExists) {
        $found = $true
        if ($item.Args -ne "") {
            try {
                $argList = $item.Args -split " "
                $output = & $cmd $argList 2>$null
                if ($output) {
                    $versionOutput = ($output | Select-Object -First 1).Trim()
                }
            } catch {
                $versionOutput = "Installed"
            }
        } else {
            $versionOutput = "Installed in PATH"
        }
    } else {
        # Kiem tra cac duong dan app Windows pho bien
        if ($cmd -eq "postman" -and (Test-Path "$env:LOCALAPPDATA\Postman\app*\Postman.exe")) {
            $found = $true
            $versionOutput = "Installed (AppData)"
        } elseif ($cmd -eq "bruno" -and (Test-Path "$env:LOCALAPPDATA\Programs\bruno\bruno.exe")) {
            $found = $true
            $versionOutput = "Installed (AppData)"
        } elseif ($cmd -eq "dbeaver" -and (Test-Path "C:\Program Files\DBeaver\dbeaver.exe")) {
            $found = $true
            $versionOutput = "Installed (Program Files)"
        }
    }

    if ($found) {
        $installedCount++
        Write-Host "  [OK] $name" -ForegroundColor Green -NoNewline
        Write-Host " ($versionOutput)" -ForegroundColor DarkGray
    } else {
        Write-Host "  [--] $name" -ForegroundColor Red -NoNewline
        Write-Host " -> Cai: $($item.Install)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  KET QUA: $installedCount / $totalCheckable cong cu he thong da san sang!" -ForegroundColor $(if ($installedCount -ge 8) { "Green" } else { "Yellow" })
Write-Host "  Chi tiet xem tai: antigravity-setup/30-recommendations.md" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
