"""Duration sanity checks between a Spotify track and a candidate audio source.

Spotify's ``duration_ms`` is the ground truth used to reject wrong search hits
(live versions, hour-long mixes, 30-second previews).
"""
from typing import Optional, Tuple

_STRICT = (10.0, 0.10)    # (min absolute seconds, fraction) - used for new downloads
_LENIENT = (30.0, 0.30)   # used when auditing files that already exist on disk


def tolerance_seconds(expected_seconds: float, lenient: bool = False) -> float:
    """Allowed deviation from the expected duration."""
    floor, fraction = _LENIENT if lenient else _STRICT
    return max(floor, fraction * expected_seconds)


def duration_bounds(expected_ms: Optional[int], lenient: bool = False) -> Optional[Tuple[float, float]]:
    """(min_seconds, max_seconds) acceptable for a track, or None if unknown."""
    if not expected_ms or expected_ms <= 0:
        return None
    expected = expected_ms / 1000.0
    tol = tolerance_seconds(expected, lenient)
    return max(0.0, expected - tol), expected + tol


def within_tolerance(actual_seconds: Optional[float], expected_ms: Optional[int], lenient: bool = False) -> bool:
    """True if ``actual_seconds`` is plausible for a track of ``expected_ms``.

    An unknown expected duration cannot be judged and is accepted; an unknown
    actual duration (unreadable file) is rejected.
    """
    if actual_seconds is None:
        return False
    bounds = duration_bounds(expected_ms, lenient)
    if bounds is None:
        return True
    low, high = bounds
    return low <= actual_seconds <= high
