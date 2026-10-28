using System.IO.Compression;
using System.Text;

namespace FH2ModStudio.Core;

/// <summary>
/// Reads the game's string tables (media\stripped\stringtables\&lt;LANG&gt;.zip, one LSB2 .str per database table) so
/// the app can show names ("Gallardo LP570-4 Superleggera") instead of string ids ("_&amp;3444639744"). A string id is
/// "_&amp;n" with n = (table hash &lt;&lt; 16) | key; only the key is needed inside one table.
/// LSB2: u32 @12 = offset of section 0; there u32 size, u32 count, (count + 1) x (u16 key, u32 offset in UTF-16
/// units), then the UTF-16 pool of NUL-terminated strings (fh3port\strtables.py has the full description).
/// </summary>
public static class StringTables
{
    public static Dictionary<int, string> Load(string mediaDir, string table, string lang = "EN")
    {
        var result = new Dictionary<int, string>();
        try
        {
            var zip = Path.Combine(mediaDir, "stripped", "stringtables", lang + ".zip");
            if (!File.Exists(zip)) return result;
            using var archive = ZipFile.OpenRead(zip);
            var entry = archive.Entries.FirstOrDefault(e => e.Name.Equals(table + ".str", StringComparison.OrdinalIgnoreCase));
            if (entry == null) return result;
            using var ms = new MemoryStream();
            using (var s = entry.Open()) s.CopyTo(ms);
            var d = ms.ToArray();
            if (d.Length < 24 || Encoding.ASCII.GetString(d, 0, 4) != "LSB2") return result;
            int sec = BitConverter.ToInt32(d, 12);
            int count = BitConverter.ToInt32(d, sec + 4);
            int pool = sec + 8 + 6 * (count + 1);
            for (int i = 0; i < count; i++)
            {
                int e = sec + 8 + 6 * i;
                int key = BitConverter.ToUInt16(d, e);
                int start = pool + 2 * BitConverter.ToInt32(d, e + 2);
                int end = start;
                while (end + 1 < d.Length && (d[end] | d[end + 1]) != 0) end += 2;
                result[key] = Encoding.Unicode.GetString(d, start, end - start);
            }
        }
        catch (Exception e) when (e is IOException or InvalidDataException or ArgumentException or UnauthorizedAccessException) { }
        return result;
    }

    /// <summary>"_&amp;n" -> the table's text, plain text as it is (ported cars may hold plain names), else null.</summary>
    public static string? Text(Dictionary<int, string> table, string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        if (!value.StartsWith("_&", StringComparison.Ordinal)) return value;
        return long.TryParse(value[2..], out var n) && table.TryGetValue((int)(n & 0xFFFF), out var s) && s.Length > 0 ? s : null;
    }
}
