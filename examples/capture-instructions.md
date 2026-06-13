# Capturing the real "accept" request

The bot replays the exact HTTP request your browser sends when you click
**accept**. Here's how to grab it. Do this on **your own** logged-in account.

## Option A — Copy as cURL (recommended)

1. Log in to `https://mywallet.cimea-diplome.it/`.
2. Open **DevTools** (`F12` or `Ctrl/Cmd+Shift+I`) → **Network** tab.
3. Tick **Preserve log**. In the filter bar choose **Fetch/XHR**.
4. Perform the accept action **once** (if you can't without spending, do it on a
   test/earlier request, or use a step that produces the *same shape* of call —
   you just need the endpoint, headers and body format).
5. In the Network list, find the request that fires on click (often a `POST`).
   Click it and check the **Payload**/**Request** to confirm it's the right one.
6. Right-click it → **Copy** → **Copy as cURL**
   - Chrome/Edge: pick **Copy as cURL (bash)** if offered.
   - Firefox: **Copy Value → Copy as cURL**.
7. Paste into a file, e.g. `accept.curl`.
8. Convert it:
   ```bash
   python -m cimea_bot import-curl accept.curl --out config.yaml
   ```

The importer pulls out the method, URL, headers, cookies and body, and writes a
ready-to-edit `config.yaml`. Open it and:

- set `schedule.target_time` (e.g. `"15:00:00"`) and `timezone: "Europe/Rome"`;
- confirm `success:` (what the server returns on a successful accept — a status
  code, and/or a string in the body like `"confirmed"`);
- optionally set `on_success.next_request` to the **follow-up** call that moves
  the payment forward (capture that one the same way).

## Option B — use the browser pilot instead

If the request carries tokens that change on every click (CSRF, nonces, anti-bot
headers), replaying a captured cURL may fail. Use the **browser pilot**, which
clicks the actual button in a real logged-in browser:

```bash
python -m cimea_bot browser --config config.yaml
```

Set in `config.yaml` under `browser:`:
- `button_selector` — how to find the accept button. Easiest is a text selector
  like `button:has-text('Accept')` (or the Italian label, e.g.
  `button:has-text('Accetta')`). To get a precise CSS selector: right-click the
  button → **Inspect** → right-click the element → **Copy → Copy selector**.
- `success_selector` — something that only appears after success, e.g.
  `text=Payment confirmed`.

## Verifying success criteria

Whatever the server returns on a *real* successful accept is what `success:`
should match. If you can, do one successful accept earlier and note:
- the **HTTP status** (200? 302 redirect?), and
- a distinctive **string** in the response body or the confirmation page.

Put those in `success.status_in` / `success.body_contains` so the bot knows
exactly when to stop and (optionally) fire the follow-up request.
