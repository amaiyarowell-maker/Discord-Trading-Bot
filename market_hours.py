"""
Helper for checking whether US stock market regular hours are currently
active, so the bot can skip stock/futures scans outside that window.
BTC scanning is unaffected - crypto markets run 24/7.
"""

from datetime import datetime, time as dt_time
import pytz

import config


def is_market_open() -> bool:
    """
    Returns True if it's currently a weekday within regular US market
    hours (default 9:30 AM - 4:00 PM Eastern), False otherwise.

    If MARKET_HOURS_ONLY is False in config, this always returns True
    so scanning behaves as if hours don't matter (legacy behavior).

    Note: this checks calendar weekday + clock time only - it does not
    account for market holidays (e.g. Thanksgiving, July 4th). On those
    days the bot will still attempt to scan during normal hours and will
    just get empty/stale data back, which it already handles gracefully.
    """
    if not getattr(config, "MARKET_HOURS_ONLY", False):
        return True

    tz = pytz.timezone(config.MARKET_TIMEZONE)
    now = datetime.now(tz)

    # Monday=0 ... Sunday=6. Markets are closed Saturday/Sunday.
    if now.weekday() >= 5:
        return False

    market_open = dt_time(config.MARKET_OPEN_HOUR, config.MARKET_OPEN_MINUTE)
    market_close = dt_time(config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE)
    current_time = now.time()

    return market_open <= current_time <= market_close
