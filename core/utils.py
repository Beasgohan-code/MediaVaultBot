#@mediavault
from __future__ import annotations

import math
import time
from typing import Optional

import humanize


def format_size(num: Optional[int]) -> str:
    if num is None:
        return "Unknown"
    return humanize.naturalsize(num, binary=True)


def progress_bar(current: int, total: int, length: int = 12) -> str:
    if total <= 0:
        return "░" * length
    filled = int(length * current / total)
    return "█" * filled + "░" * (length - filled)


def format_speed(bytes_per_sec: float) -> str:
    return humanize.naturalsize(bytes_per_sec, binary=True) + "/s"


def eta(current: int, total: int, speed: float) -> str:
    if speed <= 0 or current >= total:
        return "—"
    remaining = (total - current) / speed
    return humanize.naturaldelta(remaining)


class ProgressTracker:
    def __init__(self, total: int = 0):
        self.total = total
        self.current = 0
        self.start = time.time()
        self.last_update = 0.0

    def update(self, current: int, total: int | None = None):
        self.current = current
        if total is not None:
            self.total = total

    @property
    def speed(self) -> float:
        elapsed = time.time() - self.start
        if elapsed <= 0:
            return 0.0
        return self.current / elapsed

    def should_update(self, interval: float = 1.5) -> bool:
        now = time.time()
        if now - self.last_update >= interval:
            self.last_update = now
            return True
        return False

    def render(self, filename: str, template: str) -> str:
        bar = progress_bar(self.current, self.total)
        return template.format(
            filename=filename[:40] + ("…" if len(filename) > 40 else ""),
            bar=bar,
            speed=format_speed(self.speed),
            done=format_size(self.current),
            total=format_size(self.total),
            eta=eta(self.current, self.total, self.speed),
        )


def progress_bar(percent: float, length: int = 10) -> str:
    percent = max(0.0, min(100.0, float(percent or 0)))
    filled = int((percent / 100) * length)
    return "▓" * filled + "░" * (length - filled)


def human_duration(seconds) -> str:
    if not seconds:
        return "?"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
