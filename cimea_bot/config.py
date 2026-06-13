"""Config loading + the small decision helpers (target time, success, retry)."""
from __future__ import annotations

from datetime import date as date_cls, datetime, time as time_cls, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import yaml


def load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def compute_target_epoch(schedule: Dict[str, Any]) -> Tuple[float, datetime]:
    """Resolve ``schedule`` into (unix_epoch, aware_datetime).

    If ``date`` is omitted, uses the next occurrence of ``target_time`` in ``timezone``.
    """
    tz = ZoneInfo(schedule.get("timezone", "UTC"))
    hh, mm, ss = (int(x) for x in str(schedule["target_time"]).split(":"))
    target = time_cls(hh, mm, ss)

    date_str = schedule.get("date")
    if date_str:
        dt = datetime.combine(date_cls.fromisoformat(str(date_str)), target, tzinfo=tz)
    else:
        now = datetime.now(tz)
        dt = datetime.combine(now.date(), target, tzinfo=tz)
        if dt <= now:
            dt += timedelta(days=1)
    return dt.timestamp(), dt


def is_success(status: int, body_text: Optional[str], crit: Optional[Dict[str, Any]]) -> bool:
    """All provided conditions must hold. With no conditions, default to HTTP 2xx."""
    crit = crit or {}
    body_text = body_text or ""
    checks = []
    if "status_in" in crit:
        checks.append(status in crit["status_in"])
    if "body_contains" in crit:
        checks.append(crit["body_contains"] in body_text)
    if "body_not_contains" in crit:
        checks.append(crit["body_not_contains"] not in body_text)
    if not checks:
        return 200 <= status < 300
    return all(checks)


def should_retry(status: int, retry: Dict[str, Any], attempt: int) -> bool:
    if attempt >= retry.get("max_attempts", 1):
        return False
    return status in retry.get("retry_on_status", [429, 500, 502, 503, 504])
