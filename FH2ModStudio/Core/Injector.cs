using System.IO.Pipes;
using System.Text;
using static FH2ModStudio.Core.Native;

namespace FH2ModStudio.Core;

/// <summary>Loads fh2sql.dll into the Azimuth process (LoadLibraryW via a remote thread).</summary>
public static class Injector
{
    public const string PipeName = "fh2sql";

    public static bool IsDllLoaded()
    {
        try
        {
            using var client = new NamedPipeClientStream(".", PipeName, PipeDirection.InOut);
            client.Connect(150);
            return true;
        }
        catch
        {
            return false;
        }
    }

    /// <returns>null on success, otherwise a user-facing error message.</returns>
    public static string? Inject(int pid, string dllPath)
    {
        if (!File.Exists(dllPath)) return $"fh2sql.dll not found at {dllPath}";
        var process = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, false, pid);
        if (process == IntPtr.Zero) return "Windows refused access to the game process. Try running FH2 Mod Studio as administrator.";
        try
        {
            var path = Encoding.Unicode.GetBytes(dllPath + "\0");
            var remote = VirtualAllocEx(process, IntPtr.Zero, (IntPtr)path.Length, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
            if (remote == IntPtr.Zero) return "Could not allocate memory in the game process.";
            try
            {
                WriteProcessMemory(process, remote, path, (IntPtr)path.Length, out _);
                var loadLibrary = GetProcAddress(GetModuleHandleW("kernel32.dll"), "LoadLibraryW");
                var thread = CreateRemoteThread(process, IntPtr.Zero, IntPtr.Zero, loadLibrary, remote, 0, out _);
                if (thread == IntPtr.Zero) return "Could not start the loader thread in the game process.";
                WaitForSingleObject(thread, 15000);
                GetExitCodeThread(thread, out var module);
                CloseHandle(thread);
                return module == 0 ? "The game process could not load fh2sql.dll." : null;
            }
            finally
            {
                VirtualFreeEx(process, remote, IntPtr.Zero, MEM_RELEASE);
            }
        }
        finally
        {
            CloseHandle(process);
        }
    }
}
