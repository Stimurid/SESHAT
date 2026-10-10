# Autonomous SESHAT Codex execution with durable local result, followed by trusted publishing.
# Starts only from dispatch.ps1 after explicit acceptance gate, never itself merges PRs.
param([Parameter(Mandatory=$true)][string]$JobPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Root='C:\Users\Homee\AppData\Local\SESHAT\watch'
$Repo='C:\projects\seshat'
. (Join-Path $PSScriptRoot 'gate.ps1')
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
    if(-not (Test-SeshatCanonicalJobPath -JobPath $JobPath -Root $Root)){throw 'UNAUTHORIZED_JOB_PATH'}
    Assert-SeshatExitReceiptAbsent -Path $ExitPath
    $job=Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if(-not ([string]$job.dispatch_key -cmatch '^pr16-[0-9a-f]{40}-issue17$')){throw 'INVALID_DISPATCH_KEY'}
    $markerPath=Join-Path (Join-Path $Root 'dispatches') (([string]$job.dispatch_key)+'.json')
    if(-not(Test-Path -LiteralPath $markerPath)){throw 'DISPATCH_MARKER_MISSING'}
    $marker=Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8|ConvertFrom-Json
    $authorization=Test-SeshatJobAuthorization -Job $job -Marker $marker
    if($authorization -ne 'ADMIT'){throw $authorization}
    Assert-SeshatBundleProvenance -Job $job -Repo $Repo -ScriptRoot $PSScriptRoot
} catch {
    [Console]::Error.WriteLine([string]$_.Exception.Message)
    exit 93
}
try {
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
    $statusLines=@(& git -C $Repo -c core.quotePath=false status --porcelain=v1 -uall)
    if($LASTEXITCODE -ne 0){throw 'STATUS_FAILED'}
    $ownedPaths=@(Get-SeshatStatusPaths -StatusLines $statusLines)
    $pathDecision=Test-SeshatOwnedPathSet -ApprovedPaths @($job.approved_paths) -OwnedPaths $ownedPaths -DirtyPaths $ownedPaths
    if($pathDecision -ne 'ADMIT'){throw $pathDecision}
    if($ownedPaths -cnotcontains 'docs/S_IMPL_002B_RESULT.md'){throw 'MISSING_REQUIRED_RESULT_RECEIPT'}
    $job|Add-Member -NotePropertyName owned_paths -NotePropertyValue $ownedPaths -Force
    AtomicJson $job $JobPath
    & (Join-Path $PSScriptRoot 'publish.ps1') -JobPath $JobPath *> $ResultLog
    if($LASTEXITCODE -ne 0){throw 'PUBLISH_PROCESS_NONZERO'}
    if(-not (Test-Path (Join-Path $Root 'publish_receipt.json'))){throw 'PUBLISH_RECEIPT_MISSING'}
    $r=Get-Content (Join-Path $Root 'publish_receipt.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if([string]$r.status -ne 'PUBLISHED_DRAFT_PR'){throw 'PUBLISH_NOT_CONFIRMED'}
    if([string]$r.job_id -cne [string]$job.job_id -or [int]$r.issue -ne [int]$job.issue_number){throw 'PUBLISH_RECEIPT_JOB_MISMATCH'}
    if([string]$r.branch -cne [string]$job.branch -or [int]$r.pr_number -le 0){throw 'PUBLISH_RECEIPT_PR_MISMATCH'}
    $publishedHead=[string](& git -C $Repo rev-parse HEAD|Select-Object -First 1)
    if([string]$r.head_sha -cne $publishedHead -or [string]$r.pr_state -cne 'OPEN' -or -not [bool]$r.pr_is_draft -or [string]$r.pr_base -cne 'main' -or [string]$r.pr_head -cne [string]$job.branch){throw 'PUBLISH_RECEIPT_VERIFICATION_MISMATCH'}
    $PublishStatus='PUBLISHED_DRAFT_PR'
    $ExitCode=0
} catch {
    $ErrorType=$_.Exception.GetType().Name
    if($_.Exception.Message -in @('JOB_REPOSITORY_MISMATCH','ORIGIN_MISMATCH','BRANCH_MISMATCH','BASE_MISMATCH','DIRTY_BEFORE_START','CODEX_NONZERO','STATUS_FAILED','BLOCK_APPROVED_PATH_SET_MISMATCH','BLOCK_EMPTY_JOB_OWNED_MANIFEST','BLOCK_UNAPPROVED_JOB_PATH','BLOCK_DIRTY_PATH_SET_MISMATCH','MISSING_REQUIRED_RESULT_RECEIPT','PUBLISH_PROCESS_NONZERO','PUBLISH_RECEIPT_MISSING','PUBLISH_NOT_CONFIRMED','PUBLISH_RECEIPT_JOB_MISMATCH','PUBLISH_RECEIPT_PR_MISMATCH','PUBLISH_RECEIPT_VERIFICATION_MISMATCH')){
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
    Write-SeshatJsonCreateNew -Value $receipt -Path $ExitPath
    & (Join-Path $PSScriptRoot 'monitor.ps1') *> $null
}
exit $ExitCode
