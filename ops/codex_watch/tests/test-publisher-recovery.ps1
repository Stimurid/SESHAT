# Synthetic offline publication recovery tests. No GitHub calls or credentials.
$ErrorActionPreference='Stop'
$opsRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $opsRoot 'gate.ps1')
$temp=Join-Path ([System.IO.Path]::GetTempPath()) ('seshat-publisher-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp|Out-Null
try{
    $engine=(Get-Process -Id $PID).Path
    $audit=Join-Path $temp 'native.jsonl'
    $zeroWarning=Invoke-SeshatNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-Command',"[Console]::Error.WriteLine('synthetic warning'); exit 0") -WorkingDirectory $temp -Label 'mock-zero-warning' -AuditPath $audit -JobId 'synthetic-job'
    if($zeroWarning.exit_code -ne 0 -or -not $zeroWarning.stderr_present){throw 'EXIT_ZERO_STDERR_NOT_CAPTURED'}
    Assert-SeshatNativeSuccess -Result $zeroWarning -FailureClass 'SHOULD_NOT_FAIL'
    $zeroAudit=(Get-Content -LiteralPath $audit -Encoding UTF8|Select-Object -First 1)|ConvertFrom-Json
    if([string]$zeroAudit.classification -cne 'EXIT_ZERO_STDERR'){throw 'EXIT_ZERO_STDERR_NOT_CLASSIFIED'}
    if($zeroAudit.PSObject.Properties['stderr']){throw 'RAW_STDERR_LEAKED_TO_AUDIT'}

    $nonzero=Invoke-SeshatNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-Command',"[Console]::Error.WriteLine('synthetic failure'); exit 7") -WorkingDirectory $temp -Label 'mock-nonzero' -AuditPath $audit -JobId 'synthetic-job'
    if($nonzero.exit_code -ne 7 -or -not $nonzero.stderr_present){throw 'NONZERO_STDERR_NOT_CAPTURED'}
    $blocked=$false
    try{Assert-SeshatNativeSuccess -Result $nonzero -FailureClass 'SYNTHETIC_NATIVE_FAILED'}catch{$blocked=($_.Exception.Message -eq 'SYNTHETIC_NATIVE_FAILED')}
    if(-not $blocked){throw 'NONZERO_NATIVE_DID_NOT_FAIL_CLOSED'}

    # Temp local Git only: exercises argument handling and separated native IO.
    $gitRepo=Join-Path $temp 'repo'
    New-Item -ItemType Directory -Path $gitRepo|Out-Null
    $gitInit=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('init',$gitRepo) -WorkingDirectory $temp -Label 'temp-git-init'
    Assert-SeshatNativeSuccess -Result $gitInit -FailureClass 'TEMP_GIT_INIT_FAILED'
    Set-Content -LiteralPath (Join-Path $gitRepo 'approved.txt') -Value 'synthetic' -Encoding UTF8
    $gitStatus=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$gitRepo,'-c','core.quotePath=false','status','--porcelain=v1','-uall') -WorkingDirectory $temp -Label 'temp-git-status'
    Assert-SeshatNativeSuccess -Result $gitStatus -FailureClass 'TEMP_GIT_STATUS_FAILED'
    $statusPaths=@(Get-SeshatStatusPaths -StatusLines @(Get-SeshatOutputLines -Text $gitStatus.stdout))
    if(-not(Test-SeshatExactStringSet -Left $statusPaths -Right @('approved.txt'))){throw 'TEMP_GIT_STATUS_PATH_MISMATCH'}

    $approved=@(Get-SeshatApprovedS2BPaths)
    $owned=@('src/seshat/reconciliation.py','tests/test_reconciliation.py','docs/S_IMPL_002B_RESULT.md')
    if((Test-SeshatOwnedPathSet -ApprovedPaths $approved -OwnedPaths $owned -DirtyPaths @($owned+'tests/extra.py')) -ne 'BLOCK_DIRTY_PATH_SET_MISMATCH'){throw 'EXTRA_PATH_ACCEPTED'}
    if((Test-SeshatOwnedPathSet -ApprovedPaths $approved -OwnedPaths $owned -DirtyPaths @($owned|Select-Object -First 2)) -ne 'BLOCK_DIRTY_PATH_SET_MISMATCH'){throw 'MISSING_PATH_ACCEPTED'}

    $eventPath=Join-Path $temp 'events.jsonl'
    $receiptPath=Join-Path $temp 'publish_receipt.json'
    Start-SeshatPublicationAttempt -EventPath $eventPath -ReceiptPath $receiptPath -JobId 'synthetic-job' -Branch 'codex/synthetic' -BaseSha ('a'*40)
    $retryBlocked=$false
    try{Assert-SeshatPublicationAttemptAbsent -EventPath $eventPath -ReceiptPath $receiptPath}catch{$retryBlocked=($_.Exception.Message -eq 'PUBLICATION_ATTEMPT_ALREADY_RECORDED')}
    if(-not $retryBlocked){throw 'UNSAFE_PUBLICATION_RETRY_ACCEPTED'}
    $expectedRecovery=@{
        BEFORE_COMMIT='MANUAL_INSPECT_WORKTREE_DO_NOT_RETRY'
        STAGED_ONLY='MANUAL_INSPECT_INDEX_DO_NOT_RETRY'
        COMMITTED_ONLY='MANUAL_VERIFY_REMOTE_BEFORE_ANY_PUSH'
        PUSHED_WITHOUT_PR='MANUAL_VERIFY_GITHUB_BEFORE_ANY_PR_CREATE'
        DRAFT_PUBLISHED='READBACK_VERIFY_EXISTING_DRAFT_NO_RETRY'
    }
    foreach($phase in $expectedRecovery.Keys){
        if((Get-SeshatPublicationRecoveryDecision -Phase $phase) -cne $expectedRecovery[$phase]){throw ('BAD_RECOVERY_DECISION_'+$phase)}
    }
    $receiptJob=[pscustomobject]@{job_id='synthetic-job';issue_number=17;branch='codex/synthetic'}
    $receipt=[pscustomobject]@{status='PUBLISHED_DRAFT_PR';job_id='synthetic-job';issue=17;branch='codex/synthetic';head_sha=('b'*40);pr_number=28;pr_state='OPEN';pr_is_draft=$true;pr_base='main';pr_head='codex/synthetic'}
    if((Test-SeshatPublicationReceipt -Receipt $receipt -Job $receiptJob -HeadSha ('b'*40)) -ne 'ADMIT'){throw 'VALID_PUBLICATION_RECEIPT_REJECTED'}
    $receipt.head_sha=('c'*40)
    if((Test-SeshatPublicationReceipt -Receipt $receipt -Job $receiptJob -HeadSha ('b'*40)) -ne 'BLOCK_PUBLISH_HEAD_MISMATCH'){throw 'STALE_PUBLICATION_RECEIPT_ACCEPTED'}
    $sanitized=ConvertTo-SeshatSanitizedLogText -Text ('failure ghp_'+('A'*20))
    if($sanitized -match 'ghp_' -or $sanitized -notmatch 'REDACTED_CREDENTIAL'){throw 'PUBLISHER_LOG_CREDENTIAL_NOT_REDACTED'}

    $exitPath=Join-Path $temp 'exit.json'
    $sentinel=[byte[]](0,1,2,3,127,128,254,255)
    [System.IO.File]::WriteAllBytes($exitPath,$sentinel)
    $before=[Convert]::ToBase64String([System.IO.File]::ReadAllBytes($exitPath))
    $exitBlocked=$false
    try{Write-SeshatJsonCreateNew -Value @{replacement=$true} -Path $exitPath}catch{$exitBlocked=$true}
    if(-not $exitBlocked){throw 'IMMUTABLE_EXIT_REPLACED'}
    if([Convert]::ToBase64String([System.IO.File]::ReadAllBytes($exitPath)) -cne $before){throw 'IMMUTABLE_EXIT_MUTATED'}

    $publishSource=Get-Content -LiteralPath (Join-Path $opsRoot 'publish.ps1') -Raw -Encoding UTF8
    $executeSource=Get-Content -LiteralPath (Join-Path $opsRoot 'execute-task.ps1') -Raw -Encoding UTF8
    $reconcileSource=Get-Content -LiteralPath (Join-Path $opsRoot 'reconcile-publish.ps1') -Raw -Encoding UTF8
    if($publishSource -match '\*>|2>&1|2>\$null'){throw 'PUBLISHER_UNSAFE_NATIVE_REDIRECTION_PRESENT'}
    if($executeSource -match '\*>|2>&1'){throw 'EXECUTOR_WILDCARD_NATIVE_REDIRECTION_PRESENT'}
    foreach($required in @('git-add','git-diff-check','git-diff-scan','git-commit','git-push','gh-pr-list','gh-pr-create','gh-pr-view')){
        if($publishSource -notmatch [regex]::Escape($required)){throw ('NATIVE_CHECKPOINT_MISSING_'+$required)}
    }
    if($publishSource -match '(?im)^\s*[&.]?\s*(python|pytest|ruff|pwsh|powershell)\s+.*(pytest|ruff|test-gate\.ps1)'){throw 'TRUSTED_PUBLISHER_EXECUTES_UNREVIEWED_TESTS'}
    if($publishSource.IndexOf("'gh-pr-list'") -gt $publishSource.IndexOf("'gh-pr-create'")){throw 'PR_EXISTENCE_CHECK_AFTER_CREATE'}
    if($publishSource -notmatch 'Write-SeshatJsonCreateNew -Value \$result -Path \$receiptPath'){throw 'PUBLICATION_RECEIPT_NOT_CREATE_NEW'}
    if($reconcileSource -match "(?m)ArgumentList.*'(add|commit|push|create|edit|close|merge)'"){throw 'RECONCILE_CONTAINS_MUTATING_COMMAND'}
    if($reconcileSource -notmatch "automatic_retry='DENIED'" -or $reconcileSource -notmatch "automatic_mutation='NONE'"){throw 'RECONCILE_DENIAL_MARKERS_MISSING'}
    Write-Output 'PASS: synthetic publisher native IO, fail-closed paths, immutable receipts, stage recovery, and no-retry checks'
}finally{
    Remove-Item -LiteralPath $temp -Recurse -Force
}
