# cimea-bot

A precise, **well-behaved** scheduled-request client for completing **your own**
payment on `https://mywallet.cimea-diplome.it/` the moment it opens (e.g. exactly
**15:00:00 Europe/Rome**), and reliably retrying through congestion until it lands.

It wins a busy opening with **timing and a warm connection**, not with volume.

## What this is — and isn't

CIMEA's wallet has **no public/payment API** (the page is a client-rendered SPA),
so everything goes through the authenticated web UI. This tool fires **one**
well-timed request (or one button click) for **your own** account, then retries
politely if the server is briefly overloaded.

**It deliberately does _not_:**
- coordinate many machines to hammer the endpoint in parallel,
- send floods of concurrent requests, or
- try to evade rate limits.

Why not — beyond it being abusive? Because for **your single payment it doesn't
even help.** You can't pay one invoice twice, the server serializes on your
session, and the real delay is the network round-trip + their processing, which
is identical for 1 request or 500. A flood just gets *your* account throttled or
flagged first. So the design here is the genuinely effective one:

- **NTP clock sync** so `15:00:00` means *true* time, not your laptop's drift.
- **Connection pre-warm** so at T we send bytes on an already-open TLS connection.
- **Fire-at-the-instant** scheduling with a tunable `lead_ms`.
- **Bounded, backoff + jitter retries** that honor `Retry-After` and **stop on
  the first success** (never double-fires).

### Two "types"

| Type | Command | When to use |
|------|---------|-------------|
| **HTTP sniper** | `python -m cimea_bot run` | Fastest. Replays the exact captured request. |
| **Browser pilot** | `python -m cimea_bot browser` | Robust. Drives a real logged-in Chromium and clicks the button — best if the request carries per-click CSRF/anti-bot tokens that are hard to replay. |

### Using your extra laptops the right way: hot standby (failover)

Not a flood — a **backup**. Run the sniper on laptop B with, say,
`--standby-delay-ms 3000`. It wakes 3 s after your primary and, using the
optional `precheck:` request, first asks *"is it already paid?"* — if yes it
**stands down**; only if the primary clearly failed does it act. Same idea for a
3rd machine at 6000 ms. One payment, one winner, no duplicate firing.

## Install

```bash
pip install -r requirements.txt
# For the browser pilot only:
pip install playwright && playwright install chromium
```

## Quick start

1. **Check your clock** (handy sanity check):
   ```bash
   python -m cimea_bot sync
   ```

2. **Capture the real "accept" request.** See
   [`examples/capture-instructions.md`](examples/capture-instructions.md).
   In short: DevTools → Network → do the action once → right-click the request →
   **Copy → Copy as cURL** → paste into `accept.curl`.

3. **Turn the capture into a config:**
   ```bash
   python -m cimea_bot import-curl accept.curl --out config.yaml
   ```
   Then open `config.yaml` and set `schedule.target_time` / `timezone`, confirm
   the `success:` criteria, and (optionally) fill `on_success.next_request` with
   the follow-up "confirm/checkout" request so it **goes forward automatically**.

4. **Dress-rehearse** (does everything except sending the real request):
   ```bash
   python -m cimea_bot run --config config.yaml --dry-run
   ```

5. **Go live:**
   ```bash
   python -m cimea_bot run --config config.yaml
   ```

   Browser version instead:
   ```bash
   python -m cimea_bot browser --config config.yaml   # log in when the window opens
   ```

## Tuning for the 3:00 rush

- `schedule.lead_ms`: set to roughly **half your ping** to the site (run
  `ping mywallet.cimea-diplome.it`, halve the average) so the request *arrives*
  at T rather than leaving at T.
- `schedule.prewarm_ms`: leave at ~750; it just keeps the connection hot.
- `retry`: the defaults retry for up to 2 minutes through `429/5xx` with growing
  backoff. Raise `give_up_after_seconds` if the opening is chaotic, but keep
  `respect_retry_after: true`.
- Run on your **server** (stable clock, fast/close network, wired) as primary and
  a **laptop** as `--standby-delay-ms` backup.

## A note on credentials & safety

- `config.yaml`, `*.curl`, and the browser profile are **git-ignored** — they
  contain your session cookies. Keep them off shared machines and rotate/log out
  after the event.
- Captured sessions expire. If your capture is old, re-capture shortly before
  3:00, or use the **browser pilot**, which logs in live.
- Use this only on **your own** account and an action you're entitled to perform.

## Project layout

```
cimea_bot/
  clock.py         # NTP offset (true time)
  scheduler.py     # precise wait-until-instant
  config.py        # config load + success/retry/target-time logic
  curl_import.py   # 'Copy as cURL'  ->  request config
  http_sniper.py   # Type 1: HTTP replay sniper
  browser_pilot.py # Type 2: Playwright button-clicker
  notify.py        # success banner + webhook
  cli.py           # `python -m cimea_bot ...`
config.example.yaml
```
