# Trusted Windows GitHub publisher. NEVER run inside Codex sandbox.
# Restricted to the registered SESHAT task branch; it never merges or approves a PR.
param([Parameter(Mandatory=$true)][string]$JobPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Repo='C:\projects\seshat'
$Root='C:\Users\Homee\AppData\Local\SESHAT\watch'
. (Join-Path $PSScriptRoot 'gate.ps1')
function Need($condition, $reason) { if (-not $condition) { throw $reason } }
function RunGit([string[]]$argv) {
    $output=@(& git -C $Repo @argv 2>&1)
    Need ($LASTEXITCODE -eq 0) ("GIT_FAILED_"+($argv[0].ToUpperInvariant()))
    return $output
}
Need (Test-SeshatCanonicalJobPath -JobPath $JobPath -Root $Root) 'UNAUTHORIZED_JOB_PATH'
$job=Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8 | ConvertFrom-Json
Need ([string]$job.dispatch_key -cmatch '^pr16-[0-9a-f]{40}-issue17$') 'INVALID_DISPATCH_KEY'
$markerPath=Join-Path (Join-Path $Root 'dispatches') (([string]$job.dispatch_key)+'.json')
Need (Test-Path -LiteralPath $markerPath) 'DISPATCH_MARKER_MISSING'
$marker=Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8|ConvertFrom-Json
Need ((Test-SeshatJobAuthorization -Job $job -Marker $marker) -eq 'ADMIT') 'JOB_NOT_AUTHORIZED'
Assert-SeshatBundleProvenance -Job $job -Repo $Repo -ScriptRoot $PSScriptRoot
$branch=[string]$job.branch
$issue=[int]$job.issue_number
Need ($branch -match '^codex/[a-z0-9][a-z0-9-]{4,79}$') 'UNSAFE_BRANCH_NAME'
Need ($issue -ge 1 -and $issue -le 1000000) 'UNSAFE_ISSUE'
Need (([string](RunGit @('remote','get-url','origin') | Select-Object -First 1)) -eq 'https://github.com/Stimurid/SESHAT.git') 'REMOTE_MISMATCH'
Need (([string](RunGit @('branch','--show-current') | Select-Object -First 1)) -eq $branch) 'BRANCH_MISMATCH'
$before=[string](RunGit @('rev-parse','HEAD') | Select-Object -First 1)
Need ($before -eq [string]$job.base_sha) 'UNEXPECTED_HEAD_BEFORE_PUBLISH'
$lines=@(& git -C $Repo -c core.quotePath=false status --porcelain=v1 -uall)
Need ($LASTEXITCODE -eq 0) 'STATUS_FAILED'
Need ($lines.Count -gt 0) 'NO_CODE_CHANGES'
$paths=@(Get-SeshatStatusPaths -StatusLines $lines)
$pathDecision=Test-SeshatOwnedPathSet -ApprovedPaths @($job.approved_paths) -OwnedPaths @($job.owned_paths) -DirtyPaths $paths
Need ($pathDecision -eq 'ADMIT') $pathDecision
Need ((Test-Path (Join-Path $Repo 'docs\S_IMPL_002B_RESULT.md'))) 'MISSING_REQUIRED_RESULT_RECEIPT'
# Deliberately DO NOT execute Codex-written Python code under the privileged host account.
# The isolated GitHub Actions PR CI runs pytest and Ruff after publication.
Push-Location $Repo
try {
    & git add -- @paths
    Need ($LASTEXITCODE -eq 0) 'GIT_ADD_FAILED'
    & git diff --cached --check
    Need ($LASTEXITCODE -eq 0) 'DIFF_CHECK_FAILED'
    # Fail closed on common credential/key patterns without revealing matched values.
    $diffText=(@(& git diff --cached --no-ext-diff --unified=0) -join [Environment]::NewLine)
    Need ($LASTEXITCODE -eq 0) 'DIFF_SCAN_FAILED'
    Need ($diffText -notmatch '(?mi)^\+.*(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)') 'POSSIBLE_CREDENTIAL_IN_DIFF'
    $staged=@(& git diff --cached --name-only)
    Need (Test-SeshatExactStringSet -Left $staged -Right @($job.owned_paths)) 'STAGED_PATH_SET_MISMATCH'
    $msg="impl(s2b): bounded reconciliation controller (#$issue)"
    & git commit -m $msg
    Need ($LASTEXITCODE -eq 0) 'GIT_COMMIT_FAILED'
    $sha=[string](& git rev-parse HEAD | Select-Object -First 1)
    $env:GIT_TERMINAL_PROMPT='0'
    & git push --set-upstream origin $branch
    Need ($LASTEXITCODE -eq 0) 'GIT_PUSH_FAILED'
    # gh is already authorized in this Windows user's keyring; no token in files/arguments.
    $prRaw=@(& gh pr view $branch --repo Stimurid/SESHAT --json number,url,state,isDraft,baseRefName,headRefName,headRefOid 2>$null)
    if($LASTEXITCODE -ne 0 -or -not $prRaw) {
        $bodyFile=Join-Path $Root 'generated-pr-body.md'
        @"
Implements #$issue from pre-approved SESHAT dispatch.
Branch: $branch
Commit: $sha

Codex generated changes in a restricted sandbox. Trusted host validated the scoped file set,
credential-pattern scan and staged diff before commit/push. Isolated GitHub PR CI runs pytest
and Ruff after publication. No local execution of unreviewed code, auto-merge or semantic approval.
Result: docs/S_IMPL_002B_RESULT.md
Coordination: https://github.com/Stimurid/SESHAT/issues/6
"@ | Set-Content -LiteralPath $bodyFile -Encoding UTF8
        & gh pr create --repo Stimurid/SESHAT --draft --base main --head $branch --title "S-IMPL-002B: bounded reconciliation controller" --body-file $bodyFile *> $null
        Need ($LASTEXITCODE -eq 0) 'GITHUB_PR_CREATE_FAILED'
        $prRaw=@(& gh pr view $branch --repo Stimurid/SESHAT --json number,url,state,isDraft,baseRefName,headRefName,headRefOid 2>$null)
        Need ($LASTEXITCODE -eq 0 -and $prRaw.Count -gt 0) 'GITHUB_PR_VERIFY_QUERY_FAILED'
    }
    $publishedPr=($prRaw -join [Environment]::NewLine)|ConvertFrom-Json
    $prDecision=Test-SeshatPublishedPullRequest -PullRequest $publishedPr -Branch $branch -HeadSha $sha
    Need ($prDecision -eq 'ADMIT') $prDecision
    $result=[ordered]@{
        status='PUBLISHED_DRAFT_PR';job_id=[string]$job.job_id;issue=$issue;branch=$branch;head_sha=$sha
        pr_number=[int]$publishedPr.number;pr_url=[string]$publishedPr.url
        pr_state=[string]$publishedPr.state;pr_is_draft=[bool]$publishedPr.isDraft
        pr_base=[string]$publishedPr.baseRefName;pr_head=[string]$publishedPr.headRefName
        changed_paths=$paths
        ci_tests='PENDING_GITHUB_PR_CI'; local_code_execution='NONE'
        published_at_utc=(Get-Date).ToUniversalTime().ToString('o')
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $Root 'publish_receipt.json') -Encoding UTF8
    Write-Output ($result | ConvertTo-Json -Compress -Depth 8)
} finally { Pop-Location }
