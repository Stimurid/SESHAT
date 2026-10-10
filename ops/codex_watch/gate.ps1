# Pure governance gate. Source facts come from GitHub, not from Codex statements.
Set-StrictMode -Version Latest
function Test-SeshatDispatchGate {
    param(
        [Parameter(Mandatory=$true)][object] $Transition,
        [Parameter(Mandatory=$true)][object] $PriorPr,
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
    if ([int]$NextIssue.number -ne [int]$Transition.next_issue -or [string]$NextIssue.state -ne 'open') {
        return 'BLOCK_NEXT_ISSUE_NOT_OPEN'
    }
    if ($issueLabels -cnotcontains [string]$Transition.ready_label) {
        return 'WAIT_NEXT_ISSUE_NOT_APPROVED'
    }
    if (-not ($RemoteMainSha -match '^[0-9a-f]{40}$')) { return 'BLOCK_INVALID_MAIN_SHA' }
    if (-not (@($MainRuns | Where-Object {
        $_.name -eq 'ci' -and $_.head_sha -eq $RemoteMainSha -and
        $_.status -eq 'completed' -and $_.conclusion -eq 'success'
    }).Count -gt 0)) { return 'WAIT_MAIN_CI_NOT_GREEN' }
    return 'ADMIT'
}
