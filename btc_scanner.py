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


def _fetch_btc_ohlcv():
    """
    Shared fetch helper for BTC candles, used by both breakout and
    rejection checks so we only hit the exchange once per cycle.
    Returns the raw ohlcv list, or None if unusable.
    """
    exchange = _get_exchange()
    limit = config.OPENING_RANGE_MINUTES + max(5, config.MOMENTUM_MA_PERIOD)

    try:
        ohlcv = exchange.fetch_ohlcv(config.BTC_SYMBOL, timeframe=config.BTC_CANDLE_TIMEFRAME, limit=limit)
    except Exception as e:
        logger.warning(f"ccxt fetch_ohlcv failed: {e}")
        return None

    if not ohlcv or len(ohlcv) < config.OPENING_RANGE_MINUTES + 1:
        return None

    return ohlcv


def check_btc_breakout(ohlcv=None):
    """
    Builds a rolling opening range from the last OPENING_RANGE_MINUTES
    candles (excluding the current forming candle), and checks whether
    the latest price has broken out of that range with volume confirmation.

    ohlcv: optionally pass pre-fetched candles to avoid a duplicate
    network call (used when also checking for rejection in the same cycle).

    Returns a signal dict if triggered, else None.
    """
    if ohlcv is None:
        ohlcv = _fetch_btc_ohlcv()
    if ohlcv is None:
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

    # Momentum/trend confirmation, same approach as the stock scanner.
    if config.MOMENTUM_FILTER_ENABLED and len(ohlcv) >= config.MOMENTUM_MA_PERIOD:
        closes = [c[4] for c in ohlcv[-config.MOMENTUM_MA_PERIOD:]]
        ma = sum(closes) / len(closes)
        if direction == "UP" and price <= ma:
            return None
        if direction == "DOWN" and price >= ma:
            return None

    return {
        "symbol": "BTC/USD",
        "direction": direction,
        "price": price,
        "range_high": range_high,
        "range_low": range_low,
        "volume": volume,
        "avg_volume": avg_volume,
    }


def check_btc_rejection(ohlcv=None):
    """
    Looks for a REJECTION setup on BTC: price approached the rolling
    range high/low on the prior candle but the latest candle has
    reversed back inside the range, confirmed by volume.

    Returns a signal dict if a rejection is detected, else None.
    """
    if not getattr(config, "REJECTION_SIGNALS_ENABLED", False):
        return None

    if ohlcv is None:
        ohlcv = _fetch_btc_ohlcv()
    if ohlcv is None or len(ohlcv) < config.OPENING_RANGE_MINUTES + 2:
        return None

    # Need range candles, a "prior" candle to test the level, and the latest.
    *range_candles, prior, latest = ohlcv[-(config.OPENING_RANGE_MINUTES + 2):]

    price = float(latest[4])
    volume = float(latest[5])
    prior_high = float(prior[2])
    prior_low = float(prior[3])

    range_high = max(c[2] for c in range_candles)
    range_low = min(c[3] for c in range_candles)
    avg_volume = sum(c[5] for c in range_candles) / len(range_candles)

    if avg_volume == 0:
        return None

    volume_confirmed = volume >= avg_volume * config.VOLUME_SPIKE_MULTIPLIER
    if not volume_confirmed:
        return None

    proximity = config.REJECTION_PROXIMITY_PCT

    tested_top = prior_high >= range_high * (1 - proximity)
    tested_bottom = prior_low <= range_low * (1 + proximity)

    rejected_top = tested_top and price < range_high and price < prior_high
    rejected_bottom = tested_bottom and price > range_low and price > prior_low

    if not (rejected_top or rejected_bottom):
        return None

    direction = "DOWN" if rejected_top else "UP"

    return {
        "symbol": "BTC/USD",
        "direction": direction,
        "price": price,
        "range_high": range_high,
        "range_low": range_low,
        "volume": volume,
        "avg_volume": avg_volume,
    }
