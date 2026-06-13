"""Type 1 — the HTTP sniper.

Replays the captured 'accept' request on a pre-warmed keep-alive connection,
fires at the exact target instant, and retries with bounded exponential backoff
(honoring Retry-After) until success, a non-retryable error, or the deadline.
Stops the moment it succeeds and never double-fires.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Dict, Optional, Tuple

import httpx

from . import config as cfg
from . import notify
from .clock import ntp_offset
from .scheduler import wait_until

log = logging.getLogger("cimea_bot.http")


def run(conf: Dict[str, Any], dry_run: bool = False, standby_delay_ms: int = 0) -> bool:
    schedule = conf["schedule"]
    now, _ = _true_clock(schedule)
    target_epoch, target_dt = cfg.compute_target_epoch(schedule)
    fire_at = target_epoch - schedule.get("lead_ms", 0) / 1000 + standby_delay_ms / 1000
    prewarm_at = fire_at - schedule.get("prewarm_ms", 750) / 1000

    log.info("target %s — fires in %.1f s", target_dt.isoformat(), fire_at - now())
    if standby_delay_ms:
        log.info("STANDBY mode: +%d ms after the primary", standby_delay_ms)

    req = conf["request"]
    retry = conf.get("retry", {})
    success = conf.get("success")

    with _build_client(req) as client:
        prewarm = conf.get("prewarm")
        if prewarm:
            wait_until(prewarm_at, now)
            try:
                _send(client, prewarm)
                log.info("pre-warm done — connection is hot")
            except Exception as exc:  # noqa: BLE001
                log.warning("pre-warm failed: %s", exc)

        wait_until(fire_at, now)

        # A standby should not duplicate a payment the primary already completed.
        if standby_delay_ms and _precheck_says_done(client, conf):
            return True

        fired = now()
        log.info("FIRING at %.3f (%+.0f ms vs target)", fired, (fired - target_epoch) * 1000)
        return _fire_loop(client, req, retry, success, now, conf, dry_run)


def _fire_loop(client, req, retry, success, now, conf, dry_run) -> bool:
    attempt = 0
    backoff = retry.get("backoff_initial_ms", 150) / 1000
    deadline = now() + retry.get("give_up_after_seconds", 120)

    while True:
        attempt += 1
        if dry_run:
            log.info("[DRY RUN] would send %s %s (attempt %d)", req["method"], req["url"], attempt)
            _on_success(client, conf, {"attempt": attempt, "dry_run": True})
            return True

        start = time.perf_counter()
        try:
            resp = _send(client, req)
            elapsed = (time.perf_counter() - start) * 1000
            log.info("attempt %d -> HTTP %d in %.0f ms", attempt, resp.status_code, elapsed)

            if cfg.is_success(resp.status_code, resp.text, success):
                notify.banner(f"PAYMENT ACCEPT SUCCEEDED on attempt {attempt}")
                _on_success(client, conf, {"attempt": attempt, "status": resp.status_code})
                return True

            if not cfg.should_retry(resp.status_code, retry, attempt):
                log.error("HTTP %d non-retryable or attempts exhausted — stopping", resp.status_code)
                log.error("body (truncated): %s", resp.text[:500])
                return False
            wait = _retry_after(resp, retry, backoff)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            log.warning("attempt %d transport error: %s", attempt, exc)
            if attempt >= retry.get("max_attempts", 1):
                log.error("attempts exhausted after transport errors — stopping")
                return False
            wait = backoff

        if now() >= deadline:
            log.error("give-up deadline reached — stopping")
            return False
        wait += random.uniform(0, retry.get("jitter_ms", 250) / 1000)
        log.info("retrying in %.0f ms", wait * 1000)
        time.sleep(wait)
        backoff = min(backoff * retry.get("backoff_factor", 2.0),
                      retry.get("backoff_max_ms", 3000) / 1000)


def _true_clock(schedule: Dict[str, Any]) -> Tuple[Callable[[], float], float]:
    offset = 0.0
    if schedule.get("use_ntp", True):
        try:
            offset = ntp_offset(schedule.get("ntp_server", "pool.ntp.org"))
            log.info("NTP offset %+.1f ms (clock is %s true time)",
                     offset * 1000, "behind" if offset > 0 else "ahead of")
        except Exception as exc:  # noqa: BLE001
            log.warning("NTP sync failed (%s) — falling back to local clock", exc)
    return (lambda: time.time() + offset), offset


def _build_client(req: Dict[str, Any]) -> httpx.Client:
    timeout = req.get("timeout_ms", 8000) / 1000
    limits = httpx.Limits(max_keepalive_connections=4, keepalive_expiry=30)
    return httpx.Client(
        http2=req.get("http2", False),
        timeout=timeout,
        limits=limits,
        headers=req.get("headers") or {},
        cookies=req.get("cookies") or {},
        follow_redirects=False,
    )


def _send(client: httpx.Client, spec: Dict[str, Any]) -> httpx.Response:
    kwargs: Dict[str, Any] = {}
    if spec.get("body_json") is not None:
        kwargs["json"] = spec["body_json"]
    elif spec.get("body") is not None:
        kwargs["content"] = spec["body"]
    return client.request(spec["method"], spec["url"], **kwargs)


def _precheck_says_done(client: httpx.Client, conf: Dict[str, Any]) -> bool:
    precheck = conf.get("precheck")
    if not precheck:
        return False
    try:
        resp = _send(client, precheck)
        if cfg.is_success(resp.status_code, resp.text, precheck.get("success")):
            log.info("precheck says the action is ALREADY complete — standby stands down")
            return True
    except Exception as exc:  # noqa: BLE001
        log.warning("precheck failed (%s) — proceeding as if not done", exc)
    return False


def _retry_after(resp: httpx.Response, retry: Dict[str, Any], backoff: float) -> float:
    if retry.get("respect_retry_after"):
        header = resp.headers.get("Retry-After")
        if header:
            try:
                return max(backoff, float(header))
            except ValueError:
                pass  # HTTP-date form — fall back to our own backoff
    return backoff


def _on_success(client: httpx.Client, conf: Dict[str, Any], context: Dict[str, Any]) -> None:
    on_success: Optional[Dict[str, Any]] = conf.get("on_success") or {}
    notify.webhook(on_success, context)
    follow_up = on_success.get("next_request")
    if follow_up:
        try:
            resp = _send(client, follow_up)
            log.info("follow-up 'go forward with payment' request -> HTTP %d", resp.status_code)
        except Exception as exc:  # noqa: BLE001
            log.warning("follow-up request failed: %s", exc)

    # HYBRID: pop the checkout page in the user's default browser (where they are
    # logged in) so they can finish the card + 3-D Secure step by hand.
    open_url = on_success.get("open_url")
    if open_url:
        try:
            import webbrowser

            webbrowser.open(open_url)
            log.info("opened checkout in your default browser: %s", open_url)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not open browser (open it yourself: %s): %s", open_url, exc)
