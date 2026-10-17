param(
    [Parameter(Mandatory=$true)]
    [ValidateSet(
        'init-ledger','run','state','hint','next','record-response',
        'init-doc-session','doc-state','doc-next','doc-followup','doc-hint',
        'record-doc-response','doc-teach','void-doc-question',
        'pause-doc-session','resume-doc-session','stop-doc-session','update-doc-version'
    )]
    [string]$Action,
    [string]$Request,
    [string]$ExamId,
    [string]$AttemptId,
    [string]$QuestionId,
    [string]$HintId,
    [string]$SessionId,
    [string]$ProjectId,
    [string]$DocumentId,
    [string]$DocumentVersion,
    [string]$DocumentSha256,
    [string]$ResponseId,
    [string]$Reason,
    [string]$LedgerId = 'LEDGER-PROJECT-AUDITOR',
    [string]$StateDir,
    [switch]$Deliver
)
$ErrorActionPreference = 'Stop'
$vaultRoot = Split-Path -Parent $PSScriptRoot
$pythonRuntime = Join-Path $PSScriptRoot '.venv-project-auditor/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonRuntime)) { throw 'Project Auditor Python environment missing. See RUNTIME.md.' }
$env:PYTHONPATH = Join-Path $PSScriptRoot 'scripts'
$env:PYTHONIOENCODING = 'utf-8'
$callArgs = @('-X','utf8','-m','project_auditor_runtime',$Action,'--vault',$vaultRoot,'--ledger-id',$LedgerId)
foreach ($entry in @(
    @('--request',$Request),
    @('--exam-id',$ExamId),
    @('--attempt-id',$AttemptId),
    @('--question-id',$QuestionId),
    @('--hint-id',$HintId),
    @('--session-id',$SessionId),
    @('--project-id',$ProjectId),
    @('--document-id',$DocumentId),
    @('--document-version',$DocumentVersion),
    @('--document-sha256',$DocumentSha256),
    @('--response-id',$ResponseId),
    @('--reason',$Reason),
    @('--state-dir',$StateDir)
)) {
    if ($entry[1]) { $callArgs += $entry }
}
if ($Deliver) { $callArgs += '--deliver' }
& $pythonRuntime @callArgs
exit $LASTEXITCODE
