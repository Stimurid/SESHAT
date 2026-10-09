# SESHAT Codex completion watchdog (read-only with respect to repository).
# Runs every five minutes via the user's Windows Task Scheduler.
$ErrorActionPreference = 'Stop'
$Root = 'C:\Users\Homee\AppData\Local\SESHAT\watch'
$Repo = 'C:\projects\seshat'
$JobPath = Join-Path $Root 'job.json'
$StatePath = Join-Path $Root 'state.json'
$EventPath = Join-Path $Root 'events.jsonl'
$ExitPath = Join-Path $Root 'exit.json'
$Now = (Get-Date).ToUniversalTime()
$Mutex = New-Object System.Threading.Mutex($false, 'Local\SESHAT_Codex_Watchdog')
if (-not $Mutex.WaitOne(0)) { exit 0 }
try {
    if (-not (Test-Path -LiteralPath $Root)) { New-Item -ItemType Directory -Path $Root -Force | Out-Null }
    function Save-JsonAtomic([object] $Data, [string] $Path) {
        $temp = $Path + '.' + $PID + '.tmp'
        $Data | ConvertTo-Json -Depth 8 -Compress | Set-Content -LiteralPath $temp -Encoding UTF8
        Move-Item -LiteralPath $temp -Destination $Path -Force
    }
    $job = $null
    if (Test-Path -LiteralPath $JobPath) {
        $job = Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    $branch = ''
    $head = ''
    $dirty = @()
    if (Test-Path -LiteralPath (Join-Path $Repo '.git')) {
        $branch = (& git -C $Repo branch --show-current 2>$null | Select-Object -First 1)
        $head = (& git -C $Repo rev-parse HEAD 2>$null | Select-Object -First 1)
        $dirty = @(& git -C $Repo status --porcelain=v1 2>$null)
    }
    $alive = $false
    $runnerPid = 0
    $exitCode = $null
    if ($null -ne $job) {
        $runnerPid = [int]$job.runner_pid
        if ($runnerPid -gt 0) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$runnerPid" -ErrorAction SilentlyContinue
            if ($null -ne $proc -and $proc.CommandLine -like '*run-codex.ps1*') {
                $alive = $true
            }
        }
    }
    $state = 'IDLE_UNREGISTERED'
    if ($null -ne $job) {
        if (Test-Path -LiteralPath $ExitPath) {
            $exitRec = Get-Content -LiteralPath $ExitPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $exitCode = [int]$exitRec.exit_code
            if ($exitCode -eq 0) { $state = 'CODEX_EXITED_OK_VERIFY_OUTPUT' }
            else { $state = 'CODEX_EXITED_ERROR' }
        } elseif ($alive) {
            $state = 'RUNNING'
            $outPath = Join-Path $Root 'stdout.jsonl'
            if (Test-Path -LiteralPath $outPath) {
                $idleMinutes = ($Now - (Get-Item -LiteralPath $outPath).LastWriteTimeUtc).TotalMinutes
                if ($idleMinutes -gt 120) { $state = 'POSSIBLE_STALL' }
            }
        } elseif ($dirty.Count -gt 0) {
            $state = 'LOST_SESSION_DIRTY_WORKTREE'
        } else {
            $state = 'LOST_SESSION_NO_EXIT_RECEIPT'
        }
        if ($branch -ne [string]$job.branch) { $state = 'BRANCH_MISMATCH' }
    } elseif ($dirty.Count -gt 0) {
        $state = 'UNREGISTERED_DIRTY_WORKTREE'
    }
    $result = [ordered]@{
        checked_at_utc = $Now.ToString('o')
        state = $state
        job_id = if ($job) { [string]$job.job_id } else { $null }
        github_issue = if ($job) { [string]$job.issue_url } else { $null }
        session_id = if ($job) { [string]$job.session_id } else { $null }
        runner_pid = $runnerPid
        runner_alive = $alive
        exit_code = $exitCode
        repo = $Repo
        branch = [string]$branch
        head_sha = [string]$head
        dirty_file_count = $dirty.Count
        stdout_log = Join-Path $Root 'stdout.jsonl'
        stderr_log = Join-Path $Root 'stderr.log'
        exit_receipt = $ExitPath
    }
    $previous = $null
    if (Test-Path -LiteralPath $StatePath) {
        try { $previous = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $previous = $null }
    }
    $previousKey = if ($previous) { "$($previous.state)|$($previous.head_sha)|$($previous.dirty_file_count)|$($previous.exit_code)" } else { '' }
    $currentKey = "$($result.state)|$($result.head_sha)|$($result.dirty_file_count)|$($result.exit_code)"
    Save-JsonAtomic $result $StatePath
    if ($previousKey -ne $currentKey) {
        $event = [ordered]@{
            at_utc = $Now.ToString('o')
            state = $state
            head_sha = [string]$head
            dirty_file_count = $dirty.Count
            exit_code = $exitCode
            job_id = $result.job_id
        }
        ($event | ConvertTo-Json -Compress) | Add-Content -LiteralPath $EventPath -Encoding UTF8
    }
    Write-Output ($result | ConvertTo-Json -Compress)
} catch {
    $safeError = [ordered]@{
        at_utc = (Get-Date).ToUniversalTime().ToString('o')
        state = 'WATCHDOG_ERROR'
        error_type = $_.Exception.GetType().Name
    }
    ($safeError | ConvertTo-Json -Compress) | Add-Content -LiteralPath (Join-Path $Root 'watchdog_errors.jsonl') -Encoding UTF8
    Write-Output ($safeError | ConvertTo-Json -Compress)
    exit 1
} finally {
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}
