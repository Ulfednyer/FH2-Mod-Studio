using System.Runtime.InteropServices;

namespace FH2ModStudio.Core;

internal static class Native
{
    public const uint PROCESS_CREATE_THREAD = 0x0002, PROCESS_VM_OPERATION = 0x0008, PROCESS_VM_READ = 0x0010,
        PROCESS_VM_WRITE = 0x0020, PROCESS_QUERY_INFORMATION = 0x0400;
    public const uint MEM_COMMIT = 0x1000, MEM_RESERVE = 0x2000, MEM_RELEASE = 0x8000, MEM_PRIVATE = 0x20000;
    public const uint PAGE_READWRITE = 0x04, PAGE_EXECUTE_READWRITE = 0x40;

    [StructLayout(LayoutKind.Sequential)]
    public struct MEMORY_BASIC_INFORMATION
    {
        public IntPtr BaseAddress;
        public IntPtr AllocationBase;
        public uint AllocationProtect;
        public uint Alignment1;
        public IntPtr RegionSize;
        public uint State;
        public uint Protect;
        public uint Type;
        public uint Alignment2;
    }

    [DllImport("kernel32", SetLastError = true)]
    public static extern IntPtr OpenProcess(uint access, bool inherit, int pid);

    [DllImport("kernel32", SetLastError = true)]
    public static extern bool CloseHandle(IntPtr handle);

    [DllImport("kernel32", SetLastError = true)]
    public static extern bool ReadProcessMemory(IntPtr process, IntPtr address, byte[] buffer, IntPtr size, out IntPtr read);

    [DllImport("kernel32", SetLastError = true)]
    public static extern bool WriteProcessMemory(IntPtr process, IntPtr address, byte[] buffer, IntPtr size, out IntPtr written);

    [DllImport("kernel32", SetLastError = true)]
    public static extern IntPtr VirtualQueryEx(IntPtr process, IntPtr address, out MEMORY_BASIC_INFORMATION info, IntPtr length);

    [DllImport("kernel32", SetLastError = true)]
    public static extern IntPtr VirtualAllocEx(IntPtr process, IntPtr address, IntPtr size, uint type, uint protect);

    [DllImport("kernel32", SetLastError = true)]
    public static extern bool VirtualFreeEx(IntPtr process, IntPtr address, IntPtr size, uint type);

    [DllImport("kernel32", SetLastError = true)]
    public static extern IntPtr CreateRemoteThread(IntPtr process, IntPtr attributes, IntPtr stackSize, IntPtr start,
        IntPtr parameter, uint flags, out uint threadId);

    [DllImport("kernel32", SetLastError = true)]
    public static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);

    [DllImport("kernel32", SetLastError = true)]
    public static extern bool GetExitCodeThread(IntPtr thread, out uint code);

    [DllImport("kernel32", CharSet = CharSet.Unicode)]
    public static extern IntPtr GetModuleHandleW(string name);

    [DllImport("kernel32", CharSet = CharSet.Ansi, ExactSpelling = true)]
    public static extern IntPtr GetProcAddress(IntPtr module, string name);
}
