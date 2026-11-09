"""Retry schedule from the spec: 1, 5, 15, 60 minutes, then every 6 hours for 3 days."""
from datetime import timedelta

QUICK_STEPS_MINUTES = (1, 5, 15, 60)
SLOW_STEP = timedelta(hours=6)
SLOW_STEPS = 12  # 12 × 6 h = 3 days
MAX_ATTEMPTS = len(QUICK_STEPS_MINUTES) + SLOW_STEPS + 1  # the try after the last wait


def next_retry_delay(failed_attempts):
    """Wait before the next try, after `failed_attempts` failed tries; None = give up."""
    if failed_attempts < 1:
        raise ValueError("failed_attempts starts at 1")
    if failed_attempts <= len(QUICK_STEPS_MINUTES):
        return timedelta(minutes=QUICK_STEPS_MINUTES[failed_attempts - 1])
    if failed_attempts <= len(QUICK_STEPS_MINUTES) + SLOW_STEPS:
        return SLOW_STEP
    return None
