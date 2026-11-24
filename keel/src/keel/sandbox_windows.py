"""Genuine Windows OS enforcement for untrusted task processes.

This module is a drop-in Windows backend for ``keel.os_sandbox``.  It exposes
``capabilities()`` and ``run_confined(...)`` with the same signatures and
result type as that module (``ConfinementResult`` / ``SandboxUnavailable`` are
imported from there rather than redefined).

Mechanisms actually applied to the child process (all kernel-enforced):

* **Restricted primary token** — ``CreateRestrictedToken`` with
  ``DISABLE_MAX_PRIVILEGE | SANDBOX_INERT``, the Administrators SID converted
  to deny-only, and the Everyone SID installed as a *restricted* SID.  Every
  access check must then succeed for BOTH the normal token SIDs and the
  restricted SID.  The token is installed with ``CreateProcessAsUserW``; this
  works from a non-elevated token because the new token is derived from the
  caller's own token (no ``SeAssignPrimaryTokenPrivilege`` required).
* **Workspace-limited filesystem ACLs** — the workspace directory DACL is
  amended with an ALLOW ACE for the restricted SID.  Paths outside the
  workspace whose DACLs do not grant that SID are unreadable and unwritable.
  The original DACL is restored after the run.
* **Restricted handle inheritance** — stdout/stderr are redirected to files
  whose handles are the ONLY handles placed in a ``PROC_THREAD_ATTRIBUTE_HANDLE_LIST``
  passed via an extended startup info.  Even though ``bInheritHandles`` must be
  TRUE for those two handles, Windows restricts inheritance to exactly that
  list.  All other parent handles are non-inheritable (PEP 446).
* **Job Object** — ``KILL_ON_JOB_CLOSE``, a hard active-process limit, per-process
  and per-job CPU time limits, per-process and per-job commit limits, and no
  breakaway allowed.  The child is created SUSPENDED, assigned to the job, and
  only then resumed, so no descendant can be spawned before containment.  On
  timeout ``TerminateJobObject`` kills the whole tree.
* **Scrubbed environment** — secret-looking variables are removed and a minimal
  environment is built as a Unicode environment block.

Network boundary (non-elevated, kernel-enforced):

* **AppContainer with zero capabilities.**  ``allow_network=False`` creates a
  per-user AppContainer profile via ``userenv!CreateAppContainerProfile`` and
  starts the child with ``PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES`` and an
  empty capability set.  No ``SeImpersonatePrivilege`` /
  ``SeAssignPrimaryTokenPrivilege`` is needed: ``CreateProcessW`` succeeds for
  a normal user (HRESULT 0 / ERROR_SUCCESS).  ALE/WFP then denies outbound
  connects, DNS resolution and loopback traffic for that process and every
  descendant that inherits its token.  ``socket()`` itself still succeeds —
  AppContainer blocks traffic, not the Winsock API — which is stated in the
  returned ``limitations``.  The workspace DACL additionally grants the
  AppContainer SID, preserving the filesystem boundary.  If the AppContainer
  path cannot be established, ``run_confined`` **fails closed**.

What is NOT enforced, reported honestly (never claimed):

* **Per-process WFP filter rules.**  ``FwpmEngineOpen0`` succeeds for Everyone,
  but ``FwpmFilterAdd0`` returns ``ERROR_ACCESS_DENIED`` (5) from a
  non-elevated token even in a dynamic session, because the default BFE DACL
  grants ``FWPM_ACTRL_ADD`` only to Administrators / network configuration
  operators.  The network boundary therefore uses AppContainer instead.  Job
  Objects enforce neither filesystem nor network; they are resource/process
  boundaries only.
* **Executable dependencies.**  The target executable and every DLL it loads
  must be accessible to the restricted SID (Everyone).  Binaries under the
  user profile whose DACLs omit Everyone (a default python.org install is one)
  cannot start; the run then fails closed instead of falling back to an
  unrestricted launch.

Capability wiring (F4): the only command-bearing parameter is ``argv`` — a
non-empty ``list[str]`` whose first element is the executable.  There is no
``command``, ``cmd``, or ``shell_command`` string parameter and no shell is
interposed.  The lead should wire ``core.os.sandbox.run``'s ``p["argv"]``
(already done in ``capability_registry.py``) and must additionally forward
``env``, ``timeout_s``, ``cpu_s``, ``memory_mb`` and ``allow_network`` from the
capability params.  Authorization policy must run BEFORE this module is
called; OS confinement is the second layer, not a replacement for it.
"""

from __future__ import annotations

import ctypes
import os
import sys
import tempfile
import time
try:
    from ctypes import wintypes
except ImportError:  # pragma: no cover - ctypes.wintypes is Windows-only on some builds
    class _WintypesShim:
        HANDLE = ctypes.c_void_p
        DWORD = ctypes.c_uint32
        BOOL = ctypes.c_int
        WORD = ctypes.c_uint16

    wintypes = _WintypesShim()  # type: ignore[assignment]
from pathlib import Path

from keel import win_network
from keel.os_sandbox import ConfinementResult, SandboxUnavailable

IS_WINDOWS = os.name == "nt"

# --- Win32 constants -------------------------------------------------------
TOKEN_ALL_ACCESS = 0x000F01FF
DISABLE_MAX_PRIVILEGE = 0x0001
SANDBOX_INERT = 0x0002
SE_GROUP_USE_FOR_DENY_ONLY = 0x0010

SE_FILE_OBJECT = 1
SE_DACL_PRESENT = 0x0004
GRANT_ACCESS = 1
TRUSTEE_IS_SID = 0
GENERIC_ALL = 0x10000000

CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
STARTF_USESTDHANDLES = 0x00000100
HANDLE_FLAG_INHERIT = 0x00000001
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002

JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102

# S-1-1-0 (Everyone) is granted on System32 and other OS paths, which lets the
# loader start System32 binaries.  S-1-5-32-544 is the Administrators group.
EVERYONE_SID = "S-1-1-0"
ADMINISTRATORS_SID = "S-1-5-32-544"

MECHANISM = "windows-restricted-token+workspace-acl+job-object"
MECHANISM_NETWORK = "windows-appcontainer+workspace-acl+job-object"


def _network_limitation() -> str:
    """Fallback text used only when the AppContainer boundary is unavailable."""
    return (
        "BLOCKED: Windows network denial is NOT enforced on this host — the "
        "AppContainer profile/process path could not be established, and WFP "
        "per-process filter addition returns ERROR_ACCESS_DENIED (5) without "
        "elevation (no administrator firewall rule is applied). Job Objects "
        "do not filter network traffic."
    )


def _base_limitations() -> list[str]:
    return [
        "WFP per-process rules are BLOCKED without elevation: FwpmFilterAdd0 "
        "returns ERROR_ACCESS_DENIED (5); no administrator-configured firewall "
        "rule is applied. Job Objects do not filter network traffic.",
        "Filesystem denial relies on DACLs: paths that explicitly grant the "
        "restricted SID (Everyone) remain readable; this is a process-level "
        "boundary, not a VM.",
        "Job Object limits are CPU/memory/process-tree only; they do NOT "
        "enforce filesystem or network access.",
        "The target executable and all of its DLL dependencies must be "
        "accessible to the restricted SID, otherwise launch fails closed.",
        "F9/F16: Python audit hooks and fleet background shells are not OS "
        "confined by this module; they remain separate limitations.",
    ]


def _load_api():
    """Return (kernel32, advapi32) with argtypes configured, or (None, None)."""
    if not IS_WINDOWS:
        return None, None
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        a32 = ctypes.WinDLL("advapi32", use_last_error=True)

        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.GetCurrentProcess.argtypes = []
        k32.CreateProcessW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, ctypes.c_wchar_p,
            ctypes.POINTER(_StartupInfoExW), ctypes.POINTER(_ProcessInformation)]
        k32.CreateProcessW.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        k32.LocalFree.argtypes = [ctypes.c_void_p]
        k32.LocalFree.restype = ctypes.c_void_p
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.AssignProcessToJobObject.restype = wintypes.BOOL
        k32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.SetInformationJobObject.restype = wintypes.BOOL
        k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.TerminateJobObject.restype = wintypes.BOOL
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.GetExitCodeProcess.restype = wintypes.BOOL
        k32.ResumeThread.argtypes = [wintypes.HANDLE]
        k32.ResumeThread.restype = wintypes.DWORD
        k32.SetHandleInformation.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
        k32.SetHandleInformation.restype = wintypes.BOOL
        k32.InitializeProcThreadAttributeList.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t)]
        k32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
        k32.UpdateProcThreadAttribute.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
        k32.UpdateProcThreadAttribute.restype = wintypes.BOOL
        k32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]

        a32.OpenProcessToken.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        a32.OpenProcessToken.restype = wintypes.BOOL
        a32.CreateRestrictedToken.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
            ctypes.POINTER(wintypes.HANDLE)]
        a32.CreateRestrictedToken.restype = wintypes.BOOL
        a32.CreateProcessAsUserW.argtypes = [
            wintypes.HANDLE, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p,
            ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(_ProcessInformation)]
        a32.CreateProcessAsUserW.restype = wintypes.BOOL
        a32.ConvertStringSidToSidW.argtypes = [
            ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
        a32.ConvertStringSidToSidW.restype = wintypes.BOOL
        a32.GetNamedSecurityInfoW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p)]
        a32.GetNamedSecurityInfoW.restype = wintypes.DWORD
        a32.SetNamedSecurityInfoW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        a32.SetNamedSecurityInfoW.restype = wintypes.DWORD
        a32.SetEntriesInAclW.argtypes = [
            wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p)]
        a32.SetEntriesInAclW.restype = wintypes.DWORD
        a32.FreeSid.argtypes = [ctypes.c_void_p]
        a32.FreeSid.restype = ctypes.c_void_p
        return k32, a32
    except Exception as exc:  # pragma: no cover - diagnostic only
        if os.environ.get("KEEL_WIN_DEBUG"):
            print("sandbox_windows._load_api:", repr(exc))
        return None, None


# --- Win32 structures ------------------------------------------------------
class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _TrusteeW(ctypes.Structure):
    _fields_ = [
        ("pMultipleTrustee", ctypes.c_void_p),
        ("MultipleTrusteeOperation", ctypes.c_int),
        ("TrusteeForm", ctypes.c_int),
        ("TrusteeType", ctypes.c_int),
        ("ptstrName", ctypes.c_void_p),
    ]


class _ExplicitAccessW(ctypes.Structure):
    _fields_ = [
        ("grfAccessPermissions", wintypes.DWORD),
        ("grfAccessMode", ctypes.c_int),
        ("grfInheritance", wintypes.DWORD),
        ("Trustee", _TrusteeW),
    ]


class _StartupInfoW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", ctypes.c_wchar_p),
        ("lpDesktop", ctypes.c_wchar_p),
        ("lpTitle", ctypes.c_wchar_p),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _StartupInfoExW(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfoW), ("lpAttributeList", ctypes.c_void_p)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )
    ]


class _JobBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JobExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


# --- small helpers ---------------------------------------------------------
def _sid(a32, text: str) -> ctypes.c_void_p:
    p = ctypes.c_void_p()
    if not a32.ConvertStringSidToSidW(text, ctypes.byref(p)) or not p.value:
        raise SandboxUnavailable(f"ConvertStringSidToSidW({text}) failed: "
                                 f"{ctypes.get_last_error()}")
    return p


def _grant_sid_on_directory(a32, path: str | Path, sid: ctypes.c_void_p):
    """Add an ALLOW ACE for *sid* to the directory DACL.

    Returns ``(old_dacl, security_descriptor)``; the security descriptor must
    be freed with ``LocalFree`` only AFTER the old DACL has been restored.
    """
    old = ctypes.c_void_p()
    owner = ctypes.c_void_p()
    group = ctypes.c_void_p()
    sacl = ctypes.c_void_p()
    secdesc = ctypes.c_void_p()
    err = a32.GetNamedSecurityInfoW(
        str(path), SE_FILE_OBJECT, SE_DACL_PRESENT, ctypes.byref(owner),
        ctypes.byref(group), ctypes.byref(old), ctypes.byref(sacl),
        ctypes.byref(secdesc))
    if err != 0:
        raise SandboxUnavailable(f"GetNamedSecurityInfoW failed: {err}")
    ace = _ExplicitAccessW(
        GENERIC_ALL, GRANT_ACCESS, 0x3,
        _TrusteeW(None, 0, TRUSTEE_IS_SID, 0, ctypes.c_void_p(sid.value)))
    new = ctypes.c_void_p()
    err = a32.SetEntriesInAclW(1, ctypes.byref(ace), old, ctypes.byref(new))
    if err != 0:
        raise SandboxUnavailable(f"SetEntriesInAclW failed: {err}")
    err = a32.SetNamedSecurityInfoW(
        str(path), SE_FILE_OBJECT, SE_DACL_PRESENT, None, None, new, None)
    if err != 0:
        raise SandboxUnavailable(f"SetNamedSecurityInfoW failed: {err}")
    return old, secdesc


def _restore_dacl(a32, path: str | Path, old_dacl: ctypes.c_void_p):
    try:
        a32.SetNamedSecurityInfoW(
            str(path), SE_FILE_OBJECT, SE_DACL_PRESENT, None, None, old_dacl, None)
    except Exception:
        pass


def _make_restricted_token(k32, a32):
    token = wintypes.HANDLE()
    if not a32.OpenProcessToken(k32.GetCurrentProcess(), TOKEN_ALL_ACCESS,
                                ctypes.byref(token)):
        raise SandboxUnavailable("OpenProcessToken failed: "
                                 f"{ctypes.get_last_error()}")
    try:
        admins = _sid(a32, ADMINISTRATORS_SID)
        everyone = _sid(a32, EVERYONE_SID)
        disabled = (_SidAndAttributes * 1)(
            _SidAndAttributes(admins.value, SE_GROUP_USE_FOR_DENY_ONLY))
        restricted = (_SidAndAttributes * 1)(
            _SidAndAttributes(everyone.value, 0))
        restricted_token = wintypes.HANDLE()
        ok = a32.CreateRestrictedToken(
            token.value, DISABLE_MAX_PRIVILEGE | SANDBOX_INERT,
            1, ctypes.byref(disabled), 0, None,
            1, ctypes.byref(restricted), ctypes.byref(restricted_token))
        if not ok:
            raise SandboxUnavailable("CreateRestrictedToken failed: "
                                     f"{ctypes.get_last_error()}")
        return restricted_token.value
    finally:
        k32.CloseHandle(token)


def _job_limit_flags_for_test(cpu_s: int = 10) -> tuple[int, int]:
    """Return the LimitFlags and active-process limit used for a job.

    Exposed so tests can assert the configured boundaries without needing to
    observe the short-lived job object from outside ``run_confined``.
    """
    flags = (
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | JOB_OBJECT_LIMIT_PROCESS_TIME
        | JOB_OBJECT_LIMIT_JOB_TIME
        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | JOB_OBJECT_LIMIT_PROCESS_MEMORY
        | JOB_OBJECT_LIMIT_JOB_MEMORY
    )
    return flags, max(4, int(max(2, cpu_s)) + 2)


def _set_job_limits(k32, job, cpu_s: int, memory_mb: int,
                    max_processes: int):
    info = _JobExtendedLimitInformation()
    basic = info.BasicLimitInformation
    basic.LimitFlags = _job_limit_flags_for_test(cpu_s)[0]
    ticks = int(cpu_s) * 10_000_000  # 100 ns units
    basic.PerProcessUserTimeLimit = ticks
    basic.PerJobUserTimeLimit = ticks
    basic.ActiveProcessLimit = max_processes
    bytes_limit = int(memory_mb) * 1024 * 1024
    info.ProcessMemoryLimit = bytes_limit
    info.JobMemoryLimit = bytes_limit
    if not k32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation, ctypes.byref(info),
            ctypes.sizeof(info)):
        raise SandboxUnavailable("SetInformationJobObject failed: "
                                 f"{ctypes.get_last_error()}")


_SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD",
                 "CREDENTIAL", "KEEL_", "API_")
_ENV_ALLOW = (
    "SystemRoot", "SystemDrive", "PATH", "Path", "TEMP", "TMP", "TMPDIR",
    "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS", "OS",
    "PROCESSOR_ARCHITECTURE", "ComSpec",
)


def _scrub_env(env: dict[str, str] | None) -> dict[str, str]:
    source = dict(os.environ) if env is None else dict(env)
    out: dict[str, str] = {}
    for key, value in source.items():
        upper = key.upper()
        if any(hint in upper for hint in _SECRET_HINTS):
            continue
        if env is not None or key in _ENV_ALLOW:
            out[key] = value
    out.setdefault("SystemRoot", os.environ.get("SystemRoot", r"C:\Windows"))
    out.setdefault("TEMP", os.environ.get("TEMP", tempfile.gettempdir()))
    out.setdefault("TMP", out["TEMP"])
    return out


def _env_block(env: dict[str, str]):
    text = "\0".join(f"{k}={v}" for k, v in env.items()) + "\0\0"
    return ctypes.create_unicode_buffer(text)


def _scrub_env_for_appcontainer(env: dict[str, str] | None,
                                overrides: dict[str, str] | None = None
                                ) -> dict[str, str]:
    """Full environment minus secret-looking keys.

    AppContainer process creation fails with ERROR_ENVVAR_NOT_FOUND (203) when
    given the deliberately minimal ``_scrub_env`` allowlist; it needs the
    ordinary environment variables (USERPROFILE, APPDATA, ComSpec, ...).  Keep
    every variable except secret-looking ones, then apply workspace-scoped
    overrides.
    """
    source = dict(os.environ) if env is None else dict(env)
    out = {
        key: value for key, value in source.items()
        if not any(hint in key.upper() for hint in _SECRET_HINTS)
    }
    if overrides:
        out.update(overrides)
    out.setdefault("SystemRoot", os.environ.get("SystemRoot", r"C:\Windows"))
    return out


_APPCONTAINER_PROBE: bool | None = None
_WFP_STATUS: tuple[int, int] | None = None


def _probe_appcontainer() -> bool:
    """Launch a throwaway AppContainer child and check it really ran."""
    global _APPCONTAINER_PROBE
    if _APPCONTAINER_PROBE is not None:
        return _APPCONTAINER_PROBE
    result = False
    k32, a32 = _load_api()
    if k32 and a32:
        sid = None
        try:
            sid = win_network.appcontainer_sid()
            sc = win_network.security_capabilities(sid)
            size = ctypes.c_size_t(0)
            k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            if k32.InitializeProcThreadAttributeList(buffer, 1, 0,
                                                     ctypes.byref(size)):
                k32.UpdateProcThreadAttribute(
                    buffer, 0,
                    win_network.PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                    ctypes.byref(sc), ctypes.sizeof(sc), None, None)
                si = _StartupInfoExW()
                si.StartupInfo.cb = ctypes.sizeof(_StartupInfoExW)
                si.lpAttributeList = ctypes.cast(buffer, ctypes.c_void_p)
                pi = _ProcessInformation()
                comspec = os.environ.get("COMSPEC",
                                         r"C:\Windows\System32\cmd.exe")
                ok = k32.CreateProcessW(
                    comspec,
                    ctypes.create_unicode_buffer(
                        f'"{comspec}" /c exit 0'),
                    None, None, False, 0x00080000, None, None,
                    ctypes.byref(si), ctypes.byref(pi))
                if ok:
                    k32.WaitForSingleObject(pi.hProcess, 5000)
                    code = wintypes.DWORD()
                    result = bool(
                        k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
                        and code.value == 0)
                    k32.CloseHandle(pi.hThread)
                    k32.CloseHandle(pi.hProcess)
                k32.DeleteProcThreadAttributeList(buffer)
        except Exception:
            result = False
        finally:
            if sid:
                win_network.free_sid(sid)
    _APPCONTAINER_PROBE = result
    return result


def _make_handle_list(k32, handles: list[int],
                      extra_attributes: tuple[tuple[int, ctypes.c_void_p, int], ...] = ()
                      ):
    """Build an attribute list restricting inheritance to exactly *handles*.

    ``extra_attributes`` are ``(attribute_id, pointer, size)`` triples (used
    for the AppContainer SECURITY_CAPABILITIES attribute); the pointed-to
    objects must stay alive until CreateProcess returns.
    """
    count = 1 + len(extra_attributes)
    size = ctypes.c_size_t(0)
    k32.InitializeProcThreadAttributeList(None, count, 0, ctypes.byref(size))
    if size.value == 0:
        raise SandboxUnavailable("InitializeProcThreadAttributeList(size) failed")
    buf = ctypes.create_string_buffer(size.value)
    if not k32.InitializeProcThreadAttributeList(buf, count, 0, ctypes.byref(size)):
        raise SandboxUnavailable("InitializeProcThreadAttributeList failed")
    arr = (wintypes.HANDLE * len(handles))(*handles)
    if not k32.UpdateProcThreadAttribute(
            buf, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, ctypes.byref(arr),
            ctypes.sizeof(arr), None, None):
        k32.DeleteProcThreadAttributeList(buf)
        raise SandboxUnavailable(f"UpdateProcThreadAttribute failed: "
                                 f"{ctypes.get_last_error()}")
    for attribute_id, pointer, byte_size in extra_attributes:
        if not k32.UpdateProcThreadAttribute(
                buf, 0, attribute_id, pointer, byte_size, None, None):
            k32.DeleteProcThreadAttributeList(buf)
            raise SandboxUnavailable(
                f"UpdateProcThreadAttribute(0x{attribute_id:x}) failed: "
                f"{ctypes.get_last_error()}")
    # The attribute list stores raw pointers; keep them alive for as long as
    # the list is in use or process creation fails with ERROR_INVALID_PARAMETER.
    return buf, arr


# --- public API ------------------------------------------------------------
def capabilities() -> dict:
    """Report which Windows boundaries are genuinely available.

    ``network_enforcement`` is True only after a real AppContainer child has
    been launched successfully; it is never inferred from configuration.
    """
    k32, a32 = _load_api()
    token_ok = False
    job_ok = False
    acl_ok = False
    if k32 and a32:
        try:
            tok = _make_restricted_token(k32, a32)
            k32.CloseHandle(tok)
            token_ok = True
        except Exception:
            token_ok = False
        job = k32.CreateJobObjectW(None, None)
        if job:
            job_ok = True
            k32.CloseHandle(job)
        try:
            probe = Path(tempfile.mkdtemp(prefix="keel-acl-probe-"))
            sid = _sid(a32, EVERYONE_SID)
            _old, _sd = _grant_sid_on_directory(a32, probe, sid)
            acl_ok = True
            if _sd:
                k32.LocalFree(_sd)
        except Exception:
            acl_ok = False
        finally:
            try:
                import shutil
                shutil.rmtree(probe, ignore_errors=True)
            except Exception:
                pass
    global _WFP_STATUS
    app_ok = _probe_appcontainer() if (k32 and a32) else False
    if _WFP_STATUS is None:
        _WFP_STATUS = win_network.wfp_filter_add_status()
    wfp_add_error = _WFP_STATUS[1]
    fs = bool((token_ok or app_ok) and job_ok and acl_ok)
    limitations = _base_limitations()
    if not token_ok:
        limitations.append("BLOCKED: restricted primary token unavailable")
    if not job_ok:
        limitations.append("BLOCKED: Job Object unavailable")
    if not acl_ok:
        limitations.append("BLOCKED: filesystem ACL manipulation unavailable")
    if app_ok:
        limitations.append(
            "AppContainer (zero capabilities) denies outbound connects, DNS "
            "and loopback traffic for the child and its descendants. "
            "socket() creation itself is still allowed; AppContainer blocks "
            "network traffic, not the Winsock API.")
    else:
        limitations.append("BLOCKED: AppContainer network boundary unavailable; "
                           + _network_limitation())
    return {
        "os": sys.platform,
        "windows_restricted_token": token_ok,
        "windows_job_object": job_ok,
        "windows_workspace_acl": acl_ok,
        "windows_appcontainer": app_ok,
        "windows_restricted_handle_inheritance": bool(k32 and a32),
        "filesystem_enforcement": fs,
        "network_enforcement": bool(app_ok),
        "wfp_filter_add_error": wfp_add_error,  # live probe, see evidence
        "appcontainer_profile": win_network.APP_CONTAINER_PROFILE_NAME,
        "mechanism": MECHANISM_NETWORK if (app_ok and fs) else (
            MECHANISM if fs else "unavailable"),
        "limitations": limitations,
    }


def run_confined(argv: list[str], *, workspace: str | Path | None = None,
                 timeout_s: float = 15.0, cpu_s: int = 10,
                 memory_mb: int = 256, env: dict[str, str] | None = None,
                 allow_network: bool = False) -> ConfinementResult:
    """Run *argv* under genuine Windows OS restrictions, or fail closed.

    With the default ``allow_network=False`` the child is an AppContainer with
    no capabilities: outbound connects, DNS and loopback are denied by the
    kernel and inherited by descendants.  With ``allow_network=True`` the
    original restricted-token backend runs and the network is deliberately
    left open (stated in ``limitations``).  If either boundary cannot be
    established this raises ``SandboxUnavailable``; it never falls back to an
    unrestricted launch.
    """
    k32, a32 = _load_api()
    if not (k32 and a32):
        raise SandboxUnavailable("Windows OS enforcement unavailable on this host")
    if not argv or not isinstance(argv, (list, tuple)):
        raise SandboxUnavailable("argv must be a non-empty list")
    argv = [str(a) for a in argv]

    caps = capabilities()
    if not caps["filesystem_enforcement"]:
        raise SandboxUnavailable("Required Windows boundaries unavailable: "
                                 + "; ".join(caps["limitations"]))
    app_mode = not allow_network
    if app_mode and not caps["network_enforcement"]:
        raise SandboxUnavailable(
            "BLOCKED: " + _network_limitation()
            + " Network denial could not be applied; refusing to run.")

    ws = Path(workspace or tempfile.mkdtemp(prefix="keel-sandbox-")).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    limitations = list(caps["limitations"])
    if app_mode:
        limitations.append(
            "Network denied by AppContainer with zero capabilities; "
            "socket() creation remains permissible but all traffic is blocked.")
    else:
        limitations.append(
            "Network was explicitly enabled by the caller (allow_network=True); "
            "no network boundary was applied.")

    token = job = attr_list = attr_handles = None
    old_dacl = secdesc = ac_sid = sc = sc_ref = None
    io_dir = None
    out_fd = err_fd = -1
    pi = _ProcessInformation()
    child_started = False
    timed_out = False
    exit_code: int | None = None
    out_data = b""
    err_data = b""

    try:
        if app_mode:
            ac_sid = win_network.appcontainer_sid()
            restricted_sid = ac_sid
            sc = win_network.security_capabilities(ac_sid)
            sc_ref = ctypes.byref(sc)
        else:
            restricted_sid = _sid(a32, EVERYONE_SID)
        old_dacl, secdesc = _grant_sid_on_directory(a32, ws, restricted_sid)
        if not app_mode:
            token = _make_restricted_token(k32, a32)

        job = k32.CreateJobObjectW(None, None)
        if not job:
            raise SandboxUnavailable("CreateJobObjectW failed: "
                                     f"{ctypes.get_last_error()}")
        # ActiveProcessLimit bounds the whole tree; keep headroom for the
        # initial process plus a few children.
        _set_job_limits(k32, job, int(cpu_s), int(memory_mb),
                        _job_limit_flags_for_test(int(cpu_s))[1])

        io_dir = Path(tempfile.mkdtemp(prefix="keel-sandbox-io-"))
        out_path = io_dir / "stdout.txt"
        err_path = io_dir / "stderr.txt"
        out_fd = os.open(str(out_path), os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        err_fd = os.open(str(err_path), os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        import msvcrt
        h_out = msvcrt.get_osfhandle(out_fd)
        h_err = msvcrt.get_osfhandle(err_fd)
        for handle in (h_out, h_err):
            if not k32.SetHandleInformation(
                    handle, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT):
                raise SandboxUnavailable("SetHandleInformation failed: "
                                         f"{ctypes.get_last_error()}")

        extra = ()
        if app_mode:
            extra = ((win_network.PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                      sc_ref, ctypes.sizeof(sc)),)
        attr_list, attr_handles = _make_handle_list(
            k32, [h_out, h_err], extra_attributes=extra)
        si = _StartupInfoExW()
        si.StartupInfo.cb = ctypes.sizeof(_StartupInfoExW)
        si.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        si.StartupInfo.hStdOutput = h_out
        si.StartupInfo.hStdError = h_err
        si.lpAttributeList = ctypes.cast(attr_list, ctypes.c_void_p)

        if app_mode:
            # Full (scrubbed) environment: the minimal allowlist makes
            # AppContainer CreateProcessW fail with ERROR_ENVVAR_NOT_FOUND (203).
            env_block = _env_block(_scrub_env_for_appcontainer(
                env, {"TEMP": str(ws), "TMP": str(ws)}))
        else:
            env_block = _env_block(_scrub_env(env))
        cmdline = " ".join(_quote(a) for a in argv)
        flags = (CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT
                 | CREATE_SUSPENDED)
        if app_mode:
            launched = k32.CreateProcessW(
                None, ctypes.create_unicode_buffer(cmdline),
                None, None, True, flags, env_block, str(ws),
                ctypes.byref(si), ctypes.byref(pi))
            if not launched:
                raise SandboxUnavailable("CreateProcessW(AppContainer) failed: "
                                         f"{ctypes.get_last_error()}")
        else:
            if not a32.CreateProcessAsUserW(
                    token, None, ctypes.create_unicode_buffer(cmdline),
                    None, None, True, flags, env_block, str(ws),
                    ctypes.byref(si), ctypes.byref(pi)):
                raise SandboxUnavailable("CreateProcessAsUserW failed: "
                                         f"{ctypes.get_last_error()}")
        child_started = True

        if not k32.AssignProcessToJobObject(job, pi.hProcess):
            raise SandboxUnavailable("AssignProcessToJobObject failed: "
                                     f"{ctypes.get_last_error()}")
        k32.ResumeThread(pi.hThread)

        wait_ms = max(1, int(timeout_s * 1000))
        wait_result = k32.WaitForSingleObject(pi.hProcess, wait_ms)
        if wait_result == WAIT_TIMEOUT:
            timed_out = True
            k32.TerminateJobObject(job, 1)
            k32.WaitForSingleObject(pi.hProcess, 5000)
        code = wintypes.DWORD()
        if k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code)):
            exit_code = int(code.value)
        if out_fd >= 0:
            os.close(out_fd); out_fd = -1
        if err_fd >= 0:
            os.close(err_fd); err_fd = -1
        out_data = out_path.read_bytes()
        err_data = err_path.read_bytes()
    finally:
        if child_started and job:
            # KILL_ON_JOB_CLOSE plus an explicit terminate guarantees no
            # descendant survives the call, including on exceptions.
            k32.TerminateJobObject(job, 1)
            k32.WaitForSingleObject(pi.hProcess, 3000)
        for handle in (getattr(pi, "hThread", 0), getattr(pi, "hProcess", 0)):
            if handle:
                k32.CloseHandle(handle)
        if attr_list is not None:
            k32.DeleteProcThreadAttributeList(attr_list)
        if token:
            k32.CloseHandle(token)
        if ac_sid:
            win_network.free_sid(ac_sid)
        if job:
            k32.CloseHandle(job)
        if out_fd >= 0:
            os.close(out_fd)
        if err_fd >= 0:
            os.close(err_fd)
        if old_dacl is not None:
            _restore_dacl(a32, ws, old_dacl)
        if secdesc is not None:
            k32.LocalFree(secdesc)
        if io_dir is not None:
            import shutil
            shutil.rmtree(io_dir, ignore_errors=True)

    return ConfinementResult(
        ok=(not timed_out and exit_code == 0),
        exit_code=exit_code,
        timed_out=timed_out,
        elapsed_s=round(time.monotonic() - started, 3),
        mechanism=MECHANISM_NETWORK if app_mode else MECHANISM,
        stdout=out_data.decode("utf-8", errors="replace"),
        stderr=err_data.decode("utf-8", errors="replace"),
        limitations=limitations,
    )


def _quote(value: str) -> str:
    """Quote a single argument for a Windows command line.

    Embedded double quotes are doubled (``""``).  Unlike backslash escaping,
    this is understood both by CommandLineToArgvW (regular executables) and by
    cmd.exe's own parser (``/c`` command strings).
    """
    if value and not any(c in value for c in ' \t"'):
        return value
    return '"' + value.replace('"', '""') + '"'
