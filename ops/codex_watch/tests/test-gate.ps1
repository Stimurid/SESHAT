# Safe offline, no GitHub network, no branch changes. Run with PowerShell.
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'gate.ps1')
$repo = [string](& git -C (Join-Path $PSScriptRoot '..\..\..') rev-parse --show-toplevel)
if ($LASTEXITCODE -ne 0) { throw 'TEST_REPOSITORY_NOT_FOUND' }
$branchBefore = [string](& git -C $repo branch --show-current)
$refsBefore = @(& git -C $repo for-each-ref --format='%(refname)' refs/heads)
$statusBefore = @(& git -C $repo status --porcelain=v1 -uall)
$approvedBody = "Exact approved issue body`nwith UTF-8: SESHAT"
$approvedBodySha = Get-SeshatUtf8Sha256 -Text $approvedBody
$t = [pscustomobject]@{
    after_pr=16;ops_pr=18;next_issue=17
    next_issue_body_utf8_sha256=$approvedBodySha
    accepted_label='seshat:engineering-accepted';ready_label='seshat:codex-ready'
}
$reviewedSha=('b'*40)
$pr=[pscustomobject]@{
    number=16; merged=$true; state='closed'; merged_at='2026-10-10T01:00:00Z';
    base=[pscustomobject]@{ref='main'};
    head=[pscustomobject]@{sha=$reviewedSha};
    labels=@([pscustomobject]@{name='seshat:engineering-accepted'})
}
$comments=@([pscustomobject]@{
    user=[pscustomobject]@{login='Stimurid'}
    body=('SESHAT_ENGINEERING_ACCEPTED_SHA='+$reviewedSha)
})
$opsPr=[pscustomobject]@{
    number=18;merged=$true;state='closed';merged_at='2026-10-10T02:00:00Z';
    base=[pscustomobject]@{ref='main'}
}
$issue=[pscustomobject]@{number=17;state='open';body=$approvedBody;labels=@([pscustomobject]@{name='seshat:codex-ready'})}
$sha=('a'*40)
$runs=@([pscustomobject]@{
    name='ci';path='.github/workflows/ci.yml';event='push';head_branch='main';head_sha=$sha
    status='completed';conclusion='success';repository=[pscustomobject]@{full_name='Stimurid/SESHAT'}
})
function Check($want) {
    $got=Test-SeshatDispatchGate -Transition $t -PriorPr $pr -PriorComments $comments -OpsPr $opsPr -NextIssue $issue -RemoteMainSha $sha -MainRuns $runs
    if ($got -ne $want) { throw ("GATE expected '{0}' got '{1}'" -f $want,$got) }
}
Check 'ADMIT'
$pr.merged=$false; Check 'WAIT_PRIOR_PR_NOT_MERGED'; $pr.merged=$true
$pr.labels=@(); Check 'WAIT_EXPLICIT_ENGINEERING_ACCEPTANCE'; $pr.labels=@([pscustomobject]@{name='seshat:engineering-accepted'})
$pr.head.sha=('c'*40); Check 'WAIT_REVIEWED_PR_SHA_ACCEPTANCE_MISSING'; $pr.head.sha=$reviewedSha
$comments[0].user.login='NotStimurid'; Check 'WAIT_REVIEWED_PR_SHA_ACCEPTANCE_MISSING'; $comments[0].user.login='Stimurid'
$savedComments=$comments; $comments=@(); Check 'WAIT_REVIEWED_PR_SHA_ACCEPTANCE_MISSING'; $comments=$savedComments
$issue.body=$approvedBody+' changed'; Check 'BLOCK_NEXT_ISSUE_BODY_DRIFT'; $issue.body=$approvedBody
$opsPr.merged=$false; Check 'WAIT_OPS_PR_NOT_MERGED'; $opsPr.merged=$true
$issue.labels=@(); Check 'WAIT_NEXT_ISSUE_NOT_APPROVED'; $issue.labels=@([pscustomobject]@{name='seshat:codex-ready'})
$runs[0].head_sha=('d'*40); Check 'WAIT_MAIN_CI_NOT_GREEN'; $runs[0].head_sha=$sha
$runs[0].path='.github/workflows/not-ci.yml'; Check 'WAIT_MAIN_CI_NOT_GREEN'; $runs[0].path='.github/workflows/ci.yml'
$pr.base.ref='other'; Check 'BLOCK_PR_BASE_NOT_MAIN'; $pr.base.ref='main'
$issue.state='closed'; Check 'BLOCK_NEXT_ISSUE_NOT_OPEN'; $issue.state='open'
$t.next_issue_body_utf8_sha256='TRUSTED_HOST_PLACEHOLDER'; Check 'BLOCK_NEXT_ISSUE_BODY_NOT_PINNED'; $t.next_issue_body_utf8_sha256=$approvedBodySha
Check 'ADMIT'

$queue=Get-Content -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'task_queue.json') -Raw -Encoding UTF8|ConvertFrom-Json
if([string]$queue.transitions[0].next_issue_body_utf8_sha256 -cne '541bf6271d9a0c8f7c0ade9bc710d5fdc5d5ae3083ed6e898be04f5c8c0780b8'){throw 'REAL_ISSUE_BODY_DIGEST_CHANGED'}
if(-not(Test-SeshatExactStringSet -Left @($queue.transitions[0].approved_paths) -Right @(Get-SeshatApprovedS2BPaths))){throw 'QUEUE_APPROVED_PATHS_CHANGED'}
$opsRoot=Split-Path -Parent $PSScriptRoot
$executeSource=Get-Content -LiteralPath (Join-Path $opsRoot 'execute-task.ps1') -Raw -Encoding UTF8
$publishSource=Get-Content -LiteralPath (Join-Path $opsRoot 'publish.ps1') -Raw -Encoding UTF8
if($executeSource -notmatch 'Test-SeshatCanonicalJobPath' -or $executeSource -notmatch 'Test-SeshatJobAuthorization'){throw 'EXECUTOR_ENTRYPOINT_BINDING_MISSING'}
if($publishSource -notmatch 'Test-SeshatCanonicalJobPath' -or $publishSource -notmatch 'Test-SeshatJobAuthorization'){throw 'PUBLISHER_ENTRYPOINT_BINDING_MISSING'}
$exitPrecheck=$executeSource.IndexOf('Assert-SeshatExitReceiptAbsent -Path $ExitPath')
$exitWriter=$executeSource.IndexOf('Write-SeshatJsonCreateNew -Value $receipt -Path $ExitPath')
if($exitPrecheck -lt 0 -or $exitWriter -lt 0 -or $exitPrecheck -ge $exitWriter){throw 'EXECUTOR_EXIT_CREATE_ONCE_ORDER_MISSING'}
if($publishSource -match "\^src/seshat/\[A-Za-z0-9_" -or $publishSource -notmatch 'Test-SeshatOwnedPathSet'){throw 'PUBLISHER_EXACT_MANIFEST_ENFORCEMENT_MISSING'}

$bundle=@(Get-SeshatBundlePaths|ForEach-Object{[pscustomobject]@{path=$_;sha256=('1'*64)}})
$job=[pscustomobject]@{
    job_id='S-IMPL-17-20261010123456';issue_number=17;branch='codex/s2b-bounded-reconciliation';base_branch='main'
    base_sha=('a'*40);after_pr=16;accepted_reviewed_head_sha=('b'*40);ops_pr=18
    ops_merge_sha=('e'*40);issue_body_utf8_sha256='541bf6271d9a0c8f7c0ade9bc710d5fdc5d5ae3083ed6e898be04f5c8c0780b8'
    dispatch_key=('pr16-'+('f'*40)+'-issue17');approved_paths=@(Get-SeshatApprovedS2BPaths)
    ops_bundle=$bundle;repo='C:\projects\seshat';authorization_digest=''
}
$job.authorization_digest=Get-SeshatJobAuthorizationDigest -Job $job
$marker=[pscustomobject]@{key=$job.dispatch_key;job_id=$job.job_id;state='AUTHORIZED';authorization_digest=$job.authorization_digest}
if((Test-SeshatJobAuthorization -Job $job -Marker $marker) -ne 'ADMIT'){throw 'VALID_JOB_AUTHORIZATION_REJECTED'}
$marker.job_id='S-IMPL-17-20261010999999'
if((Test-SeshatJobAuthorization -Job $job -Marker $marker) -ne 'BLOCK_DISPATCH_MARKER_BINDING_MISMATCH'){throw 'ARBITRARY_JOB_MARKER_ACCEPTED'}
$marker.job_id=$job.job_id
$job.base_sha=('9'*40)
if((Test-SeshatJobAuthorization -Job $job -Marker $marker) -ne 'BLOCK_JOB_AUTHORIZATION_DIGEST_MISMATCH'){throw 'ALTERED_JOB_BINDING_ACCEPTED'}
$job.base_sha=('a'*40)

$approved=@(Get-SeshatApprovedS2BPaths)
$owned=@('src/seshat/reconciliation.py','tests/test_reconciliation.py','docs/S_IMPL_002B_RESULT.md')
if((Test-SeshatOwnedPathSet -ApprovedPaths $approved -OwnedPaths $owned -DirtyPaths $owned) -ne 'ADMIT'){throw 'VALID_OWNED_PATH_SET_REJECTED'}
$dirtyWithUnrelated=@($owned+'tests/unrelated.py')
if((Test-SeshatOwnedPathSet -ApprovedPaths $approved -OwnedPaths $owned -DirtyPaths $dirtyWithUnrelated) -ne 'BLOCK_DIRTY_PATH_SET_MISMATCH'){throw 'UNRELATED_TEST_PATH_ACCEPTED'}
if(Test-SeshatCanonicalJobPath -JobPath 'C:\arbitrary\job.json' -Root 'C:\trusted\watch'){throw 'ARBITRARY_JOB_PATH_ACCEPTED'}

$publishedPr=[pscustomobject]@{number=19;state='OPEN';isDraft=$true;baseRefName='main';headRefName=$job.branch;headRefOid=('2'*40)}
if((Test-SeshatPublishedPullRequest -PullRequest $publishedPr -Branch $job.branch -HeadSha ('2'*40)) -ne 'ADMIT'){throw 'VALID_DRAFT_PR_REJECTED'}
$publishedPr.headRefOid=('3'*40)
if((Test-SeshatPublishedPullRequest -PullRequest $publishedPr -Branch $job.branch -HeadSha ('2'*40)) -ne 'BLOCK_PR_HEAD_SHA_MISMATCH'){throw 'WRONG_PR_HEAD_ACCEPTED'}

$sentinelDir=Join-Path ([System.IO.Path]::GetTempPath()) ('seshat-exit-sentinel-'+[guid]::NewGuid().ToString('N'))
$sentinelPath=Join-Path $sentinelDir 'exit.json'
New-Item -ItemType Directory -Path $sentinelDir|Out-Null
try{
    $sentinelBytes=[byte[]](0,1,2,3,127,128,254,255)
    [System.IO.File]::WriteAllBytes($sentinelPath,$sentinelBytes)
    $beforeSentinel=[Convert]::ToBase64String([System.IO.File]::ReadAllBytes($sentinelPath))
    $blocked=$false
    try{Assert-SeshatExitReceiptAbsent -Path $sentinelPath}catch{$blocked=($_.Exception.Message -eq 'EXIT_RECEIPT_ALREADY_EXISTS')}
    if(-not $blocked){throw 'EXISTING_EXIT_RECEIPT_NOT_BLOCKED'}
    $createBlocked=$false
    try{Write-SeshatJsonCreateNew -Value @{replacement=$true} -Path $sentinelPath}catch{$createBlocked=$true}
    if(-not $createBlocked){throw 'EXISTING_EXIT_RECEIPT_REPLACED'}
    $afterSentinel=[Convert]::ToBase64String([System.IO.File]::ReadAllBytes($sentinelPath))
    if($afterSentinel -cne $beforeSentinel){throw 'EXISTING_EXIT_RECEIPT_MUTATED'}
}finally{
    Remove-Item -LiteralPath $sentinelDir -Recurse -Force
}

$branchAfter = [string](& git -C $repo branch --show-current)
$refsAfter = @(& git -C $repo for-each-ref --format='%(refname)' refs/heads)
$statusAfter = @(& git -C $repo status --porcelain=v1 -uall)
if ($branchAfter -cne $branchBefore) { throw 'SIDE_EFFECT_BRANCH_CHANGED' }
if (($refsAfter -join "`n") -cne ($refsBefore -join "`n")) { throw 'SIDE_EFFECT_BRANCH_REF_CREATED' }
if (($statusAfter -join "`n") -cne ($statusBefore -join "`n")) { throw 'SIDE_EFFECT_WORKTREE_CHANGED' }
Write-Output 'PASS: offline O1-O9 authorization/denial cases; no branch, worktree, or exit-sentinel side effects'
