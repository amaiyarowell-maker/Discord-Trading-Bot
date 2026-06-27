"""
BTC scanning logic using a rolling opening-range breakout, since crypto
trades 24/7 and has no single daily "open" the way equities do.

Uses ccxt's public market data endpoints (no API key required for
reading candles from most exchanges). Candle data is converted to a
pandas DataFrame so the same indicators.py / smc_signals.py /
confidence.py logic used for stocks can be reused here without
duplicating the math in a separate raw-list form.
"""

import logging
import ccxt
import pandas as pd

import config
import indicators
import smc_signals
import momentum_signals

logger = logging.getLogger("btc_scanner")

_exchange = None


def _get_exchange():
    global _exchange
    if _exchange is None:
        exchange_class = getattr(ccxt, config.BTC_EXCHANGE)
        _exchange = exchange_class({"enableRateLimit": True})
    return _exchange


def _ohlcv_to_dataframe(ohlcv: list) -> pd.DataFrame:
    """Converts ccxt's raw OHLCV list format into the same DataFrame shape used by the stock scanner."""
    df = pd.DataFrame(ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
    return df


def _fetch_btc_ohlcv():
    """
    Shared fetch helper for BTC candles, used by breakout, rejection,
    sweep, and FVG checks so we only hit the exchange once per cycle.
    Returns a pandas DataFrame, or None if unusable.
    """
    exchange = _get_exchange()
    limit = config.OPENING_RANGE_MINUTES + max(15, config.MOMENTUM_MA_PERIOD, config.SWING_LOOKBACK_CANDLES) + 5

    try:
        ohlcv = exchange.fetch_ohlcv(config.BTC_SYMBOL, timeframe=config.BTC_CANDLE_TIMEFRAME, limit=limit)
    except Exception as e:
        logger.warning(f"ccxt fetch_ohlcv failed: {e}")
        return None

    if not ohlcv or len(ohlcv) < config.OPENING_RANGE_MINUTES + 1:
        return None

    return _ohlcv_to_dataframe(ohlcv)


def _fetch_btc_htf():
    """
    Fetches higher-timeframe BTC candles (e.g. 15-min) for the HTF
    trend filter. Returns None on failure so the filter is just
    skipped for this cycle rather than blocking the whole scan.
    """
    if not getattr(config, "HTF_FILTER_ENABLED", False):
        return None

    exchange = _get_exchange()
    try:
        ohlcv = exchange.fetch_ohlcv(config.BTC_SYMBOL, timeframe=config.HTF_INTERVAL, limit=config.HTF_MA_PERIOD + 5)
    except Exception as e:
        logger.warning(f"ccxt HTF fetch_ohlcv failed: {e}")
        return None

    if not ohlcv or len(ohlcv) < config.HTF_MA_PERIOD:
        return None

    return _ohlcv_to_dataframe(ohlcv)



def _drop_trailing_zero_volume(data: pd.DataFrame):
    """
    Same fix as the stock scanner: the most recently formed candle from
    the exchange may have Volume=0 if it hasn't been fully tallied yet.
    Drops trailing zero-volume candles so .iloc[-1] always refers to a
    real, finalized candle. Returns None if trimming would drop below
    the minimum candles needed for range/MA/swing calculations.
    """
    if data is None or data.empty:
        return None

    trimmed = data
    while len(trimmed) > 0 and float(trimmed.iloc[-1]["Volume"]) == 0:
        trimmed = trimmed.iloc[:-1]

    min_needed = max(
        config.OPENING_RANGE_MINUTES + 2,
        config.MOMENTUM_MA_PERIOD + 1,
        config.SWING_LOOKBACK_CANDLES + 2,
    )
    if len(trimmed) < min_needed:
        return None

    return trimmed


def check_btc_breakout(data: pd.DataFrame = None):
    """
    Builds a rolling opening range from the last OPENING_RANGE_MINUTES
    candles (excluding the current forming candle), and checks whether
    the latest price has broken out of that range with volume confirmation.

    data: optionally pass pre-fetched candles to avoid a duplicate
    network call (used when also checking rejection/sweep/fvg in the
    same cycle).

    Returns a signal dict if triggered, else None.
    """
    if data is None:
        data = _fetch_btc_ohlcv()
    if data is None:
        return None

    data = _drop_trailing_zero_volume(data)
    if data is None:
        return None

    latest = data.iloc[-1]
    price = float(latest["Close"])
    volume = float(latest["Volume"])

    range_window = data.iloc[-(config.OPENING_RANGE_MINUTES + 1):-1]
    if range_window.empty:
        return None
    range_high = float(range_window["High"].max())
    range_low = float(range_window["Low"].min())
    avg_volume = float(range_window["Volume"].mean())

    if avg_volume == 0:
        return None

    volume_confirmed = volume >= avg_volume * config.VOLUME_SPIKE_MULTIPLIER

    breakout_up = price > range_high * (1 + config.BREAKOUT_BUFFER_PCT)
    breakout_down = price < range_low * (1 - config.BREAKOUT_BUFFER_PCT)

    if getattr(config, "DEBUG_SIGNAL_LOGGING", False):
        logger.info(
            f"[BTC/USD] BREAKOUT-CHECK price={price:.2f} range=({range_low:.2f},{range_high:.2f}) "
            f"vol={volume:.4f} avg_vol={avg_volume:.4f} vol_ratio={volume/avg_volume:.2f}x "
            f"breakout_up={breakout_up} breakout_down={breakout_down} vol_confirmed={volume_confirmed}"
        )

    if not volume_confirmed or not (breakout_up or breakout_down):
        return None

    direction = "UP" if breakout_up else "DOWN"

    if config.MOMENTUM_FILTER_ENABLED and len(data) >= config.MOMENTUM_MA_PERIOD:
        ma = float(data["Close"].iloc[-config.MOMENTUM_MA_PERIOD:].mean())
        momentum_pass = (direction == "UP" and price > ma) or (direction == "DOWN" and price < ma)
        if not momentum_pass:
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


def check_btc_rejection(data: pd.DataFrame = None):
    """
    Looks for a REJECTION setup on BTC: price approached the rolling
    range high/low on the prior candle but the latest candle has
    reversed back inside the range, confirmed by volume.

    Returns a signal dict if a rejection is detected, else None.
    """
    if not getattr(config, "REJECTION_SIGNALS_ENABLED", False):
        return None

    if data is None:
        data = _fetch_btc_ohlcv()
    if data is None:
        return None

    data = _drop_trailing_zero_volume(data)
    if data is None or len(data) < config.OPENING_RANGE_MINUTES + 2:
        return None

    latest = data.iloc[-1]
    prior = data.iloc[-2]
    price = float(latest["Close"])
    volume = float(latest["Volume"])
    prior_high = float(prior["High"])
    prior_low = float(prior["Low"])

    range_window = data.iloc[-(config.OPENING_RANGE_MINUTES + 2):-2]
    if range_window.empty:
        return None
    range_high = float(range_window["High"].max())
    range_low = float(range_window["Low"].min())
    avg_volume = float(range_window["Volume"].mean())

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


def _enrich_btc_signal(signal: dict, data: pd.DataFrame, htf_data, vix_data: dict, signal_type: str) -> dict:
    """
    Same enrichment as the stock scanner's _enrich_signal: adds HTF
    trend agreement, ATR-based risk levels, and a confidence score.
    Kept as a near-duplicate (rather than importing stock_scanner's
    version) to avoid a cross-module dependency between the two
    scanners - they're independent asset classes that happen to share
    the underlying indicators/smc_signals/confidence modules.
    """
    direction = signal["direction"]

    htf_trend = indicators.get_htf_trend_direction(htf_data) if htf_data is not None else None
    htf_agrees = indicators.htf_trend_agrees(htf_trend, direction)
    htf_blocks = config.HTF_FILTER_ENABLED and htf_trend is not None and not htf_agrees
    if htf_blocks and signal_type != "early_momentum":
        return None

    risk_data = None
    if signal_type != "fvg":
        atr = indicators.calculate_atr(data)
        risk_data = indicators.calculate_stop_target(signal["price"], atr, direction)

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
        min_required = getattr(config, "MIN_CONFIDENCE_TO_ALERT", 0)
        if confidence["total"] < min_required:
            return None

    signal["risk_data"] = risk_data
    signal["confidence"] = confidence
    signal["htf_trend"] = htf_trend

    is_a_plus = False
    if confidence is not None and signal_type != "early_momentum":
        import confidence as confidence_module
        risk_reward = risk_data.get("risk_reward") if risk_data else None
        is_a_plus = confidence_module.is_a_plus_setup(
            confidence_total=confidence["total"],
            htf_trend=htf_trend,
            htf_agrees=htf_agrees,
            risk_reward=risk_reward,
        )
    signal["is_a_plus"] = is_a_plus
    signal["signal_type"] = signal_type
    return signal


def scan_btc(vix_data: dict = None) -> dict:
    """
    Runs breakout, rejection, liquidity sweep, FVG, and early momentum
    checks for BTC, with the same enrichment (HTF trend, ATR risk,
    confidence score) as the stock scanner. Returns one signal max per
    type (BTC is a single symbol, unlike the stock watchlist loop).
    """
    results = {"breakout": [], "rejection": [], "sweep": [], "fvg": [], "early_momentum": []}

    data = _fetch_btc_ohlcv()
    if data is None:
        return results

    htf_data = _fetch_btc_htf()

    breakout = check_btc_breakout(data=data)
    if breakout:
        enriched = _enrich_btc_signal(breakout, data, htf_data, vix_data, "breakout")
        if enriched:
            results["breakout"].append(enriched)

    rejection = check_btc_rejection(data=data)
    if rejection:
        enriched = _enrich_btc_signal(rejection, data, htf_data, vix_data, "rejection")
        if enriched:
            results["rejection"].append(enriched)

    sweep = smc_signals.check_liquidity_sweep(data, "BTC/USD")
    if sweep:
        enriched = _enrich_btc_signal(sweep, data, htf_data, vix_data, "liquidity_sweep")
        if enriched:
            results["sweep"].append(enriched)

    fvg = smc_signals.check_fair_value_gap(data, "BTC/USD")
    if fvg:
        enriched = _enrich_btc_signal(fvg, data, htf_data, vix_data, "fvg")
        if enriched:
            results["fvg"].append(enriched)

    early_momentum = momentum_signals.check_early_momentum(data, "BTC/USD")
    if early_momentum:
        enriched = _enrich_btc_signal(early_momentum, data, htf_data, vix_data, "early_momentum")
        if enriched:
            results["early_momentum"].append(enriched)

    return results
