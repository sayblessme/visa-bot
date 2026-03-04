import random


def compute_interval(
    base_min: int = 60,
    base_max: int = 180,
    jitter: int = 15,
    error_count: int = 0,
    max_backoff: int = 600,
) -> float:
    """Compute next check interval with jitter and exponential backoff on errors."""
    base = random.randint(base_min, base_max)
    if error_count > 0:
        backoff = min(base * (2 ** error_count), max_backoff)
        return backoff + random.randint(0, jitter)
    return base + random.randint(0, jitter)
