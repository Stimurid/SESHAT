# Synthetic offline descendant-containment oracle. No GitHub or live Codex.
$ErrorActionPreference='Stop'
$opsRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $opsRoot 'gate.ps1')
Initialize-SeshatJobContainment | Out-Null
$engine=(Get-Process -Id $PID).Path
$temp=Join-Path ([System.IO.Path]::GetTempPath()) ('seshat-containment-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp|Out-Null
try{
    $sizes=[Seshat.Interop.JobContainmentV1]::GetStructSizes()
    $ptrSize=[int][IntPtr]::Size
    if($ptrSize -eq 8){
        if([int]$sizes.StartupInfoW -ne 104 -or [int]$sizes.StartupInfoEx -ne 112 -or [int]$sizes.JobObjectExtendedLimitInformation -ne 144 -or [int]$sizes.JobObjectBasicAccountingInformation -ne 48){throw 'STRUCT_SIZE_MISMATCH_X64'}
    }elseif($ptrSize -eq 4){
        if([int]$sizes.StartupInfoW -ne 68 -or [int]$sizes.StartupInfoEx -ne 72 -or [int]$sizes.JobObjectExtendedLimitInformation -ne 112 -or [int]$sizes.JobObjectBasicAccountingInformation -ne 48){throw 'STRUCT_SIZE_MISMATCH_X86'}
    }else{throw 'UNEXPECTED_POINTER_SIZE'}

    $fixture=Join-Path $temp 'containment-fixture.ps1'
    @'
param([string]$Mode,[string]$Sentinel)
$ErrorActionPreference='Stop'
function Start-GrandchildWriter([string]$Path){
    $arg='while($true){ Add-Content -LiteralPath '''+$Path+''' -Value x -Encoding Ascii; Start-Sleep -Milliseconds 250 }'
    return Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList @('-NoProfile','-NonInteractive','-Command',$arg) -PassThru -WindowStyle Hidden
}
if($Mode -eq 'grandchild-short'){
    $gc=Start-GrandchildWriter $Sentinel
    [Console]::Out.WriteLine([string]$gc.Id)
    Start-Sleep -Milliseconds 600
    exit 0
}
if($Mode -eq 'grandchild-long'){
    $gc=Start-GrandchildWriter $Sentinel
    [Console]::Out.WriteLine([string]$gc.Id)
    exit 0
}
if($Mode -eq 'hang-grandchild'){
    Start-GrandchildWriter $Sentinel|Out-Null
    Start-Sleep -Seconds 120
    exit 0
}
if($Mode -eq 'overflow-grandchild'){
    Start-GrandchildWriter $Sentinel|Out-Null
    [Console]::Out.Write(('x')*8192)
    [Console]::Out.Flush()
    Start-Sleep -Seconds 30
    exit 0
}
if($Mode -eq 'malformed-stream'){
    $bytes=[byte[]](0xC3,0x28)
    [Console]::OpenStandardOutput().Write($bytes,0,$bytes.Length)
    exit 0
}
if($Mode -eq 'wmi-escape'){
    try{
        $p=([wmiclass]'Win32_Process').Create('cmd.exe /c exit 0')
        if($p.ReturnValue -ne 0){ [Console]::Out.WriteLine('WMI_UNAVAILABLE'); exit 0 }
        [Console]::Out.WriteLine([string]$p.ProcessId)
        exit 0
    }catch{
        [Console]::Out.WriteLine('WMI_UNAVAILABLE')
        exit 0
    }
}
if($Mode -eq 'supervisor-block'){
    $gc=Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList @('-NoProfile','-NonInteractive','-Command','Start-Sleep -Seconds 120') -PassThru -WindowStyle Hidden
    [Console]::Out.WriteLine([string]$gc.Id)
    [Console]::Out.Flush()
    Start-Sleep -Seconds 600
    exit 0
}
exit 99
'@|Set-Content -LiteralPath $fixture -Encoding UTF8

    $sentinelA=Join-Path $temp 'sentinel-a.log'
    [System.IO.File]::WriteAllText($sentinelA,'',[System.Text.UTF8Encoding]::new($false))
    $outA=Join-Path $temp 'out-a.log'
    $errA=Join-Path $temp 'err-a.log'
    $resA=Invoke-SeshatStreamingNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$fixture,'grandchild-short',$sentinelA) -WorkingDirectory $temp -Label 'contain-short-grandchild' -StandardOutputPath $outA -StandardErrorPath $errA -MaximumStandardOutputBytes 65536 -MaximumStandardErrorBytes 65536 -DescendantQuiesceMilliseconds 8000 -NoOutputTimeoutMilliseconds 20000
    if([int]$resA.exit_code -ne 0 -or [string]$resA.status -cne 'COMPLETED'){throw 'CASE_A_STATUS'}
    if(-not [bool]$resA.descendants_contained -or [string]$resA.descendant_quiescence -cne 'QUIET'){throw 'CASE_A_QUIESCENCE'}
    if([int]$resA.total_processes -lt 2){throw 'CASE_A_TOTAL_PROCESSES'}

    $sentinelB=Join-Path $temp 'sentinel-b.log'
    [System.IO.File]::WriteAllText($sentinelB,'',[System.Text.UTF8Encoding]::new($false))
    $outB=Join-Path $temp 'out-b.log'
    $errB=Join-Path $temp 'err-b.log'
    $blockedB=$false
    $gcPid=$null
    try{
        Invoke-SeshatStreamingNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$fixture,'grandchild-long',$sentinelB) -WorkingDirectory $temp -Label 'contain-long-grandchild' -StandardOutputPath $outB -StandardErrorPath $errB -MaximumStandardOutputBytes 65536 -MaximumStandardErrorBytes 65536 -DescendantQuiesceMilliseconds 500 -NoOutputTimeoutMilliseconds 20000|Out-Null
    }catch{
        $blockedB=($_.Exception.Message -eq 'DESCENDANT_RESIDUE_TERMINATED')
        if(Test-Path -LiteralPath $outB){
            $pidLine=[System.IO.File]::ReadAllText($outB,[System.Text.Encoding]::UTF8).Trim()
            if($pidLine -match '^[0-9]+$'){$gcPid=[int]$pidLine}
        }
    }
    if(-not $blockedB){throw 'CASE_B_NOT_TERMINATED'}
    $lenBefore=(Get-Item -LiteralPath $sentinelB).Length
    Start-Sleep -Seconds 2
    if((Get-Item -LiteralPath $sentinelB).Length -ne $lenBefore){throw 'CASE_B_SENTINEL_STILL_GROWING'}
    if($gcPid -and [Seshat.Interop.JobContainmentV1]::GetProcessExitCodeIfAvailable($gcPid) -eq 259){throw 'CASE_B_GRANDCHILD_STILL_ACTIVE'}

    $sentinelC=Join-Path $temp 'sentinel-c.log'
    [System.IO.File]::WriteAllText($sentinelC,'',[System.Text.UTF8Encoding]::new($false))
    $outC=Join-Path $temp 'out-c.log'
    $errC=Join-Path $temp 'err-c.log'
    $blockedC=$false
    $lenCBefore=(Get-Item -LiteralPath $sentinelC).Length
    try{
        Invoke-SeshatStreamingNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$fixture,'hang-grandchild',$sentinelC) -WorkingDirectory $temp -Label 'contain-hang' -StandardOutputPath $outC -StandardErrorPath $errC -MaximumStandardOutputBytes 65536 -MaximumStandardErrorBytes 65536 -NoOutputTimeoutMilliseconds 3000 -DescendantQuiesceMilliseconds 5000|Out-Null
    }catch{$blockedC=($_.Exception.Message -eq 'NO_OUTPUT_TIMEOUT')}
    if(-not $blockedC){throw 'CASE_C_NO_TIMEOUT'}
    Start-Sleep -Seconds 2
    if((Get-Item -LiteralPath $sentinelC).Length -ne $lenCBefore){throw 'CASE_C_SENTINEL_GROWING'}

    $sentinelD=Join-Path $temp 'sentinel-d.log'
    [System.IO.File]::WriteAllText($sentinelD,'',[System.Text.UTF8Encoding]::new($false))
    $outD=Join-Path $temp 'out-d.log'
    $errD=Join-Path $temp 'err-d.log'
    $lenDBefore=(Get-Item -LiteralPath $sentinelD).Length
    $resD=Invoke-SeshatStreamingNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$fixture,'overflow-grandchild',$sentinelD) -WorkingDirectory $temp -Label 'contain-overflow' -StandardOutputPath $outD -StandardErrorPath $errD -MaximumStandardOutputBytes 128 -MaximumStandardErrorBytes 128 -NoOutputTimeoutMilliseconds 20000 -DescendantQuiesceMilliseconds 8000
    if(-not [bool]$resD.limit_exceeded -or [string]$resD.status -cne 'OUTPUT_LIMIT_EXCEEDED' -or [long]$resD.stdout_bytes -ne 128){throw 'CASE_D_OVERFLOW'}
    Start-Sleep -Seconds 2
    if((Get-Item -LiteralPath $sentinelD).Length -ne $lenDBefore){throw 'CASE_D_SENTINEL_GROWING'}

    $outE=Join-Path $temp 'out-e.bin'
    $errE=Join-Path $temp 'err-e.log'
    $resE=Invoke-SeshatStreamingNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$fixture,'malformed-stream') -WorkingDirectory $temp -Label 'contain-malformed' -StandardOutputPath $outE -StandardErrorPath $errE -MaximumStandardOutputBytes 65536 -MaximumStandardErrorBytes 65536
    $rawE=[System.IO.File]::ReadAllBytes($outE)
    if($rawE.Length -ne 2 -or $rawE[0] -ne 0xC3 -or $rawE[1] -ne 0x28){throw 'CASE_E_BYTES'}
    if(-not [bool]$resE.descendants_contained){throw 'CASE_E_CONTAINED'}

    $outF=Join-Path $temp 'out-f.log'
    $errF=Join-Path $temp 'err-f.log'
    $resF=Invoke-SeshatStreamingNativeCommand -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$fixture,'wmi-escape') -WorkingDirectory $temp -Label 'contain-wmi' -StandardOutputPath $outF -StandardErrorPath $errF -MaximumStandardOutputBytes 65536 -MaximumStandardErrorBytes 65536
    $wmiLine=[System.IO.File]::ReadAllText($outF,[System.Text.Encoding]::UTF8).Trim()
    if($wmiLine -eq 'WMI_UNAVAILABLE'){
        Write-Host 'SKIPPED_WMI_UNAVAILABLE'
    }elseif($wmiLine -match '^[0-9]+$'){
        if([bool]$resF.wmi_escape_detected -ne $true){throw 'CASE_F_WMI_NOT_FLAGGED'}
        if([Seshat.Interop.JobContainmentV1]::IsProcessInJobByPid([int]$wmiLine,$resF.containment_job_handle)){throw 'CASE_F_WMI_FALSELY_CONTAINED'}
        [Seshat.Interop.JobContainmentV1]::TerminateProcessByPid([int]$wmiLine)|Out-Null
    }else{throw 'CASE_F_WMI_UNEXPECTED'}

    $outI=Join-Path $temp 'out-i.log'
    $errI=Join-Path $temp 'err-i.log'
    $holder=Join-Path $temp 'holder.ps1'
    $gatePath=Join-Path $opsRoot 'gate.ps1'
    @"
. '$gatePath'
Initialize-SeshatJobContainment | Out-Null
`$out='$outI'
`$err='$errI'
`$fixture='$fixture'
`$engine='$engine'
`$temp='$temp'
Invoke-SeshatStreamingNativeCommand -FilePath `$engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',`$fixture,'supervisor-block') -WorkingDirectory `$temp -Label 'contain-supervisor' -StandardOutputPath `$out -StandardErrorPath `$err -MaximumStandardOutputBytes 65536 -MaximumStandardErrorBytes 65536 -NoOutputTimeoutMilliseconds 600000
"@|Set-Content -LiteralPath $holder -Encoding UTF8
    $supervisor=Start-Process -FilePath $engine -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$holder) -WorkingDirectory $temp -PassThru -WindowStyle Hidden
    $gcI=$null
    for($i=0;$i -lt 40;$i++){
        Start-Sleep -Milliseconds 250
        if((Test-Path -LiteralPath $outI) -and (Get-Item -LiteralPath $outI).Length -gt 0){
            $line=[System.IO.File]::ReadAllText($outI,[System.Text.Encoding]::UTF8).Trim()
            if($line -match '^[0-9]+$'){$gcI=[int]$line;break}
        }
    }
    if(-not $gcI){Stop-Process -Id $supervisor.Id -Force -ErrorAction SilentlyContinue;throw 'CASE_I_NO_GRANDCHILD'}
    Stop-Process -Id $supervisor.Id -Force
    Start-Sleep -Seconds 3
    if([Seshat.Interop.JobContainmentV1]::GetProcessExitCodeIfAvailable($gcI) -eq 259){throw 'CASE_I_GRANDCHILD_SURVIVED_SUPERVISOR_DEATH'}
}finally{
    if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue}
}
Write-Host 'DESCENDANT_CONTAINMENT_TESTS_PASSED'
