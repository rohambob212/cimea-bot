"""Turn a browser 'Copy as cURL' command into a request config block.

This is the easiest way to capture the real 'accept' request: open DevTools →
Network, click the button once on a throwaway/earlier action, right-click the
request → Copy → Copy as cURL, paste into a file, and run `import-curl` on it.
"""
from __future__ import annotations

import shlex
from typing import Any, Dict

# Headers that the HTTP client must set itself; carrying them over breaks requests.
_STRIP_HEADERS = {"content-length", "host", "connection"}


def parse_curl(text: str) -> Dict[str, Any]:
    text = text.replace("\\\n", " ").replace("^\n", " ").replace("`\n", " ")
    tokens = shlex.split(text)
    if tokens and tokens[0] == "curl":
        tokens = tokens[1:]

    method = None
    url = None
    headers: Dict[str, str] = {}
    cookies: Dict[str, str] = {}
    body = None

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-X", "--request"):
            method = tokens[i + 1]; i += 2; continue
        if tok in ("-H", "--header"):
            key, _, val = tokens[i + 1].partition(":")
            headers[key.strip()] = val.strip(); i += 2; continue
        if tok in ("-b", "--cookie"):
            _merge_cookies(cookies, tokens[i + 1]); i += 2; continue
        if tok in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii"):
            body = tokens[i + 1]; i += 2; continue
        if tok.startswith("--data-urlencode"):
            body = tokens[i + 1]; i += 2; continue
        if tok in ("--compressed", "-s", "--silent", "-i", "-k", "--insecure",
                   "-L", "--location", "-v", "--verbose", "-#", "-g"):
            i += 1; continue
        if tok.startswith("-"):
            i += 1; continue  # unknown flag — skip it
        url = tok; i += 1

    # Some captures put cookies in a Cookie header instead of -b.
    cookie_header = next((k for k in headers if k.lower() == "cookie"), None)
    if cookie_header:
        _merge_cookies(cookies, headers.pop(cookie_header))

    headers = {k: v for k, v in headers.items() if k.lower() not in _STRIP_HEADERS}
    if method is None:
        method = "POST" if body is not None else "GET"

    return {"method": method.upper(), "url": url, "headers": headers,
            "cookies": cookies, "body": body}


def _merge_cookies(into: Dict[str, str], raw: str) -> None:
    for part in raw.split(";"):
        if "=" in part:
            key, val = part.split("=", 1)
            into[key.strip()] = val.strip()


def to_config(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a parsed request into a full config skeleton with sane defaults."""
    return {
        "schedule": {
            "target_time": "15:00:00",
            "timezone": "Europe/Rome",
            "date": None,
            "lead_ms": 0,
            "prewarm_ms": 750,
            "use_ntp": True,
            "ntp_server": "pool.ntp.org",
        },
        "request": {
            "method": parsed["method"],
            "url": parsed["url"],
            "headers": parsed["headers"],
            "cookies": parsed["cookies"],
            "body": parsed["body"],
            "timeout_ms": 8000,
            "http2": False,
        },
        "prewarm": {"method": "GET", "url": parsed["url"]},
        "success": {"status_in": [200, 201, 202, 302]},
        "retry": {
            "max_attempts": 40,
            "backoff_initial_ms": 150,
            "backoff_max_ms": 3000,
            "backoff_factor": 2.0,
            "jitter_ms": 250,
            "retry_on_status": [429, 500, 502, 503, 504],
            "respect_retry_after": True,
            "give_up_after_seconds": 120,
        },
        "on_success": {"webhook_url": None, "next_request": None},
    }
