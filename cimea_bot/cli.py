"""Command-line entry point.

    python -m cimea_bot sync                         # check your clock offset
    python -m cimea_bot import-curl req.curl --out config.yaml
    python -m cimea_bot run --config config.yaml --dry-run
    python -m cimea_bot run --config config.yaml
    python -m cimea_bot browser --config config.yaml
"""
from __future__ import annotations

import argparse
import logging
import sys

import yaml

from . import config as cfg
from . import curl_import


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_sync(args: argparse.Namespace) -> None:
    from .clock import ntp_offset

    offset = ntp_offset(args.server)
    print(f"NTP offset vs {args.server}: {offset * 1000:+.1f} ms")
    print("(positive = your clock is behind true time; the bot corrects for this)")


def cmd_import_curl(args: argparse.Namespace) -> None:
    with open(args.file, "r", encoding="utf-8") as fh:
        parsed = curl_import.parse_curl(fh.read())
    if not parsed.get("url"):
        raise SystemExit("Could not find a URL in that cURL command — is the file correct?")
    config = curl_import.to_config(parsed)
    text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Wrote {args.out}")
        print("Review it (set target_time/timezone, success criteria), then dry-run:")
        print(f"    python -m cimea_bot run --config {args.out} --dry-run")
    else:
        print(text)


def cmd_run(args: argparse.Namespace) -> None:
    from . import http_sniper

    conf = cfg.load(args.config)
    ok = http_sniper.run(conf, dry_run=args.dry_run, standby_delay_ms=args.standby_delay_ms)
    sys.exit(0 if ok else 1)


def cmd_browser(args: argparse.Namespace) -> None:
    from . import browser_pilot

    conf = cfg.load(args.config)
    ok = browser_pilot.run(conf, dry_run=args.dry_run, standby_delay_ms=args.standby_delay_ms)
    sys.exit(0 if ok else 1)


def main(argv=None) -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(
        prog="cimea_bot",
        description="Precise, well-behaved scheduled-request client for your own payment.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="show NTP clock offset and exit")
    p_sync.add_argument("--server", default="pool.ntp.org")
    p_sync.set_defaults(func=cmd_sync)

    p_imp = sub.add_parser("import-curl", help="convert a 'Copy as cURL' capture into a config skeleton")
    p_imp.add_argument("file", help="text file containing the cURL command")
    p_imp.add_argument("--out", help="write the config here instead of printing it")
    p_imp.set_defaults(func=cmd_import_curl)

    for name, func, helptext in (
        ("run", cmd_run, "HTTP sniper — fastest, replays the captured request"),
        ("browser", cmd_browser, "browser pilot — drives a real logged-in Chromium"),
    ):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--config", required=True)
        sp.add_argument("--dry-run", action="store_true",
                        help="do everything except send/click the real fire action")
        sp.add_argument("--standby-delay-ms", type=int, default=0,
                        help="failover: fire this many ms after the primary, skipping if already done")
        sp.set_defaults(func=func)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
