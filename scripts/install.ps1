<#
.SYNOPSIS
    Install yaml-agno and all its dependencies in a Python virtual environment.

.DESCRIPTION
    Creates a virtual environment in <project-root>\.venv, installs:
      - core-cenf-py in editable mode (from local path)
      - yaml-agno in editable mode (from project root)
      - All PyPI runtime dependencies (requirements.txt)
      - All development dependencies (requirements-dev.txt)

    Detects the Python interpreter and validates Python 3.12+ before proceeding.
    Idempotent — safe to re-run if already installed.

.NOTES
    Project root : C:\Dropbox\DOC.RECA\06-Software\yaml-agno
    core-cenf    : C:\Dropbox\DOC.RECA\06-Software\core-cenf-py
    Venv path    : C:\Dropbox\DOC.RECA\06-Software\yaml-agno\.venv
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CoreCenfPath = "C:\Dropbox\DOC.RECA\06-Software\core-cenf-py"
$VenvPath = Join-Path -Path $ProjectRoot -ChildPath ".venv"
$Requirements = Join-Path -Path $ProjectRoot -ChildPath "requirements.txt"
$RequirementsDev = Join-Path -Path $ProjectRoot -ChildPath "requirements-dev.txt"

# ── 1. Python check ─────────────────────────────────────────────────────────
Write-Host "🔍 Checking Python interpreter..." -ForegroundColor Cyan
$py = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Error "Python not found in PATH. Install Python 3.12+ from https://www.python.org/downloads/"
    exit 1
}

$pyVersion = & python -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')"
$pyMajorMinor = & python -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')"
Write-Host "  Found Python $pyVersion at $($py.Source)" -ForegroundColor Green

if ([version]$pyMajorMinor -lt [version]"3.12") {
    Write-Error "yaml-agno requires Python 3.12+. Found $pyMajorMinor"
    exit 1
}

# ── 2. Validate project structure ───────────────────────────────────────────
Write-Host "🔍 Validating project structure..." -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $Requirements)) {
    Write-Error "requirements.txt not found at $Requirements"
    exit 1
}
if (-not (Test-Path -LiteralPath $RequirementsDev)) {
    Write-Error "requirements-dev.txt not found at $RequirementsDev"
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path -Path $ProjectRoot -ChildPath "pyproject.toml"))) {
    Write-Error "pyproject.toml not found at $ProjectRoot — is this the yaml-agno project?"
    exit 1
}
if (-not (Test-Path -LiteralPath $CoreCenfPath)) {
    Write-Warning "core-cenf-py not found at $CoreCenfPath — will try pip git+https install"
    $CoreCenfLocalAvailable = $false
} else {
    $CoreCenfLocalAvailable = $true
    Write-Host "  core-cenf-py local copy: ✅" -ForegroundColor Green
}

# ── 3. Create virtual environment ───────────────────────────────────────────
if (Test-Path -LiteralPath $VenvPath) {
    Write-Host "📦 Virtual environment already exists at $VenvPath" -ForegroundColor Yellow
    Write-Host "  (delete the folder to recreate from scratch)" -ForegroundColor DarkYellow
} else {
    Write-Host "📦 Creating virtual environment at $VenvPath..." -ForegroundColor Cyan
    & python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment" }
    Write-Host "  Virtual environment created ✅" -ForegroundColor Green
}

# ── 4. Activate and upgrade pip ─────────────────────────────────────────────
Write-Host "📦 Activating virtual environment and upgrading pip..." -ForegroundColor Cyan
$pip = Join-Path -Path $VenvPath -ChildPath "Scripts\pip.exe"
$pythonVenv = Join-Path -Path $VenvPath -ChildPath "Scripts\python.exe"

& $pythonVenv -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip" }

# ── 5. Install core-cenf-py (local editable or git) ─────────────────────────
if ($CoreCenfLocalAvailable) {
    Write-Host "📦 Installing core-cenf-py from local path (editable)..." -ForegroundColor Cyan
    & $pip install -e "$CoreCenfPath"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install core-cenf-py from local path" }
    Write-Host "  core-cenf-py installed (editable) ✅" -ForegroundColor Green
} else {
    Write-Host "📦 Installing core-cenf-py from GitHub..." -ForegroundColor Cyan
    & $pip install "core-cenf @ git+https://github.com/CENFARG/core-cenf-py.git@v0.1.0"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install core-cenf-py from GitHub" }
    Write-Host "  core-cenf-py installed (git+https) ✅" -ForegroundColor Green
}

# ── 6. Install PyPI runtime dependencies ────────────────────────────────────
Write-Host "📦 Installing PyPI runtime dependencies..." -ForegroundColor Cyan
& $pip install -r $Requirements
if ($LASTEXITCODE -ne 0) { throw "Failed to install runtime dependencies" }
Write-Host "  Runtime dependencies installed ✅" -ForegroundColor Green

# ── 7. Install yaml-agno in editable mode ───────────────────────────────────
Write-Host "📦 Installing yaml-agno in editable mode..." -ForegroundColor Cyan
& $pip install -e "$ProjectRoot"
if ($LASTEXITCODE -ne 0) { throw "Failed to install yaml-agno" }
Write-Host "  yaml-agno installed (editable) ✅" -ForegroundColor Green

# ── 8. Install dev dependencies ─────────────────────────────────────────────
Write-Host "📦 Installing development dependencies..." -ForegroundColor Cyan
& $pip install -r $RequirementsDev
if ($LASTEXITCODE -ne 0) { throw "Failed to install dev dependencies" }
Write-Host "  Dev dependencies installed ✅" -ForegroundColor Green

# ── 9. Verify installation ──────────────────────────────────────────────────
Write-Host "🔍 Verifying installation..." -ForegroundColor Cyan
& $pythonVenv -c "
import sys
print(f'Python: {sys.version}')
try:
    import yaml_agno
    print(f'yaml-agno: {yaml_agno.__version__}')
except Exception as e:
    print(f'yaml-agno: NOT FOUND ({e})')
try:
    import core_infrastructure
    print(f'core-infrastructure: OK')
except Exception as e:
    print(f'core-infrastructure: NOT FOUND ({e})')
try:
    import agno
    print(f'agno: OK')
except Exception as e:
    print(f'agno: NOT FOUND ({e})')
try:
    import sqlalchemy
    print(f'sqlalchemy: OK')
except Exception as e:
    print(f'sqlalchemy: NOT FOUND ({e})')
try:
    import structlog
    print(f'structlog: OK')
except Exception as e:
    print(f'structlog: NOT FOUND ({e})')
"

# ── 10. Summary ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ✅ yaml-agno installation complete!" -ForegroundColor Green
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Virtual environment:" -ForegroundColor White
Write-Host "    $VenvPath" -ForegroundColor Gray
Write-Host ""
Write-Host "  Activate with:" -ForegroundColor White
Write-Host "    $VenvPath\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Or run commands directly:" -ForegroundColor White
Write-Host "    $VenvPath\Scripts\python.exe -m pytest" -ForegroundColor Yellow
Write-Host "    $VenvPath\Scripts\python.exe -m ruff check src/" -ForegroundColor Yellow
Write-Host "    $VenvPath\Scripts\python.exe -m mypy src/" -ForegroundColor Yellow
Write-Host ""
