using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using static FH2ModStudio.Core.Native;

namespace FH2ModStudio.Core;

public enum GameState { NotRunning, Launcher, InGame }

/// <summary>Read/write access to the Azimuth process hosting Forza Horizon 2 (image at 0x140000000).</summary>
public sealed class GameProcess : IDisposable
{
    public const string ProcessName = "azimuth";
    private const long MarkerAddress = 0x141FF97E8;
    private static readonly byte[] Marker = Encoding.ASCII.GetBytes("game:\\Media\\Stripped\\gamedbRC.slt");

    private readonly Process _process;
    private IntPtr _handle;

    public int Pid { get; }
    public string? ExePath { get; }

    private GameProcess(Process process, IntPtr handle)
    {
        _process = process;
        _handle = handle;
        Pid = process.Id;
        try { ExePath = process.MainModule?.FileName; } catch { ExePath = null; }
    }

    public static Process? FindProcess() => Process.GetProcessesByName(ProcessName).FirstOrDefault();

    public static GameProcess? TryOpen()
    {
        var p = FindProcess();
        if (p == null) return null;
        var h = OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION, false, p.Id);
        return h == IntPtr.Zero ? null : new GameProcess(p, h);
    }

    public bool HasExited
    {
        get { try { return _process.HasExited; } catch { return true; } }
    }

    public bool IsGameLoaded => Read(MarkerAddress, Marker.Length) is { } b && b.AsSpan().SequenceEqual(Marker);

    public byte[]? Read(long address, int size)
    {
        var buf = new byte[size];
        if (!ReadProcessMemory(_handle, (IntPtr)address, buf, (IntPtr)size, out var got) || (int)got != size) return null;
        return buf;
    }

    public bool Write(long address, byte[] data) =>
        WriteProcessMemory(_handle, (IntPtr)address, data, (IntPtr)data.Length, out var written) && (int)written == data.Length;

    public long? ReadInt64(long address) => Read(address, 8) is { } b ? BitConverter.ToInt64(b) : null;
    public float? ReadFloat(long address) => Read(address, 4) is { } b ? BitConverter.ToSingle(b) : null;
    public int? ReadInt32(long address) => Read(address, 4) is { } b ? BitConverter.ToInt32(b) : null;
    public bool WriteFloat(long address, float value) => Write(address, BitConverter.GetBytes(value));
    public bool WriteInt32(long address, int value) => Write(address, BitConverter.GetBytes(value));

    /// <summary>Finds 8-byte aligned qwords equal to any needle in committed private read/write memory.</summary>
    public Dictionary<long, List<long>> ScanForPointers(IReadOnlyCollection<long> needles, CancellationToken token = default)
    {
        var found = needles.ToDictionary(n => n, _ => new List<long>());
        long min = needles.Min(), max = needles.Max();
        const int chunk = 64 << 20;
        var buffer = new byte[chunk];
        long address = 0;
        while (!token.IsCancellationRequested &&
               VirtualQueryEx(_handle, (IntPtr)address, out var mbi, (IntPtr)Marshal.SizeOf<MEMORY_BASIC_INFORMATION>()) != IntPtr.Zero)
        {
            long regionBase = (long)mbi.BaseAddress, regionSize = (long)mbi.RegionSize;
            if (mbi.State == MEM_COMMIT && mbi.Type == MEM_PRIVATE && (mbi.Protect == PAGE_READWRITE || mbi.Protect == PAGE_EXECUTE_READWRITE))
            {
                for (long off = 0; off < regionSize; off += chunk)
                {
                    int size = (int)Math.Min(chunk, regionSize - off);
                    if (!ReadProcessMemory(_handle, (IntPtr)(regionBase + off), buffer, (IntPtr)size, out var got)) continue;
                    var qwords = MemoryMarshal.Cast<byte, long>(buffer.AsSpan(0, (int)got & ~7));
                    for (int i = 0; i < qwords.Length; i++)
                    {
                        long v = qwords[i];
                        if (v < min || v > max) continue;
                        if (found.TryGetValue(v, out var list)) list.Add(regionBase + off + i * 8L);
                    }
                }
            }
            address = regionBase + regionSize;
        }
        return found;
    }

    public void Dispose()
    {
        if (_handle != IntPtr.Zero) CloseHandle(_handle);
        _handle = IntPtr.Zero;
    }
}
