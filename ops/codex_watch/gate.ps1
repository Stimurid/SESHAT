# Pure governance gate. Source facts come from GitHub, not from Codex statements.
Set-StrictMode -Version Latest
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
function Set-SeshatRunnerStart {
    param(
        [Parameter(Mandatory=$true)][object] $Job,
        [Parameter(Mandatory=$true)][int] $RunnerPid,
        [Parameter(Mandatory=$true)][string] $StartedUtc
    )
    # ConvertFrom-Json yields a PSCustomObject: strict mode forbids assigning missing properties.
    $Job | Add-Member -NotePropertyName runner_pid -NotePropertyValue $RunnerPid -Force
    $Job | Add-Member -NotePropertyName started_at_utc -NotePropertyValue $StartedUtc -Force
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
    & git -C $Repo merge-base --is-ancestor $OpsMergeSha $BaseSha
    if($LASTEXITCODE -ne 0){throw 'OPS_MERGE_NOT_ANCESTOR_OF_BASE'}
    & git -C $Repo diff --quiet $OpsMergeSha $BaseSha -- @paths
    if($LASTEXITCODE -ne 0){throw 'OPS_BUNDLE_CHANGED_AFTER_REVIEW'}
    & git -C $Repo diff --quiet $BaseSha -- @paths
    if($LASTEXITCODE -ne 0){throw 'OPS_BUNDLE_WORKTREE_DRIFT'}
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
