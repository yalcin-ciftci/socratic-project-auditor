param(
    [string]$PythonExe = "python",
    [switch]$SkipTests
)
$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$venvPath = Join-Path $repoRoot ".codex\.venv-project-auditor"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$reqFile = Join-Path $repoRoot "requirements.txt"

Write-Host "[1/3] Creating isolated virtual environment at .codex\.venv-project-auditor..." -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment using '$PythonExe'." }
}

Write-Host "[2/3] Installing validator dependencies (jsonschema, rfc3339-validator)..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r $reqFile --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to install dependencies from requirements.txt." }

if (-not $SkipTests) {
    Write-Host "[3/3] Running full 71-test acceptance suite..." -ForegroundColor Cyan
    $env:PYTHONPATH = Join-Path $repoRoot ".codex\scripts"
    $env:PYTHONIOENCODING = "utf-8"
    & $venvPython -X utf8 -m unittest discover -s (Join-Path $repoRoot ".codex\tests") -p "test_project_auditor_*.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Test suite failed." }
}

Write-Host "`nSetup complete! You can now invoke the runtime via .\.codex\Invoke-ProjectAuditor.ps1" -ForegroundColor Green
