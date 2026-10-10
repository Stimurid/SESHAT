# Autonomous SESHAT Codex execution with durable local result, followed by trusted publishing.
# Starts only from dispatch.ps1 after explicit acceptance gate, never itself merges PRs.
param([Parameter(Mandatory=$true)][string]$JobPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Root='C:\Users\Homee\AppData\Local\SESHAT\watch'
$Repo='C:\projects\seshat'
$ExitPath=Join-Path $Root 'exit.json'
$Stdout=Join-Path $Root 'stdout.jsonl'
$Stderr=Join-Path $Root 'stderr.log'
$LastMessage=Join-Path $Root 'last_message.txt'
$ResultLog=Join-Path $Root 'publisher-output.log'
$ExitCode=91
$ErrorType=$null
$PublishStatus='NOT_STARTED'
$Started=(Get-Date).ToUniversalTime().ToString('o')
$job=$null
function AtomicJson([object]$value,[string]$path) {
    $temp=$path+'.'+$PID+'.tmp'
    $value | ConvertTo-Json -Depth 8 -Compress | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $path -Force
}
try {
    if(Test-Path $ExitPath){throw 'EXIT_RECEIPT_ALREADY_EXISTS'}
    $job=Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if([string]$job.repo -ne $Repo){throw 'JOB_REPOSITORY_MISMATCH'}
    if([string](& git -C $Repo remote get-url origin) -ne 'https://github.com/Stimurid/SESHAT.git'){throw 'ORIGIN_MISMATCH'}
    if([string](& git -C $Repo branch --show-current) -ne [string]$job.branch){throw 'BRANCH_MISMATCH'}
    if([string](& git -C $Repo rev-parse HEAD) -ne [string]$job.base_sha){throw 'BASE_MISMATCH'}
    if(@(& git -C $Repo status --porcelain=v1).Count -ne 0){throw 'DIRTY_BEFORE_START'}
    $job.runner_pid=$PID
    $job.started_at_utc=$Started
    AtomicJson $job $JobPath
    Set-Location -LiteralPath $Repo
    $env:PYTHONIOENCODING='utf-8'
    $OutputEncoding=[System.Text.Encoding]::UTF8
    $prompt=Get-Content -LiteralPath (Join-Path $Root 'task_prompt.txt') -Raw -Encoding UTF8
    # Sandbox intentionally cannot modify .git and cannot use GitHub credentials.
    # Publishing occurs in the trusted host process, not by broadening Codex privileges.
    $prompt | & codex exec --json --sandbox workspace-write -C $Repo -o $LastMessage - 2> $Stderr | Out-File -LiteralPath $Stdout -Encoding UTF8
    $ExitCode=[int]$LASTEXITCODE
    if($ExitCode -ne 0){throw 'CODEX_NONZERO'}
    & (Join-Path $PSScriptRoot 'publish.ps1') -JobPath $JobPath *> $ResultLog
    if($LASTEXITCODE -ne 0){throw 'PUBLISH_PROCESS_NONZERO'}
    if(-not (Test-Path (Join-Path $Root 'publish_receipt.json'))){throw 'PUBLISH_RECEIPT_MISSING'}
    $r=Get-Content (Join-Path $Root 'publish_receipt.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if([string]$r.status -ne 'PUBLISHED_DRAFT_PR'){throw 'PUBLISH_NOT_CONFIRMED'}
    $PublishStatus='PUBLISHED_DRAFT_PR'
    $ExitCode=0
} catch {
    $ErrorType=$_.Exception.GetType().Name
    if($_.Exception.Message -in @('EXIT_RECEIPT_ALREADY_EXISTS','JOB_REPOSITORY_MISMATCH','ORIGIN_MISMATCH','BRANCH_MISMATCH','BASE_MISMATCH','DIRTY_BEFORE_START','CODEX_NONZERO','PUBLISH_PROCESS_NONZERO','PUBLISH_RECEIPT_MISSING','PUBLISH_NOT_CONFIRMED')){
        $ErrorType=$_.Exception.Message
    }
    if($ExitCode -eq 0){$ExitCode=92}
} finally {
    $head=[string](& git -C $Repo rev-parse HEAD 2>$null | Select-Object -First 1)
    $branch=[string](& git -C $Repo branch --show-current 2>$null | Select-Object -First 1)
    $dirty=@(& git -C $Repo status --porcelain=v1 2>$null)
    $receipt=[ordered]@{
        job_id=if($job){[string]$job.job_id}else{'unknown'}
        start_utc=$Started; completed_at_utc=(Get-Date).ToUniversalTime().ToString('o')
        exit_code=$ExitCode; error_type=$ErrorType; publish_status=$PublishStatus
        branch=$branch; head_sha=$head; dirty_file_count=$dirty.Count
        log_path=$Stdout; final_message_path=$LastMessage
        publication_receipt=Join-Path $Root 'publish_receipt.json'
    }
    AtomicJson $receipt $ExitPath
    & (Join-Path $PSScriptRoot 'monitor.ps1') *> $null
}
exit $ExitCode
