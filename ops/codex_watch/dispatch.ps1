# Fail-closed gate and single-active Codex dispatcher; without -Apply it is a dry run.
param([switch]$Apply)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Repo='C:\projects\seshat'
$Root='C:\Users\Homee\AppData\Local\SESHAT\watch'
. (Join-Path $PSScriptRoot 'gate.ps1')
$lock=New-Object System.Threading.Mutex($false,'Local\SESHAT_Codex_Dispatch')
if(-not $lock.WaitOne(0)){exit 0}
function Need([bool]$ok,[string]$reason){if(-not $ok){throw $reason}}
function FromGh([string]$url){
    $raw=@(& gh api $url 2>$null)
    Need ($LASTEXITCODE -eq 0) ('GH_QUERY_FAILED_'+$url.Split('?')[0])
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
    Need ((& git -C $Repo remote get-url origin) -eq 'https://github.com/Stimurid/SESHAT.git') 'ORIGIN_MISMATCH'
    $queue=Get-Content (Join-Path $PSScriptRoot 'task_queue.json') -Raw|ConvertFrom-Json
    Need ([int]$queue.schema_version -eq 1 -and @($queue.transitions).Count -eq 1) 'UNAPPROVED_QUEUE'
    $t=@($queue.transitions)[0]
    $pr=FromGh ("repos/Stimurid/SESHAT/pulls/"+[int]$t.after_pr)
    if(-not $pr.merged -or $pr.state -ne 'closed'){State 'WAIT_PRIOR_PR_NOT_MERGED';exit 0}
    if(@($pr.labels|ForEach-Object{$_.name}) -cnotcontains [string]$t.accepted_label){
        State 'WAIT_EXPLICIT_ENGINEERING_ACCEPTANCE';exit 0
    }
    $next=FromGh ("repos/Stimurid/SESHAT/issues/"+[int]$t.next_issue)
    $remote=FromGh 'repos/Stimurid/SESHAT/git/ref/heads/main'
    $sha=[string]$remote.object.sha
    $ci=FromGh 'repos/Stimurid/SESHAT/actions/runs?branch=main&per_page=30'
    $decision=Test-SeshatDispatchGate -Transition $t -PriorPr $pr -NextIssue $next -RemoteMainSha $sha -MainRuns @($ci.workflow_runs)
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
    if(@(& git -C $Repo status --porcelain=v1 -uall).Count -gt 0){
        State 'BLOCK_DIRTY_WORKTREE';exit 0
    }
    $branch=[string]$t.next_branch
    Need ($branch -match '^codex/[a-z0-9][a-z0-9-]{4,79}$') 'UNSAFE_BRANCH'
    & git -C $Repo show-ref --verify --quiet ('refs/heads/'+$branch)
    if($LASTEXITCODE -eq 0){State 'BLOCK_BRANCH_EXISTS';exit 0}
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
    & git -C $Repo fetch origin main
    Need ($LASTEXITCODE -eq 0) 'GIT_FETCH_FAILED'
    Need ((& git -C $Repo rev-parse 'origin/main') -eq $sha) 'MAIN_MOVED_RETRY'
    & git -C $Repo switch main
    Need ($LASTEXITCODE -eq 0) 'GIT_SWITCH_MAIN_FAILED'
    & git -C $Repo merge --ff-only origin/main
    Need ($LASTEXITCODE -eq 0) 'LOCAL_FAST_FORWARD_FAILED'
    & git -C $Repo switch -c $branch
    Need ($LASTEXITCODE -eq 0) 'GIT_SWITCH_TASK_FAILED'
    # No automatic remote PR merge, only local fast-forward of already accepted main.
    foreach($n in @('exit.json','stdout.jsonl','stderr.log','last_message.txt','publish_receipt.json','publisher-output.log','host-pytest.log','host-ruff.log','task_prompt.txt')){
        $p=Join-Path $Root $n
        if(Test-Path $p){Remove-Item $p -Force}
    }
    $jobId=("S-IMPL-"+[int]$t.next_issue+"-"+(Get-Date -Format 'yyyyMMddHHmmss'))
    $prompt=@"
Execute the preapproved SESHAT issue #$($t.next_issue) on branch $branch from main@$sha.
Read AGENTS.md, docs/SESHAT_IMPLEMENTATION_PLAN_v0.1.md, and coordination inbox #6.
Implement real code, tests, and docs/S_IMPL_002B_RESULT.md; do not stop at prose. Use synthetic data.
Do not perform Git writes, git commit/push/merge, or gh. The trusted host runner will lint,
test, validate files, commit, push, and open a DRAFT PR. Codex sandbox remains workspace-write.
No donor import, protected corpus, automatic scientific acceptance or unrelated feature work.

PREAPPROVED ISSUE BODY:
$($next.body)
"@
    $prompt|Set-Content (Join-Path $Root 'task_prompt.txt') -Encoding UTF8
    $job=[ordered]@{
        job_id=$jobId;issue_number=[int]$t.next_issue
        issue_url=("https://github.com/Stimurid/SESHAT/issues/"+[int]$t.next_issue)
        after_pr=[int]$t.after_pr;accepted_merge_sha=[string]$pr.merge_commit_sha
        repo=$Repo;branch=$branch;base_sha=$sha;runner_pid=0
        created_at_utc=(Get-Date).ToUniversalTime().ToString('o')
    }
    Save-Atomic $job $oldJob
    Save-Atomic ([ordered]@{key=$key;job_id=$jobId;state='LAUNCHING'}) $marker
    $exe=Join-Path $PSScriptRoot 'execute-task.ps1'
    $p=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$exe,'-JobPath',$oldJob) -WindowStyle Hidden -PassThru
    Save-Atomic ([ordered]@{key=$key;job_id=$jobId;state='LAUNCHED';runner_pid=$p.Id}) $marker
    State 'LAUNCHED' ("job="+$jobId+" PID="+$p.Id)
} catch {
    State 'DISPATCH_ERROR' $_.Exception.GetType().Name
    exit 1
} finally {
    $lock.ReleaseMutex()
    $lock.Dispose()
}
