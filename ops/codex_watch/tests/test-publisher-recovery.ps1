# Synthetic offline publication recovery tests. No GitHub calls or credentials.
$ErrorActionPreference='Stop'
$opsRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $opsRoot 'gate.ps1')
$temp=Join-Path ([System.IO.Path]::GetTempPath()) ('seshat-publisher-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp|Out-Null
try{
    $engine=(Get-Process -Id $PID).Path
    $audit=Join-Path $temp 'native.jsonl'
    $childScript=Join-Path $temp 'native child with spaces.ps1'
    @'
param([string]$Mode,[string]$One,[string]$Two,[string]$Three)
$utf8=New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding=$utf8
[Console]::OutputEncoding=$utf8
if($Mode -eq 'args'){
    $stdin=[Console]::In.ReadToEnd()
    [Console]::Out.WriteLine((@{one=$One;two=$Two;three=$Three;stdin=$stdin}|ConvertTo-Json -Compress))
    [Console]::Error.WriteLine('synthetic warning')
    exit 0
}
if($Mode -eq 'stream'){
    [Console]::Out.WriteLine('first line русский')
    [Console]::Out.Flush()
    [Console]::Error.WriteLine('separate stderr русский')
    [Console]::Error.Flush()
    Start-Sleep -Seconds 3
    [Console]::Out.WriteLine('partial before nonzero')
    [Console]::Out.Flush()
    exit 7
}
if($Mode -eq 'flood'){
    [Console]::Out.Write(('x')*8192)
    [Console]::Out.Flush()
    Start-Sleep -Seconds 1
    exit 0
}
if($Mode -eq 'floodstderr'){
    [Console]::Error.Write(('e')*8192)
    [Console]::Error.Flush()
    Start-Sleep -Seconds 1
    exit 0
}
exit 99
'@|Set-Content -LiteralPath $childScript -Encoding UTF8
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

    # Exercises the Windows PowerShell 5.1 Arguments fallback: spaces, an
    # embedded quote, a trailing backslash, and UTF-8 stdin/stdout/stderr.
    $argOne='value with spaces'
    $argTwo='embedded"quote'
    $argThree='C:\path with spaces\'
    $unicodeInput='ввод по-русски'
    $quoted=Invoke-SeshatNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$childScript,'args',$argOne,$argTwo,$argThree) -WorkingDirectory $temp -Label 'mock-quoted-arguments' -AuditPath $audit -JobId 'synthetic-job' -StandardInputText $unicodeInput
    if($quoted.exit_code -ne 0 -or -not $quoted.stderr_present){throw 'QUOTED_ARGUMENT_CHILD_FAILED'}
    $quotedPayload=$quoted.stdout.Trim()|ConvertFrom-Json
    if([string]$quotedPayload.one -cne $argOne -or [string]$quotedPayload.two -cne $argTwo -or [string]$quotedPayload.three -cne $argThree){throw 'NATIVE_ARGUMENT_QUOTING_CHANGED'}
    if([string]$quotedPayload.stdin -cne $unicodeInput){throw 'UNICODE_STDIN_CHANGED'}
    if($quoted.stderr -notmatch 'synthetic warning'){throw 'EXIT_ZERO_STDERR_WARNING_MISSING'}

    # Run the blocking streaming helper in a background PowerShell job so the
    # test can prove the durable file is updated before the child exits.
    $streamOut=Join-Path $temp 'stream-stdout.jsonl'
    $streamErr=Join-Path $temp 'stream-stderr.log'
    $streamAudit=Join-Path $temp 'stream-audit.jsonl'
    $gatePath=Join-Path $opsRoot 'gate.ps1'
    $streamJob=Start-Job -ScriptBlock {
        param($gate,$exe,$script,$work,$out,$err,$auditPath)
        . $gate
        Invoke-SeshatStreamingNativeCommand -FilePath $exe -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$script,'stream') -WorkingDirectory $work -Label 'mock-stream-nonzero' -StandardOutputPath $out -StandardErrorPath $err -MaximumStandardOutputBytes 65536 -MaximumStandardErrorBytes 65536 -AuditPath $auditPath -JobId 'synthetic-stream'
    } -ArgumentList $gatePath,$engine,$childScript,$temp,$streamOut,$streamErr,$streamAudit
    try{
        $deadline=[DateTime]::UtcNow.AddSeconds(20)
        $observedBeforeExit=$false
        while([DateTime]::UtcNow -lt $deadline){
            if($streamJob.State -eq 'Running' -and (Test-Path -LiteralPath $streamOut)){
                # Writer holds the file with FileShare.Read. A concurrent reader
                # must grant Write sharing too, otherwise Windows rejects it
                # while the child is still running (the actual assertion target).
                $readStream=[System.IO.File]::Open($streamOut,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::ReadWrite)
                try{
                    $reader=New-Object System.IO.StreamReader($readStream,[System.Text.Encoding]::UTF8)
                    try{$visible=$reader.ReadToEnd()}finally{$reader.Dispose()}
                }finally{$readStream.Dispose()}
                if($visible -match 'first line русский'){$observedBeforeExit=$true;break}
            }
            if($streamJob.State -in @('Completed','Failed','Stopped')){break}
            Start-Sleep -Milliseconds 50
        }
        if(-not $observedBeforeExit){throw 'STREAM_NOT_DURABLE_BEFORE_CHILD_EXIT'}
        Wait-Job -Job $streamJob -Timeout 20|Out-Null
        if($streamJob.State -ne 'Completed'){throw 'STREAM_TEST_JOB_DID_NOT_COMPLETE'}
        $streamResult=Receive-Job -Job $streamJob
    }finally{
        if($streamJob.State -eq 'Running'){Stop-Job -Job $streamJob}
        Remove-Job -Job $streamJob -Force
    }
    if([int]$streamResult.exit_code -ne 7 -or [string]$streamResult.status -cne 'NONZERO_EXIT' -or [bool]$streamResult.limit_exceeded){throw 'STREAM_NONZERO_STATUS_INCORRECT'}
    $streamOutText=[System.IO.File]::ReadAllText($streamOut,[System.Text.Encoding]::UTF8)
    $streamErrText=[System.IO.File]::ReadAllText($streamErr,[System.Text.Encoding]::UTF8)
    if($streamOutText -notmatch 'first line русский' -or $streamOutText -notmatch 'partial before nonzero'){throw 'STREAM_STDOUT_PARTIAL_LOG_MISSING'}
    if($streamErrText -notmatch 'separate stderr русский' -or $streamOutText -match 'separate stderr'){throw 'STREAM_STDERR_NOT_SEPARATE'}
    $streamEvents=@(Get-Content -LiteralPath $streamAudit -Encoding UTF8|ForEach-Object{$_|ConvertFrom-Json})
    if($streamEvents.Count -ne 2 -or [string]$streamEvents[0].status -cne 'STARTING' -or [bool]$streamEvents[0].terminal){throw 'STREAM_START_EVENT_INCORRECT'}
    if([string]$streamEvents[1].status -cne 'NONZERO_EXIT' -or -not [bool]$streamEvents[1].terminal -or [int]$streamEvents[1].exit_code -ne 7){throw 'STREAM_TERMINAL_EVENT_INCORRECT'}
    if($streamEvents[0].PSObject.Properties['stdout'] -or $streamEvents[1].PSObject.Properties['stderr']){throw 'RAW_STREAM_CONTENT_LEAKED_TO_AUDIT'}

    $limitedOut=Join-Path $temp 'limited-stdout.log'
    $limitedErr=Join-Path $temp 'limited-stderr.log'
    $limitAudit=Join-Path $temp 'limit-audit.jsonl'
    $limited=Invoke-SeshatStreamingNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$childScript,'flood') -WorkingDirectory $temp -Label 'mock-stream-limit' -StandardOutputPath $limitedOut -StandardErrorPath $limitedErr -MaximumStandardOutputBytes 128 -MaximumStandardErrorBytes 128 -AuditPath $limitAudit -JobId 'synthetic-limit'
    if(-not [bool]$limited.limit_exceeded -or [string]$limited.status -cne 'OUTPUT_LIMIT_EXCEEDED' -or [string]$limited.limit_stream -cne 'stdout'){throw 'STREAM_LIMIT_DID_NOT_FAIL_CLOSED'}
    if((Get-Item -LiteralPath $limitedOut).Length -ne 128 -or [long]$limited.stdout_bytes -ne 128){throw 'STREAM_LIMIT_NOT_ENFORCED_EXACTLY'}
    $limitTerminal=(Get-Content -LiteralPath $limitAudit -Encoding UTF8|Select-Object -Last 1)|ConvertFrom-Json
    if([string]$limitTerminal.status -cne 'OUTPUT_LIMIT_EXCEEDED' -or -not [bool]$limitTerminal.terminal){throw 'STREAM_LIMIT_EVENT_INCORRECT'}

    $stderrLimitedOut=Join-Path $temp 'stderr-limited-stdout.log'
    $stderrLimitedErr=Join-Path $temp 'stderr-limited-stderr.log'
    $stderrLimited=Invoke-SeshatStreamingNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$childScript,'floodstderr') -WorkingDirectory $temp -Label 'mock-stderr-stream-limit' -StandardOutputPath $stderrLimitedOut -StandardErrorPath $stderrLimitedErr -MaximumStandardOutputBytes 128 -MaximumStandardErrorBytes 64 -JobId 'synthetic-stderr-limit'
    if(-not [bool]$stderrLimited.limit_exceeded -or [string]$stderrLimited.status -cne 'OUTPUT_LIMIT_EXCEEDED' -or [string]$stderrLimited.limit_stream -cne 'stderr'){throw 'STDERR_STREAM_LIMIT_DID_NOT_FAIL_CLOSED'}
    if((Get-Item -LiteralPath $stderrLimitedErr).Length -ne 64 -or [long]$stderrLimited.stderr_bytes -ne 64){throw 'STDERR_STREAM_LIMIT_NOT_ENFORCED_EXACTLY'}

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
    Write-Output 'PASS: synthetic buffered/streaming native IO, bounded durable partial logs, quoting, immutable receipts, stage recovery, and no-retry checks'
}catch{
    # Preserve the original test failure; a Windows child can transiently hold
    # its working directory and a finally-cleanup exception must not obscure it.
    [Console]::Error.WriteLine(('PUBLISHER_RECOVERY_TEST_FAILURE={0}: {1}' -f $_.Exception.GetType().Name,$_.Exception.Message))
    throw
}finally{
    $removed=$false
    for($cleanupAttempt=0;$cleanupAttempt -lt 8;$cleanupAttempt++){
        try{
            if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction Stop}
            $removed=$true
            break
        }catch{
            Start-Sleep -Milliseconds 500
        }
    }
    if(-not $removed){Write-Warning 'PUBLISHER_TEST_TEMP_CLEANUP_DEFERRED'}
}
