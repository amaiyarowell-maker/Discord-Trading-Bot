"""
Smart Money Concepts (SMC) style signals: liquidity sweeps and Fair
Value Gaps (FVGs). These are a THIRD signal type, distinct from both
breakout and rejection - they look at recent swing points and 3-candle
imbalances rather than the session opening range.

Liquidity sweep: price wicks beyond a recent swing high/low (where
resting stop orders are likely clustered), then closes back on the
other side. Similar shape to a rejection signal, but measured against
the most recent local swing point rather than the session's opening
range - catches a different, often shorter-term setup.

Fair Value Gap (FVG): a 3-candle imbalance where candle 1's high
doesn't overlap with candle 3's low (bullish FVG) or candle 1's low
doesn't overlap with candle 3's high (bearish FVG). This leaves a
"gap" in traded price that the market often revisits later.
"""

import logging
import pandas as pd

import config

logger = logging.getLogger("smc_signals")


def find_swing_high_low(data: pd.DataFrame, lookback: int = None) -> dict:
    """
    Finds the most recent swing high and swing low over the lookback
    window, EXCLUDING the most recent 2 candles (so the swing point
    being tested is a real prior point, not the current/forming move
    itself).
    """
    if lookback is None:
        lookback = config.SWING_LOOKBACK_CANDLES

    if data is None or len(data) < lookback + 2:
        return {"swing_high": None, "swing_low": None}

    window = data.iloc[-(lookback + 2):-2]
    if window.empty:
        return {"swing_high": None, "swing_low": None}

    return {
        "swing_high": float(window["High"].max()),
        "swing_low": float(window["Low"].min()),
    }


def check_liquidity_sweep(data: pd.DataFrame, symbol: str) -> dict:
    """
    Checks the prior candle for a wick beyond the recent swing high/low
    that gets rejected (closes back inside) on the latest candle,
    confirmed by volume. Mirrors the rejection signal's two-candle
    pattern, but against swing points instead of the opening range.

    Returns a signal dict if detected, else None.
    """
    if not getattr(config, "SMC_SIGNALS_ENABLED", False):
        return None

    if data is None or len(data) < config.SWING_LOOKBACK_CANDLES + 2:
        return None

    swings = find_swing_high_low(data)
    swing_high = swings["swing_high"]
    swing_low = swings["swing_low"]
    if swing_high is None or swing_low is None:
        return None

    prior = data.iloc[-2]
    latest = data.iloc[-1]

    price = float(latest["Close"])
    volume = float(latest["Volume"])
    avg_volume = float(data["Volume"].iloc[:-1].mean())

    if avg_volume == 0:
        return None

    volume_confirmed = volume >= avg_volume * config.VOLUME_SPIKE_MULTIPLIER

    prior_high = float(prior["High"])
    prior_low = float(prior["Low"])

    swept_high = prior_high > swing_high * (1 + config.SWEEP_PROXIMITY_PCT)
    swept_low = prior_low < swing_low * (1 - config.SWEEP_PROXIMITY_PCT)

    # After sweeping the high, price should close back BELOW the swing high (expect DOWN)
    rejected_after_high_sweep = swept_high and price < swing_high
    # After sweeping the low, price should close back ABOVE the swing low (expect UP)
    rejected_after_low_sweep = swept_low and price > swing_low

    if not volume_confirmed or not (rejected_after_high_sweep or rejected_after_low_sweep):
        return None

    direction = "DOWN" if rejected_after_high_sweep else "UP"
    swept_level = swing_high if rejected_after_high_sweep else swing_low

    return {
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "swept_level": swept_level,
        "volume": volume,
        "avg_volume": avg_volume,
        "signal_type": "liquidity_sweep",
    }


def check_fair_value_gap(data: pd.DataFrame, symbol: str) -> dict:
    """
    Checks the last 3 candles for a Fair Value Gap:
    - Bullish FVG: candle[-3].High < candle[-1].Low (gap left below current price)
    - Bearish FVG: candle[-3].Low > candle[-1].High (gap left above current price)

    Only flags gaps at least FVG_MIN_GAP_PCT of price in size, to avoid
    flagging negligible micro-gaps that aren't actually tradeable zones.

    Returns a signal dict if a notable gap is found, else None.
    """
    if not getattr(config, "SMC_SIGNALS_ENABLED", False):
        return None

    if data is None or len(data) < 3:
        return None

    c1 = data.iloc[-3]
    c3 = data.iloc[-1]
    price = float(c3["Close"])

    bullish_gap = float(c1["High"]) < float(c3["Low"])
    bearish_gap = float(c1["Low"]) > float(c3["High"])

    if not (bullish_gap or bearish_gap):
        return None

    if bullish_gap:
        gap_size = float(c3["Low"]) - float(c1["High"])
        gap_top = float(c3["Low"])
        gap_bottom = float(c1["High"])
        direction = "UP"
    else:
        gap_size = float(c1["Low"]) - float(c3["High"])
        gap_top = float(c1["Low"])
        gap_bottom = float(c3["High"])
        direction = "DOWN"

    gap_pct = gap_size / price if price else 0
    if gap_pct < config.FVG_MIN_GAP_PCT:
        return None

    return {
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "gap_top": gap_top,
        "gap_bottom": gap_bottom,
        "gap_pct": round(gap_pct * 100, 3),
        "signal_type": "fvg",
    }
