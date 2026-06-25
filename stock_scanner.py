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
    'most active' / trending screener. Falls back to a static list
    of liquid large-caps if the screener call fails for any reason.
    """
    try:
        screener = yf.screen("most_actives", count=config.MAX_MOVERS_TO_SCAN)
        quotes = screener.get("quotes", [])
        tickers = [q["symbol"] for q in quotes if "symbol" in q]
        if tickers:
            logger.info(f"Pulled {len(tickers)} tickers from most-actives screener.")
            return tickers[: config.MAX_MOVERS_TO_SCAN]
    except Exception as e:
        logger.warning(f"Movers screener failed ({e}); using fallback watchlist.")

    return FALLBACK_WATCHLIST[: config.MAX_MOVERS_TO_SCAN]


def check_stock_breakout(symbol: str):
    """
    Downloads recent 1-min candles for `symbol`, computes today's
    opening range (high/low of the session so far) and checks whether
    the latest price has broken out of that range with volume confirmation.

    Returns a dict with signal details if a breakout is detected, else None.
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

    if data is None or data.empty or len(data) < 16:
        return None  # not enough candles yet to define a range

    # Flatten multi-index columns if yfinance returns them that way
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    latest = data.iloc[-1]
    price = float(latest["Close"])
    volume = float(latest["Volume"])

    if price < config.MIN_PRICE:
        return None

    # Opening range = first N minutes of the available session data
    range_window = data.iloc[: config.OPENING_RANGE_MINUTES]
    range_high = float(range_window["High"].max())
    range_low = float(range_window["Low"].min())

    # Average volume over the lookback (excluding the current forming candle)
    avg_volume = float(data["Volume"].iloc[:-1].mean())
    if avg_volume < config.MIN_AVG_VOLUME or avg_volume == 0:
        return None

    volume_confirmed = volume >= avg_volume * config.VOLUME_SPIKE_MULTIPLIER

    breakout_up = price > range_high * (1 + config.BREAKOUT_BUFFER_PCT)
    breakout_down = price < range_low * (1 - config.BREAKOUT_BUFFER_PCT)

    if not volume_confirmed or not (breakout_up or breakout_down):
        return None

    direction = "UP" if breakout_up else "DOWN"

    return {
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "range_high": range_high,
        "range_low": range_low,
        "volume": volume,
        "avg_volume": avg_volume,
    }


def scan_stocks(watchlist: list) -> list:
    """
    Runs check_stock_breakout across the given watchlist.
    Returns a list of signal dicts for every symbol that triggered.
    """
    signals = []
    for symbol in watchlist:
        result = check_stock_breakout(symbol)
        if result:
            signals.append(result)
    return signals
