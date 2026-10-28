using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;

var path = args[0];
using var fs = File.OpenRead(path);
using var pe = new PEReader(fs);
var md = pe.GetMetadataReader();
foreach (var th in md.TypeDefinitions)
{
    var t = md.GetTypeDefinition(th);
    var ns = md.GetString(t.Namespace);
    var name = md.GetString(t.Name);
    var methods = t.GetMethods().Select(mh =>
    {
        var m = md.GetMethodDefinition(mh);
        int size = m.RelativeVirtualAddress == 0 ? 0 : pe.GetMethodBody(m.RelativeVirtualAddress).Size;
        return $"{md.GetString(m.Name)}[{size}]";
    });
    var fields = t.GetFields().Select(fh => md.GetString(md.GetFieldDefinition(fh).Name));
    Console.WriteLine($"TYPE {ns}.{name}");
    Console.WriteLine("   methods: " + string.Join(", ", methods));
    var f = string.Join(", ", fields);
    if (f.Length > 0) Console.WriteLine("   fields: " + (f.Length > 600 ? f[..600] + "..." : f));
}
Console.WriteLine("== user strings");
var h = MetadataTokens.UserStringHandle(1);
int off = 1;
int heapSize = md.GetHeapSize(HeapIndex.UserString);
while (off < heapSize)
{
    var us = MetadataTokens.UserStringHandle(off);
    var s = md.GetUserString(us);
    if (s.Length > 0) Console.WriteLine("US " + s.Replace("\n", "\\n"));
    var next = md.GetNextHandle(us);
    if (next.IsNil) break;
    off = MetadataTokens.GetHeapOffset(next);
}
