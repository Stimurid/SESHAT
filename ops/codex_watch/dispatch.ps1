# Fail-closed gate and single-active Codex dispatcher; without -Apply it is a dry run.
param([switch]$Apply)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Repo='C:\projects\seshat'
$Root='C:\Users\Homee\AppData\Local\SESHAT\watch'
. (Join-Path $PSScriptRoot 'gate.ps1')
$lock=New-Object System.Threading.Mutex($false,'Local\SESHAT_Codex_Dispatch')
if(-not $lock.WaitOne(0)){exit 0}
$dispatchGit=''
$dispatchGh=''
function Need([bool]$ok,[string]$reason){if(-not $ok){throw $reason}}
function Invoke-DispatchGit {
    param([Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$GitArgs)
    if(-not $dispatchGit){throw 'DISPATCH_GIT_POLICY_UNBOUND'}
    $result=Invoke-SeshatNativeCommand -FilePath $dispatchGit -ArgumentList (@('-C',$Repo)+$GitArgs) -WorkingDirectory $Repo -Label 'dispatch-git'
    $global:LASTEXITCODE=[int]$result.exit_code
    return $result
}
function FromGh([string]$url){
    if(-not $dispatchGh){throw 'DISPATCH_GH_POLICY_UNBOUND'}
    $apiArgs=@('api',$url)
    $result=Invoke-SeshatNativeCommand -FilePath $dispatchGh -ArgumentList $apiArgs -WorkingDirectory $Repo -Label 'dispatch-gh-api'
    Need ($result.exit_code -eq 0) ('GH_QUERY_FAILED_'+$url.Split('?')[0])
    $raw=@($result.stdout -split "`n")
    return (($raw -join [Environment]::NewLine)|ConvertFrom-Json)
}
function Save-Atomic([object]$val,[string]$path){
    $tmp=$path+'.'+$PID+'.tmp'
    $val|ConvertTo-Json -Compress -Depth 8|Set-Content $tmp -Encoding UTF8
    Move-Item $tmp $path -Force
}
function State([string]$label,[string]$detail=''){
    if(-not(Test-Path $Root)){New-Item $Root -ItemType Directory -Force|Out-Null}
    $p=Join-Path $Root 'dispatch_state.json'
    $old=$null
    if(Test-Path $p){try{$old=Get-Content $p -Raw|ConvertFrom-Json}catch{}}
    $v=[ordered]@{checked_at_utc=(Get-Date).ToUniversalTime().ToString('o');status=$label;detail=$detail}
    Save-Atomic $v $p
    if(-not $old -or $old.status -ne $label -or $old.detail -ne $detail){
        ($v|ConvertTo-Json -Compress)|Add-Content (Join-Path $Root 'dispatch_events.jsonl') -Encoding UTF8
    }
    Write-Output ("DISPATCH_STATE="+$label+" "+$detail)
}
try {
    Need (Test-Path (Join-Path $PSScriptRoot 'task_queue.json')) 'QUEUE_MISSING'
    $gitGhLaunchPolicy=Get-SeshatGitGhLaunchPolicyBinding
    $dispatchGit=[string]$gitGhLaunchPolicy.git_exe_path
    $dispatchGh=[string]$gitGhLaunchPolicy.gh_exe_path
    $originResult=Invoke-DispatchGit -GitArgs @('remote','get-url','origin')
    Need ($originResult.exit_code -eq 0 -and $originResult.stdout.Trim() -eq 'https://github.com/Stimurid/SESHAT.git') 'ORIGIN_MISMATCH'
    $queue=Get-Content (Join-Path $PSScriptRoot 'task_queue.json') -Raw|ConvertFrom-Json
    Need ([int]$queue.schema_version -eq 2 -and @($queue.transitions).Count -eq 1) 'UNAPPROVED_QUEUE'
    $t=@($queue.transitions)[0]
    Need (Test-SeshatExactStringSet -Left @($t.approved_paths) -Right @(Get-SeshatApprovedS2BPaths)) 'UNAPPROVED_PATH_MANIFEST'
    $pr=FromGh ("repos/Stimurid/SESHAT/pulls/"+[int]$t.after_pr)
    $priorComments=FromGh ("repos/Stimurid/SESHAT/issues/"+[int]$t.after_pr+"/comments?per_page=100")
    $opsPr=FromGh ("repos/Stimurid/SESHAT/pulls/"+[int]$t.ops_pr)
    $next=FromGh ("repos/Stimurid/SESHAT/issues/"+[int]$t.next_issue)
    $remote=FromGh 'repos/Stimurid/SESHAT/git/ref/heads/main'
    $sha=[string]$remote.object.sha
    $ci=FromGh 'repos/Stimurid/SESHAT/actions/runs?branch=main&per_page=30'
    $decision=Test-SeshatDispatchGate -Transition $t -PriorPr $pr -PriorComments @($priorComments) -OpsPr $opsPr -NextIssue $next -RemoteMainSha $sha -MainRuns @($ci.workflow_runs)
    if($decision -ne 'ADMIT'){State $decision;exit 0}
    $key=("pr"+[int]$t.after_pr+"-"+[string]$pr.merge_commit_sha+"-issue"+[int]$t.next_issue)
    Need ($key -match '^[A-Za-z0-9-]+$') 'UNSAFE_DISPATCH_KEY'
    $dispatchDir=Join-Path $Root 'dispatches'
    New-Item $dispatchDir -ItemType Directory -Force|Out-Null
    $marker=Join-Path $dispatchDir ($key+'.json')
    if(Test-Path $marker){State 'ALREADY_DISPATCHED' $key;exit 0}
    if(-not $Apply){State 'WOULD_DISPATCH' $key;exit 0}
    $oldJob=Join-Path $Root 'job.json'
    $oldExit=Join-Path $Root 'exit.json'
    if(Test-Path $oldJob){
        $j=Get-Content $oldJob -Raw|ConvertFrom-Json
        if(-not(Test-Path $oldExit)){State 'BLOCK_UNRESOLVED_PREVIOUS_JOB';exit 0}
        $e=Get-Content $oldExit -Raw|ConvertFrom-Json
        if([string]$e.job_id -ne [string]$j.job_id){State 'BLOCK_PREVIOUS_JOB_MISMATCH';exit 0}
    }
    $statusResult=Invoke-SeshatBoundedNativeText -FilePath $dispatchGit -ArgumentList @('-C',$Repo,'-c','core.quotePath=false','status','--porcelain=v1','-uall') -WorkingDirectory $Repo -Label 'dispatch-git-status' -MaximumStandardOutputBytes 262144 -MaximumStandardErrorBytes 32768 -MaximumLines 64
    if(@($statusResult.lines).Count -gt 0){
        State 'BLOCK_DIRTY_WORKTREE';exit 0
    }
    $branch=[string]$t.next_branch
    Need ($branch -match '^codex/[a-z0-9][a-z0-9-]{4,79}$') 'UNSAFE_BRANCH'
    $showRef=Invoke-DispatchGit -GitArgs @('show-ref','--verify','--quiet',('refs/heads/'+$branch))
    if($showRef.exit_code -eq 0){State 'BLOCK_BRANCH_EXISTS';exit 0}
    $lsRemote=Invoke-DispatchGit -GitArgs @('ls-remote','--exit-code','--heads','origin',('refs/heads/'+$branch))
    if($lsRemote.exit_code -eq 0){State 'BLOCK_REMOTE_BRANCH_EXISTS';exit 0}
    Need ($lsRemote.exit_code -eq 2) 'REMOTE_BRANCH_PREFLIGHT_FAILED'
    $encodedHead=[uri]::EscapeDataString('Stimurid:'+$branch)
    $existingPulls=@(FromGh ("repos/Stimurid/SESHAT/pulls?state=all&head="+$encodedHead+"&per_page=2"))
    if($existingPulls.Count -gt 0){State 'BLOCK_REMOTE_PR_EXISTS';exit 0}
    # The pins are supplied by a separately reviewed, host-owned policy. They are
    # copied into the authorization digest; this repository never chooses them.
    $codexLaunchPolicy=Get-SeshatCodexLaunchPolicyBinding
    if(Test-Path $oldJob){
        $j=Get-Content $oldJob -Raw|ConvertFrom-Json
        $safe=([string]$j.job_id -replace '[^A-Za-z0-9_-]','_')
        $archive=Join-Path (Join-Path $Root 'archive') ($safe+'-'+(Get-Date -Format 'yyyyMMddHHmmss'))
        New-Item $archive -ItemType Directory -Force|Out-Null
        foreach($n in @('job.json','exit.json','state.json','stdout.jsonl','stderr.log','last_message.txt','publish_receipt.json','publisher-output.log','host-pytest.log','host-ruff.log','task_prompt.txt')){
            $p=Join-Path $Root $n
            if(Test-Path $p){Copy-Item $p (Join-Path $archive $n) -Force}
        }
    }
    $fetch=Invoke-DispatchGit -GitArgs @('fetch','origin','main')
    Need ($fetch.exit_code -eq 0) 'GIT_FETCH_FAILED'
    $originMain=Invoke-DispatchGit -GitArgs @('rev-parse','origin/main')
    Need ($originMain.exit_code -eq 0 -and $originMain.stdout.Trim() -eq $sha) 'MAIN_MOVED_RETRY'
    $switchMain=Invoke-DispatchGit -GitArgs @('switch','main')
    Need ($switchMain.exit_code -eq 0) 'GIT_SWITCH_MAIN_FAILED'
    $ffMerge=Invoke-DispatchGit -GitArgs @('merge','--ff-only','origin/main')
    Need ($ffMerge.exit_code -eq 0) 'LOCAL_FAST_FORWARD_FAILED'
    $headSha=Invoke-DispatchGit -GitArgs @('rev-parse','HEAD')
    Need ($headSha.exit_code -eq 0 -and $headSha.stdout.Trim() -eq $sha) 'LOCAL_MAIN_SHA_MISMATCH'
    $opsBundle=@(New-SeshatBundleManifest -Repo $Repo -ScriptRoot $PSScriptRoot -OpsMergeSha ([string]$opsPr.merge_commit_sha) -BaseSha $sha -GitExePath $dispatchGit)
    $switchBranch=Invoke-DispatchGit -GitArgs @('switch','-c',$branch)
    Need ($switchBranch.exit_code -eq 0) 'GIT_SWITCH_TASK_FAILED'
    # No automatic remote PR merge, only local fast-forward of already accepted main.
    foreach($n in @('exit.json','stdout.jsonl','stderr.log','last_message.txt','publish_receipt.json','publisher-output.log','host-pytest.log','host-ruff.log','task_prompt.txt')){
        $p=Join-Path $Root $n
        if(Test-Path $p){Remove-Item $p -Force}
    }
    $jobId=("S-IMPL-"+[int]$t.next_issue+"-"+(Get-Date -Format 'yyyyMMddHHmmss'))
    # Preserve the reviewed instruction byte-for-byte as UTF-8 (no wrapper, BOM or added newline).
    $promptPath=Join-Path $Root 'task_prompt.txt'
    [System.IO.File]::WriteAllText($promptPath,[string]$next.body,(New-Object System.Text.UTF8Encoding($false)))
    $job=[ordered]@{
        job_id=$jobId;issue_number=[int]$t.next_issue
        issue_url=("https://github.com/Stimurid/SESHAT/issues/"+[int]$t.next_issue)
        after_pr=[int]$t.after_pr;accepted_merge_sha=[string]$pr.merge_commit_sha
        accepted_reviewed_head_sha=[string]$pr.head.sha
        ops_pr=[int]$t.ops_pr;ops_merge_sha=[string]$opsPr.merge_commit_sha
        issue_body_utf8_sha256=[string]$t.next_issue_body_utf8_sha256
        dispatch_key=$key;approved_paths=@($t.approved_paths);ops_bundle=$opsBundle
        codex_launch_policy=$codexLaunchPolicy
        git_gh_launch_policy=$gitGhLaunchPolicy
        repo=$Repo;branch=$branch;base_branch='main';base_sha=$sha;runner_pid=0
        created_at_utc=(Get-Date).ToUniversalTime().ToString('o')
    }
    $job['authorization_digest']=Get-SeshatJobAuthorizationDigest -Job $job
    Save-Atomic $job $oldJob
    Save-Atomic ([ordered]@{key=$key;job_id=$jobId;state='AUTHORIZED';authorization_digest=$job.authorization_digest}) $marker
    $exe=Join-Path $PSScriptRoot 'execute-task.ps1'
    $p=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$exe,'-JobPath',$oldJob) -WindowStyle Hidden -PassThru
    Save-Atomic ([ordered]@{key=$key;job_id=$jobId;state='LAUNCHED';runner_pid=$p.Id;authorization_digest=$job.authorization_digest}) $marker
    State 'LAUNCHED' ("job="+$jobId+" PID="+$p.Id)
} catch {
    State 'DISPATCH_ERROR' $_.Exception.GetType().Name
    exit 1
} finally {
    $lock.ReleaseMutex()
    $lock.Dispose()
}
