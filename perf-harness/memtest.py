import ctypes, ctypes.wintypes as w

class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", w.DWORD),
        ("PageFaultCount", w.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_k32.GetCurrentProcess.restype = w.HANDLE
_psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(PMC), w.DWORD]
_psapi.GetProcessMemoryInfo.restype = w.BOOL

def rss():
    pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
    ok = _psapi.GetProcessMemoryInfo(_k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    if not ok:
        return None, ctypes.get_last_error()
    return (pmc.WorkingSetSize, pmc.PeakWorkingSetSize), 0

print("rss =", rss())
