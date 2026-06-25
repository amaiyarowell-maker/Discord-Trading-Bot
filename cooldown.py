"""
Simple in-memory cooldown tracker so the bot doesn't fire the same
symbol+direction+signal-type alert every single minute while a setup
is ongoing. signal_type ("breakout" or "rejection") is included in the
key so a breakout alert never suppresses a later rejection alert on the
same symbol+direction, and vice versa - they're different setups.
"""

import time
import config


class CooldownTracker:
    def __init__(self):
        self._last_alert_time = {}  # key: (symbol, direction, signal_type) -> timestamp

    def is_on_cooldown(self, symbol: str, direction: str, signal_type: str = "breakout") -> bool:
        key = (symbol, direction, signal_type)
        last_time = self._last_alert_time.get(key)
        if last_time is None:
            return False
        elapsed_minutes = (time.time() - last_time) / 60
        return elapsed_minutes < config.ALERT_COOLDOWN_MINUTES

    def mark_alerted(self, symbol: str, direction: str, signal_type: str = "breakout"):
        self._last_alert_time[(symbol, direction, signal_type)] = time.time()
