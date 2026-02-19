"""
Randomization engine: delays, shuffle action order, optional do-nothing / exit-early.
"""
from __future__ import annotations

import random
import time
from typing import List, TypeVar

T = TypeVar("T")


def random_delay(min_sec: float = 3, max_sec: float = 40) -> float:
    sec = random.uniform(min_sec, max_sec)
    time.sleep(sec)
    return sec


def shuffle_actions(items: List[T]) -> List[T]:
    out = list(items)
    random.shuffle(out)
    return out


def maybe_do_nothing(probability: float = 0.1) -> bool:
    return random.random() < probability


def maybe_exit_early(probability: float = 0.05) -> bool:
    return random.random() < probability


def random_scroll_duration(min_sec: int = 30, max_sec: int = 60) -> int:
    return random.randint(min_sec, max_sec)


def random_idle_sec(min_sec: float = 2, max_sec: float = 8) -> float:
    return random.uniform(min_sec, max_sec)
