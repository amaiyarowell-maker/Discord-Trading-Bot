"""
Stock scanning logic:
1. Pulls a shortlist of active/moving tickers (so we never try to scan all 500+ S&P names every minute).
2. For each ticker, checks for an opening-range-style breakout confirmed by a volume spike.
"""

import logging
import yfinance as yf
import pandas as pd

import config

logger = logging.getLogger("stock_scanner")

# Fallback static watchlist used only if the dynamic movers fetch fails.
# This keeps the bot alive even if Yahoo's trending endpoint is down.
FALLBACK_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "GOOGL", "AMD",
    "NFLX", "AVGO", "JPM", "BA", "XOM", "PLTR", "SOFI", "COIN",
]


def get_movers_shortlist() -> list:
    """
    Pulls a shortlist of currently active tickers using yfinance's
    'most active' / trending screener, then merges in any PINNED_TICKERS
    so those are always scanned regardless of that day's movers.
    Falls back to a static list of liquid large-caps if the screener
    call fails for any reason.
    """
    tickers = []
    try:
        screener = yf.screen("most_actives", count=config.MAX_MOVERS_TO_SCAN)
        quotes = screener.get("quotes", [])
        tickers = [q["symbol"] for q in quotes if "symbol" in q]
        if tickers:
            logger.info(f"Pulled {len(tickers)} tickers from most-actives screener.")
    except Exception as e:
        logger.warning(f"Movers screener failed ({e}); using fallback watchlist.")

    if not tickers:
        tickers = FALLBACK_WATCHLIST[: config.MAX_MOVERS_TO_SCAN]

    # Merge in pinned tickers (no duplicates), always included regardless of cap
    pinned = getattr(config, "PINNED_TICKERS", [])
    for symbol in pinned:
        if symbol not in tickers:
            tickers.append(symbol)

    if pinned:
        logger.info(f"Pinned tickers included: {pinned}")

    return tickers


def _fetch_candles(symbol: str):
    """
    Shared data-fetch helper used by both breakout and rejection checks,
    so we don't hit yfinance twice per symbol per cycle.
    Returns the cleaned dataframe, or None if unusable.
    """
    try:
        data = yf.download(
            symbol,
            period=config.STOCK_LOOKBACK_PERIOD,
            interval=config.STOCK_LOOKBACK_INTERVAL,
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        logger.warning(f"[{symbol}] yfinance download failed: {e}")
        return None

    min_candles_needed = max(16, config.MOMENTUM_MA_PERIOD + 1)
    if data is None or data.empty or len(data) < min_candles_needed:
        return None

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    return data


def check_stock_breakout(symbol: str, is_futures: bool = False, data=None):
    """
    Computes today's opening range (high/low of the session so far) and
    checks whether the latest price has broken out of that range with
    volume confirmation. If MOMENTUM_FILTER_ENABLED, also requires price
    to be on the correct side of a longer moving average.

    is_futures: when True, skips the MIN_PRICE / MIN_AVG_VOLUME equity
    filters, since those thresholds don't apply meaningfully to futures.
    data: optionally pass in pre-fetched candles to avoid a duplicate
    network call (used when also checking for rejection in the same cycle).

    Returns a dict with signal details if a breakout is detected, else None.
    """
    if data is None:
        data = _fetch_candles(symbol)
    if data is None:
        return None

    latest = data.iloc[-1]
    price = float(latest["Close"])
    volume = float(latest["Volume"])

    if not is_futures and price < config.MIN_PRICE:
        return None

    # Opening range = first N minutes of the available session data
    range_window = data.iloc[: config.OPENING_RANGE_MINUTES]
    range_high = float(range_window["High"].max())
    range_low = float(range_window["Low"].min())

    # Average volume over the lookback (excluding the current forming candle)
    avg_volume = float(data["Volume"].iloc[:-1].mean())
    if not is_futures and (avg_volume < config.MIN_AVG_VOLUME or avg_volume == 0):
        return None
    if avg_volume == 0:
        return None

    volume_confirmed = volume >= avg_volume * config.VOLUME_SPIKE_MULTIPLIER

    breakout_up = price > range_high * (1 + config.BREAKOUT_BUFFER_PCT)
    breakout_down = price < range_low * (1 - config.BREAKOUT_BUFFER_PCT)

    if not volume_confirmed or not (breakout_up or breakout_down):
        return None

    direction = "UP" if breakout_up else "DOWN"

    # Momentum/trend confirmation: price must be on the correct side of
    # the moving average for the breakout direction to count.
    if config.MOMENTUM_FILTER_ENABLED:
        ma = float(data["Close"].iloc[-config.MOMENTUM_MA_PERIOD:].mean())
        if direction == "UP" and price <= ma:
            return None
        if direction == "DOWN" and price >= ma:
            return None

    return {
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "range_high": range_high,
        "range_low": range_low,
        "volume": volume,
        "avg_volume": avg_volume,
    }


def check_stock_rejection(symbol: str, is_futures: bool = False, data=None):
    """
    Looks for a REJECTION setup: price approached a range high/low
    (within REJECTION_PROXIMITY_PCT) on a recent candle but the latest
    candle has reversed back inside the range, confirmed by volume.
    This is the opposite read of a breakout at the same level - a sign
    the level held rather than broke.

    Returns a dict with signal details if a rejection is detected, else None.
    """
    if not getattr(config, "REJECTION_SIGNALS_ENABLED", False):
        return None

    if data is None:
        data = _fetch_candles(symbol)
    if data is None:
        return None

    latest = data.iloc[-1]
    price = float(latest["Close"])
    volume = float(latest["Volume"])

    if not is_futures and price < config.MIN_PRICE:
        return None

    range_window = data.iloc[: config.OPENING_RANGE_MINUTES]
    range_high = float(range_window["High"].max())
    range_low = float(range_window["Low"].min())

    avg_volume = float(data["Volume"].iloc[:-1].mean())
    if not is_futures and (avg_volume < config.MIN_AVG_VOLUME or avg_volume == 0):
        return None
    if avg_volume == 0:
        return None

    volume_confirmed = volume >= avg_volume * config.VOLUME_SPIKE_MULTIPLIER
    if not volume_confirmed:
        return None

    proximity = config.REJECTION_PROXIMITY_PCT

    # Look at the prior candle's high/low to see if price TESTED the level...
    prior = data.iloc[-2]
    prior_high = float(prior["High"])
    prior_low = float(prior["Low"])

    tested_top = prior_high >= range_high * (1 - proximity)
    tested_bottom = prior_low <= range_low * (1 + proximity)

    # ...and the latest close has reversed back inside the range.
    rejected_top = tested_top and price < range_high and price < prior_high
    rejected_bottom = tested_bottom and price > range_low and price > prior_low

    if not (rejected_top or rejected_bottom):
        return None

    # Rejection at the top means price is likely heading DOWN, and vice versa.
    direction = "DOWN" if rejected_top else "UP"

    return {
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "range_high": range_high,
        "range_low": range_low,
        "volume": volume,
        "avg_volume": avg_volume,
    }


def scan_stocks(watchlist: list) -> dict:
    """
    Runs breakout and rejection checks across the given watchlist.
    Returns {"breakout": [...], "rejection": [...]} signal lists.
    """
    breakout_signals = []
    rejection_signals = []
    for symbol in watchlist:
        data = _fetch_candles(symbol)
        if data is None:
            continue
        breakout = check_stock_breakout(symbol, is_futures=False, data=data)
        if breakout:
            breakout_signals.append(breakout)
        rejection = check_stock_rejection(symbol, is_futures=False, data=data)
        if rejection:
            rejection_signals.append(rejection)
    return {"breakout": breakout_signals, "rejection": rejection_signals}


def scan_futures() -> dict:
    """
    Runs breakout and rejection checks across config.FUTURES_TICKERS.
    Returns {"breakout": [...], "rejection": [...]} signal lists.
    """
    if not getattr(config, "FUTURES_ENABLED", False):
        return {"breakout": [], "rejection": []}

    breakout_signals = []
    rejection_signals = []
    for symbol in config.FUTURES_TICKERS:
        data = _fetch_candles(symbol)
        if data is None:
            continue
        breakout = check_stock_breakout(symbol, is_futures=True, data=data)
        if breakout:
            breakout_signals.append(breakout)
        rejection = check_stock_rejection(symbol, is_futures=True, data=data)
        if rejection:
            rejection_signals.append(rejection)
    return {"breakout": breakout_signals, "rejection": rejection_signals}
