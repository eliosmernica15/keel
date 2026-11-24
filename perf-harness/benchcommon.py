"""Shared helpers for the read-only production performance harness."""
import ctypes
import ctypes.wintypes as w
import statistics
import sys
import time

SRC = r"C:\Users\Admin\.local\share\opencode\worktree\production\perf\keel\src"


def use_worktree():
    if SRC not in sys.path:
        sys.path.insert(0, SRC)


def percentile(values, p):
    """Linear-interpolation percentile (same method as numpy.percentile)."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def stats(values):
    if not values:
        return {}
    s = sorted(values)
    return {
        "n": len(s),
        "min": round(s[0], 4),
        "p50": round(percentile(s, 50), 4),
        "p90": round(percentile(s, 90), 4),
        "p95": round(percentile(s, 95), 4),
        "p99": round(percentile(s, 99), 4),
        "max": round(s[-1], 4),
        "mean": round(statistics.fmean(s), 4),
    }


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", w.DWORD), ("PageFaultCount", w.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_k32.GetCurrentProcess.restype = w.HANDLE
_psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(_PMC), w.DWORD]
_psapi.GetProcessMemoryInfo.restype = w.BOOL


def rss_bytes():
    pmc = _PMC(); pmc.cb = ctypes.sizeof(_PMC)
    ok = _psapi.GetProcessMemoryInfo(_k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    if not ok:
        return None
    return pmc.WorkingSetSize


def fmt_ms(v):
    return f"{v:.3f} ms" if v is not None else "n/a"
