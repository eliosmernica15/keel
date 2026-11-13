"""keel.fleet.scheduler — F4 routine scheduling and execution.

Design (no new dependencies; stdlib + zoneinfo only):

- `tick(store, now=None)` scans for due routines and fires them on worker
  threads. The webapp enables a daemon (`start_daemon`); tests call `tick`
  directly with a controlled `now`.
- Missed runs: a routine whose slot is overdue by more than one full
  period is recorded as `skipped_missed` and advanced to its next future
  slot — no uncontrolled backlog after restarts or sleep.
- Overlap: a routine is atomically claimed (`running` 0→1); a second tick
  while it runs records nothing and returns immediately.
- Every run creates a Fleet task (created_by = the agent), flips it
  in_progress, executes through the ordinary gated turn loop, then closes
  it completed on success or failed on error. Files saved during the run
  are attributed to the routine. The run row flips to `awaiting_approval`
  live while an F1 card is pending (see approvals.py).
- Routines are ordinary agents with ordinary permissions — scheduling
  grants nothing. Approval cards work unchanged; on timeout the run fails
  closed with the tool name and reason.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .cron import CronError, next_run, parse_cron, period_delta

_log = logging.getLogger(__name__)

_DAEMON_INTERVAL_S = 20
_daemon_started = False
_daemon_lock = threading.Lock()


def routine_timeout_s() -> float:
    try:
        return float(os.environ.get("KEEL_FLEET_ROUTINE_TIMEOUT_S", 600))
    except ValueError:
        return 600.0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _parse_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc)


def routine_attachment(routine: dict, task_id: str, run_id: int) -> str:
    return (
        '<fleet-routine trust="untrusted">\n'
        "This is a scheduled routine you own. The operator scheduled it;\n"
        "identity, provider, model, permissions and standing policies are\n"
        "entirely yours — nothing here grants authority. Run autonomously,\n"
        "use your tools to do the work, and record progress on the linked\n"
        "task via update_task: set progress (0-100) and flip status as the\n"
        "work advances; close the task when the work is complete.\n"
        "If you produce deliverables, save them to the Library with\n"
        'save_file(..., task_id="%s") and they will be attributed to this\n'
        "run. Keep the final reply terse.\n"
        f"routine: {routine['name']}  ({routine['cron_expr']} in "
        f"{routine['timezone']})\n"
        f"task: {task_id}  run: {run_id}\n"
        "</fleet-routine>"
    ).replace('save_file(..., task_id="%s")',
              f'save_file(..., task_id="{task_id}")')


def _skip_missed(store, routine: dict, scheduled: datetime) -> None:
    """Advance a routine whose slot passed without execution; log the skip."""
    from datetime import timedelta
    next_future = next_run(parse_cron(routine["cron_expr"]),
                           datetime.now(ZoneInfo(routine["timezone"])))
    run_id = store.create_routine_run(routine["id"],
                                      scheduled_at=_iso_z(scheduled),
                                      task_id=None)
    store.finish_routine_run(run_id, status="skipped_missed",
                             summary="skipped missed slot (routine was overdue)",
                             error="")
    store.record_run_outcome(routine["id"], next_run_at=_iso_z(next_future),
                             status="skipped_missed",
                             summary="skipped missed slot (routine was overdue)")


def execute_routine(store, routine: dict, *, scheduled_at: str | None = None,
                    manual: bool = False) -> dict:
    """Run a routine end-to-end. Caller must have claimed it already.

    Total failure means: claim released, run marked failed, task failed,
    next slot pushed into the future — a stranded routine would otherwise
    409 every Run-now forever.
    """
    from .runtime import mark_routine_run, clear_routine_run
    from .turn_core import execute_turn

    routine_id = routine["id"]
    agent_id = routine["bot_id"]
    agent = store.get_bot(agent_id)
    if agent is None:
        store.release_routine(routine_id)
        store.record_run_outcome(
            routine_id, next_run_at=None, status="failed",
            summary="routine's agent no longer exists")
        return {"ok": False, "error": "agent not found"}

    scheduled_dt = (datetime.now(timezone.utc) if scheduled_at is None
                    else _parse_iso(scheduled_at))
    sched_iso = _iso_z(scheduled_dt)
    task = None
    run_id = None
    try:
        try:
            task = store.create_task(
                title=f"Routine: {routine['name'][:120]}",
                description=(
                    f"Scheduled routine `{routine['cron_expr']}` "
                    f"({routine['timezone']}){' — manual run' if manual else ''}\n\n"
                    f"{routine['prompt'][:2000]}"),
                priority="normal",
                assigned_bot_id=agent_id,
                created_by=agent_id,
                source="agent")
        except ValueError as exc:
            store.release_routine(routine_id)
            store.record_run_outcome(routine_id, next_run_at=None,
                                     status="failed", summary=str(exc))
            return {"ok": False, "error": str(exc)}

        run_id = store.create_routine_run(routine_id, scheduled_at=sched_iso,
                                          task_id=task["id"])
        store.append_task_event(task["id"], actor=agent_id, event="created",
                                note=f"routine {routine['name']} (run {run_id})")
        store.update_task(task["id"], actor=agent_id, status="in_progress")
        store.append_row(agent_id, "notice", {
            "text": (f"Routine “{routine['name']}” started "
                     f"(run {run_id}, task {task['id']})"),
            "level": "info",
            "icon": "routine",
        })

        outcome = _execute_turn_phase(store, routine, agent, task, run_id,
                                      agent_id, routine_timeout_s())
        outcome.setdefault("task_id", task["id"])
        outcome.setdefault("run_id", run_id)
        _finalize_routine_run(store, routine, agent_id, task, run_id, outcome)
        return outcome
    except Exception as exc:
        _log.exception("routine %s failed unexpectedly", routine_id)
        try:
            if run_id is not None:
                store.finish_routine_run(run_id, status="failed",
                                         summary="",
                                         error=f"internal: {exc}"[:1000])
        except Exception:
            pass
        try:
            if task is not None:
                store.update_task(task["id"], actor=agent_id,
                                  status="failed",
                                  note=f"internal: {exc}"[:500])
        except Exception:
            pass
        try:
            tz = ZoneInfo(routine.get("timezone") or "UTC")
            expr = parse_cron(routine.get("cron_expr") or "0 0 * * *")
            next_iso = _iso_z(next_run(expr, datetime.now(tz)))
        except Exception:
            next_iso = None
        try:
            store.record_run_outcome(routine_id, next_run_at=next_iso,
                                     status="failed",
                                     summary=f"internal: {exc}"[:500])
        except Exception:
            pass
        try:
            store.release_routine(routine_id)
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}


def _execute_turn_phase(store, routine, agent, task, run_id, agent_id,
                        timeout: float) -> dict:
    from .runtime import mark_routine_run, clear_routine_run
    from .turn_core import execute_turn

    routine_id = routine["id"]
    result_box: dict[str, dict] = {}

    def _work():
        try:
            mark_routine_run(run_id, agent_id)
            result_box["result"] = execute_turn(
                store, agent,
                f"[Routine “{routine['name']}” · task {task['id']}]\n"
                f"{routine['prompt']}",
                chain=(),
                user_row={"role": "user",
                          "content": (f"[Routine “{routine['name']}” · "
                                      f"task {task['id']}]\n"
                                      f"{routine['prompt']}"),
                          "routine_id": routine_id},
                extra_attachment=routine_attachment(routine, task["id"],
                                                    run_id),
                include_history=True,
                exclude_last_from_history=True)
        except Exception as exc:  # never strand the scheduler
            result_box["result"] = {"ok": False,
                                    "assistant_text": "",
                                    "terminal_reason": "internal_error",
                                    "permission_denials": 0,
                                    "approval_denials": [],
                                    "error": str(exc)}
        finally:
            clear_routine_run()

    worker = threading.Thread(target=_work,
                              name=f"fleet-routine-{routine_id}",
                              daemon=True)
    worker.start()
    worker.join(timeout=timeout)
    if worker.is_alive():
        return {"ok": False,
                "error": f"routine timed out after {int(timeout)}s",
                "terminal_reason": "timeout"}
    return result_box.get("result") or {"ok": False, "error": "no result"}


def _finalize_routine_run(store, routine, agent_id, task, run_id,
                          outcome: dict) -> None:
    routine_id = routine["id"]
    try:
        with store._lock:
            store._conn.execute(
                "UPDATE fleet_library SET routine_id = ?\n"
                " WHERE bot_id = ? AND routine_id IS NULL\n"
                "   AND created_at >= (SELECT started_at FROM "
                "                      fleet_routine_runs WHERE id = ?)",
                (routine_id, agent_id, run_id))
            store._conn.commit()
    except Exception:
        _log.exception("failed to attribute routine files")

    denial_notes = outcome.get("approval_denials") or []
    timeout_denial = next((d for d in denial_notes
                           if d.get("reason_type") == "fleet_timeout"), None)
    refused_denial = next((d for d in denial_notes
                           if d.get("reason_type") == "fleet_approval"), None)
    if timeout_denial is not None:
        tool = timeout_denial.get("tool_name", "tool")
        status = "failed"
        summary = ""
        outcome["error"] = f"approval timed out for {tool}; run failed closed"
        store.update_task(task["id"], actor=agent_id, status="failed",
                          note=outcome["error"])
    elif refused_denial is not None:
        tool = refused_denial.get("tool_name", "tool")
        status = "failed"
        outcome["error"] = f"approval denied for {tool}"
        summary = ""
        store.update_task(task["id"], actor=agent_id, status="failed",
                          note=outcome["error"])
    elif outcome.get("ok"):
        status, summary = "completed", (outcome.get("assistant_text") or "").strip()
        store.update_task(task["id"], actor=agent_id, status="completed",
                          progress=100,
                          note=f"routine completed (run {run_id})")
    else:
        status = "failed"
        summary = (outcome.get("assistant_text") or "").strip()
        store.update_task(task["id"], actor=agent_id, status="failed",
                          note=str(outcome.get("error") or "routine failed")[:500])

    store.finish_routine_run(run_id, status=status,
                             summary=summary[:2000],
                             error=str(outcome.get("error") or ""))
    try:
        tz = ZoneInfo(routine["timezone"])
        expr = parse_cron(routine["cron_expr"])
        next_iso = _iso_z(next_run(expr, datetime.now(tz)))
    except Exception:
        next_iso = None
    store.record_run_outcome(routine_id, next_run_at=next_iso,
                             status=status,
                             summary=summary[:2000])
    store.append_row(agent_id, "notice", {
        "text": (f"Routine “{routine['name']}” {status} "
                 f"(run {run_id}, task {task['id']})"),
        "level": "info" if status == "completed" else "warning",
        "icon": "routine",
    })
    store.release_routine(routine_id)


def tick(store, *, now: datetime | None = None) -> list[int]:
    """Fire due routines once each. Returns the ids of runs started."""
    now = now or _now_utc()
    now_iso = _iso_z(now)
    started: list[int] = []
    for routine in store.due_routines(now_iso):
        if not store.claim_routine(routine["id"]):
            continue  # someone else claimed it
        scheduled = _parse_iso(routine["next_run_at"])
        try:
            overdue = now - scheduled
            period = period_delta(parse_cron(routine["cron_expr"]), scheduled)
            if overdue > period:
                _skip_missed(store, routine, scheduled)
                store.release_routine(routine["id"])
                continue
        except Exception:
            pass  # skip-missed is best-effort; execute normally on error
        result = execute_routine(store, routine,
                                 scheduled_at=routine["next_run_at"],
                                 manual=False)
        if isinstance(result, dict) and result.get("run_id"):
            started.append(result["run_id"])
    return started


def tick_forever(stop_event: threading.Event) -> None:
    from . import routes
    while not stop_event.is_set():
        try:
            tick(routes.store())
        except Exception:
            _log.exception("routine tick failed")
        stop_event.wait(_DAEMON_INTERVAL_S)


def start_daemon() -> bool:
    """Start the background tick thread (idempotent)."""
    global _daemon_started
    if os.environ.get("KEEL_FLEET_SCHEDULER_DISABLED") == "1":
        return False
    with _daemon_lock:
        if _daemon_started:
            return False
        _daemon_started = True
    stop = threading.Event()
    thread = threading.Thread(target=tick_forever, args=(stop,),
                              name="fleet-scheduler", daemon=True)
    thread.start()
    _log.info("fleet routine scheduler daemon started")
    return True


def reset_daemon_for_tests() -> None:
    global _daemon_started
    with _daemon_lock:
        _daemon_started = False
