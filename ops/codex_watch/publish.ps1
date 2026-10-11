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
$phase='BEFORE_COMMIT'
$headSha=$baseSha
Need ($branch -match '^codex/[a-z0-9][a-z0-9-]{4,79}$') 'UNSAFE_BRANCH_NAME'
Need ($issue -ge 1 -and $issue -le 1000000) 'UNSAFE_ISSUE'
Start-SeshatPublicationAttempt -EventPath $eventPath -ReceiptPath $receiptPath -JobId $jobId -Branch $branch -BaseSha $baseSha

function InvokePublisherNative([string]$file,[string[]]$arguments,[string]$label,[string]$failureClass){
    $result=Invoke-SeshatNativeCommand -FilePath $file -ArgumentList $arguments -WorkingDirectory $Repo -Label $label -AuditPath $nativeAuditPath -JobId $jobId
    Assert-SeshatNativeSuccess -Result $result -FailureClass $failureClass
    return $result
}

try{
    $remote=InvokePublisherNative 'git' @('-C',$Repo,'remote','get-url','origin') 'git-remote' 'GIT_REMOTE_FAILED'
    Need ([string]$remote.stdout.Trim() -ceq 'https://github.com/Stimurid/SESHAT.git') 'REMOTE_MISMATCH'
    $currentBranch=InvokePublisherNative 'git' @('-C',$Repo,'branch','--show-current') 'git-branch' 'GIT_BRANCH_FAILED'
    Need ([string]$currentBranch.stdout.Trim() -ceq $branch) 'BRANCH_MISMATCH'
    $head=InvokePublisherNative 'git' @('-C',$Repo,'rev-parse','HEAD') 'git-head-before' 'GIT_HEAD_FAILED'
    Need ([string]$head.stdout.Trim() -ceq $baseSha) 'UNEXPECTED_HEAD_BEFORE_PUBLISH'
    $status=InvokePublisherNative 'git' @('-C',$Repo,'-c','core.quotePath=false','status','--porcelain=v1','-uall') 'git-status' 'STATUS_FAILED'
    $statusLines=@(Get-SeshatOutputLines -Text $status.stdout)
    Need ($statusLines.Count -gt 0) 'NO_CODE_CHANGES'
    $paths=@(Get-SeshatStatusPaths -StatusLines $statusLines)
    $pathDecision=Test-SeshatOwnedPathSet -ApprovedPaths @($job.approved_paths) -OwnedPaths @($job.owned_paths) -DirtyPaths $paths
    Need ($pathDecision -eq 'ADMIT') $pathDecision
    Need (Test-Path -LiteralPath (Join-Path $Repo 'docs\S_IMPL_002B_RESULT.md')) 'MISSING_REQUIRED_RESULT_RECEIPT'

    # Deliberately DO NOT execute Codex-written code under this credential-bearing process.
    [void](InvokePublisherNative 'git' (@('-C',$Repo,'add','--')+$paths) 'git-add' 'GIT_ADD_FAILED')
    [void](InvokePublisherNative 'git' @('-C',$Repo,'diff','--cached','--check') 'git-diff-check' 'DIFF_CHECK_FAILED')
    $diff=InvokePublisherNative 'git' @('-C',$Repo,'diff','--cached','--no-ext-diff','--unified=0') 'git-diff-scan' 'DIFF_SCAN_FAILED'
    Need ($diff.stdout -notmatch '(?mi)^\+.*(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)') 'POSSIBLE_CREDENTIAL_IN_DIFF'
    $stagedResult=InvokePublisherNative 'git' @('-C',$Repo,'diff','--cached','--name-only') 'git-staged-paths' 'STAGED_PATH_QUERY_FAILED'
    $staged=@(Get-SeshatOutputLines -Text $stagedResult.stdout)
    Need (Test-SeshatExactStringSet -Left $staged -Right @($job.owned_paths)) 'STAGED_PATH_SET_MISMATCH'
    $phase='STAGED_ONLY'
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha

    $msg="impl(s2b): bounded reconciliation controller (#$issue)"
    [void](InvokePublisherNative 'git' @('-C',$Repo,'commit','-m',$msg) 'git-commit' 'GIT_COMMIT_FAILED')
    $headResult=InvokePublisherNative 'git' @('-C',$Repo,'rev-parse','HEAD') 'git-head-after' 'GIT_HEAD_FAILED'
    $headSha=[string]$headResult.stdout.Trim()
    Need ($headSha -cmatch '^[0-9a-f]{40}$' -and $headSha -cne $baseSha) 'INVALID_COMMITTED_HEAD'
    $phase='COMMITTED_ONLY'
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha

    $env:GIT_TERMINAL_PROMPT='0'
    [void](InvokePublisherNative 'git' @('-C',$Repo,'push','--set-upstream','origin',$branch) 'git-push' 'GIT_PUSH_FAILED')
    $phase='PUSHED_WITHOUT_PR'
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha

    # Empty list is distinct from transport/auth failure. A pre-existing PR is
    # held for manual reconciliation and is never reused or duplicated here.
    $list=InvokePublisherNative 'gh' @('pr','list','--repo','Stimurid/SESHAT','--head',$branch,'--state','all','--limit','2','--json','number,url,state,isDraft,baseRefName,headRefName,headRefOid') 'gh-pr-list' 'GITHUB_PR_LIST_FAILED'
    $existing=@($list.stdout|ConvertFrom-Json)
    Need ($existing.Count -eq 0) 'PREEXISTING_PR_REQUIRES_RECONCILIATION'
    $artifactDir=Join-Path (Join-Path $Root 'publication-artifacts') $jobId
    New-Item -ItemType Directory -Path $artifactDir|Out-Null
    $bodyFile=Join-Path $artifactDir 'pr-body.md'
    @"
Implements #$issue from pre-approved SESHAT dispatch.
Branch: $branch
Commit: $headSha

Codex generated changes in a restricted sandbox. Trusted host validated the scoped file set,
credential-pattern scan and staged diff before commit/push. Isolated GitHub PR CI runs pytest
and Ruff after publication. No local execution of unreviewed code, auto-merge or semantic approval.
Result: docs/S_IMPL_002B_RESULT.md
Coordination: https://github.com/Stimurid/SESHAT/issues/6
"@|Set-Content -LiteralPath $bodyFile -Encoding UTF8
    [void](InvokePublisherNative 'gh' @('pr','create','--repo','Stimurid/SESHAT','--draft','--base','main','--head',$branch,'--title','S-IMPL-002B: bounded reconciliation controller','--body-file',$bodyFile) 'gh-pr-create' 'GITHUB_PR_CREATE_FAILED')
    $view=InvokePublisherNative 'gh' @('pr','view',$branch,'--repo','Stimurid/SESHAT','--json','number,url,state,isDraft,baseRefName,headRefName,headRefOid') 'gh-pr-view' 'GITHUB_PR_VERIFY_QUERY_FAILED'
    $publishedPr=$view.stdout|ConvertFrom-Json
    $prDecision=Test-SeshatPublishedPullRequest -PullRequest $publishedPr -Branch $branch -HeadSha $headSha
    Need ($prDecision -eq 'ADMIT') $prDecision
    $phase='DRAFT_PUBLISHED'
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha
    $result=[ordered]@{
        status='PUBLISHED_DRAFT_PR';job_id=$jobId;issue=$issue;branch=$branch;head_sha=$headSha
        pr_number=[int]$publishedPr.number;pr_url=[string]$publishedPr.url
        pr_state=[string]$publishedPr.state;pr_is_draft=[bool]$publishedPr.isDraft
        pr_base=[string]$publishedPr.baseRefName;pr_head=[string]$publishedPr.headRefName
        changed_paths=$paths;stage_event_path=$eventPath;native_audit_path=$nativeAuditPath
        ci_tests='PENDING_GITHUB_PR_CI';local_code_execution='NONE'
        published_at_utc=(Get-Date).ToUniversalTime().ToString('o')
    }
    Write-SeshatJsonCreateNew -Value $result -Path $receiptPath
    Write-Output ($result|ConvertTo-Json -Compress -Depth 8)
}catch{
    $errorClass=Get-SeshatSafeErrorClass -ErrorRecord $_
    Write-SeshatPublicationEvent -Path $eventPath -JobId $jobId -Phase $phase -Branch $branch -BaseSha $baseSha -HeadSha $headSha -ErrorClass $errorClass
    [Console]::Error.WriteLine(('PUBLISH_FAILED error_class={0} phase={1}' -f $errorClass,$phase))
    exit 94
}
