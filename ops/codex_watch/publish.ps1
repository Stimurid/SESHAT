# Trusted Windows GitHub publisher. NEVER run inside Codex sandbox.
# Restricted to the registered SESHAT task branch; it never merges or approves a PR.
param([Parameter(Mandatory=$true)][string]$JobPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Repo='C:\projects\seshat'
$Root='C:\Users\Homee\AppData\Local\SESHAT\watch'
function Need($condition, $reason) { if (-not $condition) { throw $reason } }
function RunGit([string[]]$argv) {
    $output=@(& git -C $Repo @argv 2>&1)
    Need ($LASTEXITCODE -eq 0) ("GIT_FAILED_"+($argv[0].ToUpperInvariant()))
    return $output
}
$job=Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8 | ConvertFrom-Json
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
$paths=@()
foreach($line in $lines) {
    Need ($line.Length -gt 3) 'BAD_PORCELAIN_RECORD'
    $status=$line.Substring(0,2)
    $path=$line.Substring(3).Replace('\','/')
    Need ($status -notmatch 'R|C|D') 'NO_RENAMES_OR_DELETIONS_AUTOMATICALLY'
    Need ($path -notmatch '"| -> |\.\.|^/|:') 'UNSAFE_DIFF_PATH'
    $allowed=($path -match '^src/seshat/[A-Za-z0-9_./-]+\.py$' -or
              $path -match '^tests/[A-Za-z0-9_./-]+\.py$' -or
              $path -match '^profiles/[A-Za-z0-9_./-]+\.(py|md|json)$' -or
              $path -match '^docs/(S_IMPL_[A-Za-z0-9_]+_RESULT|ADR_[A-Za-z0-9_-]+)\.md$')
    Need $allowed ('UNAPPROVED_MODIFIED_PATH: '+$path)
    Need ($path -notmatch '(?i)(\.env|password|credential|secret|private_key|\.pem|\.pfx|\.key)$') 'SENSITIVE_PATH_BLOCKED'
    $paths+= $path
}
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
    Need ($staged.Count -eq $paths.Count) 'STAGED_PATH_SET_MISMATCH'
    $msg="impl(s2b): bounded reconciliation controller (#$issue)"
    & git commit -m $msg
    Need ($LASTEXITCODE -eq 0) 'GIT_COMMIT_FAILED'
    $sha=[string](& git rev-parse HEAD | Select-Object -First 1)
    $env:GIT_TERMINAL_PROMPT='0'
    & git push --set-upstream origin $branch
    Need ($LASTEXITCODE -eq 0) 'GIT_PUSH_FAILED'
    # gh is already authorized in this Windows user's keyring; no token in files/arguments.
    $url=@(& gh pr view $branch --json url --jq '.url' 2>$null)
    if($LASTEXITCODE -ne 0 -or -not $url) {
        $bodyFile=Join-Path $Root 'generated-pr-body.md'
        @"
Implements #$issue from pre-approved SESHAT dispatch.
Branch: $branch
Commit: $sha

Codex generated changes in sandbox. Trusted host checked pytest, Ruff, allowed paths,
performed Git commit/push, and created this draft PR. No auto-merge and no semantic acceptance.
Result: docs/S_IMPL_002B_RESULT.md
Coordination: https://github.com/Stimurid/SESHAT/issues/6
"@ | Set-Content -LiteralPath $bodyFile -Encoding UTF8
        $url=@(& gh pr create --draft --base main --head $branch --title "S-IMPL-002B: bounded reconciliation controller" --body-file $bodyFile)
        Need ($LASTEXITCODE -eq 0 -and $url.Count -gt 0) 'GITHUB_PR_CREATE_FAILED'
    }
    $result=[ordered]@{
        status='PUBLISHED_DRAFT_PR'; issue=$issue; branch=$branch; head_sha=$sha
        pr_url=[string]($url | Select-Object -Last 1); changed_paths=$paths
        ci_tests='PENDING_GITHUB_PR_CI'; local_code_execution='NONE'
        published_at_utc=(Get-Date).ToUniversalTime().ToString('o')
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $Root 'publish_receipt.json') -Encoding UTF8
    Write-Output ($result | ConvertTo-Json -Compress -Depth 8)
} finally { Pop-Location }
