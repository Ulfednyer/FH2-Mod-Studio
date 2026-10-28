// fh2sql.dll - runs SQL against Forza Horizon 2's live gamedb using the game's own SQLite 3.6.19.
// Inject into the game process; talk to it over \\.\pipe\fh2sql (frames: u32 little-endian length + UTF-8).
#include <windows.h>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <share.h>
#include <cstring>
#include <string>

namespace {

// Addresses are RVAs against the image's preferred base 0x140000000 (forza_durango_release_final.exe).
constexpr uintptr_t RVA_g_pApp = 0x354F4F8;
constexpr uintptr_t RVA_prepare_v2 = 0x3D710;
constexpr uintptr_t RVA_step = 0x1EEE0;
constexpr uintptr_t RVA_finalize = 0x1AB40;
constexpr uintptr_t RVA_column_count = 0x203B0;
constexpr uintptr_t RVA_column_name = 0x20840;
constexpr uintptr_t RVA_column_type = 0x20800;
constexpr uintptr_t RVA_column_text = 0x206E0;
constexpr uintptr_t RVA_errmsg = 0x7D3F0;
constexpr uintptr_t RVA_marker = 0x1FF97E8;
// AppCommandLineParameters (static at 0x1434AF7D0) + 0x2608: {u32 aaSampleCount, u32 aaQuality}, default {4, 0},
// read once by CForza::vf0B when the renderer's render targets are created.
constexpr uintptr_t RVA_aaSampleCount = 0x34B1DD8;
const char kMarker[] = "game:\\Media\\Stripped\\gamedbRC.slt";

constexpr size_t kAppDatabase = 0x40;  // App -> Database::CDatabase*
constexpr size_t kDbHandle = 0x10;     // CDatabase -> sqlite3*
constexpr size_t kDbLock = 0x18;       // CDatabase -> CRITICAL_SECTION taken by CDatabase::Execute
constexpr int kMaxRows = 100000;
constexpr uint32_t kMaxRequest = 16u << 20;
const wchar_t kPipeName[] = L"\\\\.\\pipe\\fh2sql";
// drift suspension steering ([drift] in fh2sql.ini; live: pipe request "#drift <lock> <speed>"), see DriftLoad
float g_driftLock = 60.0f, g_driftSpeed = 1.5f;

constexpr int SQLITE_NULL = 5, SQLITE_ROW = 100, SQLITE_DONE = 101;

using prepare_t = int (*)(void*, const char*, int, void**, const char**);
using stmt_fn_t = int (*)(void*);
using col_str_t = const char* (*)(void*, int);
using col_int_t = int (*)(void*, int);
using errmsg_t = const char* (*)(void*);

struct Api {
    uintptr_t base = 0;
    prepare_t prepare;
    stmt_fn_t step, finalize, column_count;
    col_str_t column_name, column_text;
    col_int_t column_type;
    errmsg_t errmsg;
} g;

bool Readable(uintptr_t p, size_t n) {
    MEMORY_BASIC_INFORMATION mbi;
    if (!VirtualQuery(reinterpret_cast<void*>(p), &mbi, sizeof mbi) || mbi.State != MEM_COMMIT) return false;
    if (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return false;
    return p + n <= reinterpret_cast<uintptr_t>(mbi.BaseAddress) + mbi.RegionSize;
}

bool IsGameImage(uintptr_t base) {
    if (!Readable(base, sizeof(IMAGE_DOS_HEADER)) || reinterpret_cast<IMAGE_DOS_HEADER*>(base)->e_magic != IMAGE_DOS_SIGNATURE)
        return false;
    uintptr_t marker = base + RVA_marker;
    return Readable(marker, sizeof kMarker) && memcmp(reinterpret_cast<void*>(marker), kMarker, sizeof kMarker) == 0;
}

// The translation layer may map the exe somewhere other than a normal module, so fall back to a memory scan.
uintptr_t FindGameImage() {
    if (auto m = GetModuleHandleW(L"forza_durango_release_final.exe"); m && IsGameImage(reinterpret_cast<uintptr_t>(m)))
        return reinterpret_cast<uintptr_t>(m);
    if (IsGameImage(0x140000000)) return 0x140000000;
    MEMORY_BASIC_INFORMATION mbi;
    for (uintptr_t p = 0x10000; p < 0x7FFFFFFF0000ull && VirtualQuery(reinterpret_cast<void*>(p), &mbi, sizeof mbi);
         p = reinterpret_cast<uintptr_t>(mbi.BaseAddress) + mbi.RegionSize) {
        if (mbi.State == MEM_COMMIT && mbi.BaseAddress == mbi.AllocationBase && IsGameImage(p)) return p;
    }
    return 0;
}

bool EnsureApi() {
    if (g.base) return true;
    uintptr_t b = FindGameImage();
    if (!b) return false;
    g.prepare = reinterpret_cast<prepare_t>(b + RVA_prepare_v2);
    g.step = reinterpret_cast<stmt_fn_t>(b + RVA_step);
    g.finalize = reinterpret_cast<stmt_fn_t>(b + RVA_finalize);
    g.column_count = reinterpret_cast<stmt_fn_t>(b + RVA_column_count);
    g.column_name = reinterpret_cast<col_str_t>(b + RVA_column_name);
    g.column_text = reinterpret_cast<col_str_t>(b + RVA_column_text);
    g.column_type = reinterpret_cast<col_int_t>(b + RVA_column_type);
    g.errmsg = reinterpret_cast<errmsg_t>(b + RVA_errmsg);
    g.base = b;
    return true;
}

void AppendJsonString(std::string& out, const char* s) {
    out += '"';
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(s); *p; ++p) {
        switch (*p) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (*p < 0x20) {
                    char buf[8];
                    snprintf(buf, sizeof buf, "\\u%04x", *p);
                    out += buf;
                } else {
                    out += static_cast<char>(*p);
                }
        }
    }
    out += '"';
}

std::string ErrorJson(const char* msg) {
    std::string out = "{\"results\":[],\"error\":";
    AppendJsonString(out, msg);
    return out + "}";
}

struct Target {
    void* app;
    uint8_t* cdb;
    void* db;
};

const char* ResolveTarget(Target& t) {
    if (!EnsureApi()) return "game image not found in this process (wrong process, or game still loading)";
    t.app = *reinterpret_cast<void**>(g.base + RVA_g_pApp);
    if (!t.app) return "App not created yet";
    t.cdb = *reinterpret_cast<uint8_t**>(static_cast<uint8_t*>(t.app) + kAppDatabase);
    if (!t.cdb) return "gamedb not opened yet";
    t.db = *reinterpret_cast<void**>(t.cdb + kDbHandle);
    return t.db ? nullptr : "sqlite3 handle is null";
}

std::string Info() {
    Target t{};
    const char* err = ResolveTarget(t);
    char buf[256];
    snprintf(buf, sizeof buf, "image=%p App=%p CDatabase=%p sqlite3=%p%s%s", reinterpret_cast<void*>(g.base), t.app,
             t.cdb, t.db, err ? " | " : "", err ? err : "");
    std::string out = "{\"results\":[],\"error\":null,\"info\":";
    AppendJsonString(out, buf);
    return out + "}";
}

struct Job {
    const std::string* sql;
    std::string* out;
    CRITICAL_SECTION* held;
};

void RunSqlImpl(Job* job) {
    const std::string& sql = *job->sql;
    std::string& out = *job->out;
    Target t{};
    if (const char* err = ResolveTarget(t)) {
        out = ErrorJson(err);
        return;
    }

    out = "{\"results\":[";
    std::string error;
    auto* lock = reinterpret_cast<CRITICAL_SECTION*>(t.cdb + kDbLock);
    EnterCriticalSection(lock);
    job->held = lock;
    bool firstBlock = true;
    for (const char* p = sql.c_str(); p && *p;) {
        void* stmt = nullptr;
        const char* tail = nullptr;
        if (g.prepare(t.db, p, -1, &stmt, &tail) != 0) {
            error = g.errmsg(t.db);
            break;
        }
        p = tail;
        if (!stmt) continue;  // whitespace or comment only

        int cols = g.column_count(stmt);
        out += firstBlock ? "{\"columns\":[" : ",{\"columns\":[";
        firstBlock = false;
        for (int c = 0; c < cols; ++c) {
            if (c) out += ',';
            const char* name = g.column_name(stmt, c);
            AppendJsonString(out, name ? name : "");
        }
        out += "],\"rows\":[";
        int rows = 0, rc;
        bool truncated = false;
        while ((rc = g.step(stmt)) == SQLITE_ROW) {
            if (rows == kMaxRows) {
                truncated = true;
                break;
            }
            out += rows++ ? ",[" : "[";
            for (int c = 0; c < cols; ++c) {
                if (c) out += ',';
                const char* v = g.column_type(stmt, c) == SQLITE_NULL ? nullptr : g.column_text(stmt, c);
                if (v) AppendJsonString(out, v);
                else out += "null";
            }
            out += ']';
        }
        out += "],\"truncated\":";
        out += truncated ? "true}" : "false}";
        if (rc != SQLITE_ROW && rc != SQLITE_DONE) error = g.errmsg(t.db);
        g.finalize(stmt);
        if (!error.empty()) break;
    }
    job->held = nullptr;
    LeaveCriticalSection(lock);

    out += "],\"error\":";
    if (error.empty()) out += "null";
    else AppendJsonString(out, error.c_str());
    out += "}";
}

// A fault inside the game's SQLite must not take the game down or leave its db lock held.
bool RunSqlGuarded(Job* job) {
    __try {
        RunSqlImpl(job);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        if (job->held) LeaveCriticalSection(job->held);
        return false;
    }
}

std::string RunSql(const std::string& sql) {
    std::string out;
    Job job{&sql, &out, nullptr};
    return RunSqlGuarded(&job) ? out : ErrorJson("access violation while running the query (caught; game left running)");
}

bool ReadExact(HANDLE h, void* buf, DWORD n) {
    for (DWORD got = 0, r; got < n; got += r)
        if (!ReadFile(h, static_cast<char*>(buf) + got, n - got, &r, nullptr) || r == 0) return false;
    return true;
}

bool WriteFrame(HANDLE h, const std::string& s) {
    uint32_t len = static_cast<uint32_t>(s.size());
    DWORD w;
    return WriteFile(h, &len, 4, &w, nullptr) && WriteFile(h, s.data(), len, &w, nullptr) && w == len;
}

DWORD WINAPI ServeClient(void* param) {
    HANDLE pipe = param;
    uint32_t len;
    while (ReadExact(pipe, &len, 4) && len <= kMaxRequest) {
        std::string req(len, '\0');
        if (len && !ReadExact(pipe, &req[0], len)) break;
        std::string resp;
        float lock, speed;
        if (req == "!info") {
            resp = Info();
        } else if (sscanf_s(req.c_str(), "#drift %f %f", &lock, &speed) == 2) {
            g_driftLock = lock;    // used for the next car the game builds
            g_driftSpeed = speed;
            char buf[96];
            sprintf_s(buf, "{\"drift\":{\"lock\":%g,\"speed\":%g}}", lock, speed);
            resp = buf;
        } else {
            resp = RunSql(req);
        }
        if (!WriteFrame(pipe, resp)) break;
    }
    DisconnectNamedPipe(pipe);
    CloseHandle(pipe);
    return 0;
}

DWORD WINAPI PipeServer(void*) {
    for (;;) {
        HANDLE pipe = CreateNamedPipeW(kPipeName, PIPE_ACCESS_DUPLEX,
                                       PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
                                       PIPE_UNLIMITED_INSTANCES, 1 << 20, 1 << 20, 0, nullptr);
        if (pipe == INVALID_HANDLE_VALUE) {
            Sleep(1000);
            continue;
        }
        HANDLE worker = nullptr;
        if (ConnectNamedPipe(pipe, nullptr) || GetLastError() == ERROR_PIPE_CONNECTED)
            worker = CreateThread(nullptr, 0, ServeClient, pipe, 0, nullptr);
        if (worker) {
            CloseHandle(worker);
        } else {
            DisconnectNamedPipe(pipe);
            CloseHandle(pipe);
        }
    }
}

int ReadMsaaSetting(HMODULE self) {
    wchar_t path[MAX_PATH];
    DWORD n = GetModuleFileNameW(self, path, MAX_PATH);
    wchar_t* slash = n ? wcsrchr(path, L'\\') : nullptr;
    if (!slash) return 0;
    wcscpy_s(slash + 1, MAX_PATH - (slash + 1 - path), L"fh2sql.ini");
    return static_cast<int>(GetPrivateProfileIntW(L"render", L"msaa", 0, path));
}

// Inject into azimuth.exe before starting the game: waits for the game's startup code to store the default
// {4, 0} and replaces the sample count before the renderer reads it. Data-only, so the exe hash is untouched.
DWORD WINAPI MsaaWatcher(void* param) {
    const uint32_t want = static_cast<uint32_t>(reinterpret_cast<uintptr_t>(param));
    for (unsigned i = 0;; ++i) {
        uintptr_t base = IsGameImage(0x140000000) ? 0x140000000 : (i % 100 == 0 ? FindGameImage() : 0);
        if (base) {
            uintptr_t addr = base + RVA_aaSampleCount;
            if (Readable(addr, 8)) {
                auto* field = reinterpret_cast<volatile uint32_t*>(addr);
                if (field[0] == 4 && field[1] == 0) {
                    field[0] = want;
                    return 0;
                }
                if (field[0] != 0) return 0;  // already changed by someone else: leave it
            }
        }
        Sleep(1);
    }
}

// Per-camera MotionBlurAmount globals (.data), read every frame by each camera's GetMotionBlurAmount.
struct BlurSetting {
    const wchar_t* key;
    uintptr_t rva;
    float value;
};
BlurSetting g_blur[] = {
    {L"blur_driver", 0x2E77558, -1.0f},
    {L"blur_hood", 0x2E77504, -1.0f},
    {L"blur_bumper", 0x2E774E4, -1.0f},
};

bool ReadBlurSettings(HMODULE self) {
    wchar_t path[MAX_PATH];
    DWORD n = GetModuleFileNameW(self, path, MAX_PATH);
    wchar_t* slash = n ? wcsrchr(path, L'\\') : nullptr;
    if (!slash) return false;
    wcscpy_s(slash + 1, MAX_PATH - (slash + 1 - path), L"fh2sql.ini");
    bool any = false;
    for (auto& b : g_blur) {
        wchar_t buf[32];
        GetPrivateProfileStringW(L"render", b.key, L"", buf, 32, path);
        if (buf[0]) {
            b.value = static_cast<float>(_wtof(buf));
            any = any || b.value >= 0.0f;
        }
    }
    return any;
}

// Re-applies the configured blur amounts every second (overrides `fh2sql.py blur set` for configured cameras).
DWORD WINAPI BlurKeeper(void*) {
    for (;;) {
        Sleep(1000);
        if (!IsGameImage(0x140000000)) continue;
        for (const auto& b : g_blur) {
            if (b.value < 0.0f) continue;
            uintptr_t addr = 0x140000000 + b.rva;
            if (!Readable(addr, 4)) continue;
            auto* p = reinterpret_cast<volatile float*>(addr);
            if (*p != b.value) *p = b.value;
        }
    }
}

// ───────────── file-system hooks: added files for the game ─────────────
// Swaps the game's import slots for kernelx file functions (memory only; the exe on disk is untouched). A call log
// is written to fh2sql_fs.log when a file "fh2sql_fslog.enable" sits next to the DLL.

constexpr uintptr_t RVA_IAT_CreateFile2 = 0x1DD1148;
constexpr uintptr_t RVA_IAT_CreateFileA = 0x1DD11B0;
constexpr uintptr_t RVA_IAT_CreateFileW = 0x1DD10C8;
constexpr uintptr_t RVA_IAT_FindFirstFileExA = 0x1DD1120;
constexpr uintptr_t RVA_IAT_GetFileAttributesExA = 0x1DD0F28;
constexpr uintptr_t RVA_IAT_GetFileAttributesExW = 0x1DD0FD8;

using CreateFile2_t = HANDLE(WINAPI*)(LPCWSTR, DWORD, DWORD, DWORD, void*);
using CreateFileA_t = HANDLE(WINAPI*)(LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
using CreateFileW_t = HANDLE(WINAPI*)(LPCWSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
using FindFirstFileExA_t = HANDLE(WINAPI*)(LPCSTR, FINDEX_INFO_LEVELS, LPVOID, FINDEX_SEARCH_OPS, LPVOID, DWORD);
using GetFileAttributesExA_t = BOOL(WINAPI*)(LPCSTR, GET_FILEEX_INFO_LEVELS, LPVOID);
using GetFileAttributesExW_t = BOOL(WINAPI*)(LPCWSTR, GET_FILEEX_INFO_LEVELS, LPVOID);

struct FsOrig {
    CreateFile2_t CreateFile2;
    CreateFileA_t CreateFileA;
    CreateFileW_t CreateFileW;
    FindFirstFileExA_t FindFirstFileExA;
    GetFileAttributesExA_t GetFileAttributesExA;
    GetFileAttributesExW_t GetFileAttributesExW;
} g_fs{};

CRITICAL_SECTION g_fsLogLock;
FILE* g_fsLog = nullptr;

void FsLog(const char* fmt, ...) {
    if (!g_fsLog) return;
    EnterCriticalSection(&g_fsLogLock);
    fprintf(g_fsLog, "%lu ", GetTickCount());
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_fsLog, fmt, ap);
    va_end(ap);
    fputc('\n', g_fsLog);
    fflush(g_fsLog);
    LeaveCriticalSection(&g_fsLogLock);
}

std::string HandlePath(HANDLE h) {
    if (h == INVALID_HANDLE_VALUE || !h) return "-";
    wchar_t buf[1024];
    DWORD n = GetFinalPathNameByHandleW(h, buf, 1024, 0);
    if (!n || n >= 1024) {
        char e[32];
        snprintf(e, sizeof e, "(no path, err %lu, type %lu)", GetLastError(), GetFileType(h));
        return e;
    }
    char out[2048];
    WideCharToMultiByte(CP_UTF8, 0, buf, -1, out, sizeof out, nullptr, nullptr);
    return out;
}

std::string Utf8(LPCWSTR w) {
    if (!w) return "(null)";
    char out[2048];
    WideCharToMultiByte(CP_UTF8, 0, w, -1, out, sizeof out, nullptr, nullptr);
    return out;
}

// ── new files for the game ──
// The game only knows files listed in Mount\hash.manifest, and Azimuth refuses to start when that file differs
// from the original. So the original stays on disk and the game is handed <game folder>\FH3Port\hash.manifest
// (original + records for added files) when it opens it. Files Azimuth refuses to open (not in the package) are
// opened straight from Mount.

CRITICAL_SECTION g_mountLock;
std::wstring g_mount;  // "\\?\C:\...\Mount\" learned from the first file Azimuth opens for the game

std::wstring GameRel(LPCWSTR name) {
    if (!name) return {};
    if ((name[0] == L'g' || name[0] == L'G') && name[1] == L':' && name[2] == L'\\') return name + 3;
    if (name[0] == L'.' && name[1] == L'\\') return name + 2;
    return {};
}

std::wstring Widen(LPCSTR s) {
    if (!s) return {};
    wchar_t buf[1024];
    int n = MultiByteToWideChar(CP_ACP, 0, s, -1, buf, 1024);
    return n ? std::wstring(buf) : std::wstring();
}

void LearnMount(HANDLE h, const std::wstring& rel) {
    if (h == INVALID_HANDLE_VALUE || rel.empty()) return;
    EnterCriticalSection(&g_mountLock);
    if (g_mount.empty()) {
        wchar_t buf[1024];
        DWORD n = GetFinalPathNameByHandleW(h, buf, 1024, 0);
        if (n && n < 1024 && n > rel.size() && _wcsicmp(buf + n - rel.size(), rel.c_str()) == 0) {
            g_mount.assign(buf, n - rel.size());
            FsLog("game folder: %s", Utf8(g_mount.c_str()).c_str());
        }
    }
    LeaveCriticalSection(&g_mountLock);
}

std::wstring MountPath() {
    EnterCriticalSection(&g_mountLock);
    std::wstring m = g_mount;
    LeaveCriticalSection(&g_mountLock);
    return m;
}

// <game folder>\FH3Port\hash.manifest, i.e. next to Mount
std::wstring OverrideManifest() {
    std::wstring m = MountPath();
    if (m.size() < 7) return {};
    size_t cut = m.find_last_of(L'\\', m.size() - 2);
    return cut == std::wstring::npos ? std::wstring() : m.substr(0, cut + 1) + L"FH3Port\\hash.manifest";
}

bool IsNotFound(DWORD e) { return e == ERROR_FILE_NOT_FOUND || e == ERROR_PATH_NOT_FOUND; }

HANDLE WINAPI HookCreateFile2(LPCWSTR name, DWORD access, DWORD share, DWORD disp, void* ext) {
    HANDLE h = g_fs.CreateFile2(name, access, share, disp, ext);
    DWORD err = GetLastError();
    std::wstring rel = GameRel(name);
    LearnMount(h, rel);
    const char* how = "";
    if (h != INVALID_HANDLE_VALUE && !rel.empty() && _wcsicmp(rel.c_str(), L"hash.manifest") == 0 && !(access & GENERIC_WRITE)) {
        std::wstring ov = OverrideManifest();
        if (!ov.empty() && GetFileAttributesW(ov.c_str()) != INVALID_FILE_ATTRIBUTES) {
            HANDLE h2 = ::CreateFile2(ov.c_str(), access, share, disp, static_cast<LPCREATEFILE2_EXTENDED_PARAMETERS>(ext));
            if (h2 != INVALID_HANDLE_VALUE) {
                CloseHandle(h);
                h = h2;
                err = 0;
                how = " [extended hash.manifest]";
            }
        }
    } else if (h == INVALID_HANDLE_VALUE && IsNotFound(err) && !rel.empty() && disp == OPEN_EXISTING) {
        std::wstring m = MountPath();
        if (!m.empty()) {
            HANDLE h2 = ::CreateFile2((m + rel).c_str(), access, share, disp, static_cast<LPCREATEFILE2_EXTENDED_PARAMETERS>(ext));
            if (h2 != INVALID_HANDLE_VALUE) {
                h = h2;
                err = 0;
                how = " [opened from Mount]";
            }
        }
    }
    FsLog("CreateFile2 \"%s\" acc=%lx disp=%lu -> %p err=%lu real=%s%s", Utf8(name).c_str(), access, disp, h,
          h == INVALID_HANDLE_VALUE ? err : 0, HandlePath(h).c_str(), how);
    SetLastError(err);
    return h;
}

HANDLE WINAPI HookCreateFileA(LPCSTR name, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES sa, DWORD disp, DWORD flags, HANDLE tmpl) {
    HANDLE h = g_fs.CreateFileA(name, access, share, sa, disp, flags, tmpl);
    DWORD err = GetLastError();
    FsLog("CreateFileA \"%s\" -> %p err=%lu real=%s", name ? name : "(null)", h, h == INVALID_HANDLE_VALUE ? err : 0, HandlePath(h).c_str());
    SetLastError(err);
    return h;
}

HANDLE WINAPI HookCreateFileW(LPCWSTR name, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES sa, DWORD disp, DWORD flags, HANDLE tmpl) {
    HANDLE h = g_fs.CreateFileW(name, access, share, sa, disp, flags, tmpl);
    DWORD err = GetLastError();
    FsLog("CreateFileW \"%s\" -> %p err=%lu real=%s", Utf8(name).c_str(), h, h == INVALID_HANDLE_VALUE ? err : 0, HandlePath(h).c_str());
    SetLastError(err);
    return h;
}

HANDLE WINAPI HookFindFirstFileExA(LPCSTR name, FINDEX_INFO_LEVELS lvl, LPVOID data, FINDEX_SEARCH_OPS op, LPVOID filter, DWORD flags) {
    HANDLE h = g_fs.FindFirstFileExA(name, lvl, data, op, filter, flags);
    DWORD err = GetLastError();
    FsLog("FindFirstFileExA \"%s\" -> %p err=%lu first=\"%s\"", name ? name : "(null)", h, h == INVALID_HANDLE_VALUE ? err : 0,
          h != INVALID_HANDLE_VALUE && data ? static_cast<WIN32_FIND_DATAA*>(data)->cFileName : "");
    SetLastError(err);
    return h;
}

// Existence checks for files Azimuth doesn't know: answer from Mount on disk.
BOOL AttributesFromMount(const std::wstring& rel, GET_FILEEX_INFO_LEVELS lvl, LPVOID info) {
    std::wstring m = MountPath();
    return !m.empty() && !rel.empty() && ::GetFileAttributesExW((m + rel).c_str(), lvl, info);
}

BOOL WINAPI HookGetFileAttributesExA(LPCSTR name, GET_FILEEX_INFO_LEVELS lvl, LPVOID info) {
    BOOL ok = g_fs.GetFileAttributesExA(name, lvl, info);
    DWORD err = GetLastError();
    const char* how = "";
    if (!ok && IsNotFound(err) && AttributesFromMount(GameRel(Widen(name).c_str()), lvl, info)) {
        ok = TRUE;
        err = 0;
        how = " [from Mount]";
    }
    FsLog("GetFileAttributesExA \"%s\" -> %d err=%lu%s", name ? name : "(null)", ok, ok ? 0 : err, how);
    SetLastError(err);
    return ok;
}

BOOL WINAPI HookGetFileAttributesExW(LPCWSTR name, GET_FILEEX_INFO_LEVELS lvl, LPVOID info) {
    BOOL ok = g_fs.GetFileAttributesExW(name, lvl, info);
    DWORD err = GetLastError();
    const char* how = "";
    if (!ok && IsNotFound(err) && AttributesFromMount(GameRel(name), lvl, info)) {
        ok = TRUE;
        err = 0;
        how = " [from Mount]";
    }
    FsLog("GetFileAttributesExW \"%s\" -> %d err=%lu%s", Utf8(name).c_str(), ok, ok ? 0 : err, how);
    SetLastError(err);
    return ok;
}

// ───────────── drift suspension steering ─────────────
// FH2 reads steering lock per car: sub_1410622C0 copies Data_Car.Steer* (degrees, unconverted) to car+0x5C
// {MaxAngle, MaxAngleFiltered, VelTurning, VelStraighten, Countersteer, DynFindPeak, ...}. FM7 gives its drift suspension
// 60 degrees and 1.5x steering speeds instead. The car builder sub_141056210 calls that loader at 0x141056DE3
// (E8 -> sub_141061070) after it has loaded every installed upgrade; its frame (rbp set once: lea rbp,[rax-0DA8h])
// holds the installed upgrade ids at rbp+0x928, SpringDamper is slot 5 (upgrade registry order). The call is pointed at a
// stub next to the image (mov r9, rbp; jmp DriftLoad); DriftLoad runs the loader and, when the installed suspension is
// FH2 Mod Studio's drift suspension (Id % 1000 == 905, DriftDragPack), applies [drift] steer_lock / steer_speed from
// fh2sql.ini (default 60 / 1.5; steer_lock=0 turns it off; pipe "#drift <lock> <speed>" sets them live). Memory only - the exe on disk is untouched.
constexpr uintptr_t RVA_CallSteerLoad = 0x1056DE3, RVA_SteerLoad = 0x1061070;
constexpr size_t kUpgradeIds = 0x928, kSpringSlot = 5, kSteer = 0x5C;
constexpr int kDriftMarker = 905;
using SteerLoad_t = int64_t (*)(int64_t, void*, void*);
SteerLoad_t g_steerLoad;

int64_t DriftLoad(int64_t car, void* row, void* db, uintptr_t frame) {
    int64_t r = g_steerLoad(car, row, db);
    uintptr_t idp = frame + kUpgradeIds + 4 * kSpringSlot;
    auto* s = reinterpret_cast<float*>(car + kSteer);
    if (Readable(idp, 4) && Readable(reinterpret_cast<uintptr_t>(s), 6 * sizeof(float))) {
        int id = *reinterpret_cast<int*>(idp);
        if (id >= 0 && id % 1000 == kDriftMarker && g_driftLock > 0.0f) {
            s[0] = g_driftLock;
            s[1] = g_driftLock;
            for (int i = 2; i < 6; ++i) s[i] *= g_driftSpeed;
            FsLog("drift steering: suspension %d -> lock %.0f", id, s[0]);
        }
    }
    return r;
}

void ReadDriftSettings(HMODULE self) {
    wchar_t path[MAX_PATH];
    DWORD n = GetModuleFileNameW(self, path, MAX_PATH);
    wchar_t* slash = n ? wcsrchr(path, L'\\') : nullptr;
    if (!slash) return;
    wcscpy_s(slash + 1, MAX_PATH - (slash + 1 - path), L"fh2sql.ini");
    wchar_t buf[32];
    GetPrivateProfileStringW(L"drift", L"steer_lock", L"60", buf, 32, path);
    g_driftLock = static_cast<float>(_wtof(buf));
    GetPrivateProfileStringW(L"drift", L"steer_speed", L"1.5", buf, 32, path);
    g_driftSpeed = static_cast<float>(_wtof(buf));
}

// Executable memory within +-2 GB of target (an E8 call reaches only that far).
void* AllocNear(uintptr_t target) {
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    const uintptr_t step = si.dwAllocationGranularity;
    for (uintptr_t d = step; d < 0x70000000; d += step) {
        for (uintptr_t a : {(target - d) & ~(step - 1), (target + d) & ~(step - 1)}) {
            if (void* p = VirtualAlloc(reinterpret_cast<void*>(a), 0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE))
                return p;
        }
    }
    return nullptr;
}

DWORD WINAPI DriftHookInstaller(void*) {
    constexpr uintptr_t base = 0x140000000;
    for (unsigned i = 0; i < 600000; ++i) {  // up to ~10 minutes, like the file hooks
        if (IsGameImage(base) && Readable(base + RVA_CallSteerLoad, 5)) {
            auto* call = reinterpret_cast<uint8_t*>(base + RVA_CallSteerLoad);
            int32_t rel;
            memcpy(&rel, call + 1, 4);
            if (call[0] != 0xE8 || base + RVA_CallSteerLoad + 5 + rel != base + RVA_SteerLoad) {
                FsLog("drift steering: unexpected code at the loader call, not hooked");
                return 0;
            }
            auto* stub = static_cast<uint8_t*>(AllocNear(base + RVA_CallSteerLoad));
            if (!stub) {
                FsLog("drift steering: no memory near the game image");
                return 0;
            }
            // mov r9, rbp ; jmp qword ptr [rip+0] ; dq DriftLoad
            const uint8_t code[] = {0x49, 0x89, 0xE9, 0xFF, 0x25, 0, 0, 0, 0};
            memcpy(stub, code, sizeof code);
            auto target = reinterpret_cast<uintptr_t>(&DriftLoad);
            memcpy(stub + sizeof code, &target, 8);
            FlushInstructionCache(GetCurrentProcess(), stub, sizeof code + 8);
            g_steerLoad = reinterpret_cast<SteerLoad_t>(base + RVA_SteerLoad);
            int32_t newRel = static_cast<int32_t>(reinterpret_cast<intptr_t>(stub) - static_cast<intptr_t>(base + RVA_CallSteerLoad + 5));
            DWORD old;
            if (!VirtualProtect(call, 5, PAGE_EXECUTE_READWRITE, &old)) {
                FsLog("drift steering: could not unprotect the loader call");
                return 0;
            }
            InterlockedExchange(reinterpret_cast<volatile LONG*>(call + 1), newRel);
            VirtualProtect(call, 5, old, &old);
            FlushInstructionCache(GetCurrentProcess(), call, 5);
            FsLog("drift steering hook installed after %u polls (lock %.0f, speed x%.2f)", i, g_driftLock, g_driftSpeed);
            return 0;
        }
        Sleep(1);
    }
    return 0;
}

// Replaces one import slot once the loader has filled it (non-null, pointing outside the game image).
bool SwapSlot(uintptr_t base, uintptr_t rva, void* hook, void** orig) {
    auto* slot = reinterpret_cast<void**>(base + rva);
    if (!Readable(reinterpret_cast<uintptr_t>(slot), 8)) return false;
    void* cur = *slot;
    auto c = reinterpret_cast<uintptr_t>(cur);
    // unresolved slots hold 0 or a small name-table RVA; resolved ones point into Azimuth's code
    if (c < 0x10000000 || (c >= base && c < base + 0x4000000)) return false;
    DWORD old;
    if (!VirtualProtect(slot, 8, PAGE_READWRITE, &old)) return false;
    *orig = cur;
    *slot = hook;
    VirtualProtect(slot, 8, old, &old);
    return true;
}

DWORD WINAPI FsHookInstaller(void*) {
    struct Item { uintptr_t rva; void* hook; void** orig; bool done; } items[] = {
        {RVA_IAT_CreateFile2, reinterpret_cast<void*>(HookCreateFile2), reinterpret_cast<void**>(&g_fs.CreateFile2), false},
        {RVA_IAT_CreateFileA, reinterpret_cast<void*>(HookCreateFileA), reinterpret_cast<void**>(&g_fs.CreateFileA), false},
        {RVA_IAT_CreateFileW, reinterpret_cast<void*>(HookCreateFileW), reinterpret_cast<void**>(&g_fs.CreateFileW), false},
        {RVA_IAT_FindFirstFileExA, reinterpret_cast<void*>(HookFindFirstFileExA), reinterpret_cast<void**>(&g_fs.FindFirstFileExA), false},
        {RVA_IAT_GetFileAttributesExA, reinterpret_cast<void*>(HookGetFileAttributesExA), reinterpret_cast<void**>(&g_fs.GetFileAttributesExA), false},
        {RVA_IAT_GetFileAttributesExW, reinterpret_cast<void*>(HookGetFileAttributesExW), reinterpret_cast<void**>(&g_fs.GetFileAttributesExW), false},
    };
    for (unsigned i = 0; i < 600000; ++i) {  // up to ~10 minutes
        if (IsGameImage(0x140000000)) {
            int left = 0;
            for (auto& it : items) {
                if (!it.done) it.done = SwapSlot(0x140000000, it.rva, it.hook, it.orig);
                left += !it.done;
            }
            if (!left) {
                FsLog("hooks installed after %u polls", i);
                return 0;
            }
        }
        Sleep(1);
    }
    FsLog("gave up waiting for the game's imports");
    return 0;
}

bool OpenFsLog(HMODULE self) {
    wchar_t path[MAX_PATH];
    DWORD n = GetModuleFileNameW(self, path, MAX_PATH);
    wchar_t* slash = n ? wcsrchr(path, L'\\') : nullptr;
    if (!slash) return false;
    wcscpy_s(slash + 1, MAX_PATH - (slash + 1 - path), L"fh2sql_fslog.enable");
    if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return false;
    wcscpy_s(slash + 1, MAX_PATH - (slash + 1 - path), L"fh2sql_fs.log");
    g_fsLog = _wfsopen(path, L"a", _SH_DENYNO);
    return g_fsLog != nullptr;
}

}  // namespace

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        // file hooks always (they make added files visible); the call log only with fh2sql_fslog.enable
        InitializeCriticalSection(&g_fsLogLock);
        InitializeCriticalSection(&g_mountLock);
        if (OpenFsLog(module)) FsLog("fh2sql loaded, pid %lu", GetCurrentProcessId());
        if (HANDLE t = CreateThread(nullptr, 0, FsHookInstaller, nullptr, 0, nullptr)) CloseHandle(t);
        if (HANDLE t = CreateThread(nullptr, 0, PipeServer, nullptr, 0, nullptr)) CloseHandle(t);
        ReadDriftSettings(module);   // steer_lock=0 leaves steering alone; the hook stays so it can be enabled live
        if (HANDLE t = CreateThread(nullptr, 0, DriftHookInstaller, nullptr, 0, nullptr)) CloseHandle(t);
        if (ReadBlurSettings(module)) {
            if (HANDLE t = CreateThread(nullptr, 0, BlurKeeper, nullptr, 0, nullptr)) CloseHandle(t);
        }
        int msaa = ReadMsaaSetting(module);
        if (msaa == 1 || msaa == 2 || msaa == 8) {
            if (HANDLE t = CreateThread(nullptr, 0, MsaaWatcher, reinterpret_cast<void*>(static_cast<uintptr_t>(msaa)), 0, nullptr))
                CloseHandle(t);
        }
    }
    return TRUE;
}
