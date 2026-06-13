# cimea-bot

A precise, **well-behaved** scheduled-request client for completing **your own**
payment on `https://mywallet.cimea-diplome.it/` the moment it opens
(e.g. exactly **15:00:00 Europe/Rome**) and reliably retrying through congestion
until it lands.

It wins a busy opening with **timing and a warm connection**, not with volume.

---

## Contents

- [What it is — and isn't](#what-it-is--and-isnt)
- [The three ways to run it](#the-three-ways-to-run-it)
- [Install (Windows-first)](#install-windows-first)
- [Quick start](#quick-start)
- [⭐ Recommended workflow: the Sniper + browser hybrid](#-recommended-workflow-the-sniper--browser-hybrid)
- [What happens when it goes through — and how you pay](#what-happens-when-it-goes-through--and-how-you-pay)
- [Payment-day playbook](#payment-day-playbook)
- [Tuning for the 3:00 rush](#tuning-for-the-300-rush)
- [Using a backup laptop (hot standby)](#using-a-backup-laptop-hot-standby)
- [Troubleshooting](#troubleshooting)
- [Credentials & safety](#credentials--safety)
- [Project layout](#project-layout)

---

## What it is — and isn't

CIMEA's wallet has **no public/payment API** (the page is a client-rendered SPA),
so everything goes through the authenticated web UI. This tool fires **one**
well-timed request (or one button click) for **your own** account, then retries
politely if the server is briefly overloaded.

**It deliberately does _not_:**
- coordinate many machines to hammer the endpoint in parallel,
- send floods of concurrent requests, or
- try to evade rate limits.

Why not — beyond being abusive? Because for **your single payment it doesn't even
help.** You can't pay one invoice twice, the server serializes on your session,
and the real delay is the network round-trip + their processing, identical for 1
request or 500. A flood just gets *your* account throttled first. So the design
here is the genuinely effective one:

- **NTP clock sync** so `15:00:00` means *true* time, not your laptop's drift.
- **Connection pre-warm** so at T we only send bytes on an already-open connection.
- **Fire-at-the-instant** scheduling with a tunable `lead_ms`.
- **Bounded, backoff + jitter retries** that honor `Retry-After` and **stop on the
  first success** (never double-fires).

---

## The three ways to run it

| Mode | Command | Needs Playwright? | Best for |
|------|---------|:--:|----------|
| **HTTP sniper** | `py -m cimea_bot run` | ❌ | Fastest. Replays the exact captured "accept" request. |
| **Browser pilot** | `py -m cimea_bot browser` | ✅ | Fully automated click in a real logged-in Chromium. Robust to per-click CSRF/anti-bot tokens. |
| **⭐ Hybrid** | `py -m cimea_bot run` + `on_success.open_url` | ❌ | **Recommended.** Sniper wins the *accept* race, then auto-pops the checkout in your normal browser so you finish the (legally human) card + 3-D Secure step. |

> On Windows, `py` is the Python launcher. `python` works too if it's on your PATH.

---

## Install (Windows-first)

```powershell
# from the repo root (the folder that CONTAINS the cimea_bot\ folder)
cd C:\Users\pc\Documents\hooman\APPLY\apply\cimea-bot-claude-confident-ride-peejcc

# 1. Make sure pip is current (old pip causes weird "no matching distribution" errors)
py -m pip install --upgrade pip

# 2. Core dependencies — pure Python, install on any Python incl. 32-bit
py -m pip install -r requirements.txt
```

That's everything the **sniper** and **hybrid** need. Playwright is **only** for
the `browser` command, and it is **64-bit only** — skip it unless you specifically
want the fully-automated click:

```powershell
py -m pip install playwright
py -m playwright install chromium
```

> Check your Python bitness with:
> `py -c "import platform; print(platform.architecture()[0])"`
> If it says `32bit`, Playwright won't install — use the sniper/hybrid, or install
> 64-bit Python from python.org. (See [Troubleshooting](#troubleshooting).)

macOS/Linux: same commands with `python3` instead of `py`.

---

## Quick start

**1. Sanity-check your clock:**

```powershell
py -m cimea_bot sync
```

**2. Capture the real "accept" request.** Full walkthrough in
[`examples/capture-instructions.md`](examples/capture-instructions.md). Short
version: log in → DevTools (F12) → **Network** → do the action once →
right-click the request → **Copy → Copy as cURL** → save it as `accept.curl`.

**3. Turn the capture into a config:**

```powershell
py -m cimea_bot import-curl accept.curl --out config.yaml
```

(No capture yet? `copy config.example.yaml config.yaml` and fill it in by hand.)

**4. Edit `config.yaml`** — set at least:
- `schedule.target_time` (`"15:00:00"`) and `schedule.timezone` (`"Europe/Rome"`),
- the `success:` criteria (what the server returns on a real accept),
- for the hybrid: `on_success.open_url` = your checkout URL.

```powershell
notepad config.yaml
```

**5. Dress-rehearse** (does everything *except* sending the real request):

```powershell
py -m cimea_bot run --config config.yaml --dry-run
```

**6. Go live:**

```powershell
py -m cimea_bot run --config config.yaml
```

---

## ⭐ Recommended workflow: the Sniper + browser hybrid

This is the best of both worlds: the **machine wins the race**, and **you do the
one step only a human legally can** (the card / 3-D Secure confirmation — see the
[payment section](#what-happens-when-it-goes-through--and-how-you-pay)).

**How it works:** the sniper fires the captured *accept* request at 3:00:00 on a
pre-warmed connection. The instant it succeeds it (a) prints a big banner,
(b) optionally pings your phone via `webhook_url`, and (c) **opens the checkout
page in your default browser** via `open_url` — and because you're already logged
into the site in that browser, the page loads authenticated and ready to pay.

**Set this in `config.yaml`:**

```yaml
on_success:
  open_url: "https://mywallet.cimea-diplome.it/checkout"   # your real pay/checkout URL
  webhook_url: "https://ntfy.sh/your-private-topic"        # optional phone ping
```

**On the day:**
1. Open your **normal browser**, log into `mywallet.cimea-diplome.it`, and leave it
   on the request page.
2. In a terminal at the repo root, run `py -m cimea_bot run --config config.yaml`.
3. At 3:00:00 the sniper accepts → your browser pops open at checkout → you enter/
   confirm the card and approve the **3-D Secure** prompt on your phone. Done.

> No Playwright needed for the hybrid — `open_url` uses your operating system's
> default browser.

---

## What happens when it goes through — and how you pay

**"mywallet" is a _credentials_ wallet** (a blockchain store for your certificates),
**not** a money/balance wallet — so there's nothing to pre-fund. Payment is
**per-request, at a checkout, after you accept.**

**When the accept succeeds**, the request flips from *to-accept* →
*accepted / awaiting payment*. That unlocks a checkout, and an invoice (a temporary
*fattura di cortesia*, later the final one) appears under
**My account → Receipts and invoices**. **Accept commits you to the cost — it is
not itself the charge.**

**How you pay (most likely):** an online **credit/debit card** payment at checkout
(possibly PayPal). Because it's an EU card payment, the final step is
**3-D Secure / Strong Customer Authentication** — you approving in your bank app or
via OTP. **That confirmation is a human step by law (PSD2); the bot can't and
shouldn't do it.** The bot's job ends by landing you on checkout, instantly and
logged in.

**If checkout instead offers bank transfer / "pay by invoice later":** there's *no
payment race at all* — you win the accept at 3:00 and pay the invoice afterward
within its window.

**Safety:** accept ≠ charge, the bot **stops on the first successful accept**, and
`on_success.next_request` is meant only to *advance to checkout* — never wire it to
auto-submit a charge (that risks double-charges and just fails SCA anyway).

---

## Payment-day playbook

- [ ] A day before: capture the accept request **and** the checkout URL; fill in
      `config.yaml`; run `--dry-run` successfully.
- [ ] If your account allows it, **save your card / set a default payment method**
      now, so checkout is one approval.
- [ ] Know your method: have the card + your **phone** (for the OTP) in hand; if
      using PayPal, be logged into PayPal in the same browser.
- [ ] ~10 min before 3:00: re-capture the request if your session is old (cookies
      expire), or just rely on the hybrid where your browser is logged in live.
- [ ] Log into the site in your **normal browser**, on the request page.
- [ ] Start the sniper: `py -m cimea_bot run --config config.yaml`.
- [ ] At success: complete card + 3-D Secure in the browser tab that pops open.
- [ ] Confirm the receipt under **My account → Receipts and invoices**.

---

## Tuning for the 3:00 rush

- `schedule.lead_ms` — fire this many ms **early** so the request *arrives* at T.
  Set it to roughly **half your ping** to the site:
  `ping mywallet.cimea-diplome.it`, take the average round-trip, halve it.
- `schedule.prewarm_ms` — leave ~750; it just keeps the TLS connection hot.
- `retry` — defaults retry for up to 2 minutes through `429/5xx` with growing
  backoff. Raise `give_up_after_seconds` for a chaotic opening, but keep
  `respect_retry_after: true`.
- Run the primary on your **server** (stable clock, wired, fast/close network);
  keep a **laptop** as a standby (next section).

---

## Using a backup laptop (hot standby)

Not a flood — a **failover**. Run the sniper on laptop B with a delay; it wakes a
few seconds after the primary and, using the optional `precheck:` request, first
asks *"is it already paid?"* — if yes it **stands down**; only if the primary
clearly failed does it act:

```powershell
py -m cimea_bot run --config config.yaml --standby-delay-ms 3000
```

Add a third machine at `--standby-delay-ms 6000`. One payment, one winner, no
duplicate firing. Configure `precheck:` in `config.yaml` (see `config.example.yaml`).

---

## Troubleshooting

**`No module named cimea_bot`**
You're running from *inside* the `cimea_bot\` package folder. `python -m cimea_bot`
must be run from the folder that **contains** `cimea_bot\` (the repo root):
```powershell
cd ..
py -m cimea_bot --help
```

**`pip install playwright` → "Could not find a version ... (from versions: none)"**
Playwright ships **64-bit wheels only**, and old pip mis-resolves wheels. Fix:
```powershell
py -m pip install --upgrade pip
py -c "import platform; print(platform.architecture()[0])"   # need 64bit
```
If it prints `32bit`, install 64-bit Python — **or just don't use Playwright.** The
**sniper/hybrid need only** `httpx` + `pyyaml` (pure Python, work on 32-bit):
```powershell
py -m pip install -r requirements.txt
py -m cimea_bot run --config config.yaml --dry-run
```
If even `httpx`/`pyyaml` won't install, it's your network/proxy, not the package.

**`the following arguments are required: --config`**
Pass it: `py -m cimea_bot run --config config.yaml`.

**`No such file or directory: 'config.yaml'`**
You only have `config.example.yaml`. Make your own (it's git-ignored):
`copy config.example.yaml config.yaml`.

**`NTP sync failed ... falling back to local clock`**
Harmless — your firewall blocks UDP 123. The bot uses your local clock instead. To
keep it accurate on Windows, run (as admin) `w32tm /resync` before the event.

**Fire returns `401`/`403`, or "session expired"**
Your captured cookies expired. Re-capture shortly before 3:00, or use the **hybrid/
browser** modes where you log in live.

**The accept "succeeds" but nothing happens / wrong success detection**
Tune `success:` in `config.yaml` to match what a real accept returns — a
`status_in` code and/or a `body_contains` string. Use `--dry-run` to iterate.

---

## Credentials & safety

- `config.yaml`, `*.curl`, and the browser profile are **git-ignored** — they hold
  your session cookies. Keep them off shared machines; log out / rotate after the
  event.
- Captured sessions expire. Re-capture close to the event, or use the hybrid/browser
  modes which log in live.
- Use this only on **your own** account, for an action you're entitled to perform.

---

## Project layout

```
cimea_bot/
  clock.py         # NTP offset (true time)
  scheduler.py     # precise wait-until-instant
  config.py        # config load + success/retry/target-time logic
  curl_import.py   # 'Copy as cURL'  ->  request config
  http_sniper.py   # Type 1: HTTP replay sniper (+ hybrid open_url hook)
  browser_pilot.py # Type 2: Playwright button-clicker
  notify.py        # success banner + webhook
  cli.py           # `py -m cimea_bot ...`
config.example.yaml
examples/capture-instructions.md
```
