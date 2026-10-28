import re, collections
d = open(r"C:\Users\opsuc\Downloads\Forza Horizon 2 Convertor\ForzaToolsCli.exe", "rb").read()
print("size", len(d))
# .NET single-file bundle: find embedded assembly names (".dll" names near the bundle manifest)
names = sorted(set(m.group().decode() for m in re.finditer(rb"[A-Za-z0-9_.\-]{3,80}\.dll", d)))
own = [n for n in names if not re.match(r"(System|Microsoft|mscorlib|netstandard|WindowsBase|api-ms|clr|hostfxr|hostpolicy|coreclr|vcruntime|ucrt|msvcp|Presentation|Accessibility|DirectWrite|D3D|PenImc|wpfgfx|mscordaccore|mscordbi|createdump|Unity)", n)]
print("non-framework dlls:", own[:60])
kw = re.compile(r"(swizzl|tiling|tile ?mode|untile|HCXT|BCXT|swatch|texconv|xg|addrlib|Durango|vertex|VLay|VerB|Mesh|modelbin|carbin|materialbin|param|shader|stub|not implemented|NotImplemented|downgrad|convert|MatI|MATI|PrmS|LBTS|burG)", re.I)
c = collections.OrderedDict()
for m in re.finditer(rb"(?:[\x20-\x7e]\x00){6,200}", d):
    s = m.group().decode("utf-16le")
    if kw.search(s):
        c.setdefault(s, None)
for m in re.finditer(rb"[A-Za-z_][A-Za-z0-9_]{5,80}", d):
    s = m.group().decode()
    if kw.search(s) and not s.startswith(("System", "Microsoft", "get_", "set_")):
        c.setdefault(s, None)
items = list(c)
print("matches:", len(items))
for s in items[:400]:
    print(" ", s[:160])
