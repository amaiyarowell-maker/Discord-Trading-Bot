"""
Simple in-memory cooldown tracker so the bot doesn't fire the same
symbol+direction alert every single minute while a breakout is ongoing.
"""

import time
import config


class CooldownTracker:
    def __init__(self):
        self._last_alert_time = {}  # key: (symbol, direction) -> timestamp

    def is_on_cooldown(self, symbol: str, direction: str) -> bool:
        key = (symbol, direction)
        last_time = self._last_alert_time.get(key)
        if last_time is None:
            return False
        elapsed_minutes = (time.time() - last_time) / 60
        return elapsed_minutes < config.ALERT_COOLDOWN_MINUTES

    def mark_alerted(self, symbol: str, direction: str):
        self._last_alert_time[(symbol, direction)] = time.time()
