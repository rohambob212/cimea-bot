"""Precise 'wait until an exact instant' helper.

Coarse-sleep until just before the target, then busy-spin the final few
milliseconds so we hit the instant tightly without burning a CPU core for long.
"""
from __future__ import annotations

import time
from typing import Callable


def wait_until(target_epoch: float, now_fn: Callable[[], float] = time.time,
               spin_window: float = 0.05) -> float:
    """Block until ``now_fn() >= target_epoch``. Returns the actual fire time.

    ``now_fn`` should already include any NTP offset so we're aligned to true time.
    """
    while True:
        remaining = target_epoch - now_fn()
        if remaining <= 0:
            return now_fn()
        if remaining > spin_window:
            time.sleep(remaining - spin_window)
        else:
            while target_epoch - now_fn() > 0:
                pass
            return now_fn()
