# Detached Codex runner for the active SESHAT job; writes a durable exit receipt.
# Invoked as the current Windows user. No auto-merge or task chaining.
$ErrorActionPreference = 'Stop'
$Root = 'C:\Users\Homee\AppData\Local\SESHAT\watch'
$JobFile = Join-Path $Root 'job.json'
$ExitFile = Join-Path $Root 'exit.json'
$Repo = 'C:\projects\seshat'
$Stdout = Join-Path $Root 'stdout.jsonl'
$Stderr = Join-Path $Root 'stderr.log'
$FinalMessage = Join-Path $Root 'last_message.txt'
function Save-Atomic([object] $Data, [string] $Path) {
    $temp = $Path + '.' + $PID + '.tmp'
    $Data | ConvertTo-Json -Depth 8 -Compress | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $Path -Force
}
$ExitCode = 91
$ErrorType = $null
$Started = (Get-Date).ToUniversalTime().ToString('o')
try {
    $job = Get-Content -LiteralPath $JobFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ((& git -C $Repo branch --show-current) -ne [string]$job.branch) { throw 'BRANCH_MISMATCH' }
    if ((& git -C $Repo remote get-url origin) -ne 'https://github.com/Stimurid/SESHAT.git') { throw 'ORIGIN_MISMATCH' }
    if (((& git -C $Repo rev-parse --show-toplevel) -replace '/', '\') -ne $Repo) { throw 'ROOT_MISMATCH' }
    if (Test-Path -LiteralPath $ExitFile) { throw 'ALREADY_HAS_EXIT_RECEIPT' }
    $job.runner_pid = $PID
    $job.started_at_utc = $Started
    Save-Atomic $job $JobFile
    Set-Location -LiteralPath $Repo
    $env:PYTHONIOENCODING = 'utf-8'
    $OutputEncoding = [System.Text.Encoding]::UTF8
    $resume = [string]$job.session_id
    $prompt = Get-Content -LiteralPath (Join-Path $Root 'resume_prompt.txt') -Raw -Encoding UTF8
    # The stream is saved only locally. The final assistant message is a separate receipt.
    $prompt | & codex exec resume --json -c 'sandbox_mode="workspace-write"' -o $FinalMessage $resume '-' 2> $Stderr | Out-File -LiteralPath $Stdout -Encoding UTF8
    $ExitCode = [int]$LASTEXITCODE
} catch {
    $ErrorType = $_.Exception.GetType().Name
    if ($null -ne $_.Exception.Message -and $_.Exception.Message -in @('BRANCH_MISMATCH','ORIGIN_MISMATCH','ROOT_MISMATCH','ALREADY_HAS_EXIT_RECEIPT')) {
        $ErrorType = $_.Exception.Message
    }
    $ExitCode = 91
} finally {
    $branch = (& git -C $Repo branch --show-current 2>$null | Select-Object -First 1)
    $head = (& git -C $Repo rev-parse HEAD 2>$null | Select-Object -First 1)
    $dirty = @(& git -C $Repo status --porcelain=v1 2>$null)
    $record = [ordered]@{
        job_id = if ($job) { [string]$job.job_id } else { 'unknown' }
        start_utc = $Started
        completed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        exit_code = $ExitCode
        error_type = $ErrorType
        branch = [string]$branch
        head_sha = [string]$head
        dirty_file_count = $dirty.Count
        log_path = $Stdout
        final_message_path = $FinalMessage
    }
    Save-Atomic $record $ExitFile
    & (Join-Path $Root 'monitor.ps1') | Out-Null
}
exit $ExitCode
