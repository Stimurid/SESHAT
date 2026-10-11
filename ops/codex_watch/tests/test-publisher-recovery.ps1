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
    $zeroWarningResults=@(Invoke-SeshatNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-Command',"[Console]::Error.WriteLine('synthetic warning'); exit 0") -WorkingDirectory $temp -Label 'mock-zero-warning' -AuditPath $audit -JobId 'synthetic-job')
    if($zeroWarningResults.Count -ne 1){throw 'NO_STDIN_NATIVE_RESULT_COUNT_CHANGED'}
    $zeroWarning=$zeroWarningResults[0]
    if($zeroWarning -isnot [System.Management.Automation.PSCustomObject]){throw 'NO_STDIN_NATIVE_RESULT_TYPE_CHANGED'}
    foreach($property in @('exit_code','stdout','stderr','stderr_present')){if(-not $zeroWarning.PSObject.Properties[$property]){throw ('NO_STDIN_NATIVE_RESULT_PROPERTY_MISSING_'+$property)}}
    if($zeroWarning.exit_code -ne 0 -or -not $zeroWarning.stderr_present){throw 'EXIT_ZERO_STDERR_NOT_CAPTURED'}
    Assert-SeshatNativeSuccess -Result $zeroWarning -FailureClass 'SHOULD_NOT_FAIL'
    $zeroAudit=(Get-Content -LiteralPath $audit -Encoding UTF8|Select-Object -First 1)|ConvertFrom-Json
    if([string]$zeroAudit.classification -cne 'EXIT_ZERO_STDERR'){throw 'EXIT_ZERO_STDERR_NOT_CLASSIFIED'}
    if($zeroAudit.PSObject.Properties['stderr']){throw 'RAW_STDERR_LEAKED_TO_AUDIT'}

    $nonzeroResults=@(Invoke-SeshatNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-Command',"[Console]::Error.WriteLine('synthetic failure'); exit 7") -WorkingDirectory $temp -Label 'mock-nonzero' -AuditPath $audit -JobId 'synthetic-job')
    if($nonzeroResults.Count -ne 1){throw 'NONZERO_NATIVE_RESULT_COUNT_CHANGED'}
    $nonzero=$nonzeroResults[0]
    if($nonzero -isnot [System.Management.Automation.PSCustomObject]){throw 'NONZERO_NATIVE_RESULT_TYPE_CHANGED'}
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
    $quotedResults=@(Invoke-SeshatNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$childScript,'args',$argOne,$argTwo,$argThree) -WorkingDirectory $temp -Label 'mock-quoted-arguments' -AuditPath $audit -JobId 'synthetic-job' -StandardInputText $unicodeInput)
    if($quotedResults.Count -ne 1){throw 'STDIN_NATIVE_RESULT_COUNT_CHANGED'}
    $quoted=$quotedResults[0]
    if($quoted -isnot [System.Management.Automation.PSCustomObject]){throw 'STDIN_NATIVE_RESULT_TYPE_CHANGED'}
    foreach($property in @('exit_code','stdout','stderr','stderr_present')){if(-not $quoted.PSObject.Properties[$property]){throw ('STDIN_NATIVE_RESULT_PROPERTY_MISSING_'+$property)}}
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

    # Synthetic pins are created only inside this isolated CI fixture. Production
    # pins live in the separately reviewed host policy and are never in the repo.
    $node=(Get-Command node.exe -CommandType Application|Select-Object -First 1).Source
    $nodeSignature=Get-AuthenticodeSignature -LiteralPath $node
    if([string]$nodeSignature.Status -cne 'Valid' -or -not $nodeSignature.SignerCertificate){throw 'CI_NODE_NOT_AUTHENTICODE_SIGNED'}
    $npmMockRoot=Join-Path $temp 'pinned npm package with spaces'
    $npmMockBin=Join-Path $npmMockRoot 'bin'
    [void][System.IO.Directory]::CreateDirectory($npmMockBin)
    $mockJs=Join-Path $npmMockBin 'codex.js'
    [System.IO.File]::WriteAllText($mockJs,'process.stdout.write("SESHAT_MOCK_NODE_CLI_READY\\n");',[System.Text.UTF8Encoding]::new($false))
    $packageJson=Join-Path $npmMockRoot 'package.json'
    [System.IO.File]::WriteAllText($packageJson,'{"name":"@openai/codex","version":"9.9.9"}',[System.Text.UTF8Encoding]::new($false))
    $policyPath=Join-Path $temp 'codex-launch-policy.json'
    $policy=[ordered]@{schema='seshat.codex-launch-policy.v1';policy_id='isolated-ci-fixture';node_path=$node;node_root=(Split-Path -Parent $node);node_sha256=(Get-SeshatFileSha256 -Path $node);node_signer_thumbprint=[string]$nodeSignature.SignerCertificate.Thumbprint;node_version=[string]([System.Diagnostics.FileVersionInfo]::GetVersionInfo($node).ProductVersion);codex_root=$npmMockRoot;codex_js_path=$mockJs;codex_js_sha256=(Get-SeshatFileSha256 -Path $mockJs);package_json_path=$packageJson;package_json_sha256=(Get-SeshatFileSha256 -Path $packageJson);package_name='@openai/codex';package_version='9.9.9'}
    [System.IO.File]::WriteAllText($policyPath,($policy|ConvertTo-Json -Compress),[System.Text.UTF8Encoding]::new($false))
    $binding=Get-SeshatCodexLaunchPolicyBinding -PolicyPath $policyPath
    $oldPath=$env:PATH
    $shadow=Join-Path $temp 'shadow-path'
    [void][System.IO.Directory]::CreateDirectory($shadow)
    [System.IO.File]::WriteAllText((Join-Path $shadow 'codex.cmd'),'@exit 99',[System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllBytes((Join-Path $shadow 'node.exe'),[byte[]](1,2,3,4))
    $env:PATH=$shadow+';'+$oldPath
    $npmLaunch=Resolve-SeshatCodexLaunch -ExpectedBinding $binding
    if([string]$npmLaunch.launch_mode -cne 'PINNED_NPM_NODE_ENTRYPOINT' -or [string]$npmLaunch.file_path -cne $node -or [string]$npmLaunch.argv_prefix[0] -cne $mockJs){throw 'PINNED_CODEX_LAUNCH_WRONG_ENTRYPOINT'}
    $cliOut=Join-Path $temp 'cli-mock-stdout.jsonl'
    $cliErr=Join-Path $temp 'cli-mock-stderr.log'
    try{$cliResult=Invoke-SeshatStreamingNativeCommand -FilePath ([string]$npmLaunch.file_path) -ArgumentList (@($npmLaunch.argv_prefix)+@('exec')) -WorkingDirectory $temp -Label 'mock-npm-codex' -StandardOutputPath $cliOut -StandardErrorPath $cliErr -MaximumStandardOutputBytes 8192 -MaximumStandardErrorBytes 8192 -JobId 'synthetic-cli'}finally{Close-SeshatCodexLaunch -Launch $npmLaunch;$env:PATH=$oldPath}
    if($cliResult.exit_code -ne 0 -or [string]$cliResult.status -cne 'COMPLETED' -or (Get-Content -LiteralPath $cliOut -Raw -Encoding UTF8) -notmatch 'SESHAT_MOCK_NODE_CLI_READY'){throw 'NPM_CODEX_LAUNCH_FAILED'}
    $admitted=Get-SeshatCodexLaunchPolicyBinding -PolicyPath $policyPath
    [System.IO.File]::AppendAllText($mockJs,'// drift',[System.Text.UTF8Encoding]::new($false))
    $blockedDrift=$false
    try{[void](Resolve-SeshatCodexLaunch -ExpectedBinding $admitted)}catch{$blockedDrift=([string]$_.Exception.Message -in @('CODEX_TRUSTED_FILE_HASH_DRIFT','CODEX_TRUST_POLICY_BINDING_DRIFT'))}
    if(-not $blockedDrift){throw 'POST_ADMISSION_CODEX_DRIFT_ACCEPTED'}
    $policy.package_json_path=Join-Path $npmMockRoot 'missing-package.json'
    [System.IO.File]::WriteAllText($policyPath,($policy|ConvertTo-Json -Compress),[System.Text.UTF8Encoding]::new($false))
    $blockedMissing=$false
    try{[void](Get-SeshatCodexLaunchPolicyBinding -PolicyPath $policyPath)}catch{$blockedMissing=([string]$_.Exception.Message -ceq 'TRUSTED_LAUNCH_FILE_MISSING')}
    if(-not $blockedMissing){throw 'MISSING_PINNED_PACKAGE_WAS_ACCEPTED'}
    $junction=Join-Path $temp 'rerouted-codex-root'
    New-Item -ItemType Junction -Path $junction -Target $npmMockRoot|Out-Null
    $policy.codex_root=$junction
    $policy.codex_js_path=Join-Path $junction 'bin\codex.js'
    $policy.codex_js_sha256=Get-SeshatFileSha256 -Path $mockJs
    $policy.package_json_path=Join-Path $junction 'package.json'
    $policy.package_json_sha256=Get-SeshatFileSha256 -Path $packageJson
    [System.IO.File]::WriteAllText($policyPath,($policy|ConvertTo-Json -Compress),[System.Text.UTF8Encoding]::new($false))
    $blockedReroute=$false
    try{[void](Get-SeshatCodexLaunchPolicyBinding -PolicyPath $policyPath)}catch{$blockedReroute=([string]$_.Exception.Message -ceq 'TRUSTED_LAUNCH_REPARSE_POINT')}
    if(-not $blockedReroute){throw 'REPARSE_REROUTED_CODEX_ROOT_ACCEPTED'}

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

    $hugePath=Join-Path $gitRepo 'huge-approved.txt'
    [System.IO.File]::WriteAllBytes($hugePath,(New-Object byte[] 2097153))
    $hugeBlocked=$false
    try{[void](Assert-SeshatChangedFileLimits -Repo $gitRepo -Paths @('huge-approved.txt'))}catch{$hugeBlocked=([string]$_.Exception.Message -ceq 'CHANGED_FILE_SIZE_LIMIT_EXCEEDED')}
    if(-not $hugeBlocked){throw 'HUGE_APPROVED_FILE_ACCEPTED'}
    $cachedAfterHuge=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$gitRepo,'diff','--cached','--name-only') -WorkingDirectory $temp -Label 'temp-git-cached-after-huge'
    Assert-SeshatNativeSuccess -Result $cachedAfterHuge -FailureClass 'TEMP_GIT_CACHED_DIFF_FAILED'
    if(@(Get-SeshatOutputLines -Text $cachedAfterHuge.stdout).Count -ne 0){throw 'HUGE_FILE_WAS_STAGED_BEFORE_REJECTION'}

    $boundaryPatch=Join-Path $temp 'boundary.patch'
    [System.IO.File]::WriteAllText($boundaryPatch,('+'+('x'*4093)+'ghp_'+('A'*20)+"`n"),[System.Text.UTF8Encoding]::new($false))
    if((Test-SeshatAddedDiffFile -Path $boundaryPatch) -cne 'POSSIBLE_CREDENTIAL_IN_DIFF'){throw 'CHUNK_BOUNDARY_SECRET_NOT_DETECTED'}
    $largePatch=Join-Path $temp 'large.patch'
    [System.IO.File]::WriteAllBytes($largePatch,(New-Object byte[] 257))
    if((Test-SeshatAddedDiffFile -Path $largePatch -MaximumBytes 256) -cne 'DIFF_SCAN_SIZE_LIMIT_EXCEEDED'){throw 'LARGE_PATCH_NOT_REJECTED'}
    $invalidPatch=Join-Path $temp 'invalid.patch'
    [System.IO.File]::WriteAllBytes($invalidPatch,[byte[]](43,255,10))
    if((Test-SeshatAddedDiffFile -Path $invalidPatch) -cne 'DIFF_NOT_VALID_UTF8'){throw 'UNSCANNABLE_DIFF_NOT_REJECTED'}
    if((Test-SeshatNumstatTextOnly -Lines @("-`t-`tbinary.bin")) -cne 'BINARY_STAGED_CONTENT_DENIED'){throw 'BINARY_NUMSTAT_NOT_REJECTED'}

    # Hermetic local bare-remote proof of the empty-expected-OID lease. Neither
    # collision path can alter the existing remote object.
    $bare=Join-Path $temp 'remote.git'
    $source=Join-Path $temp 'source'
    $bareInit=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('init','--bare',$bare) -WorkingDirectory $temp -Label 'collision-bare-init'
    Assert-SeshatNativeSuccess -Result $bareInit -FailureClass 'BARE_INIT_FAILED'
    $sourceInit=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('init',$source) -WorkingDirectory $temp -Label 'collision-source-init'
    Assert-SeshatNativeSuccess -Result $sourceInit -FailureClass 'SOURCE_INIT_FAILED'
    $configEmail=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'config','user.email','ci@example.invalid') -WorkingDirectory $temp -Label 'collision-config-email'
    Assert-SeshatNativeSuccess -Result $configEmail -FailureClass 'SOURCE_CONFIG_EMAIL_FAILED'
    $configName=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'config','user.name','SESHAT CI') -WorkingDirectory $temp -Label 'collision-config-name'
    Assert-SeshatNativeSuccess -Result $configName -FailureClass 'SOURCE_CONFIG_NAME_FAILED'
    [System.IO.File]::WriteAllText((Join-Path $source 'file.txt'),'base',[System.Text.UTF8Encoding]::new($false))
    $baseAdd=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'add','file.txt') -WorkingDirectory $temp -Label 'collision-base-add'
    Assert-SeshatNativeSuccess -Result $baseAdd -FailureClass 'SOURCE_ADD_FAILED'
    $baseCommit=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'commit','-m','base') -WorkingDirectory $temp -Label 'collision-base-commit'
    Assert-SeshatNativeSuccess -Result $baseCommit -FailureClass 'SOURCE_COMMIT_FAILED'
    $remoteAdd=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'remote','add','origin',$bare) -WorkingDirectory $temp -Label 'collision-remote-add'
    Assert-SeshatNativeSuccess -Result $remoteAdd -FailureClass 'SOURCE_REMOTE_ADD_FAILED'
    $seedPush=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'push','origin','HEAD:refs/heads/codex/existing') -WorkingDirectory $temp -Label 'collision-seed-push'
    Assert-SeshatNativeSuccess -Result $seedPush -FailureClass 'SEED_REMOTE_FAILED'
    $existingBeforeResult=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @(('--git-dir='+$bare),'rev-parse','refs/heads/codex/existing') -WorkingDirectory $temp -Label 'collision-existing-before'
    Assert-SeshatNativeSuccess -Result $existingBeforeResult -FailureClass 'EXISTING_REMOTE_READ_FAILED'
    $existingBefore=([string]$existingBeforeResult.stdout).Trim()
    [System.IO.File]::AppendAllText((Join-Path $source 'file.txt'),'next',[System.Text.UTF8Encoding]::new($false))
    $nextAdd=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'add','file.txt') -WorkingDirectory $temp -Label 'collision-next-add'
    Assert-SeshatNativeSuccess -Result $nextAdd -FailureClass 'SOURCE_NEXT_ADD_FAILED'
    $nextCommit=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'commit','-m','next') -WorkingDirectory $temp -Label 'collision-next-commit'
    Assert-SeshatNativeSuccess -Result $nextCommit -FailureClass 'SOURCE_NEXT_COMMIT_FAILED'
    $existingCollision=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'push','--atomic','origin','HEAD:refs/heads/codex/existing','--force-with-lease=refs/heads/codex/existing:') -WorkingDirectory $temp -Label 'collision-existing-create-only'
    if($existingCollision.exit_code -eq 0){throw 'CREATE_ONLY_PUSH_OVERWROTE_EXISTING_REF'}
    $existingAfterResult=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @(('--git-dir='+$bare),'rev-parse','refs/heads/codex/existing') -WorkingDirectory $temp -Label 'collision-existing-after'
    Assert-SeshatNativeSuccess -Result $existingAfterResult -FailureClass 'EXISTING_REMOTE_READ_AFTER_FAILED'
    $existingAfter=([string]$existingAfterResult.stdout).Trim()
    if($existingAfter -cne $existingBefore){throw 'EXISTING_REMOTE_REF_CHANGED'}
    $interimPreflight=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'ls-remote','--exit-code','--heads','origin','refs/heads/codex/interim') -WorkingDirectory $temp -Label 'collision-interim-preflight'
    if($interimPreflight.exit_code -ne 2){throw 'INTERIM_PREFLIGHT_NOT_ABSENT'}
    $nonzeroGitBlocked=$false
    try{Assert-SeshatNativeSuccess -Result $interimPreflight -FailureClass 'EXPECTED_NONZERO_GIT'}catch{$nonzeroGitBlocked=($_.Exception.Message -ceq 'EXPECTED_NONZERO_GIT')}
    if(-not $nonzeroGitBlocked){throw 'EXPECTED_NONZERO_GIT_WRAPPER_DID_NOT_FAIL_CLOSED'}
    $interimWriter=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'push','origin',($existingBefore+':refs/heads/codex/interim')) -WorkingDirectory $temp -Label 'collision-interim-writer'
    Assert-SeshatNativeSuccess -Result $interimWriter -FailureClass 'INTERIM_WRITER_FAILED'
    $interimBeforeResult=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @(('--git-dir='+$bare),'rev-parse','refs/heads/codex/interim') -WorkingDirectory $temp -Label 'collision-interim-before'
    Assert-SeshatNativeSuccess -Result $interimBeforeResult -FailureClass 'INTERIM_REMOTE_READ_FAILED'
    $interimBefore=([string]$interimBeforeResult.stdout).Trim()
    $interimCollision=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$source,'push','--atomic','origin','HEAD:refs/heads/codex/interim','--force-with-lease=refs/heads/codex/interim:') -WorkingDirectory $temp -Label 'collision-interim-create-only'
    if($interimCollision.exit_code -eq 0){throw 'INTERIM_REMOTE_WRITER_WAS_OVERWRITTEN'}
    $interimAfterResult=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @(('--git-dir='+$bare),'rev-parse','refs/heads/codex/interim') -WorkingDirectory $temp -Label 'collision-interim-after'
    Assert-SeshatNativeSuccess -Result $interimAfterResult -FailureClass 'INTERIM_REMOTE_READ_AFTER_FAILED'
    $interimAfter=([string]$interimAfterResult.stdout).Trim()
    if($interimAfter -cne $interimBefore){throw 'INTERIM_REMOTE_REF_CHANGED'}

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
        PRECHECK='NO_MUTATION_RECORDED_INSPECT_BEFORE_RETRY'
        BEFORE_COMMIT='MANUAL_INSPECT_WORKTREE_DO_NOT_RETRY'
        STAGED_ONLY='MANUAL_INSPECT_INDEX_DO_NOT_RETRY'
        COMMITTED_ONLY='MANUAL_VERIFY_REMOTE_BEFORE_ANY_PUSH'
        PUSHED_WITHOUT_PR='MANUAL_VERIFY_GITHUB_BEFORE_ANY_PR_CREATE'
        DRAFT_PUBLISHED='READBACK_VERIFY_EXISTING_DRAFT_NO_RETRY'
        RECONCILIATION_REQUIRED='READBACK_ALL_WITNESSES_MANUAL_DECISION_NO_RETRY'
    }
    foreach($phase in $expectedRecovery.Keys){
        if((Get-SeshatPublicationRecoveryDecision -Phase $phase) -cne $expectedRecovery[$phase]){throw ('BAD_RECOVERY_DECISION_'+$phase)}
    }
    foreach($action in @('git-add','git-commit','git-push-create-only','gh-pr-create')){
        $faultEvents=Join-Path $temp ('fault-'+$action+'.jsonl')
        $nonce=[guid]::NewGuid().ToString('N')
        $before=[ordered]@{head=('a'*40);index_present=($action -ne 'git-add');remote_head=if($action -in @('git-push-create-only','gh-pr-create')){('b'*40)}else{$null};pr_present=($action -eq 'gh-pr-create')}
        Write-SeshatMutationEvent -Path $faultEvents -JobId 'synthetic-job' -AttemptNonce $nonce -Action $action -Status 'INTENT' -Phase 'FAULT_BEFORE' -BeforeWitness $before
        $intent=(Get-Content -LiteralPath $faultEvents -Tail 1|ConvertFrom-Json)
        if((Get-SeshatMutationRecoveryState -LatestMutation $intent) -cne 'RECONCILIATION_REQUIRED_INTENT_WITHOUT_RETURN'){throw ('FAULT_BEFORE_NOT_RECONCILED_'+$action)}
        Write-SeshatMutationEvent -Path $faultEvents -JobId 'synthetic-job' -AttemptNonce $nonce -Action $action -Status 'RETURNED' -Phase 'FAULT_AFTER' -BeforeWitness $before -ExitCode 0
        $returned=(Get-Content -LiteralPath $faultEvents -Tail 1|ConvertFrom-Json)
        if((Get-SeshatMutationRecoveryState -LatestMutation $returned) -cne 'RECONCILIATION_REQUIRED_RETURN_WITHOUT_WITNESS'){throw ('FAULT_AFTER_NOT_RECONCILED_'+$action)}
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
    foreach($required in @('git-add','git-diff-check','git-diff-scan','git-commit','git-push-create-only','gh-pr-list-preflight','gh-pr-create','gh-pr-view')){
        if($publishSource -notmatch [regex]::Escape($required)){throw ('NATIVE_CHECKPOINT_MISSING_'+$required)}
    }
    if($publishSource -match '(?im)^\s*[&.]?\s*(python|pytest|ruff|pwsh|powershell)\s+.*(pytest|ruff|test-gate\.ps1)'){throw 'TRUSTED_PUBLISHER_EXECUTES_UNREVIEWED_TESTS'}
    if($publishSource.IndexOf("'gh-pr-list-preflight'") -lt 0 -or $publishSource.IndexOf("'gh-pr-list-preflight'") -gt $publishSource.IndexOf("'git-add'")){throw 'PR_EXISTENCE_CHECK_AFTER_STAGING'}
    if($publishSource.IndexOf("'gh-pr-create'") -lt $publishSource.IndexOf("'git-push-create-only'")){throw 'PR_CREATE_PRECEDES_CREATE_ONLY_PUSH'}
    if($publishSource -notmatch '--force-with-lease=refs/heads/' -or $publishSource -notmatch "expected_remote_oid='EMPTY'"){throw 'CREATE_ONLY_REMOTE_LEASE_MISSING'}
    if($publishSource -notmatch 'Write-SeshatMutationEvent' -or $publishSource -notmatch "'INTENT'" -or $publishSource -notmatch "'RETURNED'" -or $publishSource -notmatch "'COMPLETE'"){throw 'MUTATION_JOURNAL_MISSING'}
    if($publishSource -notmatch "phase='RECONCILIATION_REQUIRED'"){throw 'AMBIGUOUS_MUTATION_NOT_RECONCILED'}
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
