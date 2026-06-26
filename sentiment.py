"""
Market-wide sentiment via VIX. Fetched once per scan cycle (not per
symbol) since it's a market-level indicator, not specific to any one
ticker. Used both as a display field and as one input into the
confidence score.
"""

import logging
import yfinance as yf

import config

logger = logging.getLogger("sentiment")

_cached_vix = {"value": None, "label": "UNKNOWN"}


def fetch_vix() -> dict:
    """
    Fetches the latest VIX close. Returns a dict with the raw value
    and a human label ("LOW FEAR", "NORMAL", "HIGH FEAR").

    On failure, returns the last successfully cached value rather than
    None, so a single failed fetch doesn't blank out sentiment context
    for the whole cycle. If there's never been a successful fetch,
    returns value=None / label="UNKNOWN".
    """
    global _cached_vix

    if not getattr(config, "SENTIMENT_ENABLED", False):
        return {"value": None, "label": "DISABLED"}

    try:
        data = yf.download(config.VIX_TICKER, period="5d", interval="1d", progress=False, auto_adjust=True)
        if data is None or data.empty:
            logger.warning("VIX fetch returned no data; using last cached value.")
            return _cached_vix

        latest_close = float(data["Close"].iloc[-1])
        label = classify_vix(latest_close)
        _cached_vix = {"value": round(latest_close, 2), "label": label}
        return _cached_vix

    except Exception as e:
        logger.warning(f"VIX fetch failed ({e}); using last cached value.")
        return _cached_vix


def classify_vix(vix_value: float) -> str:
    """Classifies a VIX value into a human-readable fear label."""
    if vix_value is None:
        return "UNKNOWN"
    if vix_value >= config.VIX_HIGH_FEAR_THRESHOLD:
        return "HIGH FEAR"
    if vix_value <= config.VIX_LOW_FEAR_THRESHOLD:
        return "LOW FEAR"
    return "NORMAL"
