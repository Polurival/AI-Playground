"""Retry helper used by the delivery channels."""

from typing import Callable

MAX_ATTEMPTS = 3


def with_retry(fn: Callable[[], bool], attempts: int = MAX_ATTEMPTS) -> bool:
    """Call `fn` up to `attempts` times, returning its first truthy result.

    Returns False if every attempt failed.
    """
    # TODO: add exponential backoff between attempts instead of retrying immediately.
    for _ in range(attempts):
        if fn():
            return True
    return False
