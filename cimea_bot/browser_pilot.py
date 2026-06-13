"""Type 2 — the browser pilot (Playwright).

Drives a real, logged-in Chromium via a persistent profile (you log in once and
the session is reused). At the target instant it clicks the button and verifies
the result. Slower than the HTTP sniper but resilient to JS-rendered per-click
tokens, CSRF, and anti-bot checks that are awkward to replay by hand.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from . import config as cfg
from . import notify
from .clock import ntp_offset
from .scheduler import wait_until

log = logging.getLogger("cimea_bot.browser")


def run(conf: Dict[str, Any], dry_run: bool = False, standby_delay_ms: int = 0) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Playwright is not installed. Run:\n"
            "    pip install playwright\n"
            "    playwright install chromium"
        ) from exc

    schedule = conf["schedule"]
    offset = _ntp_offset(schedule)
    now = lambda: time.time() + offset  # noqa: E731

    target_epoch, target_dt = cfg.compute_target_epoch(schedule)
    fire_at = target_epoch - schedule.get("lead_ms", 0) / 1000 + standby_delay_ms / 1000

    b = conf["browser"]
    retry = conf.get("retry", {})

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=b.get("user_data_dir", "./.cimea_profile"),
            headless=b.get("headless", False),
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(b["page_url"])
        notify.banner("LOG IN NOW if you aren't already. The bot clicks at the target time.")
        log.info("target %s — fires in %.1f s", target_dt.isoformat(), fire_at - now())

        wait_until(fire_at, now)
        log.info("FIRING (clicking) at %.3f", now())

        selector = b["button_selector"]
        success_selector = b.get("success_selector")
        click_timeout = b.get("click_timeout_ms", 5000)
        deadline = now() + retry.get("give_up_after_seconds", 120)

        attempt = 0
        while True:
            attempt += 1
            try:
                page.wait_for_selector(selector, timeout=click_timeout, state="visible")
                if dry_run:
                    log.info("[DRY RUN] would click %s (attempt %d)", selector, attempt)
                    _on_success(page, conf, {"attempt": attempt, "dry_run": True})
                    return True
                page.click(selector)
                log.info("clicked (attempt %d)", attempt)
                if success_selector:
                    page.wait_for_selector(success_selector, timeout=click_timeout)
                notify.banner(f"PAYMENT ACCEPT CLICKED & CONFIRMED on attempt {attempt}")
                _on_success(page, conf, {"attempt": attempt})
                return True
            except Exception as exc:  # noqa: BLE001 - Playwright raises many error types
                log.warning("attempt %d failed: %s", attempt, exc)
                if attempt >= retry.get("max_attempts", 1) or now() >= deadline:
                    log.error("giving up after %d attempt(s)", attempt)
                    return False
                time.sleep(retry.get("backoff_initial_ms", 150) / 1000)
                try:
                    page.reload()
                except Exception:  # noqa: BLE001
                    pass


def _ntp_offset(schedule: Dict[str, Any]) -> float:
    if not schedule.get("use_ntp", True):
        return 0.0
    try:
        offset = ntp_offset(schedule.get("ntp_server", "pool.ntp.org"))
        log.info("NTP offset %+.1f ms", offset * 1000)
        return offset
    except Exception as exc:  # noqa: BLE001
        log.warning("NTP sync failed (%s) — using local clock", exc)
        return 0.0


def _on_success(page, conf: Dict[str, Any], context: Dict[str, Any]) -> None:
    on_success: Optional[Dict[str, Any]] = conf.get("on_success") or {}
    notify.webhook(on_success, context)
    open_url = on_success.get("open_url")
    if open_url:
        try:
            page.goto(open_url)
            log.info("opened follow-up payment URL to go forward")
        except Exception as exc:  # noqa: BLE001
            log.warning("could not open follow-up URL: %s", exc)
