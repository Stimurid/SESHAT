# Pure governance gate. Source facts come from GitHub, not from Codex statements.
Set-StrictMode -Version Latest
function ConvertTo-SeshatNativeArgument {
    param([Parameter(Mandatory=$true)][AllowEmptyString()][string]$Value)
    if($Value.Length -eq 0){return '""'}
    if($Value -notmatch '[\s"]'){return $Value}
    # Windows PowerShell 5 lacks ProcessStartInfo.ArgumentList. This is the
    # CommandLineToArgvW-compatible quoting used only on that fallback path.
    return '"'+([regex]::Replace($Value,'(\\*)"','$1$1\"') -replace '(\\+)$','$1$1')+'"'
}
function Get-SeshatTextSha256 {
    param([Parameter(Mandatory=$true)][AllowEmptyString()][string]$Text)
    return Get-SeshatUtf8Sha256 -Text $Text
}
function Get-SeshatSafeErrorClass {
    param([Parameter(Mandatory=$true)][object]$ErrorRecord)
    $message=[string]$ErrorRecord.Exception.Message
    if($message -cmatch '^[A-Z][A-Z0-9_]{2,127}$'){return $message}
    $type=[string]$ErrorRecord.Exception.GetType().Name
    if($type -cmatch '^[A-Za-z][A-Za-z0-9]{1,127}$'){return $type}
    return 'UNCLASSIFIED_ERROR'
}
function ConvertTo-SeshatSanitizedLogText {
    param([AllowEmptyString()][string]$Text,[int]$MaximumLength=65536)
    $safe=[string]$Text
    $safe=$safe -replace '(?i)(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})','[REDACTED_CREDENTIAL]'
    $safe=$safe -replace '(?i)(https?://)[^/@\s:]+:[^/@\s]+@','$1[REDACTED_USERINFO]@'
    if($safe.Length -gt $MaximumLength){$safe=$safe.Substring(0,$MaximumLength)+"`n[TRUNCATED]"}
    return $safe
}
function Write-SeshatAppendJsonLine {
    param([Parameter(Mandatory=$true)][object]$Value,[Parameter(Mandatory=$true)][string]$Path)
    $parent=Split-Path -Parent $Path
    [void][System.IO.Directory]::CreateDirectory($parent)
    $json=($Value|ConvertTo-Json -Depth 8 -Compress)+"`n"
    $bytes=[System.Text.UTF8Encoding]::new($false).GetBytes($json)
    $stream=[System.IO.File]::Open($Path,[System.IO.FileMode]::Append,[System.IO.FileAccess]::Write,[System.IO.FileShare]::Read)
    try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush()}finally{$stream.Dispose()}
}
function Invoke-SeshatNativeCommand {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$ArgumentList,
        [Parameter(Mandatory=$true)][string]$WorkingDirectory,
        [Parameter(Mandatory=$true)][string]$Label,
        [string]$AuditPath,
        [string]$JobId='unknown',
        [AllowEmptyString()][string]$StandardInputText
    )
    if($Label -cnotmatch '^[a-z0-9][a-z0-9-]{1,63}$'){throw 'INVALID_NATIVE_COMMAND_LABEL'}
    $start=[System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$FilePath
    $start.WorkingDirectory=$WorkingDirectory
    $start.UseShellExecute=$false
    $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true
    $start.RedirectStandardError=$true
    $hasStandardInput=$PSBoundParameters.ContainsKey('StandardInputText')
    $start.RedirectStandardInput=$hasStandardInput
    $utf8NoBom=[System.Text.UTF8Encoding]::new($false)
    if($start.PSObject.Properties['StandardInputEncoding']){$start.StandardInputEncoding=$utf8NoBom}
    if($start.PSObject.Properties['StandardOutputEncoding']){$start.StandardOutputEncoding=$utf8NoBom}
    if($start.PSObject.Properties['StandardErrorEncoding']){$start.StandardErrorEncoding=$utf8NoBom}
    if($start.PSObject.Properties['ArgumentList']){
        foreach($argument in $ArgumentList){[void]$start.ArgumentList.Add([string]$argument)}
    }else{
        $start.Arguments=(@($ArgumentList|ForEach-Object{ConvertTo-SeshatNativeArgument -Value ([string]$_)}) -join ' ')
    }
    $process=[System.Diagnostics.Process]::new()
    $process.StartInfo=$start
    try{
        if(-not $process.Start()){throw 'NATIVE_PROCESS_START_FAILED'}
        $stdoutTask=$process.StandardOutput.ReadToEndAsync()
        $stderrTask=$process.StandardError.ReadToEndAsync()
        if($hasStandardInput){
            $process.StandardInput.Write($StandardInputText)
            $process.StandardInput.Close()
        }
        $process.WaitForExit()
        $stdout=[string]$stdoutTask.GetAwaiter().GetResult()
        $stderr=[string]$stderrTask.GetAwaiter().GetResult()
        $result=[pscustomobject]@{
            label=$Label;exit_code=[int]$process.ExitCode;stdout=$stdout;stderr=$stderr
            stderr_present=(-not [string]::IsNullOrWhiteSpace($stderr))
        }
        if($AuditPath){
            $event=[ordered]@{
                schema='seshat.native-command.v1';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
                job_id=$JobId;command=$Label;exit_code=$result.exit_code
                stderr_present=$result.stderr_present
                stderr_sha256=if($result.stderr_present){Get-SeshatTextSha256 -Text $stderr}else{$null}
                stderr_line_count=if($result.stderr_present){@($stderr -split "\r?\n"|Where-Object{$_}).Count}else{0}
                classification=if($result.exit_code -ne 0){'NONZERO_EXIT'}elseif($result.stderr_present){'EXIT_ZERO_STDERR'}else{'CLEAN_EXIT'}
            }
            Write-SeshatAppendJsonLine -Value $event -Path $AuditPath
        }
        return $result
    }finally{$process.Dispose()}
}
function Invoke-SeshatStreamingNativeCommand {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$ArgumentList,
        [Parameter(Mandatory=$true)][string]$WorkingDirectory,
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][string]$StandardOutputPath,
        [Parameter(Mandatory=$true)][string]$StandardErrorPath,
        [Parameter(Mandatory=$true)][long]$MaximumStandardOutputBytes,
        [Parameter(Mandatory=$true)][long]$MaximumStandardErrorBytes,
        [string]$AuditPath,
        [string]$JobId='unknown',
        [AllowEmptyString()][string]$StandardInputText
    )
    if($Label -cnotmatch '^[a-z0-9][a-z0-9-]{1,63}$'){throw 'INVALID_NATIVE_COMMAND_LABEL'}
    if($MaximumStandardOutputBytes -le 0 -or $MaximumStandardErrorBytes -le 0){throw 'INVALID_STREAM_LIMIT'}
    $stdoutFull=[System.IO.Path]::GetFullPath($StandardOutputPath)
    $stderrFull=[System.IO.Path]::GetFullPath($StandardErrorPath)
    if($stdoutFull -ieq $stderrFull){throw 'STREAM_PATH_COLLISION'}
    foreach($path in @($stdoutFull,$stderrFull)){
        $parent=Split-Path -Parent $path
        [void][System.IO.Directory]::CreateDirectory($parent)
    }
    $start=[System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$FilePath
    $start.WorkingDirectory=$WorkingDirectory
    $start.UseShellExecute=$false
    $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true
    $start.RedirectStandardError=$true
    $hasStandardInput=$PSBoundParameters.ContainsKey('StandardInputText')
    $start.RedirectStandardInput=$hasStandardInput
    $utf8NoBom=[System.Text.UTF8Encoding]::new($false)
    if($start.PSObject.Properties['StandardInputEncoding']){$start.StandardInputEncoding=$utf8NoBom}
    if($start.PSObject.Properties['StandardOutputEncoding']){$start.StandardOutputEncoding=$utf8NoBom}
    if($start.PSObject.Properties['StandardErrorEncoding']){$start.StandardErrorEncoding=$utf8NoBom}
    if($start.PSObject.Properties['ArgumentList']){
        foreach($argument in $ArgumentList){[void]$start.ArgumentList.Add([string]$argument)}
    }else{
        $start.Arguments=(@($ArgumentList|ForEach-Object{ConvertTo-SeshatNativeArgument -Value ([string]$_)}) -join ' ')
    }
    $process=[System.Diagnostics.Process]::new()
    $process.StartInfo=$start
    $stdoutFile=$null
    $stderrFile=$null
    $started=$false
    $terminalWritten=$false
    $stdoutBytes=[long]0
    $stderrBytes=[long]0
    $limitStream=$null
    try{
        $stdoutFile=[System.IO.File]::Open($stdoutFull,[System.IO.FileMode]::Create,[System.IO.FileAccess]::Write,[System.IO.FileShare]::Read)
        $stderrFile=[System.IO.File]::Open($stderrFull,[System.IO.FileMode]::Create,[System.IO.FileAccess]::Write,[System.IO.FileShare]::Read)
        if($AuditPath){
            Write-SeshatAppendJsonLine -Value ([ordered]@{
                schema='seshat.streaming-native-command.v1';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
                job_id=$JobId;command=$Label;status='STARTING';terminal=$false
                stdout_path=$stdoutFull;stderr_path=$stderrFull
                stdout_limit_bytes=$MaximumStandardOutputBytes;stderr_limit_bytes=$MaximumStandardErrorBytes
            }) -Path $AuditPath
        }
        if(-not $process.Start()){throw 'NATIVE_PROCESS_START_FAILED'}
        $started=$true
        if($hasStandardInput){
            $process.StandardInput.Write($StandardInputText)
            $process.StandardInput.Close()
        }
        $stdoutBuffer=New-Object byte[] 4096
        $stderrBuffer=New-Object byte[] 4096
        $stdoutTask=$process.StandardOutput.BaseStream.ReadAsync($stdoutBuffer,0,$stdoutBuffer.Length)
        $stderrTask=$process.StandardError.BaseStream.ReadAsync($stderrBuffer,0,$stderrBuffer.Length)
        $stdoutDone=$false
        $stderrDone=$false
        while(-not($stdoutDone -and $stderrDone)){
            $madeProgress=$false
            if(-not $stdoutDone -and $stdoutTask.IsCompleted){
                $count=[int]$stdoutTask.GetAwaiter().GetResult()
                if($count -eq 0){$stdoutDone=$true}else{
                    $remaining=$MaximumStandardOutputBytes-$stdoutBytes
                    $writeCount=[int][Math]::Min([long]$count,[Math]::Max([long]0,$remaining))
                    if($writeCount -gt 0){$stdoutFile.Write($stdoutBuffer,0,$writeCount);$stdoutFile.Flush();$stdoutBytes+=$writeCount}
                    if($writeCount -lt $count){$limitStream='stdout'}else{$stdoutTask=$process.StandardOutput.BaseStream.ReadAsync($stdoutBuffer,0,$stdoutBuffer.Length)}
                }
                $madeProgress=$true
            }
            if(-not $stderrDone -and $stderrTask.IsCompleted){
                $count=[int]$stderrTask.GetAwaiter().GetResult()
                if($count -eq 0){$stderrDone=$true}else{
                    $remaining=$MaximumStandardErrorBytes-$stderrBytes
                    $writeCount=[int][Math]::Min([long]$count,[Math]::Max([long]0,$remaining))
                    if($writeCount -gt 0){$stderrFile.Write($stderrBuffer,0,$writeCount);$stderrFile.Flush();$stderrBytes+=$writeCount}
                    if($writeCount -lt $count){$limitStream='stderr'}else{$stderrTask=$process.StandardError.BaseStream.ReadAsync($stderrBuffer,0,$stderrBuffer.Length)}
                }
                $madeProgress=$true
            }
            if($limitStream){
                if(-not $process.HasExited){$process.Kill()}
                $process.WaitForExit()
                $stdoutDone=$true
                $stderrDone=$true
            }elseif(-not $madeProgress){
                [System.Threading.Thread]::Sleep(20)
            }
        }
        $process.WaitForExit()
        $exitCode=[int]$process.ExitCode
        $status=if($limitStream){'OUTPUT_LIMIT_EXCEEDED'}elseif($exitCode -ne 0){'NONZERO_EXIT'}else{'COMPLETED'}
        if($AuditPath){
            Write-SeshatAppendJsonLine -Value ([ordered]@{
                schema='seshat.streaming-native-command.v1';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
                job_id=$JobId;command=$Label;status=$status;terminal=$true;exit_code=$exitCode
                stdout_bytes=$stdoutBytes;stderr_bytes=$stderrBytes;limit_stream=$limitStream
            }) -Path $AuditPath
            $terminalWritten=$true
        }
        return [pscustomobject]@{
            label=$Label;exit_code=$exitCode;status=$status;limit_exceeded=[bool]$limitStream
            limit_stream=$limitStream;stdout_path=$stdoutFull;stderr_path=$stderrFull
            stdout_bytes=$stdoutBytes;stderr_bytes=$stderrBytes
        }
    }catch{
        $streamError=$_
        if($started -and -not $process.HasExited){try{$process.Kill()}catch{}}
        if($AuditPath -and -not $terminalWritten){
            Write-SeshatAppendJsonLine -Value ([ordered]@{
                schema='seshat.streaming-native-command.v1';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
                job_id=$JobId;command=$Label;status='FAILED';terminal=$true
                exit_code=if($started -and $process.HasExited){[int]$process.ExitCode}else{$null}
                stdout_bytes=$stdoutBytes;stderr_bytes=$stderrBytes;error_class=(Get-SeshatSafeErrorClass -ErrorRecord $streamError)
            }) -Path $AuditPath
        }
        throw $streamError
    }finally{
        if($stdoutFile){$stdoutFile.Dispose()}
        if($stderrFile){$stderrFile.Dispose()}
        $process.Dispose()
    }
}
function Assert-SeshatNativeSuccess {
    param([Parameter(Mandatory=$true)][object]$Result,[Parameter(Mandatory=$true)][string]$FailureClass)
    if([int]$Result.exit_code -ne 0){throw $FailureClass}
}
function Get-SeshatOutputLines {
    param([Parameter(Mandatory=$true)][AllowEmptyString()][string]$Text)
    if([string]::IsNullOrEmpty($Text)){return @()}
    return @($Text -split "\r?\n"|Where-Object{$_ -ne ''})
}
function Write-SeshatPublicationEvent {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$JobId,
        [Parameter(Mandatory=$true)][ValidateSet('BEFORE_COMMIT','STAGED_ONLY','COMMITTED_ONLY','PUSHED_WITHOUT_PR','DRAFT_PUBLISHED')][string]$Phase,
        [Parameter(Mandatory=$true)][string]$Branch,
        [Parameter(Mandatory=$true)][string]$BaseSha,
        [string]$HeadSha,
        [string]$ErrorClass
    )
    $event=[ordered]@{
        schema='seshat.publication-stage.v1';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
        job_id=$JobId;phase=$Phase;branch=$Branch;base_sha=$BaseSha;head_sha=$HeadSha;error_class=$ErrorClass
    }
    Write-SeshatAppendJsonLine -Value $event -Path $Path
}
function Assert-SeshatPublicationAttemptAbsent {
    param([Parameter(Mandatory=$true)][string]$EventPath,[Parameter(Mandatory=$true)][string]$ReceiptPath)
    if(Test-Path -LiteralPath $ReceiptPath){throw 'PUBLICATION_RECEIPT_ALREADY_EXISTS'}
    if(Test-Path -LiteralPath $EventPath){throw 'PUBLICATION_ATTEMPT_ALREADY_RECORDED'}
}
function Start-SeshatPublicationAttempt {
    param(
        [Parameter(Mandatory=$true)][string]$EventPath,
        [Parameter(Mandatory=$true)][string]$ReceiptPath,
        [Parameter(Mandatory=$true)][string]$JobId,
        [Parameter(Mandatory=$true)][string]$Branch,
        [Parameter(Mandatory=$true)][string]$BaseSha
    )
    if(Test-Path -LiteralPath $ReceiptPath){throw 'PUBLICATION_RECEIPT_ALREADY_EXISTS'}
    $parent=Split-Path -Parent $EventPath
    [void][System.IO.Directory]::CreateDirectory($parent)
    $event=[ordered]@{
        schema='seshat.publication-stage.v1';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
        job_id=$JobId;phase='BEFORE_COMMIT';branch=$Branch;base_sha=$BaseSha;head_sha=$BaseSha;error_class=$null
    }
    $bytes=[System.Text.UTF8Encoding]::new($false).GetBytes((($event|ConvertTo-Json -Depth 8 -Compress)+"`n"))
    try{$stream=[System.IO.File]::Open($EventPath,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::Read)}catch{if(Test-Path -LiteralPath $EventPath){throw 'PUBLICATION_ATTEMPT_ALREADY_RECORDED'};throw}
    try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush()}finally{$stream.Dispose()}
}
function Test-SeshatPublicationReceipt {
    param([Parameter(Mandatory=$true)][object]$Receipt,[Parameter(Mandatory=$true)][object]$Job,[Parameter(Mandatory=$true)][string]$HeadSha)
    try{
        if([string]$Receipt.status -cne 'PUBLISHED_DRAFT_PR'){return 'BLOCK_PUBLISH_STATUS'}
        if([string]$Receipt.job_id -cne [string]$Job.job_id -or [int]$Receipt.issue -ne [int]$Job.issue_number){return 'BLOCK_PUBLISH_JOB_MISMATCH'}
        if([string]$Receipt.branch -cne [string]$Job.branch -or [string]$Receipt.head_sha -cne $HeadSha){return 'BLOCK_PUBLISH_HEAD_MISMATCH'}
        if([int]$Receipt.pr_number -le 0 -or [string]$Receipt.pr_state -cne 'OPEN' -or -not [bool]$Receipt.pr_is_draft){return 'BLOCK_PUBLISH_PR_STATE'}
        if([string]$Receipt.pr_base -cne 'main' -or [string]$Receipt.pr_head -cne [string]$Job.branch){return 'BLOCK_PUBLISH_PR_REFS'}
        return 'ADMIT'
    }catch{return 'BLOCK_MALFORMED_PUBLICATION_RECEIPT'}
}
function Get-SeshatPublicationRecoveryDecision {
    param([Parameter(Mandatory=$true)][ValidateSet('BEFORE_COMMIT','STAGED_ONLY','COMMITTED_ONLY','PUSHED_WITHOUT_PR','DRAFT_PUBLISHED')][string]$Phase)
    switch($Phase){
        'BEFORE_COMMIT' {return 'MANUAL_INSPECT_WORKTREE_DO_NOT_RETRY'}
        'STAGED_ONLY' {return 'MANUAL_INSPECT_INDEX_DO_NOT_RETRY'}
        'COMMITTED_ONLY' {return 'MANUAL_VERIFY_REMOTE_BEFORE_ANY_PUSH'}
        'PUSHED_WITHOUT_PR' {return 'MANUAL_VERIFY_GITHUB_BEFORE_ANY_PR_CREATE'}
        'DRAFT_PUBLISHED' {return 'READBACK_VERIFY_EXISTING_DRAFT_NO_RETRY'}
    }
}
function Get-SeshatUtf8Sha256 {
    param([Parameter(Mandatory=$true)][AllowEmptyString()][string] $Text)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$Text)
        return ([System.BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha256.Dispose()
    }
}
function Get-SeshatApprovedS2BPaths {
    return @(
        'src/seshat/reconciliation.py'
        'tests/test_reconciliation.py'
        'docs/S_IMPL_002B_RESULT.md'
    )
}
function Get-SeshatBundlePaths {
    return @(
        'ops/codex_watch/dispatch.ps1'
        'ops/codex_watch/gate.ps1'
        'ops/codex_watch/execute-task.ps1'
        'ops/codex_watch/publish.ps1'
        'ops/codex_watch/task_queue.json'
    )
}
function Test-SeshatExactStringSet {
    param(
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][object[]] $Left,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][object[]] $Right
    )
    $leftValues=@($Left | ForEach-Object {[string]$_})
    $rightValues=@($Right | ForEach-Object {[string]$_})
    if($leftValues.Count -ne $rightValues.Count){return $false}
    $set=New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    foreach($value in $leftValues){if(-not $set.Add($value)){return $false}}
    foreach($value in $rightValues){if(-not $set.Contains($value)){return $false}}
    return $true
}
function Test-SeshatOwnedPathSet {
    param(
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][object[]] $ApprovedPaths,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][object[]] $OwnedPaths,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][object[]] $DirtyPaths
    )
    $canonical=@(Get-SeshatApprovedS2BPaths)
    if(-not (Test-SeshatExactStringSet -Left $ApprovedPaths -Right $canonical)){return 'BLOCK_APPROVED_PATH_SET_MISMATCH'}
    $owned=@($OwnedPaths|ForEach-Object{[string]$_})
    if($owned.Count -eq 0){return 'BLOCK_EMPTY_JOB_OWNED_MANIFEST'}
    foreach($path in $owned){if($canonical -cnotcontains $path){return 'BLOCK_UNAPPROVED_JOB_PATH'}}
    if(-not (Test-SeshatExactStringSet -Left $owned -Right $DirtyPaths)){return 'BLOCK_DIRTY_PATH_SET_MISMATCH'}
    return 'ADMIT'
}
function Get-SeshatStatusPaths {
    param([Parameter(Mandatory=$true)][AllowEmptyCollection()][object[]] $StatusLines)
    $paths=@()
    foreach($item in $StatusLines){
        $line=[string]$item
        if($line.Length -le 3){throw 'BAD_PORCELAIN_RECORD'}
        $status=$line.Substring(0,2)
        $path=$line.Substring(3).Replace('\','/')
        if($status -match 'R|C|D'){throw 'NO_RENAMES_OR_DELETIONS_AUTOMATICALLY'}
        if($path -match '"| -> |\.\.|^/|:'){throw 'UNSAFE_DIFF_PATH'}
        $paths+=$path
    }
    return $paths
}
function Get-SeshatJobAuthorizationDigest {
    param([Parameter(Mandatory=$true)][object] $Job)
    $approved=(@($Job.approved_paths|ForEach-Object{[string]$_}|Sort-Object)-join ',')
    $bundle=(@($Job.ops_bundle|ForEach-Object{([string]$_.path)+'='+([string]$_.sha256)}|Sort-Object)-join ',')
    $fields=@(
        [string]$Job.job_id,[string]$Job.issue_number,[string]$Job.branch,[string]$Job.base_branch,[string]$Job.base_sha,
        [string]$Job.after_pr,[string]$Job.accepted_reviewed_head_sha,[string]$Job.ops_pr,
        [string]$Job.ops_merge_sha,[string]$Job.issue_body_utf8_sha256,[string]$Job.dispatch_key,
        $approved,$bundle
    )
    return Get-SeshatUtf8Sha256 -Text ($fields -join "`n")
}
function Test-SeshatJobAuthorization {
    param(
        [Parameter(Mandatory=$true)][object] $Job,
        [Parameter(Mandatory=$true)][object] $Marker
    )
    try {
        if([string]$Job.repo -cne 'C:\projects\seshat'){return 'BLOCK_JOB_REPOSITORY_MISMATCH'}
        if([int]$Job.issue_number -ne 17 -or [int]$Job.after_pr -ne 16 -or [int]$Job.ops_pr -ne 18){return 'BLOCK_JOB_TASK_BINDING_MISMATCH'}
        if([string]$Job.branch -cne 'codex/s2b-bounded-reconciliation'){return 'BLOCK_JOB_BRANCH_MISMATCH'}
        if([string]$Job.base_branch -cne 'main'){return 'BLOCK_JOB_BASE_BRANCH_MISMATCH'}
        if(-not ([string]$Job.job_id -cmatch '^S-IMPL-17-[0-9]{14}$')){return 'BLOCK_INVALID_JOB_ID'}
        if(-not ([string]$Job.base_sha -cmatch '^[0-9a-f]{40}$')){return 'BLOCK_INVALID_JOB_BASE'}
        if(-not ([string]$Job.accepted_reviewed_head_sha -cmatch '^[0-9a-f]{40}$')){return 'BLOCK_INVALID_REVIEWED_HEAD'}
        if(-not ([string]$Job.ops_merge_sha -cmatch '^[0-9a-f]{40}$')){return 'BLOCK_INVALID_OPS_MERGE_SHA'}
        if([string]$Job.issue_body_utf8_sha256 -cne '541bf6271d9a0c8f7c0ade9bc710d5fdc5d5ae3083ed6e898be04f5c8c0780b8'){return 'BLOCK_JOB_ISSUE_BODY_PIN_MISMATCH'}
        if(-not (Test-SeshatExactStringSet -Left @($Job.approved_paths) -Right @(Get-SeshatApprovedS2BPaths))){return 'BLOCK_APPROVED_PATH_SET_MISMATCH'}
        if(-not (Test-SeshatExactStringSet -Left @($Job.ops_bundle|ForEach-Object{$_.path}) -Right @(Get-SeshatBundlePaths))){return 'BLOCK_OPS_BUNDLE_PATH_SET_MISMATCH'}
        if(-not ([string]$Job.dispatch_key -cmatch '^pr16-[0-9a-f]{40}-issue17$')){return 'BLOCK_INVALID_DISPATCH_KEY'}
        if([string]$Marker.key -cne [string]$Job.dispatch_key -or [string]$Marker.job_id -cne [string]$Job.job_id){return 'BLOCK_DISPATCH_MARKER_BINDING_MISMATCH'}
        if([string]$Marker.state -cnotin @('AUTHORIZED','LAUNCHED')){return 'BLOCK_DISPATCH_MARKER_STATE'}
        $digest=Get-SeshatJobAuthorizationDigest -Job $Job
        if([string]$Job.authorization_digest -cne $digest -or [string]$Marker.authorization_digest -cne $digest){return 'BLOCK_JOB_AUTHORIZATION_DIGEST_MISMATCH'}
        return 'ADMIT'
    } catch {
        return 'BLOCK_MALFORMED_JOB_AUTHORIZATION'
    }
}
function Test-SeshatCanonicalJobPath {
    param([Parameter(Mandatory=$true)][string]$JobPath,[Parameter(Mandatory=$true)][string]$Root)
    $expected=[System.IO.Path]::GetFullPath((Join-Path $Root 'job.json'))
    $actual=[System.IO.Path]::GetFullPath($JobPath)
    return ($actual -ceq $expected)
}
function Test-SeshatPublishedPullRequest {
    param(
        [Parameter(Mandatory=$true)][object]$PullRequest,
        [Parameter(Mandatory=$true)][string]$Branch,
        [Parameter(Mandatory=$true)][string]$HeadSha
    )
    if([string]$PullRequest.state -cne 'OPEN'){return 'BLOCK_PR_NOT_OPEN'}
    if(-not [bool]$PullRequest.isDraft){return 'BLOCK_PR_NOT_DRAFT'}
    if([string]$PullRequest.baseRefName -cne 'main'){return 'BLOCK_PR_BASE_MISMATCH'}
    if([string]$PullRequest.headRefName -cne $Branch){return 'BLOCK_PR_HEAD_BRANCH_MISMATCH'}
    if([string]$PullRequest.headRefOid -cne $HeadSha){return 'BLOCK_PR_HEAD_SHA_MISMATCH'}
    if([int]$PullRequest.number -le 0){return 'BLOCK_PR_NUMBER_INVALID'}
    return 'ADMIT'
}
function Assert-SeshatExitReceiptAbsent {
    param([Parameter(Mandatory=$true)][string]$Path)
    if(Test-Path -LiteralPath $Path){throw 'EXIT_RECEIPT_ALREADY_EXISTS'}
}
function Write-SeshatJsonCreateNew {
    param([Parameter(Mandatory=$true)][object]$Value,[Parameter(Mandatory=$true)][string]$Path)
    $json=$Value|ConvertTo-Json -Depth 8 -Compress
    $bytes=[System.Text.UTF8Encoding]::new($false).GetBytes($json)
    $stream=[System.IO.File]::Open($Path,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
    try{$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
}
function Get-SeshatFileSha256 {
    param([Parameter(Mandatory=$true)][string]$Path)
    return ([string](Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash).ToLowerInvariant()
}
function New-SeshatBundleManifest {
    param(
        [Parameter(Mandatory=$true)][string]$Repo,
        [Parameter(Mandatory=$true)][string]$ScriptRoot,
        [Parameter(Mandatory=$true)][string]$OpsMergeSha,
        [Parameter(Mandatory=$true)][string]$BaseSha
    )
    $paths=@(Get-SeshatBundlePaths)
    $ancestor=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'merge-base','--is-ancestor',$OpsMergeSha,$BaseSha) -WorkingDirectory $Repo -Label 'bundle-ancestor'
    if($ancestor.exit_code -ne 0){throw 'OPS_MERGE_NOT_ANCESTOR_OF_BASE'}
    $reviewDiff=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList (@('-C',$Repo,'diff','--quiet',$OpsMergeSha,$BaseSha,'--')+$paths) -WorkingDirectory $Repo -Label 'bundle-reviewed-diff'
    if($reviewDiff.exit_code -ne 0){throw 'OPS_BUNDLE_CHANGED_AFTER_REVIEW'}
    $worktreeDiff=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList (@('-C',$Repo,'diff','--quiet',$BaseSha,'--')+$paths) -WorkingDirectory $Repo -Label 'bundle-worktree-diff'
    if($worktreeDiff.exit_code -ne 0){throw 'OPS_BUNDLE_WORKTREE_DRIFT'}
    $manifest=@()
    foreach($relative in $paths){
        $installed=Join-Path $ScriptRoot ([System.IO.Path]::GetFileName($relative))
        $source=Join-Path $Repo $relative
        if(-not(Test-Path -LiteralPath $installed) -or -not(Test-Path -LiteralPath $source)){throw 'OPS_BUNDLE_FILE_MISSING'}
        $installedSha=Get-SeshatFileSha256 -Path $installed
        if($installedSha -cne (Get-SeshatFileSha256 -Path $source)){throw 'OPS_INSTALLED_BUNDLE_HASH_MISMATCH'}
        $manifest+=[pscustomobject]@{path=$relative;sha256=$installedSha}
    }
    return $manifest
}
function Assert-SeshatBundleProvenance {
    param(
        [Parameter(Mandatory=$true)][object]$Job,
        [Parameter(Mandatory=$true)][string]$Repo,
        [Parameter(Mandatory=$true)][string]$ScriptRoot
    )
    $actual=@(New-SeshatBundleManifest -Repo $Repo -ScriptRoot $ScriptRoot -OpsMergeSha ([string]$Job.ops_merge_sha) -BaseSha ([string]$Job.base_sha))
    foreach($entry in $actual){
        $record=@($Job.ops_bundle|Where-Object{[string]$_.path -ceq [string]$entry.path})
        if($record.Count -ne 1 -or [string]$record[0].sha256 -cne [string]$entry.sha256){throw 'OPS_BUNDLE_MANIFEST_MISMATCH'}
    }
}
function Test-SeshatDispatchGate {
    param(
        [Parameter(Mandatory=$true)][object] $Transition,
        [Parameter(Mandatory=$true)][object] $PriorPr,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][object[]] $PriorComments,
        [Parameter(Mandatory=$true)][object] $OpsPr,
        [Parameter(Mandatory=$true)][object] $NextIssue,
        [Parameter(Mandatory=$true)][string] $RemoteMainSha,
        [Parameter(Mandatory=$true)][object[]] $MainRuns
    )
    $prLabels = @($PriorPr.labels | ForEach-Object { [string]$_.name })
    $issueLabels = @($NextIssue.labels | ForEach-Object { [string]$_.name })
    if ([int]$PriorPr.number -ne [int]$Transition.after_pr) { return 'BLOCK_PR_ID_MISMATCH' }
    if ([string]$PriorPr.base.ref -ne 'main') { return 'BLOCK_PR_BASE_NOT_MAIN' }
    if (-not [bool]$PriorPr.merged -or [string]$PriorPr.state -ne 'closed' -or -not $PriorPr.merged_at) {
        return 'WAIT_PRIOR_PR_NOT_MERGED'
    }
    if ($prLabels -cnotcontains [string]$Transition.accepted_label) {
        return 'WAIT_EXPLICIT_ENGINEERING_ACCEPTANCE'
    }
    $reviewedHeadSha = [string]$PriorPr.head.sha
    if (-not ($reviewedHeadSha -cmatch '^[0-9a-f]{40}$')) { return 'BLOCK_INVALID_PRIOR_HEAD_SHA' }
    $acceptanceToken = 'SESHAT_ENGINEERING_ACCEPTED_SHA=' + $reviewedHeadSha
    $acceptedComments = @($PriorComments | Where-Object {
        [string]$_.user.login -ceq 'Stimurid' -and
        @([string]$_.body -split "\r?\n") -ccontains $acceptanceToken
    })
    if ($acceptedComments.Count -eq 0) { return 'WAIT_REVIEWED_PR_SHA_ACCEPTANCE_MISSING' }
    if (-not $Transition.PSObject.Properties['ops_pr'] -or [int]$Transition.ops_pr -ne 18) {
        return 'BLOCK_OPS_PR_NOT_PINNED'
    }
    if ([int]$OpsPr.number -ne [int]$Transition.ops_pr) { return 'BLOCK_OPS_PR_ID_MISMATCH' }
    if ([string]$OpsPr.base.ref -ne 'main') { return 'BLOCK_OPS_PR_BASE_NOT_MAIN' }
    if (-not [bool]$OpsPr.merged -or [string]$OpsPr.state -ne 'closed' -or -not $OpsPr.merged_at) {
        return 'WAIT_OPS_PR_NOT_MERGED'
    }
    if ([int]$NextIssue.number -ne [int]$Transition.next_issue -or [string]$NextIssue.state -ne 'open') {
        return 'BLOCK_NEXT_ISSUE_NOT_OPEN'
    }
    if ($issueLabels -cnotcontains [string]$Transition.ready_label) {
        return 'WAIT_NEXT_ISSUE_NOT_APPROVED'
    }
    if (-not $Transition.PSObject.Properties['next_issue_body_utf8_sha256']) {
        return 'BLOCK_NEXT_ISSUE_BODY_NOT_PINNED'
    }
    $approvedBodySha = [string]$Transition.next_issue_body_utf8_sha256
    if (-not ($approvedBodySha -cmatch '^[0-9a-f]{64}$')) {
        return 'BLOCK_NEXT_ISSUE_BODY_NOT_PINNED'
    }
    $liveBodySha = Get-SeshatUtf8Sha256 -Text ([string]$NextIssue.body)
    if ($liveBodySha -cne $approvedBodySha) { return 'BLOCK_NEXT_ISSUE_BODY_DRIFT' }
    if (-not ($RemoteMainSha -match '^[0-9a-f]{40}$')) { return 'BLOCK_INVALID_MAIN_SHA' }
    if (-not (@($MainRuns | Where-Object {
        [string]$_.path -ceq '.github/workflows/ci.yml' -and
        [string]$_.repository.full_name -ceq 'Stimurid/SESHAT' -and
        [string]$_.event -ceq 'push' -and [string]$_.head_branch -ceq 'main' -and
        [string]$_.head_sha -ceq $RemoteMainSha -and
        [string]$_.status -ceq 'completed' -and [string]$_.conclusion -ceq 'success'
    }).Count -gt 0)) { return 'WAIT_MAIN_CI_NOT_GREEN' }
    return 'ADMIT'
}
