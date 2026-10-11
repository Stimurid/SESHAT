# Trusted Windows GitHub publisher. NEVER run inside Codex sandbox.
# Restricted to the registered SESHAT task branch; it never merges or approves a PR.
param([Parameter(Mandatory=$true)][string]$JobPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Repo='C:\projects\seshat'
$Root='C:\Users\Homee\AppData\Local\SESHAT\watch'
. (Join-Path $PSScriptRoot 'gate.ps1')
function Need($condition,$reason){if(-not $condition){throw $reason}}

Need (Test-SeshatCanonicalJobPath -JobPath $JobPath -Root $Root) 'UNAUTHORIZED_JOB_PATH'
$job=Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8|ConvertFrom-Json
Need ([string]$job.dispatch_key -cmatch '^pr16-[0-9a-f]{40}-issue17$') 'INVALID_DISPATCH_KEY'
$markerPath=Join-Path (Join-Path $Root 'dispatches') (([string]$job.dispatch_key)+'.json')
Need (Test-Path -LiteralPath $markerPath) 'DISPATCH_MARKER_MISSING'
$marker=Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8|ConvertFrom-Json
Need ((Test-SeshatJobAuthorization -Job $job -Marker $marker) -eq 'ADMIT') 'JOB_NOT_AUTHORIZED'
Assert-SeshatBundleProvenance -Job $job -Repo $Repo -ScriptRoot $PSScriptRoot

$jobId=[string]$job.job_id
$branch=[string]$job.branch
$baseSha=[string]$job.base_sha
$issue=[int]$job.issue_number
$eventPath=Join-Path (Join-Path $Root 'publication-events') ($jobId+'.jsonl')
$nativeAuditPath=Join-Path (Join-Path $Root 'publication-events') ($jobId+'-native.jsonl')
$receiptPath=Join-Path $Root 'publish_receipt.json'
$phase='PRECHECK'
$headSha=$baseSha
$attemptNonce=[guid]::NewGuid().ToString('N')
$mutationStarted=$false
Need ($branch -match '^codex/[a-z0-9][a-z0-9-]{4,79}$') 'UNSAFE_BRANCH_NAME'
Need ($issue -ge 1 -and $issue -le 1000000) 'UNSAFE_ISSUE'
Start-SeshatPublicationAttempt -EventPath $eventPath -ReceiptPath $receiptPath -JobId $jobId -Branch $branch -BaseSha $baseSha

function InvokePublisherNative([string]$file,[string[]]$arguments,[string]$label,[string]$failureClass){
    $result=Invoke-SeshatNativeCommand -FilePath $file -ArgumentList $arguments -WorkingDirectory $Repo -Label $label -AuditPath $nativeAuditPath -JobId $jobId
    Assert-SeshatNativeSuccess -Result $result -FailureClass $failureClass
    return $result
}
function StartMutation([string]$action,[object]$before){
    $script:mutationStarted=$true
    Write-SeshatMutationEvent -Path $eventPath -JobId $jobId -AttemptNonce $attemptNonce -Action $action -Status 'INTENT' -Phase $phase -BeforeWitness $before
}
function RecordMutationReturn([string]$action,[object]$before,[object]$result){
    Write-SeshatMutationEvent -Path $eventPath -JobId $jobId -AttemptNonce $attemptNonce -Action $action -Status 'RETURNED' -Phase $phase -BeforeWitness $before -ExitCode ([int]$result.exit_code)
}
function CompleteMutation([string]$action,[object]$before,[object]$after,[int]$exitCode){
    Write-SeshatMutationEvent -Path $eventPath -JobId $jobId -AttemptNonce $attemptNonce -Action $action -Status 'COMPLETE' -Phase $phase -BeforeWitness $before -AfterWitness $after -ExitCode $exitCode
}
function InvokeMutation([string]$file,[string[]]$arguments,[string]$label,[string]$failureClass,[string]$action,[object]$before){
    StartMutation $action $before
    $result=Invoke-SeshatNativeCommand -FilePath $file -ArgumentList $arguments -WorkingDirectory $Repo -Label $label -AuditPath $nativeAuditPath -JobId $jobId
    RecordMutationReturn $action $before $result
    Assert-SeshatNativeSuccess -Result $result -FailureClass $failureClass
    return $result
}
function AssertRemoteBranchAbsent([string]$label){
    $result=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'ls-remote','--exit-code','--heads','origin',('refs/heads/'+$branch)) -WorkingDirectory $Repo -Label $label -AuditPath $nativeAuditPath -JobId $jobId
    if([int]$result.exit_code -eq 0){throw 'REMOTE_BRANCH_ALREADY_EXISTS'}
    if([int]$result.exit_code -ne 2){throw 'REMOTE_BRANCH_QUERY_FAILED'}
}
function AssertNoPullRequest([string]$label){
    $list=InvokePublisherNative 'gh' @('pr','list','--repo','Stimurid/SESHAT','--head',$branch,'--state','all','--limit','2','--json','number,state,isDraft,baseRefName,headRefName,headRefOid') $label 'GITHUB_PR_LIST_FAILED'
    $existing=@($list.stdout|ConvertFrom-Json)
    Need ($existing.Count -eq 0) 'PREEXISTING_PR_REQUIRES_RECONCILIATION'
}

try{
    $remote=InvokePublisherNative 'git' @('-C',$Repo,'remote','get-url','origin') 'git-remote' 'GIT_REMOTE_FAILED'
    Need ([string]$remote.stdout.Trim() -ceq 'https://github.com/Stimurid/SESHAT.git') 'REMOTE_MISMATCH'
    $currentBranch=InvokePublisherNative 'git' @('-C',$Repo,'branch','--show-current') 'git-branch' 'GIT_BRANCH_FAILED'
    Need ([string]$currentBranch.stdout.Trim() -ceq $branch) 'BRANCH_MISMATCH'
    $head=InvokePublisherNative 'git' @('-C',$Repo,'rev-parse','HEAD') 'git-head-before' 'GIT_HEAD_FAILED'
    Need ([string]$head.stdout.Trim() -ceq $baseSha) 'UNEXPECTED_HEAD_BEFORE_PUBLISH'
    AssertRemoteBranchAbsent 'git-remote-branch-preflight'
    AssertNoPullRequest 'gh-pr-list-preflight'

    $cachedBefore=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'diff','--cached','--quiet') -WorkingDirectory $Repo -Label 'git-index-clean-preflight' -AuditPath $nativeAuditPath -JobId $jobId
    Need ([int]$cachedBefore.exit_code -eq 0) 'PREEXISTING_STAGED_CHANGES'
    $status=InvokePublisherNative 'git' @('-C',$Repo,'-c','core.quotePath=false','status','--porcelain=v1','-uall') 'git-status' 'STATUS_FAILED'
    $statusLines=@(Get-SeshatOutputLines -Text $status.stdout)
    Need ($statusLines.Count -gt 0) 'NO_CODE_CHANGES'
    $paths=@(Get-SeshatStatusPaths -StatusLines $statusLines)
    $pathDecision=Test-SeshatOwnedPathSet -ApprovedPaths @($job.approved_paths) -OwnedPaths @($job.owned_paths) -DirtyPaths $paths
    Need ($pathDecision -eq 'ADMIT') $pathDecision
    Need (Test-Path -LiteralPath (Join-Path $Repo 'docs\S_IMPL_002B_RESULT.md')) 'MISSING_REQUIRED_RESULT_RECEIPT'
    [void](Assert-SeshatChangedFileLimits -Repo $Repo -Paths $paths -MaximumFileBytes 2097152 -MaximumTotalBytes 5242880)

    $phase='BEFORE_COMMIT'
    $addBefore=[ordered]@{head=$baseSha;index='CLEAN';paths_sha256=Get-SeshatTextSha256 -Text (($paths|Sort-Object)-join "`n")}
    $addResult=InvokeMutation 'git' (@('-C',$Repo,'add','--')+$paths) 'git-add' 'GIT_ADD_FAILED' 'git-add' $addBefore
    $stagedResult=InvokePublisherNative 'git' @('-C',$Repo,'diff','--cached','--name-only') 'git-staged-paths' 'STAGED_PATH_QUERY_FAILED'
    $staged=@(Get-SeshatOutputLines -Text $stagedResult.stdout)
    Need (Test-SeshatExactStringSet -Left $staged -Right @($job.owned_paths)) 'STAGED_PATH_SET_MISMATCH'
    CompleteMutation 'git-add' $addBefore ([ordered]@{staged_paths_sha256=Get-SeshatTextSha256 -Text (($staged|Sort-Object)-join "`n");staged_count=$staged.Count}) ([int]$addResult.exit_code)

    $indexLines=InvokePublisherNative 'git' (@('-C',$Repo,'ls-files','-s','--')+$paths) 'git-staged-objects' 'STAGED_OBJECT_QUERY_FAILED'
    $objectTotal=[long]0
    foreach($line in @(Get-SeshatOutputLines -Text $indexLines.stdout)){
        Need ($line -cmatch '^100[67][0-9]{2} ([0-9a-f]{40}|[0-9a-f]{64}) 0\t') 'STAGED_OBJECT_NOT_REGULAR_FILE'
        $sizeResult=InvokePublisherNative 'git' @('-C',$Repo,'cat-file','-s',$Matches[1]) 'git-staged-object-size' 'STAGED_OBJECT_SIZE_FAILED'
        $objectSize=[long]$sizeResult.stdout.Trim()
        Need ($objectSize -le 2097152) 'STAGED_OBJECT_FILE_SIZE_LIMIT_EXCEEDED'
        $objectTotal+=$objectSize
        Need ($objectTotal -le 5242880) 'STAGED_OBJECT_TOTAL_SIZE_LIMIT_EXCEEDED'
    }
    [void](InvokePublisherNative 'git' @('-C',$Repo,'diff','--cached','--check') 'git-diff-check' 'DIFF_CHECK_FAILED')
    $numstat=InvokePublisherNative 'git' (@('-C',$Repo,'diff','--cached','--numstat','--')+$paths) 'git-diff-numstat' 'DIFF_NUMSTAT_FAILED'
    $numstatDecision=Test-SeshatNumstatTextOnly -Lines @(Get-SeshatOutputLines -Text $numstat.stdout)
    Need ($numstatDecision -eq 'ADMIT') $numstatDecision
    $artifactDir=Join-Path (Join-Path $Root 'publication-artifacts') $jobId
    New-Item -ItemType Directory -Path $artifactDir -Force|Out-Null
    $diffPath=Join-Path $artifactDir ('staged-diff-'+$attemptNonce+'.patch')
    $diffErrorPath=Join-Path $artifactDir ('staged-diff-'+$attemptNonce+'.stderr')
    $diffSha=$null
    try{
        $diffResult=Invoke-SeshatStreamingNativeCommand -FilePath 'git' -ArgumentList (@('-C',$Repo,'diff','--cached','--no-ext-diff','--unified=0','--')+$paths) -WorkingDirectory $Repo -Label 'git-diff-scan' -StandardOutputPath $diffPath -StandardErrorPath $diffErrorPath -MaximumStandardOutputBytes 8388608 -MaximumStandardErrorBytes 65536 -AuditPath $nativeAuditPath -JobId $jobId
        Need (-not [bool]$diffResult.limit_exceeded -and [int]$diffResult.exit_code -eq 0) 'DIFF_STREAM_FAILED_OR_TOO_LARGE'
        $scanDecision=Test-SeshatAddedDiffFile -Path $diffPath -MaximumBytes 8388608
        Need ($scanDecision -eq 'ADMIT') $scanDecision
        $diffSha=Get-SeshatFileSha256 -Path $diffPath
    }finally{
        foreach($temporaryDiff in @($diffPath,$diffErrorPath)){if(Test-Path -LiteralPath $temporaryDiff){Remove-Item -LiteralPath $temporaryDiff -Force}}
    }
    $phase='STAGED_ONLY'
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha

    $commitBefore=[ordered]@{head=$baseSha;staged_diff_sha256=$diffSha}
    $msg="impl(s2b): bounded reconciliation controller (#$issue)"
    $commitResult=InvokeMutation 'git' @('-C',$Repo,'commit','-m',$msg) 'git-commit' 'GIT_COMMIT_FAILED' 'git-commit' $commitBefore
    $headResult=InvokePublisherNative 'git' @('-C',$Repo,'rev-parse','HEAD') 'git-head-after' 'GIT_HEAD_FAILED'
    $headSha=[string]$headResult.stdout.Trim()
    Need ($headSha -cmatch '^[0-9a-f]{40}$' -and $headSha -cne $baseSha) 'INVALID_COMMITTED_HEAD'
    CompleteMutation 'git-commit' $commitBefore ([ordered]@{head=$headSha}) ([int]$commitResult.exit_code)
    $phase='COMMITTED_ONLY'
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha

    AssertRemoteBranchAbsent 'git-remote-branch-before-push'
    AssertNoPullRequest 'gh-pr-list-before-push'
    $pushBefore=[ordered]@{local_head=$headSha;remote_ref='ABSENT';expected_remote_oid='EMPTY'}
    $env:GIT_TERMINAL_PROMPT='0'
    $pushResult=InvokeMutation 'git' @('-C',$Repo,'push','--atomic','--set-upstream','origin',('HEAD:refs/heads/'+$branch),('--force-with-lease=refs/heads/'+$branch+':')) 'git-push-create-only' 'GIT_CREATE_ONLY_PUSH_FAILED' 'git-push-create-only' $pushBefore
    $remoteAfter=InvokePublisherNative 'git' @('-C',$Repo,'ls-remote','--heads','origin',('refs/heads/'+$branch)) 'git-remote-branch-after-push' 'REMOTE_BRANCH_VERIFY_FAILED'
    $remoteLines=@(Get-SeshatOutputLines -Text $remoteAfter.stdout)
    Need ($remoteLines.Count -eq 1 -and $remoteLines[0] -cmatch ('^'+[regex]::Escape($headSha)+'\s')) 'REMOTE_BRANCH_POST_PUSH_MISMATCH'
    CompleteMutation 'git-push-create-only' $pushBefore ([ordered]@{remote_head=$headSha}) ([int]$pushResult.exit_code)
    $phase='PUSHED_WITHOUT_PR'
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha

    AssertNoPullRequest 'gh-pr-list-before-create'
    $bodyFile=Join-Path $artifactDir 'pr-body.md'
    @"
Implements #$issue from pre-approved SESHAT dispatch.
Branch: $branch
Commit: $headSha

Codex generated changes in a restricted sandbox. Trusted host validated the scoped file set,
bounded content/object/diff limits and credential patterns before a create-only branch push.
Isolated GitHub PR CI runs tests after publication. No local execution, auto-merge or semantic approval.
Result: docs/S_IMPL_002B_RESULT.md
Coordination: https://github.com/Stimurid/SESHAT/issues/6
"@|Set-Content -LiteralPath $bodyFile -Encoding UTF8
    $prBefore=[ordered]@{remote_head=$headSha;matching_pr_count=0}
    $createResult=InvokeMutation 'gh' @('pr','create','--repo','Stimurid/SESHAT','--draft','--base','main','--head',$branch,'--title','S-IMPL-002B: bounded reconciliation controller','--body-file',$bodyFile) 'gh-pr-create' 'GITHUB_PR_CREATE_FAILED' 'gh-pr-create' $prBefore
    $view=InvokePublisherNative 'gh' @('pr','view',$branch,'--repo','Stimurid/SESHAT','--json','number,url,state,isDraft,baseRefName,headRefName,headRefOid') 'gh-pr-view' 'GITHUB_PR_VERIFY_QUERY_FAILED'
    $publishedPr=$view.stdout|ConvertFrom-Json
    $prDecision=Test-SeshatPublishedPullRequest -PullRequest $publishedPr -Branch $branch -HeadSha $headSha
    Need ($prDecision -eq 'ADMIT') $prDecision
    CompleteMutation 'gh-pr-create' $prBefore ([ordered]@{pr_number=[int]$publishedPr.number;head_sha=[string]$publishedPr.headRefOid;state=[string]$publishedPr.state;draft=[bool]$publishedPr.isDraft}) ([int]$createResult.exit_code)
    $phase='DRAFT_PUBLISHED'
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha
    $result=[ordered]@{
        status='PUBLISHED_DRAFT_PR';job_id=$jobId;issue=$issue;branch=$branch;head_sha=$headSha
        pr_number=[int]$publishedPr.number;pr_url=[string]$publishedPr.url
        pr_state=[string]$publishedPr.state;pr_is_draft=[bool]$publishedPr.isDraft
        pr_base=[string]$publishedPr.baseRefName;pr_head=[string]$publishedPr.headRefName
        changed_paths=$paths;stage_event_path=$eventPath;native_audit_path=$nativeAuditPath
        attempt_nonce=$attemptNonce;push_policy='CREATE_ONLY_EMPTY_LEASE';content_limits='2MiB_FILE_5MiB_TOTAL_8MiB_DIFF'
        ci_tests='PENDING_GITHUB_PR_CI';local_code_execution='NONE'
        published_at_utc=(Get-Date).ToUniversalTime().ToString('o')
    }
    Write-SeshatJsonCreateNew -Value $result -Path $receiptPath
    Write-Output ($result|ConvertTo-Json -Compress -Depth 8)
}catch{
    $errorClass=Get-SeshatSafeErrorClass -ErrorRecord $_
    if($mutationStarted){$phase='RECONCILIATION_REQUIRED'}
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha -ErrorClass $errorClass
    [Console]::Error.WriteLine(('PUBLISH_FAILED error_class={0} phase={1}' -f $errorClass,$phase))
    exit 94
}
