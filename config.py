"""
Configuration for the Stock + BTC Discord Alert Bot.
Edit these values to tune behavior without touching the core logic.
"""

import os

# ── Discord Webhooks ──────────────────────────────────────────────
# Create these in Discord: Channel Settings -> Integrations -> Webhooks -> New Webhook -> Copy URL
# Set as environment variables (recommended) or paste directly as fallback strings below.
STOCK_WEBHOOK_URL = os.environ.get("STOCK_WEBHOOK_URL", "PASTE_STOCK_WEBHOOK_URL_HERE")
BTC_WEBHOOK_URL = os.environ.get("BTC_WEBHOOK_URL", "PASTE_BTC_WEBHOOK_URL_HERE")
# Optional separate channel for futures. If left as-is (not set), futures
# alerts will just post to the STOCK_WEBHOOK_URL instead.
FUTURES_WEBHOOK_URL = os.environ.get("FUTURES_WEBHOOK_URL", "")

# ── Scan Timing ───────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS = 60          # how often the main loop runs (1 min)
OPENING_RANGE_MINUTES = 15          # rolling range window for BTC breakout logic
STOCK_LOOKBACK_PERIOD = "1d"        # yfinance lookback window for stocks
STOCK_LOOKBACK_INTERVAL = "1m"      # yfinance candle interval for stocks

# Skip stock/futures scanning entirely outside regular US market hours
# (9:30 AM - 4:00 PM Eastern, Mon-Fri). BTC keeps scanning 24/7 regardless,
# since crypto markets never close. This saves wasted API calls and avoids
# alerting on stale/closed-market data.
MARKET_HOURS_ONLY = True
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
MARKET_TIMEZONE = "America/New_York"

# ── Stock Universe ────────────────────────────────────────────────
MAX_MOVERS_TO_SCAN = 25             # shortlist size pulled from the movers feed
MIN_PRICE = 2.0                     # ignore penny stocks below this price
MIN_AVG_VOLUME = 500_000            # ignore illiquid names

# Tickers you always want scanned, regardless of whether they show up
# on the day's "movers" list. Add/remove freely.
PINNED_TICKERS = [
    "SPY",
    "TSLA",
]

# ── Futures ────────────────────────────────────────────────────────
# yfinance continuous futures tickers (free tier, no key needed).
# ES=F = E-mini S&P 500, NQ=F = E-mini Nasdaq-100.
FUTURES_ENABLED = True
FUTURES_TICKERS = ["ES=F", "NQ=F"]
# Futures data on the free tier can be a bit looser/delayed than stocks -
# this is a known tradeoff of not using a paid feed.

# ── Signal Thresholds ─────────────────────────────────────────────
VOLUME_SPIKE_MULTIPLIER = 1.2       # current volume must be >= 1.2x the recent average (loosened from 1.5x)
BREAKOUT_BUFFER_PCT = 0.0002        # 0.02% buffer above/below range to avoid noise triggers (loosened from 0.05%)

# ── Momentum / Trend Confirmation Filter ──────────────────────────
# A breakout only alerts if price is also on the "correct" side of a
# longer moving average - e.g. an UP breakout needs price above the MA,
# a DOWN breakout needs price below it. This cuts down on fakeouts,
# especially on fast-moving instruments like futures.
MOMENTUM_FILTER_ENABLED = True
MOMENTUM_MA_PERIOD = 10             # number of candles in the moving average (shortened from 20, reacts faster to sharp moves)

# ── Rejection / Reversal Signals ──────────────────────────────────
# A DIFFERENT signal from breakout: price approaches a range high/low,
# fails to close beyond it, and reverses back - confirmed by volume.
# This catches "tested and held" setups, the opposite read of a breakout
# at the same level. Posts as a separate, clearly labeled alert type.
REJECTION_SIGNALS_ENABLED = True
# How close price must get to the range edge (as a % of price) to count
# as "testing" the level before reversing.
REJECTION_PROXIMITY_PCT = 0.0015    # 0.15% (loosened from 0.1%)
# Volume confirmation reuses VOLUME_SPIKE_MULTIPLIER above.

# ── BTC Settings ───────────────────────────────────────────────────
BTC_EXCHANGE = "coinbase"           # ccxt exchange id (no API key needed for public data)
BTC_SYMBOL = "BTC/USD"
BTC_CANDLE_TIMEFRAME = "1m"

# ── Cooldown (avoid spamming the same signal repeatedly) ──────────
ALERT_COOLDOWN_MINUTES = 15         # don't re-alert the same symbol+direction within this window

# ── Higher Timeframe Trend Filter ─────────────────────────────────
# Checks a longer timeframe (e.g. 15-min) alongside the 1-min signal -
# an alert only fires if the higher timeframe trend agrees with the
# direction of the 1-min signal. This is DIFFERENT from the same-
# timeframe MOMENTUM_FILTER above; it's a second, independent check
# at a higher zoom level, which catches a different kind of fakeout
# (e.g. a 1-min breakout against the prevailing 15-min downtrend).
HTF_FILTER_ENABLED = True
HTF_INTERVAL = "15m"                # higher timeframe candle interval
HTF_PERIOD = "5d"                   # lookback window needed to get enough 15m candles
HTF_MA_PERIOD = 20                  # moving average period on the higher timeframe

# ── Liquidity Sweep / Fair Value Gap (FVG) Signals ────────────────
# A THIRD signal type, distinct from breakout and rejection:
# - Liquidity sweep: price wicks beyond a recent swing high/low (grabbing
#   resting stop orders) then closes back on the other side - similar
#   shape to a rejection, but specifically measured against recent
#   swing points rather than the opening range.
# - FVG (Fair Value Gap): a 3-candle imbalance where candle 1's high/low
#   doesn't overlap with candle 3's low/high, leaving a "gap" in price
#   that often gets revisited. Detected here as a standalone notable
#   zone, posted as a separate alert type.
SMC_SIGNALS_ENABLED = True
SWING_LOOKBACK_CANDLES = 10         # how many candles back to look for the swing high/low being swept
SWEEP_PROXIMITY_PCT = 0.0015        # how close price must wick beyond the swing point to count as a sweep
FVG_MIN_GAP_PCT = 0.0008            # minimum gap size (% of price) for an FVG to be considered notable

# ── ATR-Based Stops & Risk Management ─────────────────────────────
# Every alert now includes a suggested entry, stop-loss, take-profit,
# and resulting risk:reward ratio - calculated from ATR (Average True
# Range), not a fixed dollar/percent. This is a SUGGESTION only, not
# financial advice or an automated trade - you still decide position
# size and whether to take the trade.
ATR_PERIOD = 14                     # candles used to calculate ATR
ATR_STOP_MULTIPLIER = 1.5           # stop-loss distance = ATR x this multiplier
ATR_TARGET_MULTIPLIER = 3.0         # take-profit distance = ATR x this multiplier (2:1 R:R by default)

# ── Market Sentiment (VIX) ────────────────────────────────────────
# Pulled ONCE per cycle (not per-symbol) since it's market-wide context,
# not a per-symbol indicator. Used to flag elevated-fear conditions and
# as one input into the confidence score below. Free via yfinance, no
# key needed - ticker ^VIX.
SENTIMENT_ENABLED = True
VIX_TICKER = "^VIX"
VIX_HIGH_FEAR_THRESHOLD = 25        # VIX above this = elevated fear / less reliable breakouts
VIX_LOW_FEAR_THRESHOLD = 15         # VIX below this = complacent / calmer conditions

# ── Confidence Scoring ─────────────────────────────────────────────
# Combines volume strength, HTF agreement, momentum alignment, and VIX
# context into a single 0-100 score shown on every alert, so signals
# can be ranked by conviction instead of being a flat pass/fail.
CONFIDENCE_SCORING_ENABLED = True
# Minimum score required to actually send an alert. Signals that pass
# every gate but score below this are suppressed as low-conviction.
# Set to 0 to disable score-based suppression and just display the score.
MIN_CONFIDENCE_TO_ALERT = 40

# ── Logging ────────────────────────────────────────────────────────
LOG_FILE = "bot.log"

# ── Debugging ──────────────────────────────────────────────────────
# When True, logs the exact computed values (price, range, volume ratio,
# moving average) for every symbol every cycle, so you can see exactly
# why a signal did or didn't fire. Very chatty - turn off once things
# are working as expected.
DEBUG_SIGNAL_LOGGING = True
