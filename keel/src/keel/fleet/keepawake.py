"""keel.fleet.keepawake — "Keep awake" backed by a real process.

The Scheduled view shows a Keep-awake switch. This is not a decoration:
toggling on spawns a detached PowerShell that calls
SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED), which stops
Windows from sleeping while it lives, and prints "keep-awake active" to its
(captured) stdout so the handle proves it actually got there. Toggling off
kills the process. Windows-only, honestly — elsewhere it refuses.

The marker comment in the script is how we find the process again across
bridge restarts within this process. Across a full bridge restart the
registry forgets it (documented in shells.py); the machine may then sleep.
"""

from __future__ import annotations

import os

from . import shells as _shells

KEEP_AWAKE_MARK = "__KEEL_KEEP_AWAKE__"

_PS_SCRIPT = (
    f"$null = '{KEEP_AWAKE_MARK}'; "
    "try { "
    "  $sig = '[DllImport(\"kernel32.dll\")] public static extern uint SetThreadExecutionState(uint esFlags);'; "
    "  $type = Add-Type -Namespace Keel -Name KeepAwake -MemberDefinition $sig -PassThru; "
    "  $ok = [Keel.KeepAwake]::SetThreadExecutionState([uint32]2147483649); "
    "  if ($ok -eq [uint32]0) { Write-Output 'keep-awake FAILED'; exit 1 }; "
    "  Write-Output 'keep-awake active'; "
    "} catch { "
    "  Write-Output ('keep-awake FAILED: ' + $_.Exception.Message); exit 1 "
    "}; "
    "while ($true) { Start-Sleep -Seconds 30 }"
)


def status() -> dict:
    entries = _shells.find_by_command_prefix(f"$null = '{KEEP_AWAKE_MARK}'")
    running = [e for e in entries if e.finished_at is None]
    return {"supported": os.name == "nt",
            "on": len(running) > 0,
            "handle": running[0].handle if running else None}


def set_on(store) -> dict:
    if os.name != "nt":
        return {"ok": False, "error": "keep-awake is Windows-only"}
    current = status()
    if current["on"]:
        return {"ok": True, "on": True, "handle": current["handle"],
                "already": True}
    try:
        entry = _shells.start(store, {"id": "__keepawake__"},
                              _PS_SCRIPT, "powershell")
    except (ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    # verify honestly: the script prints one of two markers to its log;
    # wait briefly and report what the machine actually did, not what we hoped
    import time as _time
    deadline = _time.time() + 2.5
    while _time.time() < deadline:
        _time.sleep(0.15)
        out = _shells.read_output(entry.handle).get("output", "")
        if "keep-awake active" in out:
            return {"ok": True, "on": True, "handle": entry.handle}
        if "keep-awake FAILED" in out or entry.finished_at is not None:
            return {"ok": False, "on": False,
                    "error": (out.strip().splitlines() or ["keep-awake failed"])[0][:200]}
    return {"ok": True, "on": True, "handle": entry.handle,
            "note": "started; verification timed out"}


def set_off() -> dict:
    current = status()
    if not current["on"]:
        return {"ok": True, "on": False}
    result = _shells.kill(current["handle"])
    result["on"] = False if result.get("ok") else current["on"]
    return result
