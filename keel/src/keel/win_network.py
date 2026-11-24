"""Non-elevated Windows AppContainer network isolation (ctypes only).

An AppContainer process is created with a *derived app package SID* and **no**
capabilities.  Windows then treats the process as an unpackaged AppContainer:
WFP/ALE denies outbound connects, DNS/name resolution and loopback traffic,
and the filesystem is restricted to locations granted to that SID (plus the
ALL APPLICATION PACKAGES SIDs that ship in the OS DACLs).

Empirically verified on Windows 10 1809 AMD64, Python 3.11.9, non-elevated
(IsUserAnAdmin() == 0), see ``master-plan-v6-win-network-evidence.md``:

* ``userenv!CreateAppContainerProfile`` succeeds (HRESULT 0) for a normal user
  and returns an ``S-1-15-2-...`` SID; the profile is per-user and needs no
  elevation.  If it already exists (HRESULT 0x800700B7), the SID is recovered
  with ``userenv!DeriveAppContainerSidFromAppContainerName``.
* ``CreateProcessW`` + ``PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES`` with
  that SID and zero capabilities succeeds with ``ERROR_SUCCESS``.
* A capability-less AppContainer child cannot connect outbound, resolve DNS or
  connect to 127.0.0.1, while an otherwise identical non-AppContainer control
  can do all three.  Children it spawns inherit the same token and are denied.
* By contrast, per-process WFP filters cannot be installed non-elevated:
  ``FwpmFilterAdd0`` returns ``ERROR_ACCESS_DENIED (5)`` even from a dynamic
  session, because the default BFE DACL grants FWPM_ACTRL_ADD only to
  Administrators / network configuration operators.

The AppContainer profile is intentionally left in place: deleting it while a
confined process still holds a token derived from it would race.  It is a
small per-user profile (a directory under ``%LOCALAPPDATA%\\Packages`` plus a
registry key), keyed by the stable name below.
"""

from __future__ import annotations

import ctypes
import os

try:
    from ctypes import wintypes
except ImportError:  # pragma: no cover - non-Windows import hygiene
    class _WintypesShim:  # type: ignore[no-redef]
        HANDLE = ctypes.c_void_p
        DWORD = ctypes.c_uint32
        BOOL = ctypes.c_int
        UINT = ctypes.c_uint32

    wintypes = _WintypesShim()  # type: ignore[assignment]

IS_WINDOWS = os.name == "nt"

APP_CONTAINER_PROFILE_NAME = "Keel.Sandbox.NetworkDeny.v1"

# winbase.h PROC_THREAD_ATTRIBUTE_NUMBER(0x0009) | INPUT(0x00020000)
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009

HRESULT_ALREADY_EXISTS = 0x800700B7  # HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS)


class NetworkIsolationUnavailable(RuntimeError):
    """Raised when an AppContainer boundary cannot be established."""


class _CapabilityAndAttributes(ctypes.Structure):
    _fields_ = [("CapabilitySid", ctypes.c_void_p),
                ("Attributes", wintypes.DWORD)]


class SecurityCapabilities(ctypes.Structure):
    """SECURITY_CAPABILITIES from winnt.h; no capabilities == default deny."""

    _fields_ = [("AppContainerSid", ctypes.c_void_p),
                ("Capabilities", ctypes.POINTER(_CapabilityAndAttributes)),
                ("CapabilityCount", wintypes.DWORD),
                ("Reserved", wintypes.DWORD)]


def security_capabilities(sid: ctypes.c_void_p) -> SecurityCapabilities:
    """Return a capability-less SECURITY_CAPABILITIES for *sid*."""
    if not sid:
        raise NetworkIsolationUnavailable("null AppContainer SID")
    return SecurityCapabilities(sid, None, 0, 0)


def _apis():
    if not IS_WINDOWS:
        return None, None, None
    try:
        userenv = ctypes.WinDLL("userenv", use_last_error=True)
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        userenv.CreateAppContainerProfile.argtypes = [
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        userenv.CreateAppContainerProfile.restype = ctypes.c_long
        userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [
            ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
        userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long

        advapi32.FreeSid.argtypes = [ctypes.c_void_p]
        advapi32.FreeSid.restype = ctypes.c_void_p
        advapi32.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
        advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        return userenv, advapi32, kernel32
    except Exception as exc:  # pragma: no cover - diagnostic only
        if os.environ.get("KEEL_WIN_DEBUG"):
            print("win_network._apis:", repr(exc))
        return None, None, None


def sid_to_string(sid: ctypes.c_void_p) -> str:
    """Human-readable SID for evidence / diagnostics (empty string on error)."""
    _ue, advapi32, kernel32 = _apis()
    if not (advapi32 and sid):
        return ""
    text = ctypes.c_wchar_p()
    if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        return ""
    value = text.value or ""
    kernel32.LocalFree(text)
    return value


def free_sid(sid: ctypes.c_void_p) -> None:
    if not sid:
        return
    _ue, advapi32, _k32 = _apis()
    if advapi32:
        advapi32.FreeSid(sid)


def appcontainer_sid(profile_name: str = APP_CONTAINER_PROFILE_NAME,
                     ) -> ctypes.c_void_p:
    """Create (or reuse) an AppContainer profile and return its SID.

    Caller owns the SID and must release it with :func:`free_sid` after the
    child process has been created.  No elevation is required.
    """
    userenv, advapi32, _kernel32 = _apis()
    if not (userenv and advapi32):
        raise NetworkIsolationUnavailable(
            "userenv/advapi32 AppContainer APIs unavailable")

    sid = ctypes.c_void_p()
    hr = userenv.CreateAppContainerProfile(
        profile_name, profile_name, "Keel network-denied sandbox",
        None, 0, ctypes.byref(sid))
    if hr == 0 and sid.value:
        return sid
    if hr < 0:
        hr &= 0xFFFFFFFF
    if hr != HRESULT_ALREADY_EXISTS:
        raise NetworkIsolationUnavailable(
            f"CreateAppContainerProfile failed: HRESULT 0x{hr:08x}")

    # Profile already exists: derive the same SID instead of replacing it.
    sid = ctypes.c_void_p()
    hr = userenv.DeriveAppContainerSidFromAppContainerName(
        profile_name, ctypes.byref(sid))
    if hr < 0:
        hr &= 0xFFFFFFFF
    if hr != 0 or not sid.value:
        raise NetworkIsolationUnavailable(
            f"DeriveAppContainerSidFromAppContainerName failed: "
            f"HRESULT 0x{hr:08x}")
    return sid


# --- evidence helper: WFP per-process filter permission probe ---------------
class _Guid(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


class _FwpValue0(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("value", ctypes.c_uint64)]


class _FwpmDisplayData0(ctypes.Structure):
    _fields_ = [("name", ctypes.c_wchar_p), ("description", ctypes.c_wchar_p)]


class _FwpByteBlob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.c_void_p)]


class _FwpmAction0(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("filterType", _Guid)]


class _FwpmSession0(ctypes.Structure):
    _fields_ = [("sessionKey", _Guid), ("displayData", _FwpmDisplayData0),
                ("flags", ctypes.c_uint32), ("txnWaitTimeoutInMSec", ctypes.c_uint32),
                ("processId", wintypes.DWORD), ("sid", ctypes.c_void_p),
                ("username", ctypes.c_wchar_p), ("kernelMode", wintypes.BOOL)]


class _FwpmFilter0(ctypes.Structure):
    _fields_ = [("filterKey", _Guid), ("displayData", _FwpmDisplayData0),
                ("flags", ctypes.c_uint32), ("providerKey", ctypes.c_void_p),
                ("providerData", _FwpByteBlob), ("layerKey", _Guid),
                ("subLayerKey", _Guid), ("weight", _FwpValue0),
                ("numFilterConditions", ctypes.c_uint32),
                ("filterCondition", ctypes.c_void_p),
                ("action", _FwpmAction0), ("rawContext", ctypes.c_uint64),
                ("reserved", ctypes.c_void_p), ("filterId", ctypes.c_uint64),
                ("effectiveWeight", _FwpValue0)]


def wfp_filter_add_status() -> tuple[int, int]:
    """Return ``(engine_open_rc, filter_add_rc)`` from a live WFP probe.

    The probe uses a dynamic session and a harmless PERMIT filter at the IPv4
    ALE connect layer; it is deleted immediately if an elevated caller happens
    to be able to add it.  On a non-elevated token the filter add is expected
    to return ``ERROR_ACCESS_DENIED (5)``.  This is an *evidence* helper; the
    network boundary itself uses AppContainer, not WFP.
    """
    import uuid

    if not IS_WINDOWS:
        return -1, -1
    try:
        fwpm = ctypes.WinDLL("fwpuclnt", use_last_error=True)
        fwpm.FwpmEngineOpen0.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.POINTER(_FwpmSession0), ctypes.POINTER(wintypes.HANDLE)]
        fwpm.FwpmEngineOpen0.restype = wintypes.DWORD
        fwpm.FwpmEngineClose0.argtypes = [wintypes.HANDLE]
        fwpm.FwpmEngineClose0.restype = wintypes.DWORD
        fwpm.FwpmFilterAdd0.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_FwpmFilter0),
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64)]
        fwpm.FwpmFilterAdd0.restype = wintypes.DWORD
        fwpm.FwpmFilterDeleteById0.argtypes = [wintypes.HANDLE, ctypes.c_uint64]
        fwpm.FwpmFilterDeleteById0.restype = wintypes.DWORD

        session = _FwpmSession0()
        session.flags = 0x00000001  # FWPM_SESSION_FLAG_DYNAMIC
        session.txnWaitTimeoutInMSec = 5000
        handle = wintypes.HANDLE()
        open_rc = fwpm.FwpmEngineOpen0(
            None, 10, None, ctypes.byref(session), ctypes.byref(handle))  # RPC_C_AUTHN_WINNT
        if open_rc != 0:
            return open_rc, -1
        try:
            layer = _Guid()
            parsed = uuid.UUID("c38d57d1-05a7-4c33-904f-7fbceee60e82")  # ALE_AUTH_CONNECT_V4
            layer.Data1, layer.Data2, layer.Data3 = (
                parsed.time_low, parsed.time_mid, parsed.time_hi_version)
            for i, byte in enumerate(parsed.bytes[8:]):
                layer.Data4[i] = byte

            filt = _FwpmFilter0()
            filt.displayData.name = "KeelWfpAccessProbe"
            filt.layerKey = layer
            filt.weight.type = 0       # FWP_EMPTY
            filt.action.type = 0x1002  # FWP_ACTION_PERMIT (non-destructive)
            filter_id = ctypes.c_uint64()
            add_rc = fwpm.FwpmFilterAdd0(
                handle, ctypes.byref(filt), None, ctypes.byref(filter_id))
            if add_rc == 0:
                fwpm.FwpmFilterDeleteById0(handle, filter_id.value)
            return open_rc, add_rc
        finally:
            fwpm.FwpmEngineClose0(handle)
    except Exception:
        return -1, -1
