param(
    [string]$PythonExe = "python",
    [switch]$SkipTests
)
$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$venvPath = Join-Path $repoRoot ".codex\.venv-project-auditor"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

Write-Host "[1/3] Creating isolated virtual environment at .codex\.venv-project-auditor..." -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment using '$PythonExe'." }
}

Write-Host "[2/3] Installing the auditor package and validator dependencies..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install $repoRoot --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to install the auditor package." }

if (-not $SkipTests) {
    Write-Host "[3/3] Running full acceptance suite..." -ForegroundColor Cyan
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    $env:PYTHONIOENCODING = "utf-8"
    & $venvPython -X utf8 -m unittest discover -s (Join-Path $repoRoot ".codex\tests") -p "test_project_auditor_*.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Test suite failed." }
}

Write-Host "`nSetup complete! Run .\.codex\.venv-project-auditor\Scripts\auditor.exe --file my_script.py --provider ollama --model qwen2.5:7b" -ForegroundColor Green
