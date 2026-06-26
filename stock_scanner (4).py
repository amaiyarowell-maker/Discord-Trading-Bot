"""
Stock scanning logic:
1. Pulls a shortlist of active/moving tickers (so we never try to scan all 500+ S&P names every minute).
2. For each ticker, checks for breakout, rejection, liquidity sweep, and FVG signals.
3. Enriches qualifying signals with higher-timeframe trend, ATR-based risk levels, and a confidence score.
"""

import logging
import yfinance as yf
import pandas as pd

import config
import indicators
import smc_signals

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


def _drop_trailing_zero_volume(data):
    """
    yfinance's most recent 1-min candle is frequently still "forming" -
    Yahoo hasn't tallied its volume yet, so it reads as Volume=0 even
    though price has already updated. Comparing against that 0 makes
    volume confirmation mathematically impossible to pass.

    Drops any trailing candles with Volume == 0 so that .iloc[-1] always
    refers to the last fully-closed, real candle. Keeps at least the
    minimum candle count needed for range/MA calculations - if trimming
    would drop below that, returns None rather than returning bad data.
    """
    if data is None or data.empty:
        return None

    trimmed = data
    while len(trimmed) > 0 and float(trimmed.iloc[-1]["Volume"]) == 0:
        trimmed = trimmed.iloc[:-1]

    min_needed = max(16, config.MOMENTUM_MA_PERIOD + 1, config.OPENING_RANGE_MINUTES + 1)
    if len(trimmed) < min_needed:
        return None

    return trimmed


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
        if getattr(config, "DEBUG_SIGNAL_LOGGING", False):
            actual_len = 0 if data is None else len(data)
            logger.info(f"[{symbol}] Skipped - only {actual_len} candles available, need {min_candles_needed}.")
        return None

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    return data


def _fetch_htf_candles(symbol: str):
    """
    Fetches higher-timeframe candles (e.g. 15-min) for the HTF trend
    filter. Separate from _fetch_candles since it uses a different
    interval/period. Returns None on failure rather than raising, so
    a failed HTF fetch just disables that one filter for this symbol
    this cycle instead of blocking the whole scan.
    """
    if not getattr(config, "HTF_FILTER_ENABLED", False):
        return None
    try:
        data = yf.download(
            symbol,
            period=config.HTF_PERIOD,
            interval=config.HTF_INTERVAL,
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        logger.warning(f"[{symbol}] HTF yfinance download failed: {e}")
        return None

    if data is None or data.empty or len(data) < config.HTF_MA_PERIOD:
        return None

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    return data


def _enrich_signal(signal: dict, data: pd.DataFrame, htf_data, vix_data: dict, signal_type: str) -> dict:
    """
    Takes a raw signal dict (from breakout/rejection/sweep/FVG checks)
    and adds: HTF trend agreement, ATR-based risk levels, and a
    confidence score. Returns the enriched signal, or None if the HTF
    filter is enabled and the higher timeframe actively disagrees with
    the signal's direction (the one place this function can reject a
    signal outright, rather than just annotate it).

    FVG signals skip ATR-based risk levels (a gap is a zone to watch,
    not a breakout/rejection trade trigger), but still get HTF +
    confidence scoring.
    """
    direction = signal["direction"]

    # Higher-timeframe trend check
    htf_trend = indicators.get_htf_trend_direction(htf_data) if htf_data is not None else None
    htf_agrees = indicators.htf_trend_agrees(htf_trend, direction)
    if config.HTF_FILTER_ENABLED and htf_trend is not None and not htf_agrees:
        if getattr(config, "DEBUG_SIGNAL_LOGGING", False):
            logger.info(f"[{signal['symbol']}] HTF-CHECK signal_dir={direction} htf_trend={htf_trend} -> blocked")
        return None

    # ATR-based stop/target (skipped for FVG zones)
    risk_data = None
    if signal_type != "fvg":
        atr = indicators.calculate_atr(data)
        risk_data = indicators.calculate_stop_target(signal["price"], atr, direction)

    # Momentum pass/fail, re-derived here for scoring purposes (the
    # breakout check already enforces this as a hard gate; for other
    # signal types it's informational only, contributing to the score
    # rather than blocking the alert).
    momentum_pass = True
    if config.MOMENTUM_FILTER_ENABLED and len(data) >= config.MOMENTUM_MA_PERIOD:
        ma = float(data["Close"].iloc[-config.MOMENTUM_MA_PERIOD:].mean())
        price = signal["price"]
        momentum_pass = (direction == "UP" and price > ma) or (direction == "DOWN" and price < ma)

    confidence = None
    if getattr(config, "CONFIDENCE_SCORING_ENABLED", False):
        import confidence as confidence_module
        vol_ratio = signal["volume"] / signal["avg_volume"] if signal.get("avg_volume") else None
        confidence = confidence_module.calculate_confidence_score(
            vol_ratio=vol_ratio,
            htf_agrees=htf_agrees,
            htf_trend=htf_trend,
            momentum_pass=momentum_pass,
            vix_label=vix_data.get("label") if vix_data else None,
            signal_direction=direction,
            signal_type=signal_type,
        )
        if getattr(config, "DEBUG_SIGNAL_LOGGING", False):
            logger.info(f"[{signal['symbol']}] CONFIDENCE-SCORE {confidence['total']}/100 breakdown={confidence['breakdown']}")

        min_required = getattr(config, "MIN_CONFIDENCE_TO_ALERT", 0)
        if confidence["total"] < min_required:
            if getattr(config, "DEBUG_SIGNAL_LOGGING", False):
                logger.info(f"[{signal['symbol']}] Suppressed - confidence {confidence['total']} below minimum {min_required}.")
            return None

    signal["risk_data"] = risk_data
    signal["confidence"] = confidence
    signal["htf_trend"] = htf_trend
    signal["signal_type"] = signal_type
    return signal


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

    # Drop any trailing still-forming candle(s) with no tallied volume yet,
    # so the "latest" candle used below always has real, finalized volume.
    data = _drop_trailing_zero_volume(data)
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

    # Average volume over the lookback (excluding the current candle)
    avg_volume = float(data["Volume"].iloc[:-1].mean())
    if not is_futures and (avg_volume < config.MIN_AVG_VOLUME or avg_volume == 0):
        return None
    if avg_volume == 0:
        return None

    volume_confirmed = volume >= avg_volume * config.VOLUME_SPIKE_MULTIPLIER

    breakout_up = price > range_high * (1 + config.BREAKOUT_BUFFER_PCT)
    breakout_down = price < range_low * (1 - config.BREAKOUT_BUFFER_PCT)

    if getattr(config, "DEBUG_SIGNAL_LOGGING", False):
        logger.info(
            f"[{symbol}] BREAKOUT-CHECK price={price:.2f} range=({range_low:.2f},{range_high:.2f}) "
            f"vol={volume:.0f} avg_vol={avg_volume:.0f} vol_ratio={volume/avg_volume:.2f}x "
            f"breakout_up={breakout_up} breakout_down={breakout_down} vol_confirmed={volume_confirmed}"
        )

    if not volume_confirmed or not (breakout_up or breakout_down):
        return None

    direction = "UP" if breakout_up else "DOWN"

    # Momentum/trend confirmation: price must be on the correct side of
    # the moving average for the breakout direction to count.
    if config.MOMENTUM_FILTER_ENABLED:
        ma = float(data["Close"].iloc[-config.MOMENTUM_MA_PERIOD:].mean())
        momentum_pass = (direction == "UP" and price > ma) or (direction == "DOWN" and price < ma)
        if getattr(config, "DEBUG_SIGNAL_LOGGING", False):
            logger.info(f"[{symbol}] MOMENTUM-CHECK direction={direction} price={price:.2f} ma={ma:.2f} pass={momentum_pass}")
        if not momentum_pass:
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

    # Drop any trailing still-forming candle(s) with no tallied volume yet,
    # so -1/-2 indexing below always refers to real, finalized candles.
    data = _drop_trailing_zero_volume(data)
    if data is None or len(data) < 2:
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


def scan_stocks(watchlist: list, vix_data: dict = None) -> dict:
    """
    Runs breakout, rejection, liquidity sweep, and FVG checks across the
    given watchlist. Each qualifying signal is enriched with HTF trend
    agreement, ATR-based risk levels, and a confidence score.
    Returns {"breakout": [...], "rejection": [...], "sweep": [...], "fvg": [...]}.
    """
    results = {"breakout": [], "rejection": [], "sweep": [], "fvg": []}
    for symbol in watchlist:
        data = _fetch_candles(symbol)
        if data is None:
            continue

        htf_data = _fetch_htf_candles(symbol)

        breakout = check_stock_breakout(symbol, is_futures=False, data=data)
        if breakout:
            enriched = _enrich_signal(breakout, data, htf_data, vix_data, "breakout")
            if enriched:
                results["breakout"].append(enriched)

        rejection = check_stock_rejection(symbol, is_futures=False, data=data)
        if rejection:
            enriched = _enrich_signal(rejection, data, htf_data, vix_data, "rejection")
            if enriched:
                results["rejection"].append(enriched)

        sweep = smc_signals.check_liquidity_sweep(data, symbol)
        if sweep:
            enriched = _enrich_signal(sweep, data, htf_data, vix_data, "liquidity_sweep")
            if enriched:
                results["sweep"].append(enriched)

        fvg = smc_signals.check_fair_value_gap(data, symbol)
        if fvg:
            enriched = _enrich_signal(fvg, data, htf_data, vix_data, "fvg")
            if enriched:
                results["fvg"].append(enriched)

    return results


def scan_futures(vix_data: dict = None) -> dict:
    """
    Runs breakout, rejection, liquidity sweep, and FVG checks across
    config.FUTURES_TICKERS, with the same enrichment as scan_stocks.
    Returns {"breakout": [...], "rejection": [...], "sweep": [...], "fvg": [...]}.
    """
    results = {"breakout": [], "rejection": [], "sweep": [], "fvg": []}
    if not getattr(config, "FUTURES_ENABLED", False):
        return results

    for symbol in config.FUTURES_TICKERS:
        data = _fetch_candles(symbol)
        if data is None:
            continue

        htf_data = _fetch_htf_candles(symbol)

        breakout = check_stock_breakout(symbol, is_futures=True, data=data)
        if breakout:
            enriched = _enrich_signal(breakout, data, htf_data, vix_data, "breakout")
            if enriched:
                results["breakout"].append(enriched)

        rejection = check_stock_rejection(symbol, is_futures=True, data=data)
        if rejection:
            enriched = _enrich_signal(rejection, data, htf_data, vix_data, "rejection")
            if enriched:
                results["rejection"].append(enriched)

        sweep = smc_signals.check_liquidity_sweep(data, symbol)
        if sweep:
            enriched = _enrich_signal(sweep, data, htf_data, vix_data, "liquidity_sweep")
            if enriched:
                results["sweep"].append(enriched)

        fvg = smc_signals.check_fair_value_gap(data, symbol)
        if fvg:
            enriched = _enrich_signal(fvg, data, htf_data, vix_data, "fvg")
            if enriched:
                results["fvg"].append(enriched)

    return results
