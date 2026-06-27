"""
Early Momentum signals: the fastest, least-confirmed signal type in
the bot. Deliberately does NOT require a broken range, a higher
timeframe trend check, or a momentum-MA filter - all of those are
inherently lagging (they need a range to already be broken, or a
trend to already be established). This signal instead looks at the
last 2-3 candles directly for a sudden acceleration in price AND
volume, moving the same direction.

The tradeoff is explicit: this catches moves earlier, but with less
confirmation, so it will produce more false signals than breakout,
rejection, or liquidity sweep. It's meant to complement those, not
replace them - use it as "something is accelerating right now, worth
a look," not "definitely a clean setup."
"""

import logging
import pandas as pd

import config

logger = logging.getLogger("momentum_signals")


def check_early_momentum(data: pd.DataFrame, symbol: str) -> dict:
    """
    Looks at the most recent few candles for:
      1. Price acceleration: the latest candle's % move is meaningfully
         larger than the recent average candle-to-candle % move.
      2. Volume acceleration: latest candle's volume is a multiple of
         the recent average (same VOLUME_SPIKE_MULTIPLIER used elsewhere).
      3. Directional consistency: the last EARLY_MOMENTUM_CONFIRM_CANDLES
         candles are all moving the same direction, so a single noisy
         spike doesn't qualify on its own.

    No range, HTF, or momentum-MA requirement - this is intentionally
    the most reactive signal type. Returns a signal dict if detected,
    else None.
    """
    if not getattr(config, "EARLY_MOMENTUM_ENABLED", False):
        return None

    confirm_n = getattr(config, "EARLY_MOMENTUM_CONFIRM_CANDLES", 3)
    lookback = getattr(config, "EARLY_MOMENTUM_LOOKBACK_CANDLES", 20)
    min_needed = lookback + confirm_n + 1

    if data is None or len(data) < min_needed:
        return None

    recent = data.iloc[-(lookback + confirm_n):]
    confirm_window = recent.iloc[-confirm_n:]
    baseline_window = recent.iloc[:-confirm_n]

    if baseline_window.empty or confirm_window.empty:
        return None

    latest = confirm_window.iloc[-1]
    price = float(latest["Close"])
    volume = float(latest["Volume"])

    # Directional consistency: every candle in the confirm window moves
    # the same way (close > open for UP, close < open for DOWN).
    confirm_closes_up = (confirm_window["Close"] > confirm_window["Open"]).all()
    confirm_closes_down = (confirm_window["Close"] < confirm_window["Open"]).all()
    if not (confirm_closes_up or confirm_closes_down):
        return None
    direction = "UP" if confirm_closes_up else "DOWN"

    # Price acceleration: latest candle's % move vs. the baseline average
    # candle-to-candle % move.
    baseline_pct_moves = (baseline_window["Close"] - baseline_window["Open"]).abs() / baseline_window["Open"]
    baseline_avg_pct = float(baseline_pct_moves.mean())
    latest_pct_move = abs(float(latest["Close"]) - float(latest["Open"])) / float(latest["Open"]) if latest["Open"] else 0

    if baseline_avg_pct == 0:
        return None

    acceleration_multiplier = getattr(config, "EARLY_MOMENTUM_PRICE_ACCEL_MULTIPLIER", 2.0)
    price_accelerated = latest_pct_move >= baseline_avg_pct * acceleration_multiplier

    # Volume acceleration, same approach as the other signal types.
    avg_volume = float(baseline_window["Volume"].mean())
    if avg_volume == 0:
        return None
    volume_confirmed = volume >= avg_volume * config.VOLUME_SPIKE_MULTIPLIER

    if getattr(config, "DEBUG_SIGNAL_LOGGING", False):
        logger.info(
            f"[{symbol}] EARLY-MOMENTUM-CHECK direction={direction} price={price:.2f} "
            f"latest_pct={latest_pct_move:.4f} baseline_pct={baseline_avg_pct:.4f} "
            f"price_accelerated={price_accelerated} vol_ratio={volume/avg_volume:.2f}x vol_confirmed={volume_confirmed}"
        )

    if not (price_accelerated and volume_confirmed):
        return None

    return {
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "volume": volume,
        "avg_volume": avg_volume,
        "price_accel_ratio": round(latest_pct_move / baseline_avg_pct, 2) if baseline_avg_pct else None,
        "signal_type": "early_momentum",
    }
