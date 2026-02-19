"""
Randomization engine: delays 3-40s, shuffle action order, optional do-nothing / exit-early.
"""
from __future__ import annotations

import random
import time
from typing import Any, List, TypeVar

T = TypeVar("T")


def random_delay(min_sec: float = 3, max_sec: float = 40) -> float:
    """Return a random delay in [min_sec, max_sec] and sleep for it. Returns actual seconds slept."""
    sec = random.uniform(min_sec, max_sec)
    time.sleep(sec)
    return sec


def shuffle_actions(items: List[T]) -> List[T]:
    """Shuffle list in place and return. No fixed sequence."""
    out = list(items)
    random.shuffle(out)
    return out


def maybe_do_nothing(probability: float = 0.1) -> bool:
    """Return True with given probability (skip current optional action)."""
    return random.random() < probability


def maybe_exit_early(probability: float = 0.05) -> bool:
    """Return True with given probability (end session early)."""
    return random.random() < probability


def random_scroll_duration(min_sec: int = 120, max_sec: int = 240) -> int:
    """Random scroll duration in seconds for feed."""
    return random.randint(min_sec, max_sec)


def random_idle_sec(min_sec: float = 2, max_sec: float = 8) -> float:
    """Short idle pause (human-like)."""
    return random.uniform(min_sec, max_sec)
