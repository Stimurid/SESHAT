# Pure governance gate. Source facts come from GitHub, not from Codex statements.
Set-StrictMode -Version Latest

$script:SeshatJobContainmentSource = @'

using System;
using System.Collections;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Seshat.Interop
{
    public sealed class StructSizeReport
    {
        public int StartupInfoW;
        public int StartupInfoEx;
        public int JobObjectExtendedLimitInformation;
        public int JobObjectBasicAccountingInformation;
    }

    public sealed class AccountingInfo
    {
        public uint ActiveProcesses;
        public uint TotalProcesses;
        public uint TotalTerminatedProcesses;
    }

    public sealed class ContainedStartResult
    {
        public SafeWaitHandle JobHandle;
        public SafeWaitHandle ProcessHandle;
        public int ProcessId;
        public FileStream StdinWrite;
        public FileStream StdoutRead;
        public FileStream StderrRead;
    }

    public static class JobContainmentV1
    {
        private const uint CREATE_UNICODE_ENVIRONMENT = 0x00000400;
        private const uint CREATE_NO_WINDOW = 0x08000000;
        private const uint EXTENDED_STARTUPINFO_PRESENT = 0x00080000;
        private const uint STARTF_USESTDHANDLES = 0x00000100;
        private const uint HANDLE_FLAG_INHERIT = 0x00000001;
        private const uint JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008;
        private const uint JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400;
        private const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
        private const int JobObjectBasicAccountingInformation = 1;
        private const int JobObjectExtendedLimitInformation = 9;
        private const int PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D;
        private const int PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002;
        private const uint STILL_ACTIVE = 259;
        private const uint PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
        private const uint PROCESS_TERMINATE = 0x0001;

        [StructLayout(LayoutKind.Sequential)]
        private struct STARTUPINFOW
        {
            public int cb;
            public IntPtr lpReserved;
            public IntPtr lpDesktop;
            public IntPtr lpTitle;
            public int dwX;
            public int dwY;
            public int dwXSize;
            public int dwYSize;
            public int dwXCountChars;
            public int dwYCountChars;
            public int dwFillAttribute;
            public int dwFlags;
            public short wShowWindow;
            public short cbReserved2;
            public IntPtr lpReserved2;
            public IntPtr hStdInput;
            public IntPtr hStdOutput;
            public IntPtr hStdError;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct STARTUPINFOEX
        {
            public STARTUPINFOW StartupInfo;
            public IntPtr lpAttributeList;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct PROCESS_INFORMATION
        {
            public IntPtr hProcess;
            public IntPtr hThread;
            public int dwProcessId;
            public int dwThreadId;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct SECURITY_ATTRIBUTES
        {
            public int nLength;
            public IntPtr lpSecurityDescriptor;
            public int bInheritHandle;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
        {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct IO_COUNTERS
        {
            public ulong ReadOperationCount;
            public ulong WriteOperationCount;
            public ulong OtherOperationCount;
            public ulong ReadTransferCount;
            public ulong WriteTransferCount;
            public ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        {
            public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
            public IO_COUNTERS IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_BASIC_ACCOUNTING_INFORMATION
        {
            public long TotalUserTime;
            public long TotalKernelTime;
            public long ThisPeriodTotalUserTime;
            public long ThisPeriodTotalKernelTime;
            public uint TotalPageFaultCount;
            public uint TotalProcesses;
            public uint ActiveProcesses;
            public uint TotalTerminatedProcesses;
        }

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool CreateProcessW(
            string lpApplicationName,
            StringBuilder lpCommandLine,
            IntPtr lpProcessAttributes,
            IntPtr lpThreadAttributes,
            bool bInheritHandles,
            uint dwCreationFlags,
            IntPtr lpEnvironment,
            string lpCurrentDirectory,
            ref STARTUPINFOEX lpStartupInfo,
            out PROCESS_INFORMATION lpProcessInformation);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CreatePipe(out IntPtr hReadPipe, out IntPtr hWritePipe, ref SECURITY_ATTRIBUTES lpPipeAttributes, uint nSize);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetHandleInformation(IntPtr hObject, uint dwMask, uint dwFlags);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool InitializeProcThreadAttributeList(IntPtr lpAttributeList, int dwAttributeCount, int dwFlags, ref IntPtr lpSize);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool UpdateProcThreadAttribute(IntPtr lpAttributeList, uint dwFlags, IntPtr Attribute, IntPtr lpValue, IntPtr cbSize, IntPtr lpPreviousValue, IntPtr lpReturnSize);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern void DeleteProcThreadAttributeList(IntPtr lpAttributeList);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern SafeWaitHandle CreateJobObjectW(IntPtr lpJobAttributes, string lpName);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(SafeWaitHandle hJob, int JobObjectInfoClass, ref JOBOBJECT_EXTENDED_LIMIT_INFORMATION lpJobObjectInfo, int cbJobObjectInfoLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool QueryInformationJobObject(SafeWaitHandle hJob, int JobObjectInfoClass, out JOBOBJECT_BASIC_ACCOUNTING_INFORMATION lpJobObjectInfo, int cbJobObjectInfoLength, out int lpReturnLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool TerminateJobObject(SafeWaitHandle hJob, uint uExitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool IsProcessInJob(IntPtr ProcessHandle, SafeWaitHandle JobHandle, out bool Result);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern uint WaitForSingleObject(SafeWaitHandle hHandle, uint dwMilliseconds);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetExitCodeProcess(SafeWaitHandle hProcess, out uint lpExitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr hObject);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern SafeWaitHandle OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool TerminateProcess(SafeWaitHandle hProcess, uint uExitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool PeekNamedPipe(IntPtr hNamedPipe, IntPtr lpBuffer, int nBufferSize, IntPtr lpBytesRead, out int lpTotalBytesAvail, IntPtr lpBytesLeftThisMessage);

        private static void Fail(string code)
        {
            throw new ApplicationException(code);
        }

        private static string BuildSanitizedEnvironmentBlock()
        {
            var blocked = new System.Collections.Generic.HashSet<string>(StringComparer.OrdinalIgnoreCase);
            blocked.Add("GH_TOKEN");
            blocked.Add("GITHUB_TOKEN");
            blocked.Add("GH_ENTERPRISE_TOKEN");
            blocked.Add("GIT_ASKPASS");
            blocked.Add("SSH_AUTH_SOCK");
            blocked.Add("SSH_ASKPASS");
            var pairs = new System.Collections.Generic.List<string>();
            foreach (System.Collections.DictionaryEntry entry in Environment.GetEnvironmentVariables())
            {
                var name = (string)entry.Key;
                if (blocked.Contains(name)) continue;
                pairs.Add(name + "=" + (string)entry.Value);
            }
            if (!pairs.Exists(s => s.StartsWith("GIT_TERMINAL_PROMPT=", StringComparison.OrdinalIgnoreCase)))
                pairs.Add("GIT_TERMINAL_PROMPT=0");
            pairs.Sort(StringComparer.OrdinalIgnoreCase);
            var sb = new StringBuilder();
            for (int i = 0; i < pairs.Count; i++)
            {
                sb.Append(pairs[i]);
                sb.Append('\0');
            }
            sb.Append('\0');
            return sb.ToString();
        }

        public static StructSizeReport GetStructSizes()
        {
            return new StructSizeReport
            {
                StartupInfoW = Marshal.SizeOf(typeof(STARTUPINFOW)),
                StartupInfoEx = Marshal.SizeOf(typeof(STARTUPINFOEX)),
                JobObjectExtendedLimitInformation = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION)),
                JobObjectBasicAccountingInformation = Marshal.SizeOf(typeof(JOBOBJECT_BASIC_ACCOUNTING_INFORMATION))
            };
        }

        public static ContainedStartResult Start(string applicationName, string commandLine, string workingDirectory, bool redirectStdin)
        {
            SafeWaitHandle job = null;
            IntPtr attrList = IntPtr.Zero;
            IntPtr jobPtr = IntPtr.Zero;
            IntPtr handleListPtr = IntPtr.Zero;
            IntPtr hStdinRead = IntPtr.Zero;
            IntPtr hStdinWrite = IntPtr.Zero;
            IntPtr hStdoutRead = IntPtr.Zero;
            IntPtr hStdoutWrite = IntPtr.Zero;
            IntPtr hStderrRead = IntPtr.Zero;
            IntPtr hStderrWrite = IntPtr.Zero;
            IntPtr envBlock = IntPtr.Zero;
            try
            {
                job = CreateJobObjectW(IntPtr.Zero, null);
                if (job == null || job.IsInvalid) Fail("JOB_CONTAINMENT_UNAVAILABLE");
                var ext = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
                ext.BasicLimitInformation.LimitFlags =
                    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
                    JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION |
                    JOB_OBJECT_LIMIT_ACTIVE_PROCESS;
                ext.BasicLimitInformation.ActiveProcessLimit = 256;
                if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, ref ext, Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION))))
                    Fail("JOB_CONTAINMENT_UNAVAILABLE");

                var sa = new SECURITY_ATTRIBUTES();
                sa.nLength = Marshal.SizeOf(typeof(SECURITY_ATTRIBUTES));
                sa.bInheritHandle = 1;
                if (!CreatePipe(out hStdoutRead, out hStdoutWrite, ref sa, 0)) Fail("PIPE_CREATE_FAILED");
                if (!SetHandleInformation(hStdoutRead, HANDLE_FLAG_INHERIT, 0)) Fail("PIPE_CREATE_FAILED");
                if (!CreatePipe(out hStderrRead, out hStderrWrite, ref sa, 0)) Fail("PIPE_CREATE_FAILED");
                if (!SetHandleInformation(hStderrRead, HANDLE_FLAG_INHERIT, 0)) Fail("PIPE_CREATE_FAILED");
                if (!CreatePipe(out hStdinRead, out hStdinWrite, ref sa, 0)) Fail("PIPE_CREATE_FAILED");
                if (!SetHandleInformation(hStdinWrite, HANDLE_FLAG_INHERIT, 0)) Fail("PIPE_CREATE_FAILED");

                IntPtr size = IntPtr.Zero;
                InitializeProcThreadAttributeList(IntPtr.Zero, 2, 0, ref size);
                attrList = Marshal.AllocHGlobal(size.ToInt32());
                if (!InitializeProcThreadAttributeList(attrList, 2, 0, ref size)) Fail("JOB_CONTAINMENT_UNAVAILABLE");
                jobPtr = Marshal.AllocHGlobal(IntPtr.Size);
                Marshal.WriteIntPtr(jobPtr, job.DangerousGetHandle());
                if (!UpdateProcThreadAttribute(attrList, 0, (IntPtr)PROC_THREAD_ATTRIBUTE_JOB_LIST, jobPtr, (IntPtr)IntPtr.Size, IntPtr.Zero, IntPtr.Zero))
                    Fail("JOB_CONTAINMENT_UNAVAILABLE");

                handleListPtr = Marshal.AllocHGlobal(IntPtr.Size * 3);
                Marshal.WriteIntPtr(handleListPtr, 0, hStdinRead);
                Marshal.WriteIntPtr(handleListPtr, IntPtr.Size, hStdoutWrite);
                Marshal.WriteIntPtr(handleListPtr, IntPtr.Size * 2, hStderrWrite);
                if (!UpdateProcThreadAttribute(attrList, 0, (IntPtr)PROC_THREAD_ATTRIBUTE_HANDLE_LIST, handleListPtr, (IntPtr)(IntPtr.Size * 3), IntPtr.Zero, IntPtr.Zero))
                    Fail("JOB_CONTAINMENT_UNAVAILABLE");

                var siex = new STARTUPINFOEX();
                siex.StartupInfo.cb = Marshal.SizeOf(typeof(STARTUPINFOEX));
                siex.lpAttributeList = attrList;
                siex.StartupInfo.dwFlags = (int)STARTF_USESTDHANDLES;
                siex.StartupInfo.hStdInput = hStdinRead;
                siex.StartupInfo.hStdOutput = hStdoutWrite;
                siex.StartupInfo.hStdError = hStderrWrite;

                var envString = BuildSanitizedEnvironmentBlock();
                envBlock = Marshal.StringToHGlobalUni(envString);
                var cmd = new StringBuilder(commandLine);
                PROCESS_INFORMATION pi;
                if (!CreateProcessW(applicationName, cmd, IntPtr.Zero, IntPtr.Zero, true, CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT, envBlock, workingDirectory, ref siex, out pi))
                    Fail("PROCESS_CREATE_FAILED");

                CloseHandle(pi.hThread);
                CloseHandle(hStdinRead);
                CloseHandle(hStdoutWrite);
                CloseHandle(hStderrWrite);

                var procHandle = new SafeWaitHandle(pi.hProcess, true);
                bool inJob;
                if (!IsProcessInJob(pi.hProcess, job, out inJob) || !inJob)
                {
                    TerminateProcess(procHandle, 1);
                    Fail("JOB_ASSIGNMENT_NOT_VERIFIED");
                }

                var stdinStream = new FileStream(new SafeFileHandle(hStdinWrite, true), FileAccess.Write);
                var stdoutStream = new FileStream(new SafeFileHandle(hStdoutRead, true), FileAccess.Read);
                var stderrStream = new FileStream(new SafeFileHandle(hStderrRead, true), FileAccess.Read);

                return new ContainedStartResult
                {
                    JobHandle = job,
                    ProcessHandle = procHandle,
                    ProcessId = pi.dwProcessId,
                    StdinWrite = stdinStream,
                    StdoutRead = stdoutStream,
                    StderrRead = stderrStream
                };
            }
            catch (ApplicationException)
            {
                throw;
            }
            catch
            {
                Fail("JOB_CONTAINMENT_UNAVAILABLE");
            }
            finally
            {
                if (attrList != IntPtr.Zero)
                {
                    DeleteProcThreadAttributeList(attrList);
                    Marshal.FreeHGlobal(attrList);
                }
                if (jobPtr != IntPtr.Zero) Marshal.FreeHGlobal(jobPtr);
                if (handleListPtr != IntPtr.Zero) Marshal.FreeHGlobal(handleListPtr);
                if (envBlock != IntPtr.Zero) Marshal.FreeHGlobal(envBlock);
            }
            return null;
        }

        [DllImport("kernel32.dll")]
        private static extern IntPtr GetStdHandle(int nStdHandle);

        public static AccountingInfo QueryAccounting(SafeWaitHandle job)
        {
            JOBOBJECT_BASIC_ACCOUNTING_INFORMATION info;
            int returned;
            if (!QueryInformationJobObject(job, JobObjectBasicAccountingInformation, out info, Marshal.SizeOf(typeof(JOBOBJECT_BASIC_ACCOUNTING_INFORMATION)), out returned))
                Fail("JOB_CONTAINMENT_UNAVAILABLE");
            return new AccountingInfo
            {
                ActiveProcesses = info.ActiveProcesses,
                TotalProcesses = info.TotalProcesses,
                TotalTerminatedProcesses = info.TotalTerminatedProcesses
            };
        }

        public static void TerminateJob(SafeWaitHandle job, uint exitCode)
        {
            if (job == null || job.IsInvalid) return;
            TerminateJobObject(job, exitCode);
        }

        public static void WaitForProcess(SafeWaitHandle process, uint timeoutMs)
        {
            var result = WaitForSingleObject(process, timeoutMs);
            if (result == 0x00000102) Fail("WALL_CLOCK_TIMEOUT");
            if (result != 0) Fail("JOB_CONTAINMENT_UNAVAILABLE");
        }

        public static int GetProcessExitCode(SafeWaitHandle process)
        {
            uint code;
            if (!GetExitCodeProcess(process, out code)) Fail("JOB_CONTAINMENT_UNAVAILABLE");
            return (int)code;
        }

        public static bool IsProcessInJobByPid(int pid, IntPtr jobHandleRaw)
        {
            using (var proc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid))
            {
                if (proc == null || proc.IsInvalid) return false;
                using (var job = new SafeWaitHandle(jobHandleRaw, false))
                {
                    bool result;
                    if (!IsProcessInJob(proc.DangerousGetHandle(), job, out result)) return false;
                    return result;
                }
            }
        }

        public static int GetProcessExitCodeIfAvailable(int pid)
        {
            using (var proc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid))
            {
                if (proc == null || proc.IsInvalid) return -1;
                uint code;
                if (!GetExitCodeProcess(proc, out code)) return -1;
                return (int)code;
            }
        }

        public static bool TerminateProcessByPid(int pid)
        {
            using (var proc = OpenProcess(PROCESS_TERMINATE, false, pid))
            {
                if (proc == null || proc.IsInvalid) return false;
                return TerminateProcess(proc, 1);
            }
        }

        public static System.Threading.Tasks.Task<string> ReadStreamToEndAsync(FileStream stream)
        {
            return System.Threading.Tasks.Task.Run(delegate()
            {
                using (var reader = new StreamReader(stream, Encoding.UTF8, false, 4096, true))
                {
                    return reader.ReadToEnd();
                }
            });
        }

        public static int GetPipeBytesAvailable(FileStream stream)
        {
            int avail;
            if (!PeekNamedPipe(stream.SafeFileHandle.DangerousGetHandle(), IntPtr.Zero, 0, IntPtr.Zero, out avail, IntPtr.Zero))
                return 0;
            return avail;
        }

        public static bool WaitProcessHandle(SafeWaitHandle process, int timeoutMilliseconds)
        {
            if (process == null || process.IsInvalid) return true;
            var result = WaitForSingleObject(process, (uint)timeoutMilliseconds);
            return result == 0;
        }
    }
}

'@

function Get-SeshatJobContainmentSourceSha256 {
    Initialize-SeshatJobContainment | Out-Null
    return Get-SeshatUtf8Sha256 -Text $script:SeshatJobContainmentSource
}

function Initialize-SeshatJobContainment {
    if('Seshat.Interop.JobContainmentV1' -as [type]){ return $true }
    try {
        Add-Type -TypeDefinition $script:SeshatJobContainmentSource -Language CSharp -ErrorAction Stop
        return $true
    } catch {
        throw 'JOB_CONTAINMENT_UNAVAILABLE'
    }
}

function Resolve-SeshatNativeExecutablePath {
    param([Parameter(Mandatory=$true)][string]$FilePath)
    if($FilePath -match '[\\/]' -or [System.IO.Path]::IsPathRooted($FilePath)){return [System.IO.Path]::GetFullPath($FilePath)}
    $resolved=Get-Command -Name $FilePath -CommandType Application -ErrorAction SilentlyContinue
    if($resolved){return [string]$resolved.Source}
    return [System.IO.Path]::GetFullPath($FilePath)
}

function New-SeshatContainedCommandLine {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$ArgumentList
    )
    $app=Resolve-SeshatNativeExecutablePath -FilePath $FilePath
    $tokens=@($app)+@($ArgumentList|ForEach-Object{[string]$_})
    $line=($tokens|ForEach-Object{ConvertTo-SeshatNativeArgument -Value $_}) -join ' '
    return [pscustomobject]@{application_name=$app;command_line=$line}
}

function Wait-SeshatContainedQuiescence {
    param(
        [Parameter(Mandatory=$true)]$Session,
        [int]$DescendantQuiesceMilliseconds=5000
    )
    $deadline=(Get-Date).AddMilliseconds($DescendantQuiesceMilliseconds)
    $last=$null
    while((Get-Date) -lt $deadline){
        $last=[Seshat.Interop.JobContainmentV1]::QueryAccounting($Session.JobHandle)
        if([uint32]$last.ActiveProcesses -eq 0){
            return [pscustomobject]@{
                descendants_contained=$true
                descendant_quiescence='QUIET'
                residual_active_processes=0
                total_processes=[uint32]$last.TotalProcesses
                total_terminated_processes=[uint32]$last.TotalTerminatedProcesses
            }
        }
        [System.Threading.Thread]::Sleep(50)
    }
    $residual=[int]$last.ActiveProcesses
    [Seshat.Interop.JobContainmentV1]::TerminateJob($Session.JobHandle,1)
    $deadline2=(Get-Date).AddSeconds(2)
    while((Get-Date) -lt $deadline2){
        $last=[Seshat.Interop.JobContainmentV1]::QueryAccounting($Session.JobHandle)
        if([uint32]$last.ActiveProcesses -eq 0){ throw 'DESCENDANT_RESIDUE_TERMINATED' }
        [System.Threading.Thread]::Sleep(50)
    }
    throw 'DESCENDANT_QUIESCENCE_TIMEOUT'
}

function Get-SeshatContainmentAuditFields {
    param([object]$Quiescence)
    return [ordered]@{
        descendants_contained=[bool]$Quiescence.descendants_contained
        descendant_quiescence=[string]$Quiescence.descendant_quiescence
        residual_active_processes=[int]$Quiescence.residual_active_processes
        total_processes=[int]$Quiescence.total_processes
        total_terminated_processes=[int]$Quiescence.total_terminated_processes
        containment_impl='ADD_TYPE_INPROC_V1'
        containment_source_sha256=(Get-SeshatJobContainmentSourceSha256)
    }
}

function Test-SeshatContainedProcessExited {
    param([Parameter(Mandatory=$true)]$ProcessHandle,[int]$TimeoutMilliseconds=0)
    return [Seshat.Interop.JobContainmentV1]::WaitProcessHandle($ProcessHandle,$TimeoutMilliseconds)
}

function Dispose-SeshatContainedSession {
    param($Session)
    if(-not $Session){return}
    foreach($name in @('StdinWrite','StdoutRead','StderrRead')){
        if($Session.PSObject.Properties[$name] -and $Session.$name){ try{$Session.$name.Dispose()}catch{} }
    }
    if($Session.ProcessHandle){ try{$Session.ProcessHandle.Dispose()}catch{} }
    if($Session.JobHandle){ try{$Session.JobHandle.Dispose()}catch{} }
}

function ConvertTo-SeshatNativeArgument {
    param([Parameter(Mandatory=$true)][AllowEmptyString()][string]$Value)
    if($Value.Length -eq 0){return '""'}
    if($Value -notmatch '[\s"]'){return $Value}
    # Windows PowerShell 5 lacks ProcessStartInfo.ArgumentList. This is the
    # CommandLineToArgvW-compatible quoting used only on that fallback path.
    return '"'+([regex]::Replace($Value,'(\\*)"','$1$1\"') -replace '(\\+)$','$1$1')+'"'
}
function Get-SeshatTextSha256 {
    param([Parameter(Mandatory=$true)][AllowEmptyString()][string]$Text)
    return Get-SeshatUtf8Sha256 -Text $Text
}
function Get-SeshatSafeErrorClass {
    param([Parameter(Mandatory=$true)][object]$ErrorRecord)
    $message=[string]$ErrorRecord.Exception.Message
    if($message -cmatch '^[A-Z][A-Z0-9_]{2,127}$'){return $message}
    $type=[string]$ErrorRecord.Exception.GetType().Name
    if($type -cmatch '^[A-Za-z][A-Za-z0-9]{1,127}$'){return $type}
    return 'UNCLASSIFIED_ERROR'
}
function ConvertTo-SeshatSanitizedLogText {
    param([AllowEmptyString()][string]$Text,[int]$MaximumLength=65536)
    $safe=[string]$Text
    $safe=$safe -replace '(?i)(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})','[REDACTED_CREDENTIAL]'
    $safe=$safe -replace '(?i)(https?://)[^/@\s:]+:[^/@\s]+@','$1[REDACTED_USERINFO]@'
    if($safe.Length -gt $MaximumLength){$safe=$safe.Substring(0,$MaximumLength)+"`n[TRUNCATED]"}
    return $safe
}
function Write-SeshatAppendJsonLine {
    param([Parameter(Mandatory=$true)][object]$Value,[Parameter(Mandatory=$true)][string]$Path,[scriptblock]$FlushAction)
    $parent=Split-Path -Parent $Path
    [void][System.IO.Directory]::CreateDirectory($parent)
    $json=($Value|ConvertTo-Json -Depth 8 -Compress)+"`n"
    $bytes=[System.Text.UTF8Encoding]::new($false).GetBytes($json)
    $stream=[System.IO.File]::Open($Path,[System.IO.FileMode]::Append,[System.IO.FileAccess]::Write,[System.IO.FileShare]::Read)
    try{$stream.Write($bytes,0,$bytes.Length);Invoke-SeshatDurableFlush -Stream $stream -FlushAction $FlushAction}finally{$stream.Dispose()}
}
function Invoke-SeshatDurableFlush {
    param([Parameter(Mandatory=$true)][System.IO.FileStream]$Stream,[scriptblock]$FlushAction)
    if($FlushAction){& $FlushAction $Stream}else{$Stream.Flush($true)}
}
function Invoke-SeshatBoundedNativeText {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$ArgumentList,
        [Parameter(Mandatory=$true)][string]$WorkingDirectory,
        [Parameter(Mandatory=$true)][string]$Label,
        [long]$MaximumStandardOutputBytes=262144,
        [long]$MaximumStandardErrorBytes=32768,
        [int]$MaximumLines=64
    )
    if($MaximumLines -le 0){throw 'INVALID_NATIVE_LINE_LIMIT'}
    $token=[guid]::NewGuid().ToString('N')
    $outPath=Join-Path ([System.IO.Path]::GetTempPath()) ('seshat-'+$token+'.out')
    $errPath=Join-Path ([System.IO.Path]::GetTempPath()) ('seshat-'+$token+'.err')
    try{
        $result=Invoke-SeshatStreamingNativeCommand -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -Label $Label -StandardOutputPath $outPath -StandardErrorPath $errPath -MaximumStandardOutputBytes $MaximumStandardOutputBytes -MaximumStandardErrorBytes $MaximumStandardErrorBytes
        if($result.limit_exceeded){throw 'NATIVE_OUTPUT_LIMIT_EXCEEDED'}
        Assert-SeshatNativeSuccess -Result $result -FailureClass 'NATIVE_COMMAND_FAILED'
        $strictUtf8=[System.Text.UTF8Encoding]::new($false,$true)
        $reader=[System.IO.StreamReader]::new($outPath,$strictUtf8,$false,4096)
        $lines=New-Object 'System.Collections.Generic.List[string]'
        $lineCount=0
        try{
            while($null -ne ($line=$reader.ReadLine())){
                $lineCount++
                if($lineCount -gt $MaximumLines){throw 'NATIVE_LINE_LIMIT_EXCEEDED'}
                if($line.Length -gt 0){$lines.Add($line)}
            }
        }finally{$reader.Dispose()}
        return [pscustomobject]@{exit_code=[int]$result.exit_code;lines=@($lines.ToArray());stderr_present=([long]$result.stderr_bytes -gt 0)}
    }finally{
        foreach($path in @($outPath,$errPath)){if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path -Force}}
    }
}
function Invoke-SeshatNativeCommand {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$ArgumentList,
        [Parameter(Mandatory=$true)][string]$WorkingDirectory,
        [Parameter(Mandatory=$true)][string]$Label,
        [string]$AuditPath,
        [string]$JobId='unknown',
        [AllowEmptyString()][string]$StandardInputText,
        [int]$DescendantQuiesceMilliseconds=5000,
        [int]$WallClockTimeoutMilliseconds=0
    )
    if($Label -cnotmatch '^[a-z0-9][a-z0-9-]{1,63}$'){throw 'INVALID_NATIVE_COMMAND_LABEL'}
    Initialize-SeshatJobContainment | Out-Null
    $hasStandardInput=$PSBoundParameters.ContainsKey('StandardInputText')
    $cmd=New-SeshatContainedCommandLine -FilePath $FilePath -ArgumentList $ArgumentList
    $workDir=[System.IO.Path]::GetFullPath($WorkingDirectory)
    $session=$null
    $wmiEscape=$false
    try{
        $session=[Seshat.Interop.JobContainmentV1]::Start($cmd.application_name,$cmd.command_line,$workDir,$true)
        if($hasStandardInput -and $session.StdinWrite){
            $bytes=[System.Text.UTF8Encoding]::new($false).GetBytes($StandardInputText)
            $session.StdinWrite.Write($bytes,0,$bytes.Length)
            $session.StdinWrite.Flush()
            $session.StdinWrite.Dispose()
            $session.StdinWrite=$null
        }elseif($session.StdinWrite){
            $session.StdinWrite.Dispose()
            $session.StdinWrite=$null
        }
        $timeout=if($WallClockTimeoutMilliseconds -gt 0){[uint32]$WallClockTimeoutMilliseconds}else{[uint32]4294967295}
        [Seshat.Interop.JobContainmentV1]::WaitForProcess($session.ProcessHandle,$timeout)
        $stdoutReader=New-Object System.IO.StreamReader($session.StdoutRead,[System.Text.UTF8Encoding]::new($false),$false,4096,$true)
        $stderrReader=New-Object System.IO.StreamReader($session.StderrRead,[System.Text.UTF8Encoding]::new($false),$false,4096,$true)
        $stdoutText=[string]$stdoutReader.ReadToEnd()
        $stderrText=[string]$stderrReader.ReadToEnd()
        $stdoutReader.Dispose();$stderrReader.Dispose()
        $exitCode=[Seshat.Interop.JobContainmentV1]::GetProcessExitCode($session.ProcessHandle)
        $quiescence=Wait-SeshatContainedQuiescence -Session $session -DescendantQuiesceMilliseconds $DescendantQuiesceMilliseconds
        $auditFields=Get-SeshatContainmentAuditFields -Quiescence $quiescence
        $result=[pscustomobject]@{
            label=$Label;exit_code=$exitCode;stdout=$stdoutText;stderr=$stderrText
            stderr_present=(-not [string]::IsNullOrWhiteSpace($stderrText))
        }
        foreach($prop in $auditFields.Keys){$result|Add-Member -NotePropertyName $prop -NotePropertyValue $auditFields[$prop]}
        if($AuditPath){
            $event=[ordered]@{
                schema='seshat.native-command.v2';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
                job_id=$JobId;command=$Label;exit_code=$result.exit_code
                stderr_present=$result.stderr_present
                stderr_sha256=if($result.stderr_present){Get-SeshatTextSha256 -Text $result.stderr}else{$null}
                stderr_line_count=if($result.stderr_present){@($result.stderr -split "\r?\n"|Where-Object{$_}).Count}else{0}
                classification=if($result.exit_code -ne 0){'NONZERO_EXIT'}elseif($result.stderr_present){'EXIT_ZERO_STDERR'}else{'CLEAN_EXIT'}
            }
            foreach($prop in $auditFields.Keys){$event[$prop]=$auditFields[$prop]}
            [void](Write-SeshatAppendJsonLine -Value $event -Path $AuditPath)
        }
        return $result
    }catch{
        if($session){ try{[Seshat.Interop.JobContainmentV1]::TerminateJob($session.JobHandle,1)}catch{} }
        throw
    }finally{
        Dispose-SeshatContainedSession -Session $session
    }
}
function Invoke-SeshatStreamingNativeCommand {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][string[]]$ArgumentList,
        [Parameter(Mandatory=$true)][string]$WorkingDirectory,
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][string]$StandardOutputPath,
        [Parameter(Mandatory=$true)][string]$StandardErrorPath,
        [Parameter(Mandatory=$true)][long]$MaximumStandardOutputBytes,
        [Parameter(Mandatory=$true)][long]$MaximumStandardErrorBytes,
        [string]$AuditPath,
        [string]$JobId='unknown',
        [AllowEmptyString()][string]$StandardInputText,
        [int]$NoOutputTimeoutMilliseconds=7200000,
        [int]$WallClockTimeoutMilliseconds=0,
        [int]$DescendantQuiesceMilliseconds=5000
    )
    if($Label -cnotmatch '^[a-z0-9][a-z0-9-]{1,63}$'){throw 'INVALID_NATIVE_COMMAND_LABEL'}
    if($MaximumStandardOutputBytes -le 0 -or $MaximumStandardErrorBytes -le 0){throw 'INVALID_STREAM_LIMIT'}
    Initialize-SeshatJobContainment | Out-Null
    $stdoutFull=[System.IO.Path]::GetFullPath($StandardOutputPath)
    $stderrFull=[System.IO.Path]::GetFullPath($StandardErrorPath)
    if($stdoutFull -ieq $stderrFull){throw 'STREAM_PATH_COLLISION'}
    foreach($path in @($stdoutFull,$stderrFull)){
        $parent=Split-Path -Parent $path
        [void][System.IO.Directory]::CreateDirectory($parent)
    }
    $hasStandardInput=$PSBoundParameters.ContainsKey('StandardInputText')
    $cmd=New-SeshatContainedCommandLine -FilePath $FilePath -ArgumentList $ArgumentList
    $workDir=[System.IO.Path]::GetFullPath($WorkingDirectory)
    $session=$null
    $stdoutFile=$null
    $stderrFile=$null
    $terminalWritten=$false
    $stdoutBytes=[long]0
    $stderrBytes=[long]0
    $limitStream=$null
    $wmiEscapeDetected=$false
    $containmentJobPtr=[IntPtr]::Zero
    try{
        $stdoutFile=[System.IO.File]::Open($stdoutFull,[System.IO.FileMode]::Create,[System.IO.FileAccess]::Write,[System.IO.FileShare]::Read)
        $stderrFile=[System.IO.File]::Open($stderrFull,[System.IO.FileMode]::Create,[System.IO.FileAccess]::Write,[System.IO.FileShare]::Read)
        if($AuditPath){
            Write-SeshatAppendJsonLine -Value ([ordered]@{
                schema='seshat.streaming-native-command.v2';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
                job_id=$JobId;command=$Label;status='STARTING';terminal=$false
                stdout_path=$stdoutFull;stderr_path=$stderrFull
                stdout_limit_bytes=$MaximumStandardOutputBytes;stderr_limit_bytes=$MaximumStandardErrorBytes
            }) -Path $AuditPath
        }
        $session=[Seshat.Interop.JobContainmentV1]::Start($cmd.application_name,$cmd.command_line,$workDir,$true)
        $containmentJobPtr=$session.JobHandle.DangerousGetHandle()
        $stdinClosed=$false
        if($hasStandardInput -and $session.StdinWrite){
            $inBytes=[System.Text.UTF8Encoding]::new($false).GetBytes($StandardInputText)
            $session.StdinWrite.Write($inBytes,0,$inBytes.Length)
            $session.StdinWrite.Flush()
            $session.StdinWrite.Dispose()
            $session.StdinWrite=$null
            $stdinClosed=$true
        }elseif($session.StdinWrite){
            $session.StdinWrite.Dispose()
            $session.StdinWrite=$null
            $stdinClosed=$true
        }
        $stdoutBuffer=New-Object byte[] 4096
        $stderrBuffer=New-Object byte[] 4096
        $stdoutDone=$false
        $stderrDone=$false
        $lastOutputUtc=(Get-Date).ToUniversalTime()
        $wallStart=(Get-Date).ToUniversalTime()
        while(-not($stdoutDone -and $stderrDone)){
            $madeProgress=$false
            if(-not $stdoutDone){
                $stdoutAvail=[Seshat.Interop.JobContainmentV1]::GetPipeBytesAvailable($session.StdoutRead)
                if($stdoutAvail -gt 0){
                    $count=$session.StdoutRead.Read($stdoutBuffer,0,[int][Math]::Min($stdoutBuffer.Length,$stdoutAvail))
                    if($count -gt 0){
                        $lastOutputUtc=(Get-Date).ToUniversalTime()
                        $remaining=$MaximumStandardOutputBytes-$stdoutBytes
                        $writeCount=[int][Math]::Min([long]$count,[Math]::Max([long]0,$remaining))
                        if($writeCount -gt 0){$stdoutFile.Write($stdoutBuffer,0,$writeCount);$stdoutFile.Flush();$stdoutBytes+=$writeCount}
                        if($writeCount -lt $count){$limitStream='stdout'}
                    }
                    $madeProgress=$true
                }elseif(Test-SeshatContainedProcessExited -ProcessHandle $session.ProcessHandle -TimeoutMilliseconds 0){$stdoutDone=$true}
            }
            if(-not $stderrDone){
                $stderrAvail=[Seshat.Interop.JobContainmentV1]::GetPipeBytesAvailable($session.StderrRead)
                if($stderrAvail -gt 0){
                    $count=$session.StderrRead.Read($stderrBuffer,0,[int][Math]::Min($stderrBuffer.Length,$stderrAvail))
                    if($count -gt 0){
                        $lastOutputUtc=(Get-Date).ToUniversalTime()
                        $remaining=$MaximumStandardErrorBytes-$stderrBytes
                        $writeCount=[int][Math]::Min([long]$count,[Math]::Max([long]0,$remaining))
                        if($writeCount -gt 0){$stderrFile.Write($stderrBuffer,0,$writeCount);$stderrFile.Flush();$stderrBytes+=$writeCount}
                        if($writeCount -lt $count){$limitStream='stderr'}
                    }
                    $madeProgress=$true
                }elseif(Test-SeshatContainedProcessExited -ProcessHandle $session.ProcessHandle -TimeoutMilliseconds 0){$stderrDone=$true}
            }
            if($limitStream){
                [Seshat.Interop.JobContainmentV1]::TerminateJob($session.JobHandle,1)
                $stdoutDone=$true
                $stderrDone=$true
            }elseif(-not $madeProgress){
                $now=(Get-Date).ToUniversalTime()
                if($NoOutputTimeoutMilliseconds -gt 0 -and ($now-$lastOutputUtc).TotalMilliseconds -gt $NoOutputTimeoutMilliseconds){
                    [Seshat.Interop.JobContainmentV1]::TerminateJob($session.JobHandle,1)
                    throw 'NO_OUTPUT_TIMEOUT'
                }
                if($WallClockTimeoutMilliseconds -gt 0 -and ($now-$wallStart).TotalMilliseconds -gt $WallClockTimeoutMilliseconds){
                    [Seshat.Interop.JobContainmentV1]::TerminateJob($session.JobHandle,1)
                    throw 'WALL_CLOCK_TIMEOUT'
                }
                if(-not (Test-SeshatContainedProcessExited -ProcessHandle $session.ProcessHandle -TimeoutMilliseconds 20)){}
            }
        }
        $procTimeout=if($WallClockTimeoutMilliseconds -gt 0){[uint32]$WallClockTimeoutMilliseconds}else{[uint32]4294967295}
        [Seshat.Interop.JobContainmentV1]::WaitForProcess($session.ProcessHandle,$procTimeout)
        $exitCode=[Seshat.Interop.JobContainmentV1]::GetProcessExitCode($session.ProcessHandle)
        $quiescence=Wait-SeshatContainedQuiescence -Session $session -DescendantQuiesceMilliseconds $DescendantQuiesceMilliseconds
        $auditFields=Get-SeshatContainmentAuditFields -Quiescence $quiescence
        if($containmentJobPtr -ne [IntPtr]::Zero -and $stdoutBytes -gt 0 -and $stdoutBytes -lt 64){
            $probe=[System.IO.File]::ReadAllText($stdoutFull,[System.Text.UTF8Encoding]::new($false)).Trim()
            if($probe -match '^[0-9]+$'){
                $wmiEscapeDetected= -not [Seshat.Interop.JobContainmentV1]::IsProcessInJobByPid([int]$probe,$containmentJobPtr)
            }
        }
        $status=if($limitStream){'OUTPUT_LIMIT_EXCEEDED'}elseif($exitCode -ne 0){'NONZERO_EXIT'}else{'COMPLETED'}
        if($AuditPath){
            $terminal=[ordered]@{
                schema='seshat.streaming-native-command.v2';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
                job_id=$JobId;command=$Label;status=$status;terminal=$true;exit_code=$exitCode
                stdout_bytes=$stdoutBytes;stderr_bytes=$stderrBytes;limit_stream=$limitStream
            }
            foreach($prop in $auditFields.Keys){$terminal[$prop]=$auditFields[$prop]}
            Write-SeshatAppendJsonLine -Value $terminal -Path $AuditPath
            $terminalWritten=$true
        }
        return [pscustomobject]@{
            label=$Label;exit_code=$exitCode;status=$status;limit_exceeded=[bool]$limitStream
            limit_stream=$limitStream;stdout_path=$stdoutFull;stderr_path=$stderrFull
            stdout_bytes=$stdoutBytes;stderr_bytes=$stderrBytes
            descendants_contained=[bool]$quiescence.descendants_contained
            descendant_quiescence=[string]$quiescence.descendant_quiescence
            residual_active_processes=[int]$quiescence.residual_active_processes
            total_processes=[int]$quiescence.total_processes
            total_terminated_processes=[int]$quiescence.total_terminated_processes
            containment_impl='ADD_TYPE_INPROC_V1'
            containment_source_sha256=$auditFields.containment_source_sha256
            containment_job_handle=$containmentJobPtr
            wmi_escape_detected=$wmiEscapeDetected
        }
    }catch{
        $streamError=$_
        if($session){ try{[Seshat.Interop.JobContainmentV1]::TerminateJob($session.JobHandle,1)}catch{} }
        if($AuditPath -and -not $terminalWritten){
            Write-SeshatAppendJsonLine -Value ([ordered]@{
                schema='seshat.streaming-native-command.v2';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
                job_id=$JobId;command=$Label;status='FAILED';terminal=$true
                exit_code=$null
                stdout_bytes=$stdoutBytes;stderr_bytes=$stderrBytes;error_class=(Get-SeshatSafeErrorClass -ErrorRecord $streamError)
            }) -Path $AuditPath
        }
        throw $streamError
    }finally{
        if($stdoutFile){$stdoutFile.Dispose()}
        if($stderrFile){$stderrFile.Dispose()}
        Dispose-SeshatContainedSession -Session $session
    }
}
function Assert-SeshatNativeSuccess {
    param([Parameter(Mandatory=$true)][object]$Result,[Parameter(Mandatory=$true)][string]$FailureClass)
    if([int]$Result.exit_code -ne 0){throw $FailureClass}
}
function Get-SeshatOutputLines {
    param([Parameter(Mandatory=$true)][AllowEmptyString()][string]$Text)
    if([string]::IsNullOrEmpty($Text)){return @()}
    return @($Text -split "\r?\n"|Where-Object{$_ -ne ''})
}
function Write-SeshatPublicationEvent {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$JobId,
        [Parameter(Mandatory=$true)][ValidateSet('PRECHECK','BEFORE_COMMIT','STAGED_ONLY','COMMITTED_ONLY','PUSHED_WITHOUT_PR','DRAFT_PUBLISHED','RECONCILIATION_REQUIRED')][string]$Phase,
        [Parameter(Mandatory=$true)][string]$Branch,
        [Parameter(Mandatory=$true)][string]$BaseSha,
        [string]$HeadSha,
        [string]$ErrorClass
    )
    $event=[ordered]@{
        schema='seshat.publication-stage.v1';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
        job_id=$JobId;phase=$Phase;branch=$Branch;base_sha=$BaseSha;head_sha=$HeadSha;error_class=$ErrorClass
    }
    Write-SeshatAppendJsonLine -Value $event -Path $Path
}
function Write-SeshatMutationEvent {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$JobId,
        [Parameter(Mandatory=$true)][string]$AttemptNonce,
        [Parameter(Mandatory=$true)][ValidateSet('git-add','git-commit','git-push-create-only','gh-pr-create')][string]$Action,
        [Parameter(Mandatory=$true)][ValidateSet('INTENT','RETURNED','COMPLETE')][string]$Status,
        [Parameter(Mandatory=$true)][string]$Phase,
        [Parameter(Mandatory=$true)][object]$BeforeWitness,
        [object]$AfterWitness,
        [Nullable[int]]$ExitCode,
        [scriptblock]$FlushAction
    )
    Write-SeshatAppendJsonLine -Value ([ordered]@{
        schema='seshat.publication-mutation.v2';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
        job_id=$JobId;attempt_nonce=$AttemptNonce;action=$Action;status=$Status;phase=$Phase
        before_witness=$BeforeWitness;after_witness=$AfterWitness;exit_code=$ExitCode
    }) -Path $Path -FlushAction $FlushAction
}
function Get-SeshatMutationRecoveryState {
    param([AllowNull()][object]$LatestMutation)
    if(-not $LatestMutation){return 'NO_MUTATION'}
    try{
        if([string]$LatestMutation.schema -cne 'seshat.publication-mutation.v2'){return 'INVALID_MUTATION_EVENT'}
        if(-not([string]$LatestMutation.attempt_nonce -cmatch '^[0-9a-f]{32}$')){return 'INVALID_MUTATION_EVENT'}
        switch([string]$LatestMutation.status){
            'COMPLETE' {return 'COMPLETE'}
            'INTENT' {return 'RECONCILIATION_REQUIRED_INTENT_WITHOUT_RETURN'}
            'RETURNED' {return 'RECONCILIATION_REQUIRED_RETURN_WITHOUT_WITNESS'}
            default {return 'INVALID_MUTATION_EVENT'}
        }
    }catch{return 'INVALID_MUTATION_EVENT'}
}
function Assert-SeshatPublicationAttemptAbsent {
    param([Parameter(Mandatory=$true)][string]$EventPath,[Parameter(Mandatory=$true)][string]$ReceiptPath)
    if(Test-Path -LiteralPath $ReceiptPath){throw 'PUBLICATION_RECEIPT_ALREADY_EXISTS'}
    if(Test-Path -LiteralPath $EventPath){throw 'PUBLICATION_ATTEMPT_ALREADY_RECORDED'}
}
function Start-SeshatPublicationAttempt {
    param(
        [Parameter(Mandatory=$true)][string]$EventPath,
        [Parameter(Mandatory=$true)][string]$ReceiptPath,
        [Parameter(Mandatory=$true)][string]$JobId,
        [Parameter(Mandatory=$true)][string]$Branch,
        [Parameter(Mandatory=$true)][string]$BaseSha,
        [scriptblock]$FlushAction
    )
    if(Test-Path -LiteralPath $ReceiptPath){throw 'PUBLICATION_RECEIPT_ALREADY_EXISTS'}
    $parent=Split-Path -Parent $EventPath
    [void][System.IO.Directory]::CreateDirectory($parent)
    $event=[ordered]@{
        schema='seshat.publication-stage.v1';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
        job_id=$JobId;phase='PRECHECK';branch=$Branch;base_sha=$BaseSha;head_sha=$BaseSha;error_class=$null
    }
    $bytes=[System.Text.UTF8Encoding]::new($false).GetBytes((($event|ConvertTo-Json -Depth 8 -Compress)+"`n"))
    try{$stream=[System.IO.File]::Open($EventPath,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::Read)}catch{if(Test-Path -LiteralPath $EventPath){throw 'PUBLICATION_ATTEMPT_ALREADY_RECORDED'};throw}
    try{$stream.Write($bytes,0,$bytes.Length);Invoke-SeshatDurableFlush -Stream $stream -FlushAction $FlushAction}finally{$stream.Dispose()}
}
function Test-SeshatPublicationReceipt {
    param([Parameter(Mandatory=$true)][object]$Receipt,[Parameter(Mandatory=$true)][object]$Job,[Parameter(Mandatory=$true)][string]$HeadSha)
    try{
        if([string]$Receipt.status -cne 'PUBLISHED_DRAFT_PR'){return 'BLOCK_PUBLISH_STATUS'}
        if([string]$Receipt.job_id -cne [string]$Job.job_id -or [int]$Receipt.issue -ne [int]$Job.issue_number){return 'BLOCK_PUBLISH_JOB_MISMATCH'}
        if([string]$Receipt.branch -cne [string]$Job.branch -or [string]$Receipt.head_sha -cne $HeadSha){return 'BLOCK_PUBLISH_HEAD_MISMATCH'}
        if([int]$Receipt.pr_number -le 0 -or [string]$Receipt.pr_state -cne 'OPEN' -or -not [bool]$Receipt.pr_is_draft){return 'BLOCK_PUBLISH_PR_STATE'}
        if([string]$Receipt.pr_base -cne 'main' -or [string]$Receipt.pr_head -cne [string]$Job.branch){return 'BLOCK_PUBLISH_PR_REFS'}
        return 'ADMIT'
    }catch{return 'BLOCK_MALFORMED_PUBLICATION_RECEIPT'}
}
function Get-SeshatPublicationRecoveryDecision {
    param([Parameter(Mandatory=$true)][ValidateSet('PRECHECK','BEFORE_COMMIT','STAGED_ONLY','COMMITTED_ONLY','PUSHED_WITHOUT_PR','DRAFT_PUBLISHED','RECONCILIATION_REQUIRED')][string]$Phase)
    switch($Phase){
        'PRECHECK' {return 'NO_MUTATION_RECORDED_INSPECT_BEFORE_RETRY'}
        'BEFORE_COMMIT' {return 'MANUAL_INSPECT_WORKTREE_DO_NOT_RETRY'}
        'STAGED_ONLY' {return 'MANUAL_INSPECT_INDEX_DO_NOT_RETRY'}
        'COMMITTED_ONLY' {return 'MANUAL_VERIFY_REMOTE_BEFORE_ANY_PUSH'}
        'PUSHED_WITHOUT_PR' {return 'MANUAL_VERIFY_GITHUB_BEFORE_ANY_PR_CREATE'}
        'DRAFT_PUBLISHED' {return 'READBACK_VERIFY_EXISTING_DRAFT_NO_RETRY'}
        'RECONCILIATION_REQUIRED' {return 'READBACK_ALL_WITNESSES_MANUAL_DECISION_NO_RETRY'}
    }
}
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
function Assert-SeshatPathUnderRootNoReparse {
    param([Parameter(Mandatory=$true)][string]$Path,[Parameter(Mandatory=$true)][string]$Root,[switch]$Leaf)
    $full=[System.IO.Path]::GetFullPath($Path)
    $rootFull=[System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    if($full -cne $rootFull -and -not $full.StartsWith($rootFull+'\',[System.StringComparison]::OrdinalIgnoreCase)){throw 'TRUSTED_PATH_OUTSIDE_PINNED_ROOT'}
    if($Leaf -and -not(Test-Path -LiteralPath $full -PathType Leaf)){throw 'TRUSTED_LAUNCH_FILE_MISSING'}
    $cursor=$full
    while($cursor -and $cursor.Length -ge $rootFull.Length){
        $item=Get-Item -LiteralPath $cursor -Force
        if(($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0){throw 'TRUSTED_LAUNCH_REPARSE_POINT'}
        if($cursor -ieq $rootFull){break}
        $cursor=Split-Path -Parent $cursor
    }
    if($cursor -ine $rootFull){throw 'TRUSTED_LAUNCH_ROOT_NOT_REACHED'}
    return $full
}
function Assert-SeshatChangedFileLimits {
    param(
        [Parameter(Mandatory=$true)][string]$Repo,
        [Parameter(Mandatory=$true)][object[]]$Paths,
        [long]$MaximumFileBytes=2097152,
        [long]$MaximumTotalBytes=5242880
    )
    $root=[System.IO.Path]::GetFullPath($Repo).TrimEnd('\')
    $total=[long]0
    foreach($relativeValue in $Paths){
        $relative=[string]$relativeValue
        if($relative -match '(^|/)\.\.(/|$)|^/|:|\\'){throw 'UNSAFE_CHANGED_PATH'}
        $full=[System.IO.Path]::GetFullPath((Join-Path $root $relative.Replace('/','\')))
        if(-not $full.StartsWith($root+'\',[System.StringComparison]::OrdinalIgnoreCase)){throw 'CHANGED_PATH_OUTSIDE_REPOSITORY'}
        if(-not(Test-Path -LiteralPath $full -PathType Leaf)){throw 'CHANGED_PATH_NOT_REGULAR_FILE'}
        $cursor=$full
        while($cursor -and $cursor.Length -gt $root.Length){
            $item=Get-Item -LiteralPath $cursor -Force
            if(($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0){throw 'CHANGED_PATH_REPARSE_POINT'}
            $cursor=Split-Path -Parent $cursor
        }
        $length=[long](Get-Item -LiteralPath $full -Force).Length
        if($length -gt $MaximumFileBytes){throw 'CHANGED_FILE_SIZE_LIMIT_EXCEEDED'}
        $total+=$length
        if($total -gt $MaximumTotalBytes){throw 'CHANGED_TOTAL_SIZE_LIMIT_EXCEEDED'}
    }
    return $total
}
function Test-SeshatAddedDiffFile {
    param([Parameter(Mandatory=$true)][string]$Path,[long]$MaximumBytes=8388608,[int]$MaximumLineCharacters=131072)
    if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){return 'DIFF_SCAN_FILE_MISSING'}
    if([long](Get-Item -LiteralPath $Path).Length -gt $MaximumBytes){return 'DIFF_SCAN_SIZE_LIMIT_EXCEEDED'}
    $secret=[regex]::new('(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)',[System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    $stream=[System.IO.File]::Open($Path,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::Read)
    try{
        $reader=New-Object System.IO.StreamReader($stream,(New-Object System.Text.UTF8Encoding($false,$true)),$true,4096,$true)
        try{
            $buffer=New-Object char[] 4096
            $carry=''
            while(($count=$reader.Read($buffer,0,$buffer.Length)) -gt 0){
                $carry+=(-join $buffer[0..($count-1)])
                if($carry.Length -gt ($MaximumLineCharacters+4096) -and $carry.IndexOf("`n") -lt 0){return 'DIFF_LINE_LIMIT_EXCEEDED'}
                while(($newline=$carry.IndexOf("`n")) -ge 0){
                    $line=$carry.Substring(0,$newline).TrimEnd("`r")
                    $carry=$carry.Substring($newline+1)
                    if($line.Length -gt $MaximumLineCharacters){return 'DIFF_LINE_LIMIT_EXCEEDED'}
                    if($line.StartsWith('+') -and -not $line.StartsWith('+++') -and $secret.IsMatch($line.Substring(1))){return 'POSSIBLE_CREDENTIAL_IN_DIFF'}
                }
            }
            if($carry.Length -gt $MaximumLineCharacters){return 'DIFF_LINE_LIMIT_EXCEEDED'}
            if($carry.StartsWith('+') -and -not $carry.StartsWith('+++') -and $secret.IsMatch($carry.Substring(1))){return 'POSSIBLE_CREDENTIAL_IN_DIFF'}
        }finally{$reader.Dispose()}
    }catch{return 'DIFF_NOT_VALID_UTF8'}finally{$stream.Dispose()}
    return 'ADMIT'
}
function Test-SeshatNumstatTextOnly {
    param([Parameter(Mandatory=$true)][AllowEmptyCollection()][object[]]$Lines)
    foreach($value in $Lines){
        $line=[string]$value
        if($line -cmatch '^-\t-\t'){return 'BINARY_STAGED_CONTENT_DENIED'}
        if($line -cnotmatch '^[0-9]+\t[0-9]+\t'){return 'MALFORMED_DIFF_NUMSTAT'}
    }
    return 'ADMIT'
}
function Get-SeshatCodexLaunchPolicyBinding {
    param([string]$PolicyPath='C:\ProgramData\SESHAT\codex-launch-policy.json')
    if(-not(Test-Path -LiteralPath $PolicyPath -PathType Leaf)){throw 'CODEX_TRUST_POLICY_MISSING'}
    $policyFull=[System.IO.Path]::GetFullPath($PolicyPath)
    try{[void](Assert-SeshatPathUnderRootNoReparse -Path $policyFull -Root (Split-Path -Parent $policyFull) -Leaf)}catch{throw 'CODEX_TRUST_POLICY_REPARSE_POINT'}
    $policy=Get-Content -LiteralPath $policyFull -Raw -Encoding UTF8|ConvertFrom-Json
    try{
        if([string]$policy.schema -cne 'seshat.codex-launch-policy.v1'){throw 'CODEX_TRUST_POLICY_SCHEMA'}
        if(-not([string]$policy.policy_id -cmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$')){throw 'CODEX_TRUST_POLICY_ID'}
        foreach($name in @('node_sha256','codex_js_sha256','package_json_sha256')){if(-not([string]$policy.$name -cmatch '^[0-9a-f]{64}$')){throw 'CODEX_TRUST_POLICY_PIN_INVALID'}}
        if(-not([string]$policy.node_signer_thumbprint -match '^[0-9a-f]{40,64}$')){throw 'CODEX_TRUST_POLICY_PIN_INVALID'}
        if(-not([string]$policy.node_version -cmatch '^[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?$')){throw 'CODEX_NODE_VERSION_INVALID'}
        if([string]$policy.package_name -cne '@openai/codex' -or -not([string]$policy.package_version -cmatch '^[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?$')){throw 'CODEX_PACKAGE_IDENTITY_INVALID'}
        $node=Assert-SeshatPathUnderRootNoReparse -Path ([string]$policy.node_path) -Root ([string]$policy.node_root) -Leaf
        $js=Assert-SeshatPathUnderRootNoReparse -Path ([string]$policy.codex_js_path) -Root ([string]$policy.codex_root) -Leaf
        $package=Assert-SeshatPathUnderRootNoReparse -Path ([string]$policy.package_json_path) -Root ([string]$policy.codex_root) -Leaf
        if($js -ine [System.IO.Path]::GetFullPath((Join-Path ([string]$policy.codex_root) 'bin\codex.js')) -or $package -ine [System.IO.Path]::GetFullPath((Join-Path ([string]$policy.codex_root) 'package.json'))){throw 'CODEX_PACKAGE_LAYOUT_INVALID'}
        if([System.IO.Path]::GetExtension($node) -cne '.exe' -or [System.IO.Path]::GetExtension($js) -cne '.js'){throw 'CODEX_TRUST_POLICY_PATH_KIND'}
        if((Get-SeshatFileSha256 -Path $node) -cne [string]$policy.node_sha256 -or (Get-SeshatFileSha256 -Path $js) -cne [string]$policy.codex_js_sha256 -or (Get-SeshatFileSha256 -Path $package) -cne [string]$policy.package_json_sha256){throw 'CODEX_TRUSTED_FILE_HASH_DRIFT'}
        $signature=Get-AuthenticodeSignature -LiteralPath $node
        if([string]$signature.Status -cne 'Valid' -or -not $signature.SignerCertificate -or ([string]$signature.SignerCertificate.Thumbprint).ToUpperInvariant() -cne ([string]$policy.node_signer_thumbprint).ToUpperInvariant()){throw 'CODEX_NODE_SIGNATURE_INVALID'}
        $nodeVersion=[string]([System.Diagnostics.FileVersionInfo]::GetVersionInfo($node).ProductVersion)
        if($nodeVersion -cne [string]$policy.node_version){throw 'CODEX_NODE_VERSION_DRIFT'}
        $packageIdentity=Get-Content -LiteralPath $package -Raw -Encoding UTF8|ConvertFrom-Json
        if([string]$packageIdentity.name -cne [string]$policy.package_name -or [string]$packageIdentity.version -cne [string]$policy.package_version){throw 'CODEX_PACKAGE_IDENTITY_DRIFT'}
        return [pscustomobject]@{policy_path=$policyFull;policy_sha256=(Get-SeshatFileSha256 -Path $policyFull);policy_id=[string]$policy.policy_id;node_path=$node;node_root=[System.IO.Path]::GetFullPath([string]$policy.node_root);node_sha256=[string]$policy.node_sha256;node_signer_thumbprint=([string]$policy.node_signer_thumbprint).ToUpperInvariant();node_version=$nodeVersion;codex_root=[System.IO.Path]::GetFullPath([string]$policy.codex_root);codex_js_path=$js;codex_js_sha256=[string]$policy.codex_js_sha256;package_json_path=$package;package_json_sha256=[string]$policy.package_json_sha256;package_name=[string]$policy.package_name;package_version=[string]$policy.package_version}
    }catch{if($_.Exception.Message -cmatch '^[A-Z][A-Z0-9_]+$'){throw};throw 'CODEX_TRUST_POLICY_MALFORMED'}
}
function Resolve-SeshatCodexLaunch {
    param([Parameter(Mandatory=$true)][object]$ExpectedBinding)
    $actual=Get-SeshatCodexLaunchPolicyBinding -PolicyPath ([string]$ExpectedBinding.policy_path)
    foreach($field in @('policy_sha256','policy_id','node_path','node_root','node_sha256','node_signer_thumbprint','node_version','codex_root','codex_js_path','codex_js_sha256','package_json_path','package_json_sha256','package_name','package_version')){if([string]$actual.$field -cne [string]$ExpectedBinding.$field){throw 'CODEX_TRUST_POLICY_BINDING_DRIFT'}}
    $locks=@()
    try{
        foreach($path in @($actual.node_path,$actual.codex_js_path,$actual.package_json_path)){$locks+=,[System.IO.File]::Open([string]$path,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::Read)}
        if((Get-SeshatFileSha256 -Path $actual.node_path) -cne $actual.node_sha256 -or (Get-SeshatFileSha256 -Path $actual.codex_js_path) -cne $actual.codex_js_sha256 -or (Get-SeshatFileSha256 -Path $actual.package_json_path) -cne $actual.package_json_sha256){throw 'CODEX_TRUSTED_FILE_POST_LOCK_DRIFT'}
        return [pscustomobject]@{file_path=$actual.node_path;argv_prefix=@($actual.codex_js_path);launch_mode='PINNED_NPM_NODE_ENTRYPOINT';provenance=$actual;identity_locks=$locks}
    }catch{foreach($stream in $locks){$stream.Dispose()};throw}
}
function Close-SeshatCodexLaunch {
    param([object]$Launch)
    if($Launch -and $Launch.PSObject.Properties['identity_locks']){foreach($stream in @($Launch.identity_locks)){if($stream){$stream.Dispose()}}}
}
function Set-SeshatRunnerStart {
    param(
        [Parameter(Mandatory=$true)][object]$Job,
        [Parameter(Mandatory=$true)][int]$RunnerPid,
        [Parameter(Mandatory=$true)][string]$StartedUtc
    )
    # A deserialized PSCustomObject may lack the runtime-generated property.
    # Direct assignment under Set-StrictMode Latest failed before Codex ran.
    $Job|Add-Member -NotePropertyName runner_pid -NotePropertyValue $RunnerPid -Force
    $Job|Add-Member -NotePropertyName started_at_utc -NotePropertyValue $StartedUtc -Force
}
function Get-SeshatJobAuthorizationDigest {
    param([Parameter(Mandatory=$true)][object] $Job)
    $approved=(@($Job.approved_paths|ForEach-Object{[string]$_}|Sort-Object)-join ',')
    $bundle=(@($Job.ops_bundle|ForEach-Object{([string]$_.path)+'='+([string]$_.sha256)}|Sort-Object)-join ',')
    $launch=if($Job.PSObject.Properties['codex_launch_policy']){(@($Job.codex_launch_policy.PSObject.Properties|ForEach-Object{([string]$_.Name)+'='+([string]$_.Value)}|Sort-Object)-join ',')}else{''}
    $fields=@(
        [string]$Job.job_id,[string]$Job.issue_number,[string]$Job.branch,[string]$Job.base_branch,[string]$Job.base_sha,
        [string]$Job.after_pr,[string]$Job.accepted_reviewed_head_sha,[string]$Job.ops_pr,
        [string]$Job.ops_merge_sha,[string]$Job.issue_body_utf8_sha256,[string]$Job.dispatch_key,
        $approved,$bundle,$launch
    )
    return Get-SeshatUtf8Sha256 -Text ($fields -join "`n")
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
        if(-not $Job.PSObject.Properties['codex_launch_policy']){return 'BLOCK_CODEX_TRUST_POLICY_MISSING'}
        if([string]$Job.codex_launch_policy.policy_path -cne 'C:\ProgramData\SESHAT\codex-launch-policy.json' -or -not([string]$Job.codex_launch_policy.policy_sha256 -cmatch '^[0-9a-f]{64}$') -or [string]$Job.codex_launch_policy.package_name -cne '@openai/codex'){return 'BLOCK_CODEX_TRUST_POLICY_BINDING'}
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
    $ancestor=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList @('-C',$Repo,'merge-base','--is-ancestor',$OpsMergeSha,$BaseSha) -WorkingDirectory $Repo -Label 'bundle-ancestor'
    if($ancestor.exit_code -ne 0){throw 'OPS_MERGE_NOT_ANCESTOR_OF_BASE'}
    $reviewDiff=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList (@('-C',$Repo,'diff','--quiet',$OpsMergeSha,$BaseSha,'--')+$paths) -WorkingDirectory $Repo -Label 'bundle-reviewed-diff'
    if($reviewDiff.exit_code -ne 0){throw 'OPS_BUNDLE_CHANGED_AFTER_REVIEW'}
    $worktreeDiff=Invoke-SeshatNativeCommand -FilePath 'git' -ArgumentList (@('-C',$Repo,'diff','--quiet',$BaseSha,'--')+$paths) -WorkingDirectory $Repo -Label 'bundle-worktree-diff'
    if($worktreeDiff.exit_code -ne 0){throw 'OPS_BUNDLE_WORKTREE_DRIFT'}
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
