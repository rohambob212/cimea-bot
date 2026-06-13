"""Success notification helpers: console banner + optional webhook ping."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("cimea_bot.notify")


def banner(message: str) -> None:
    line = "=" * max(40, len(message) + 4)
    print(f"\n{line}\n  {message}\n{line}\n", flush=True)


def webhook(on_success: Optional[Dict[str, Any]], context: Dict[str, Any]) -> None:
    if not on_success:
        return
    url = on_success.get("webhook_url")
    if not url:
        return
    try:
        httpx.post(url, json={"event": "cimea_bot_success", **context}, timeout=10)
        log.info("success webhook delivered")
    except Exception as exc:  # noqa: BLE001 - notification must never crash the run
        log.warning("success webhook failed: %s", exc)
