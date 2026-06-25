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

# ── Logging ────────────────────────────────────────────────────────
LOG_FILE = "bot.log"
