# Safe offline, no GitHub network, no branch changes. Run with PowerShell.
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'gate.ps1')
$t = [pscustomobject]@{after_pr=16;next_issue=17;accepted_label='seshat:engineering-accepted';ready_label='seshat:codex-ready'}
$pr=[pscustomobject]@{
    number=16; merged=$true; state='closed'; merged_at='2026-10-10T01:00:00Z';
    base=[pscustomobject]@{ref='main'};
    labels=@([pscustomobject]@{name='seshat:engineering-accepted'})
}
$issue=[pscustomobject]@{number=17;state='open';labels=@([pscustomobject]@{name='seshat:codex-ready'})}
$sha=('a'*40)
$runs=@([pscustomobject]@{name='ci';head_sha=$sha;status='completed';conclusion='success'})
function Check($want) {
    $got=Test-SeshatDispatchGate -Transition $t -PriorPr $pr -NextIssue $issue -RemoteMainSha $sha -MainRuns $runs
    if ($got -ne $want) { throw ("GATE expected '{0}' got '{1}'" -f $want,$got) }
}
Check 'ADMIT'
$pr.merged=$false; Check 'WAIT_PRIOR_PR_NOT_MERGED'; $pr.merged=$true
$pr.labels=@(); Check 'WAIT_EXPLICIT_ENGINEERING_ACCEPTANCE'; $pr.labels=@([pscustomobject]@{name='seshat:engineering-accepted'})
$issue.labels=@(); Check 'WAIT_NEXT_ISSUE_NOT_APPROVED'; $issue.labels=@([pscustomobject]@{name='seshat:codex-ready'})
$runs[0].conclusion='failure'; Check 'WAIT_MAIN_CI_NOT_GREEN'; $runs[0].conclusion='success'
$pr.base.ref='other'; Check 'BLOCK_PR_BASE_NOT_MAIN'; $pr.base.ref='main'
$issue.state='closed'; Check 'BLOCK_NEXT_ISSUE_NOT_OPEN'; $issue.state='open'
Write-Output 'PASS: 7 synthetic authorization/denial cases'
