"""Minimal SNTP client so 'fire at 15:00:00' means *true* time, not your laptop's
drifted clock. No third-party dependency — talks to an NTP server over UDP.
"""
from __future__ import annotations

import socket
import struct
import time

# Seconds between the NTP epoch (1900-01-01) and the Unix epoch (1970-01-01).
_NTP_EPOCH_OFFSET = 2208988800


def ntp_offset(server: str = "pool.ntp.org", timeout: float = 5.0, samples: int = 4) -> float:
    """Estimate the offset (in seconds) to ADD to ``time.time()`` to get true time.

    A positive result means the local clock is *behind* true time. Takes several
    samples and returns the median to shrug off the odd jittery packet.
    """
    offsets = []
    for _ in range(max(1, samples)):
        try:
            offsets.append(_query_once(server, timeout))
        except OSError:
            continue
    if not offsets:
        raise RuntimeError(f"NTP query to {server!r} failed (no usable samples)")
    offsets.sort()
    return offsets[len(offsets) // 2]


def _query_once(server: str, timeout: float) -> float:
    packet = bytearray(48)
    packet[0] = 0x1B  # LI = 0, VN = 3, Mode = 3 (client)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        t1 = time.time()
        sock.sendto(packet, (server, 123))
        data, _ = sock.recvfrom(48)
        t4 = time.time()
    finally:
        sock.close()

    recv_secs, recv_frac = struct.unpack("!II", data[32:40])  # server receive ts
    xmit_secs, xmit_frac = struct.unpack("!II", data[40:48])  # server transmit ts
    t2 = (recv_secs - _NTP_EPOCH_OFFSET) + recv_frac / 2 ** 32
    t3 = (xmit_secs - _NTP_EPOCH_OFFSET) + xmit_frac / 2 ** 32
    # Standard NTP clock-offset estimate.
    return ((t2 - t1) + (t3 - t4)) / 2
