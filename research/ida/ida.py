"""ida.py list | ida.py <tool> '<json args>' | ida.py <tool> @args.json  -- calls the IDA MCP server."""
import json, sys, urllib.request

URL = "http://127.0.0.1:13337/mcp"


def rpc(method, params=None):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    raw = urllib.request.urlopen(req, timeout=600).read().decode("utf-8", "replace")
    if raw.lstrip().startswith("event:") or raw.lstrip().startswith("data:"):
        raw = [l[5:] for l in raw.splitlines() if l.startswith("data:")][-1]
    msg = json.loads(raw)
    if "error" in msg:
        sys.exit("ERROR: " + json.dumps(msg["error"]))
    return msg["result"]


sys.stdout.reconfigure(encoding="utf-8")
if sys.argv[1] == "list":
    for t in rpc("tools/list")["tools"]:
        props = ", ".join(t.get("inputSchema", {}).get("properties", {}))
        print(f"{t['name']}({props}): {(t.get('description') or '').splitlines()[0][:110] if t.get('description') else ''}")
else:
    a = sys.argv[2] if len(sys.argv) > 2 else "{}"
    if sys.argv[1] == "py":
        name, args = "py_exec_file", {"file_path": __import__("os").path.abspath(a)}
    else:
        name = sys.argv[1]
        args = json.load(open(a[1:], encoding="utf-8")) if a.startswith("@") else json.loads(a)
    res = rpc("tools/call", {"name": name, "arguments": args})
    for c in res.get("content", []):
        print(c.get("text", c))
    if res.get("isError"):
        sys.exit(1)
