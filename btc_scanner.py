"""
BTC scanning logic using a rolling opening-range breakout, since crypto
trades 24/7 and has no single daily "open" the way equities do.

Uses ccxt's public market data endpoints (no API key required for
reading candles from most exchanges).
"""

import logging
import ccxt

import config

logger = logging.getLogger("btc_scanner")

_exchange = None


def _get_exchange():
    global _exchange
    if _exchange is None:
        exchange_class = getattr(ccxt, config.BTC_EXCHANGE)
        _exchange = exchange_class({"enableRateLimit": True})
    return _exchange


def check_btc_breakout():
    """
    Fetches recent 1-min OHLCV candles for BTC, builds a rolling
    opening range from the last OPENING_RANGE_MINUTES candles
    (excluding the current forming candle), and checks whether the
    latest price has broken out of that range with volume confirmation.

    Returns a signal dict if triggered, else None.
    """
    exchange = _get_exchange()
    limit = config.OPENING_RANGE_MINUTES + 5  # small buffer

    try:
        ohlcv = exchange.fetch_ohlcv(config.BTC_SYMBOL, timeframe=config.BTC_CANDLE_TIMEFRAME, limit=limit)
    except Exception as e:
        logger.warning(f"ccxt fetch_ohlcv failed: {e}")
        return None

    if not ohlcv or len(ohlcv) < config.OPENING_RANGE_MINUTES + 1:
        return None

    # Each candle: [timestamp, open, high, low, close, volume]
    *range_candles, latest = ohlcv[-(config.OPENING_RANGE_MINUTES + 1):]

    price = float(latest[4])
    volume = float(latest[5])

    range_high = max(c[2] for c in range_candles)
    range_low = min(c[3] for c in range_candles)
    avg_volume = sum(c[5] for c in range_candles) / len(range_candles)

    if avg_volume == 0:
        return None

    volume_confirmed = volume >= avg_volume * config.VOLUME_SPIKE_MULTIPLIER

    breakout_up = price > range_high * (1 + config.BREAKOUT_BUFFER_PCT)
    breakout_down = price < range_low * (1 - config.BREAKOUT_BUFFER_PCT)

    if not volume_confirmed or not (breakout_up or breakout_down):
        return None

    direction = "UP" if breakout_up else "DOWN"

    return {
        "symbol": "BTC/USD",
        "direction": direction,
        "price": price,
        "range_high": range_high,
        "range_low": range_low,
        "volume": volume,
        "avg_volume": avg_volume,
    }
