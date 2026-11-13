"""keel.fleet.cron — minimal, correct 5-field cron for routines.

Supported syntax (per field):
  *           any
  */n          every n within the field's range
  a           exact value (names allowed for month/dow)
  a,b,c       list
  a-b         inclusive range
  a-b/n       stepped range

Month names: JAN FEB … DEC (case-insensitive). Day-of-week names: SUN … SAT
(case-insensitive; 0 and 7 are Sunday). When BOTH day-of-month and
day-of-week are restricted (not `*`), a day matches if either matches —
standard cron semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
_DOWS = {d: i for i, d in enumerate(
    ["sun", "mon", "tue", "wed", "thu", "fri", "sat"])}


class CronError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    spec: str
    allowed: frozenset[int]


def _parse_field(name: str, part: str, lo: int, hi: int,
                 names: dict[str, int] | None = None) -> frozenset[int]:
    part = part.strip()
    if not part:
        raise CronError(f"empty {name} field")
    allowed: set[int] = set()
    for chunk in part.split(","):
        chunk = chunk.strip()
        if not chunk:
            raise CronError(f"empty item in {name} field")
        step = 1
        if "/" in chunk:
            chunk, step_raw = chunk.split("/", 1)
            try:
                step = int(step_raw)
            except ValueError:
                raise CronError(f"invalid step {step_raw!r} in {name}")
            if step < 1:
                raise CronError(f"step must be >= 1 in {name}")
        if chunk == "*":
            base_lo, base_hi = lo, hi
        elif "-" in chunk:
            a, b = chunk.split("-", 1)
            base_lo = _parse_value(name, a, lo, hi, names)
            base_hi = _parse_value(name, b, lo, hi, names)
            if base_lo > base_hi:
                raise CronError(f"reversed range {chunk!r} in {name}")
        else:
            base_lo = base_hi = _parse_value(name, chunk, lo, hi, names)
        values = range(base_lo, base_hi + 1, step)
        allowed.update(values)
    return frozenset(allowed)


def _parse_value(name: str, token: str, lo: int, hi: int,
                 names: dict[str, int] | None) -> int:
    token = token.strip().lower()
    if names and token in names:
        return names[token]
    try:
        value = int(token)
    except ValueError:
        raise CronError(f"unrecognized {name} value {token!r}")
    if value == 7 and name == "dow":
        value = 0  # both 0 and 7 mean Sunday
    if not (lo <= value <= hi):
        raise CronError(f"{name} value {value} out of range [{lo}, {hi}]")
    return value


@dataclass(frozen=True)
class CronExpression:
    minute: frozenset[int]
    hour: frozenset[int]
    dom: frozenset[int]
    month: frozenset[int]
    dow: frozenset[int]
    dom_restricted: bool
    dow_restricted: bool
    raw: str


def parse_cron(expr: str) -> CronExpression:
    parts = expr.split()
    if len(parts) != 5:
        raise CronError(
            f"cron needs exactly 5 fields (minute hour dom month dow), "
            f"got {len(parts)}")
    minute = _parse_field("minute", parts[0], 0, 59)
    hour = _parse_field("hour", parts[1], 0, 23)
    dom = _parse_field("dom", parts[2], 1, 31)
    month = _parse_field("month", parts[3], 1, 12, _MONTHS)
    dow = _parse_field("dow", parts[4], 0, 6, _DOWS)
    return CronExpression(
        minute=minute, hour=hour, dom=dom, month=month, dow=dow,
        dom_restricted=parts[2].strip() != "*",
        dow_restricted=parts[4].strip() != "*",
        raw=" ".join(parts))


def _cron_dow(moment: datetime) -> int:
    # Python weekday(): Mon=0..Sun=6  →  cron dow: Sun=0..Sat=6
    return (moment.weekday() + 1) % 7


def _is_valid_wall_time(moment: datetime) -> bool:
    """False for the nonexistent wall times inside a spring-forward gap."""
    tz = moment.tzinfo
    probe = moment.replace(fold=0)
    back = probe.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    return back == moment.replace(tzinfo=None)


def _day_matches(expr: CronExpression, day: datetime) -> bool:
    dom_ok = day.day in expr.dom
    dow_ok = _cron_dow(day) in expr.dow
    if expr.dom_restricted and expr.dow_restricted:
        return dom_ok or dow_ok  # standard cron: dom OR dow
    return dom_ok and dow_ok


def matches(expr: CronExpression, moment: datetime) -> bool:
    if not _is_valid_wall_time(moment):
        return False
    if moment.month not in expr.month:
        return False
    if moment.minute not in expr.minute:
        return False
    if moment.hour not in expr.hour:
        return False
    return _day_matches(expr, moment)


def next_run(expr: CronExpression, after: datetime) -> datetime:
    """First datetime strictly after `after` (tz-aware) that matches expr."""
    if after.tzinfo is None:
        raise ValueError("after must be timezone-aware")
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = candidate + timedelta(days=366 * 6)
    while candidate < limit:
        if not _is_valid_wall_time(candidate):
            candidate += timedelta(minutes=1)
            continue
        # month fast-forward
        if candidate.month not in expr.month:
            candidate = (candidate.replace(day=1, hour=0, minute=0)
                         + timedelta(days=32)).replace(day=1, hour=0,
                                                       minute=0)
            continue
        # day fast-forward
        if not _day_matches(expr, candidate):
            candidate = (candidate + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            continue
        # hour fast-forward
        if candidate.hour not in expr.hour:
            candidate = (candidate + timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0)
            continue
        # minute fast-forward within the hour
        if candidate.minute not in expr.minute:
            candidate += timedelta(minutes=1)
            continue
        return candidate
    raise CronError(f"no matching time within 6 years for {expr.raw!r}")


def next_runs(expr: CronExpression, after: datetime, count: int = 3) -> list[datetime]:
    out = []
    cursor = after
    for _ in range(count):
        cursor = next_run(expr, cursor)
        out.append(cursor)
    return out


def period_delta(expr: CronExpression, after: datetime) -> timedelta:
    """Approximate interval between consecutive matches (for skip-missed)."""
    first = next_run(expr, after)
    second = next_run(expr, first)
    return second - first
