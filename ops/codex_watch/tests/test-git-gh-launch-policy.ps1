# Offline B01 git/gh launch-policy tests. No live GitHub CLI credential calls.
$ErrorActionPreference = 'Stop'
$opsRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $opsRoot 'gate.ps1')

function New-SeshatSyntheticGitGhPolicy {
    param(
        [Parameter(Mandatory=$true)][string]$PolicyDir,
        [Parameter(Mandatory=$true)][string]$ToolRoot,
        [Parameter(Mandatory=$true)][string]$GitExe,
        [Parameter(Mandatory=$true)][string]$GhExe,
        [hashtable]$Overrides
    )
    $policyPath = Join-Path $PolicyDir 'git-gh-launch-policy.json'
    $gitInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($GitExe)
    $ghInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($GhExe)
    $policy = [ordered]@{
        schema = 'seshat.git-gh-launch-policy.v1'
        policy_id = 'ci-synthetic-git-gh'
        synthetic_test_fixture = $true
        implementation_binding_sha256 = (Get-SeshatGitGhLaunchImplementationBindingSha256)
        git_exe_path = $GitExe
        git_exe_root = $ToolRoot
        git_exe_sha256 = (Get-SeshatFileSha256 -Path $GitExe)
        git_signer_thumbprint = ('a'*40)
        git_file_version = [string]$gitInfo.ProductVersion
        gh_exe_path = $GhExe
        gh_exe_root = $ToolRoot
        gh_exe_sha256 = (Get-SeshatFileSha256 -Path $GhExe)
        gh_signer_thumbprint = ('b'*40)
        gh_file_version = [string]$ghInfo.ProductVersion
    }
    if($Overrides){foreach($key in $Overrides.Keys){$policy[$key]=$Overrides[$key]}}
    ($policy | ConvertTo-Json -Compress) | Set-Content -LiteralPath $policyPath -Encoding UTF8
    $policy.policy_sha256 = (Get-SeshatFileSha256 -Path $policyPath)
    return [pscustomobject]$policy
}

$hostGit = (Get-Command git -ErrorAction Stop).Source
$hostGh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if(-not $hostGh){$hostGh = $hostGit}

$temp = Join-Path ([System.IO.Path]::GetTempPath()) ('seshat-git-gh-policy-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
$policyDir = Join-Path $temp 'policy'
New-Item -ItemType Directory -Path $policyDir | Out-Null
$gitGood = [System.IO.Path]::GetFullPath($hostGit)
$ghGood = [System.IO.Path]::GetFullPath($hostGh)
$gitRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $gitGood)).TrimEnd('\')
$ghRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $ghGood)).TrimEnd('\')
$binding = New-SeshatSyntheticGitGhPolicy -PolicyDir $policyDir -ToolRoot $gitRoot -GitExe $gitGood -GhExe $ghGood -Overrides @{
    gh_exe_root = $ghRoot
}
$policyPath = Join-Path $policyDir 'git-gh-launch-policy.json'
$expectedBinding = [pscustomobject]@{
    policy_path = [System.IO.Path]::GetFullPath($policyPath)
    policy_sha256 = [string]$binding.policy_sha256
    policy_id = 'ci-synthetic-git-gh'
    implementation_binding_sha256 = (Get-SeshatGitGhLaunchImplementationBindingSha256)
    git_exe_path = [System.IO.Path]::GetFullPath($gitGood)
    git_exe_root = $gitRoot
    git_exe_sha256 = (Get-SeshatFileSha256 -Path $gitGood)
    git_signer_thumbprint = (('a'*40).ToUpperInvariant())
    git_file_version = [string]([System.Diagnostics.FileVersionInfo]::GetVersionInfo($gitGood).ProductVersion)
    gh_exe_path = [System.IO.Path]::GetFullPath($ghGood)
    gh_exe_root = $ghRoot
    gh_exe_sha256 = (Get-SeshatFileSha256 -Path $ghGood)
    gh_signer_thumbprint = (('b'*40).ToUpperInvariant())
    gh_file_version = [string]([System.Diagnostics.FileVersionInfo]::GetVersionInfo($ghGood).ProductVersion)
}

$launch = Resolve-SeshatGitGhLaunch -ExpectedBinding $expectedBinding -AllowSyntheticTestFixture
$version = Invoke-SeshatNativeCommand -FilePath (Get-SeshatPrivilegedNativeExecutablePath -Tool 'git' -Launch $launch) -ArgumentList @('--version') -WorkingDirectory $temp -Label 'synthetic-git-version'
if($version.exit_code -ne 0){throw 'PINNED_GIT_CONTRACT_FAILED'}
Close-SeshatGitGhLaunch -Launch $launch

$shadowRepo = Join-Path $temp 'repo-shadow'
New-Item -ItemType Directory -Path $shadowRepo | Out-Null
Copy-Item -LiteralPath $gitGood -Destination (Join-Path $shadowRepo 'git.exe')
try { Assert-SeshatPrivilegedRepositorySurface -Repo $shadowRepo; throw 'REPO_SHADOW_NOT_REJECTED' } catch {
    if($_.Exception.Message -cne 'GIT_GH_REPO_EXECUTABLE_SHADOW'){throw 'REPO_SHADOW_WRONG_ERROR'}
}

$pathTrapDir = Join-Path $temp 'path-trap'
New-Item -ItemType Directory -Path $pathTrapDir | Out-Null
$evilMarker = Join-Path $temp 'evil-ran.txt'
if(Test-Path -LiteralPath $evilMarker){Remove-Item -LiteralPath $evilMarker -Force}
$evilBat = Join-Path $pathTrapDir 'git.cmd'
'@echo off' | Set-Content -LiteralPath $evilBat -Encoding ASCII
'echo evil> "'+$evilMarker+'"' | Add-Content -LiteralPath $evilBat -Encoding ASCII
$oldPath = $env:PATH
$env:PATH = $pathTrapDir + ';' + $oldPath
$launch2 = Resolve-SeshatGitGhLaunch -ExpectedBinding $expectedBinding -AllowSyntheticTestFixture
[void](Invoke-SeshatNativeCommand -FilePath (Get-SeshatPrivilegedNativeExecutablePath -Tool 'git' -Launch $launch2) -ArgumentList @('--version') -WorkingDirectory $shadowRepo -Label 'synthetic-git-path-trap')
Close-SeshatGitGhLaunch -Launch $launch2
$env:PATH = $oldPath
if(Test-Path -LiteralPath $evilMarker){throw 'PATH_OR_CWD_SHADOW_EXECUTED'}

$missingBlocked = $false
try { Get-SeshatGitGhLaunchPolicyBinding -PolicyPath (Join-Path $temp 'missing.json') -AllowSyntheticTestFixture } catch { $missingBlocked = ($_.Exception.Message -eq 'GIT_GH_TRUST_POLICY_MISSING') }
if(-not $missingBlocked){throw 'MISSING_POLICY_NOT_BLOCKED'}

$driftBinding = [pscustomobject]@{
    policy_path = [System.IO.Path]::GetFullPath($policyPath)
    policy_sha256 = ('d'*64)
    policy_id = 'ci-synthetic-git-gh'
    implementation_binding_sha256 = (Get-SeshatGitGhLaunchImplementationBindingSha256)
    git_exe_path = [System.IO.Path]::GetFullPath($gitGood); git_exe_root = $gitRoot; git_exe_sha256 = (Get-SeshatFileSha256 -Path $gitGood)
    git_signer_thumbprint = (('a'*40).ToUpperInvariant()); git_file_version = $expectedBinding.git_file_version
    gh_exe_path = [System.IO.Path]::GetFullPath($ghGood); gh_exe_root = $ghRoot; gh_exe_sha256 = (Get-SeshatFileSha256 -Path $ghGood)
    gh_signer_thumbprint = (('b'*40).ToUpperInvariant()); gh_file_version = $expectedBinding.gh_file_version
}
$driftBlocked = $false
try { Resolve-SeshatGitGhLaunch -ExpectedBinding $driftBinding -AllowSyntheticTestFixture } catch { $driftBlocked = ($_.Exception.Message -eq 'GIT_GH_TRUST_POLICY_BINDING_DRIFT') }
if(-not $driftBlocked){throw 'POLICY_DIGEST_DRIFT_NOT_BLOCKED'}

$forged = New-SeshatSyntheticGitGhPolicy -PolicyDir $policyDir -ToolRoot $gitRoot -GitExe $gitGood -GhExe $ghGood -Overrides @{git_exe_sha256=('f'*64); gh_exe_root = $ghRoot}
$forgedPath = Join-Path $policyDir 'git-gh-launch-policy.json'
$forgedBlocked = $false
try { Get-SeshatGitGhLaunchPolicyBinding -PolicyPath $forgedPath -AllowSyntheticTestFixture } catch { $forgedBlocked = ($_.Exception.Message -eq 'GIT_GH_TRUSTED_FILE_HASH_DRIFT') }
if(-not $forgedBlocked){throw 'FORGED_POLICY_HASH_NOT_BLOCKED'}

$writablePolicyDir = Join-Path $temp 'writable-policy'
New-Item -ItemType Directory -Path $writablePolicyDir | Out-Null
$writablePolicy = Join-Path $writablePolicyDir 'git-gh-launch-policy.json'
Copy-Item -LiteralPath $policyPath -Destination $writablePolicy
$writableBlocked = $false
try { Get-SeshatGitGhLaunchPolicyBinding -PolicyPath $writablePolicy } catch { $writableBlocked = ($_.Exception.Message -match '^GIT_GH_TRUST_POLICY_') }
if(-not $writableBlocked){throw 'NON_PROGRAMDATA_OR_WRITABLE_POLICY_NOT_BLOCKED'}

$syntheticDenied = $false
try { Get-SeshatGitGhLaunchPolicyBinding -PolicyPath $policyPath } catch {
    $syntheticDenied = ($_.Exception.Message -in @('GIT_GH_TRUST_POLICY_SYNTHETIC_FIXTURE_DENIED','GIT_GH_TRUST_POLICY_LOCATION_INVALID'))
}
if(-not $syntheticDenied){throw 'SYNTHETIC_FIXTURE_NOT_DENIED_IN_PRODUCTION_MODE'}

Remove-Item -LiteralPath $temp -Recurse -Force
Write-Output 'PASS: offline git/gh launch-policy negative and contract cases'
