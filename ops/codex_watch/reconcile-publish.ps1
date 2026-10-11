# Side-effect-free publication readback. It never stages, commits, pushes, creates,
# edits, closes, or merges a pull request.
param([Parameter(Mandatory=$true)][string]$JobPath,[switch]$SkipGithub)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Repo='C:\projects\seshat'
$Root='C:\Users\Homee\AppData\Local\SESHAT\watch'
. (Join-Path $PSScriptRoot 'gate.ps1')

if(-not(Test-SeshatCanonicalJobPath -JobPath $JobPath -Root $Root)){throw 'UNAUTHORIZED_JOB_PATH'}
$job=Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8|ConvertFrom-Json
$jobId=[string]$job.job_id
$eventPath=Join-Path (Join-Path $Root 'publication-events') ($jobId+'.jsonl')
$receiptPath=Join-Path $Root 'publish_receipt.json'
$events=@()
$eventsInvalid=$false
if(Test-Path -LiteralPath $eventPath){
    foreach($line in @(Get-Content -LiteralPath $eventPath -Encoding UTF8|Where-Object{$_})){
        try{$events+=($line|ConvertFrom-Json)}catch{$eventsInvalid=$true}
    }
}
$stageEvents=@($events|Where-Object{[string]$_.schema -ceq 'seshat.publication-stage.v1'})
$mutationEvents=@($events|Where-Object{[string]$_.schema -ceq 'seshat.publication-mutation.v2'})
$latest=if($stageEvents.Count -gt 0){$stageEvents[-1]}else{$null}
$latestMutation=if($mutationEvents.Count -gt 0){$mutationEvents[-1]}else{$null}
$phase=if($latest -and $latest.PSObject.Properties['phase']){[string]$latest.phase}else{$null}
$validPhases=@('PRECHECK','BEFORE_COMMIT','STAGED_ONLY','COMMITTED_ONLY','PUSHED_WITHOUT_PR','DRAFT_PUBLISHED','RECONCILIATION_REQUIRED')
$eventValid=(-not $eventsInvalid)
if($latest){
    try{$eventValid=$eventValid -and (
        [string]$latest.job_id -ceq $jobId -and [string]$latest.branch -ceq [string]$job.branch -and
        [string]$latest.base_sha -ceq [string]$job.base_sha -and $phase -cin $validPhases
    )}catch{$eventValid=$false}
}
$headResult=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'rev-parse','HEAD') -WorkingDirectory $Repo -Label 'reconcile-git-head'
$branchResult=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'branch','--show-current') -WorkingDirectory $Repo -Label 'reconcile-git-branch'
$statusResult=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'status','--porcelain=v1','-uall') -WorkingDirectory $Repo -Label 'reconcile-git-status'
$indexResult=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'diff','--cached','--name-only') -WorkingDirectory $Repo -Label 'reconcile-git-index'
$remoteResult=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'ls-remote','--heads','origin',('refs/heads/'+[string]$job.branch)) -WorkingDirectory $Repo -Label 'reconcile-git-remote-ref'
$localHead=if($headResult.exit_code -eq 0){$headResult.stdout.Trim()}else{$null}
$localBranch=if($branchResult.exit_code -eq 0){$branchResult.stdout.Trim()}else{$null}
$dirtyCount=if($statusResult.exit_code -eq 0){@(Get-SeshatOutputLines -Text $statusResult.stdout).Count}else{$null}
$indexPaths=if($indexResult.exit_code -eq 0){@(Get-SeshatOutputLines -Text $indexResult.stdout)}else{@()}
$remoteLines=if($remoteResult.exit_code -eq 0){@(Get-SeshatOutputLines -Text $remoteResult.stdout)}else{@()}
$remoteHead=if($remoteLines.Count -eq 1 -and $remoteLines[0] -cmatch '^([0-9a-f]{40})\s'){[string]$Matches[1]}else{$null}

$githubState=if($SkipGithub){'SKIPPED'}else{'NOT_NEEDED_BEFORE_PUSH'}
$githubPrNumber=$null
if(-not $SkipGithub){
    $query=Invoke-SeshatNativeCommand -FilePath 'gh' -ArgumentList @('pr','list','--repo','Stimurid/SESHAT','--head',([string]$job.branch),'--state','all','--limit','2','--json','number,state,isDraft,baseRefName,headRefName,headRefOid') -WorkingDirectory $Repo -Label 'reconcile-gh-pr-list'
    if($query.exit_code -ne 0){
        $githubState='UNKNOWN_GITHUB_QUERY_FAILED'
    }else{
        $prs=@($query.stdout|ConvertFrom-Json)
        if($prs.Count -eq 0){$githubState='NO_PR_FOUND'}
        elseif($prs.Count -gt 1){$githubState='AMBIGUOUS_MULTIPLE_PRS'}
        else{
            $githubPrNumber=[int]$prs[0].number
            if($localHead -cmatch '^[0-9a-f]{40}$'){
                $decision=Test-SeshatPublishedPullRequest -PullRequest $prs[0] -Branch ([string]$job.branch) -HeadSha $localHead
                $githubState=if($decision -eq 'ADMIT'){'VERIFIED_DRAFT_PR'}else{$decision}
            }else{$githubState='UNKNOWN_LOCAL_HEAD_UNAVAILABLE'}
        }
    }
}
$receiptState='MISSING'
if(Test-Path -LiteralPath $receiptPath){
    try{
        $receipt=Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8|ConvertFrom-Json
        if($localHead -cmatch '^[0-9a-f]{40}$'){$receiptState=Test-SeshatPublicationReceipt -Receipt $receipt -Job $job -HeadSha $localHead}else{$receiptState='LOCAL_HEAD_UNAVAILABLE'}
    }catch{$receiptState='INVALID'}
}
$result=[ordered]@{
    schema='seshat.publication-reconcile.v1';checked_at_utc=(Get-Date).ToUniversalTime().ToString('o')
    job_id=$jobId;recorded_phase=if(-not $eventValid){'INVALID_EVENT'}elseif($phase){$phase}else{'NO_ATTEMPT_RECORDED'}
    recorded_error_class=if($latest -and $latest.PSObject.Properties['error_class']){[string]$latest.error_class}else{$null}
    recovery_action=if(-not $eventValid){'MANUAL_INSPECT_INVALID_EVENT_DO_NOT_RETRY'}elseif($phase){Get-SeshatPublicationRecoveryDecision -Phase $phase}else{'NO_PUBLICATION_ATTEMPT_TO_RECOVER'}
    branch=[string]$job.branch;base_sha=[string]$job.base_sha;local_branch=$localBranch;local_head=$localHead
    dirty_file_count=$dirtyCount;github_state=$githubState;github_pr_number=$githubPrNumber
    staged_paths=$indexPaths;remote_head=$remoteHead
    latest_mutation_action=if($latestMutation){[string]$latestMutation.action}else{$null}
    latest_mutation_status=if($latestMutation){[string]$latestMutation.status}else{$null}
    mutation_recovery_state=Get-SeshatMutationRecoveryState -LatestMutation $latestMutation
    attempt_nonce=if($latestMutation){[string]$latestMutation.attempt_nonce}else{$null}
    publication_receipt=$receiptState;automatic_retry='DENIED';automatic_mutation='NONE'
}
Write-Output ($result|ConvertTo-Json -Depth 8)
