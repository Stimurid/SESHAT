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
$PublisherStderr=Join-Path $Root 'publisher-stderr.log'
$ExitCode=91
$PublisherExitCode=$null
$PublisherErrorClass=$null
$CodexStreamStatus='NOT_STARTED'
$CodexStdoutBytes=$null
$CodexStderrBytes=$null
$CodexLimitStream=$null
$PowerShellExe=(Get-Process -Id $PID).Path
$ErrorType=$null
$PublishStatus='NOT_STARTED'
$CodexLaunchProvenance=$null
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
    $executorAudit=Join-Path (Join-Path $Root 'publication-events') (([string]$job.job_id)+'-executor-native.jsonl')
    function InvokeExecutorNative([string]$file,[string[]]$arguments,[string]$label,[string]$failureClass,[string]$stdin){
        if($PSBoundParameters.ContainsKey('stdin')){
            $result=Invoke-SeshatNativeCommand -FilePath $file -ArgumentList $arguments -WorkingDirectory $Repo -Label $label -AuditPath $executorAudit -JobId ([string]$job.job_id) -StandardInputText $stdin
        }else{
            $result=Invoke-SeshatNativeCommand -FilePath $file -ArgumentList $arguments -WorkingDirectory $Repo -Label $label -AuditPath $executorAudit -JobId ([string]$job.job_id)
        }
        Assert-SeshatNativeSuccess -Result $result -FailureClass $failureClass
        return $result
    }
    if([string]$job.repo -ne $Repo){throw 'JOB_REPOSITORY_MISMATCH'}
    $origin=InvokeExecutorNative 'git' @('-C',$Repo,'remote','get-url','origin') 'executor-git-origin' 'ORIGIN_QUERY_FAILED'
    if($origin.stdout.Trim() -cne 'https://github.com/Stimurid/SESHAT.git'){throw 'ORIGIN_MISMATCH'}
    $branchBefore=InvokeExecutorNative 'git' @('-C',$Repo,'branch','--show-current') 'executor-git-branch' 'BRANCH_QUERY_FAILED'
    if($branchBefore.stdout.Trim() -cne [string]$job.branch){throw 'BRANCH_MISMATCH'}
    $headBefore=InvokeExecutorNative 'git' @('-C',$Repo,'rev-parse','HEAD') 'executor-git-head' 'HEAD_QUERY_FAILED'
    if($headBefore.stdout.Trim() -cne [string]$job.base_sha){throw 'BASE_MISMATCH'}
    $clean=InvokeExecutorNative 'git' @('-C',$Repo,'status','--porcelain=v1') 'executor-git-status-before' 'STATUS_FAILED'
    if(@(Get-SeshatOutputLines -Text $clean.stdout).Count -ne 0){throw 'DIRTY_BEFORE_START'}
    Set-SeshatRunnerStart -Job $job -RunnerPid $PID -StartedUtc $Started
    AtomicJson $job $JobPath
    Set-Location -LiteralPath $Repo
    $env:PYTHONIOENCODING='utf-8'
    $OutputEncoding=[System.Text.Encoding]::UTF8
    $prompt=Get-Content -LiteralPath (Join-Path $Root 'task_prompt.txt') -Raw -Encoding UTF8
    # Sandbox intentionally cannot modify .git and cannot use GitHub credentials.
    # Publishing occurs in the trusted host process, not by broadening Codex privileges.
    $codexLaunch=Resolve-SeshatCodexLaunch -ExpectedBinding $job.codex_launch_policy
    $CodexLaunchProvenance=$codexLaunch.provenance
    $CodexStreamStatus='STARTING'
    try{
        $codexResult=Invoke-SeshatStreamingNativeCommand -FilePath $codexLaunch.file_path -ArgumentList (@($codexLaunch.argv_prefix)+@('exec','--json','--sandbox','workspace-write','-C',$Repo,'-o',$LastMessage,'-')) -WorkingDirectory $Repo -Label 'codex-exec' -StandardOutputPath $Stdout -StandardErrorPath $Stderr -MaximumStandardOutputBytes 67108864 -MaximumStandardErrorBytes 8388608 -AuditPath $executorAudit -JobId ([string]$job.job_id) -StandardInputText $prompt
    }catch{
        $CodexStreamStatus='FAILED'
        throw
    }finally{
        Close-SeshatCodexLaunch -Launch $codexLaunch
    }
    $ExitCode=[int]$codexResult.exit_code
    $CodexStreamStatus=[string]$codexResult.status
    $CodexStdoutBytes=[long]$codexResult.stdout_bytes
    $CodexStderrBytes=[long]$codexResult.stderr_bytes
    $CodexLimitStream=$codexResult.limit_stream
    if($codexResult.limit_exceeded){throw 'CODEX_OUTPUT_LIMIT_EXCEEDED'}
    if($ExitCode -ne 0){throw 'CODEX_NONZERO'}
    $statusResult=InvokeExecutorNative 'git' @('-C',$Repo,'-c','core.quotePath=false','status','--porcelain=v1','-uall') 'executor-git-status-after' 'STATUS_FAILED'
    $statusLines=@(Get-SeshatOutputLines -Text $statusResult.stdout)
    $ownedPaths=@(Get-SeshatStatusPaths -StatusLines $statusLines)
    $pathDecision=Test-SeshatOwnedPathSet -ApprovedPaths @($job.approved_paths) -OwnedPaths $ownedPaths -DirtyPaths $ownedPaths
    if($pathDecision -ne 'ADMIT'){throw $pathDecision}
    if($ownedPaths -cnotcontains 'docs/S_IMPL_002B_RESULT.md'){throw 'MISSING_REQUIRED_RESULT_RECEIPT'}
    $job|Add-Member -NotePropertyName owned_paths -NotePropertyValue $ownedPaths -Force
    AtomicJson $job $JobPath
    $publisherResult=Invoke-SeshatNativeCommand -FilePath $PowerShellExe -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'publish.ps1'),'-JobPath',$JobPath) -WorkingDirectory $Repo -Label 'publisher-child' -AuditPath $executorAudit -JobId ([string]$job.job_id)
    $publisherResult.stdout|Set-Content -LiteralPath $ResultLog -Encoding UTF8
    $publisherSafeStderr=ConvertTo-SeshatSanitizedLogText -Text $publisherResult.stderr
    $publisherSafeStderr|Set-Content -LiteralPath $PublisherStderr -Encoding UTF8
    $PublisherExitCode=[int]$publisherResult.exit_code
    if($publisherSafeStderr -cmatch 'PUBLISH_FAILED error_class=([A-Z][A-Z0-9_]{2,127}) phase=([A-Z_]+)'){$PublisherErrorClass=$Matches[1]}
    if($PublisherExitCode -ne 0){throw 'PUBLISH_PROCESS_NONZERO'}
    if(-not (Test-Path (Join-Path $Root 'publish_receipt.json'))){throw 'PUBLISH_RECEIPT_MISSING'}
    try{$r=Get-Content (Join-Path $Root 'publish_receipt.json') -Raw -Encoding UTF8|ConvertFrom-Json}catch{throw 'PUBLISH_RECEIPT_INVALID'}
    $publishedHeadResult=InvokeExecutorNative 'git' @('-C',$Repo,'rev-parse','HEAD') 'executor-git-published-head' 'HEAD_QUERY_FAILED'
    $publishedHead=$publishedHeadResult.stdout.Trim()
    $receiptDecision=Test-SeshatPublicationReceipt -Receipt $r -Job $job -HeadSha $publishedHead
    if($receiptDecision -ne 'ADMIT'){throw $receiptDecision}
    $PublishStatus='PUBLISHED_DRAFT_PR'
    $ExitCode=0
} catch {
    $ErrorType=$_.Exception.GetType().Name
    if($_.Exception.Message -in @('JOB_REPOSITORY_MISMATCH','ORIGIN_QUERY_FAILED','ORIGIN_MISMATCH','BRANCH_QUERY_FAILED','BRANCH_MISMATCH','HEAD_QUERY_FAILED','BASE_MISMATCH','DIRTY_BEFORE_START','CODEX_OUTPUT_LIMIT_EXCEEDED','CODEX_NONZERO','STATUS_FAILED','BLOCK_APPROVED_PATH_SET_MISMATCH','BLOCK_EMPTY_JOB_OWNED_MANIFEST','BLOCK_UNAPPROVED_JOB_PATH','BLOCK_DIRTY_PATH_SET_MISMATCH','MISSING_REQUIRED_RESULT_RECEIPT','PUBLISH_PROCESS_NONZERO','PUBLISH_RECEIPT_MISSING','PUBLISH_RECEIPT_INVALID','BLOCK_PUBLISH_STATUS','BLOCK_PUBLISH_JOB_MISMATCH','BLOCK_PUBLISH_HEAD_MISMATCH','BLOCK_PUBLISH_PR_STATE','BLOCK_PUBLISH_PR_REFS','BLOCK_MALFORMED_PUBLICATION_RECEIPT')){
        $ErrorType=$_.Exception.Message
    }elseif($_.Exception.Message -cmatch '^(CODEX|TRUSTED)_[A-Z0-9_]+$'){
        $ErrorType=$_.Exception.Message
    }
    if($ExitCode -eq 0){$ExitCode=92}
} finally {
    $head=$null;$branch=$null;$dirty=@()
    try{$finalHead=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'rev-parse','HEAD') -WorkingDirectory $Repo -Label 'executor-final-head';if($finalHead.exit_code -eq 0){$head=$finalHead.stdout.Trim()}}catch{}
    try{$finalBranch=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'branch','--show-current') -WorkingDirectory $Repo -Label 'executor-final-branch';if($finalBranch.exit_code -eq 0){$branch=$finalBranch.stdout.Trim()}}catch{}
    try{$finalStatus=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'status','--porcelain=v1') -WorkingDirectory $Repo -Label 'executor-final-status';if($finalStatus.exit_code -eq 0){$dirty=@(Get-SeshatOutputLines -Text $finalStatus.stdout)}}catch{}
    $receipt=[ordered]@{
        job_id=if($job){[string]$job.job_id}else{'unknown'}
        start_utc=$Started; completed_at_utc=(Get-Date).ToUniversalTime().ToString('o')
        exit_code=$ExitCode; error_type=$ErrorType; publish_status=$PublishStatus
        publisher_exit_code=$PublisherExitCode;publisher_error_class=$PublisherErrorClass
        codex_stream_status=$CodexStreamStatus;codex_stdout_bytes=$CodexStdoutBytes
        codex_stderr_bytes=$CodexStderrBytes;codex_limit_stream=$CodexLimitStream
        codex_launch_provenance=$CodexLaunchProvenance
        publisher_stdout_path=$ResultLog;publisher_stderr_path=$PublisherStderr
        branch=$branch; head_sha=$head; dirty_file_count=$dirty.Count
        log_path=$Stdout; final_message_path=$LastMessage
        publication_receipt=Join-Path $Root 'publish_receipt.json'
    }
    Write-SeshatJsonCreateNew -Value $receipt -Path $ExitPath
    try{[void](Invoke-SeshatNativeCommand -FilePath $PowerShellExe -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'monitor.ps1')) -WorkingDirectory $Repo -Label 'monitor-after-exit')}catch{}
}
exit $ExitCode
