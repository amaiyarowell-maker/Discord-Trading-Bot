"""
Shared technical indicator calculations used across the stock and BTC
scanners: ATR (for stops/targets) and higher-timeframe trend direction.

Kept separate from the scanner modules so the math is defined once and
tested once, rather than duplicated per asset class.
"""

import logging
import pandas as pd

import config

logger = logging.getLogger("indicators")


def calculate_atr(data: pd.DataFrame, period: int = None) -> float:
    """
    Calculates Average True Range over the given OHLC dataframe.
    True Range for each candle = max of:
      - high - low
      - abs(high - previous close)
      - abs(low - previous close)
    ATR = simple moving average of True Range over `period` candles.

    Returns the most recent ATR value as a float, or None if there
    isn't enough data to compute it.
    """
    if period is None:
        period = config.ATR_PERIOD

    if data is None or len(data) < period + 1:
        return None

    high = data["High"]
    low = data["Low"]
    prev_close = data["Close"].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean().iloc[-1]

    if pd.isna(atr):
        return None

    return float(atr)


def calculate_stop_target(entry_price: float, atr: float, direction: str) -> dict:
    """
    Given an entry price, ATR value, and direction ("UP" or "DOWN"),
    returns suggested stop-loss, take-profit, and the resulting
    risk:reward ratio. This is a suggestion based on volatility, not
    a guarantee or financial advice - position sizing and the actual
    decision to trade are left to the person reading the alert.
    """
    if atr is None or atr <= 0:
        return {"entry": entry_price, "stop": None, "target": None, "risk_reward": None}

    stop_distance = atr * config.ATR_STOP_MULTIPLIER
    target_distance = atr * config.ATR_TARGET_MULTIPLIER

    if direction == "UP":
        stop = entry_price - stop_distance
        target = entry_price + target_distance
    else:  # DOWN
        stop = entry_price + stop_distance
        target = entry_price - target_distance

    risk = abs(entry_price - stop)
    reward = abs(target - entry_price)
    risk_reward = round(reward / risk, 2) if risk > 0 else None

    return {
        "entry": round(entry_price, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "risk_reward": risk_reward,
    }


def get_htf_trend_direction(htf_data: pd.DataFrame) -> str:
    """
    Given higher-timeframe OHLC data, returns "UP", "DOWN", or "FLAT"
    based on whether the latest close is above, below, or at the
    HTF_MA_PERIOD moving average.

    Returns None if there isn't enough data to compute the MA.
    """
    if htf_data is None or len(htf_data) < config.HTF_MA_PERIOD:
        return None

    closes = htf_data["Close"].iloc[-config.HTF_MA_PERIOD:]
    ma = float(closes.mean())
    latest_close = float(htf_data["Close"].iloc[-1])

    if latest_close > ma:
        return "UP"
    elif latest_close < ma:
        return "DOWN"
    return "FLAT"


def htf_trend_agrees(htf_trend: str, signal_direction: str) -> bool:
    """
    Checks whether a higher-timeframe trend agrees with a signal's
    direction. "FLAT" or None trend is treated as neutral (does not
    block the signal) since there's no clear HTF bias to contradict.
    """
    if htf_trend is None or htf_trend == "FLAT":
        return True
    return htf_trend == signal_direction
