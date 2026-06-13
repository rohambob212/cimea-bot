"""cimea-bot — a precise, well-behaved scheduled-request client for your own payment.

Design goals:
  * Fire ONE well-timed request (or one button click) for *your own* account at a
    precise moment (e.g. 15:00:00.000 Europe/Rome).
  * Beat congestion with *timing and a warm connection*, not with volume.
  * Be a good citizen: bounded retries, exponential backoff with jitter, honor
    `Retry-After`, stop immediately on success, never double-fire.

This is explicitly NOT a load generator. It does not coordinate many machines to
hammer an endpoint, and it does not try to evade rate limits. Use it only on
accounts and actions you are authorized to perform.
"""

__version__ = "0.1.0"
