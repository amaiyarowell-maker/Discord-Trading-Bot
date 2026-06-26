"""
Simple in-memory cooldown tracker so the bot doesn't fire the same
symbol+direction+signal-type alert every single minute while a setup
is ongoing. signal_type (e.g. "breakout", "rejection", "liquidity_sweep",
"fvg") is included in the key so an alert of one type never suppresses
a different type on the same symbol+direction - they're different setups.
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
