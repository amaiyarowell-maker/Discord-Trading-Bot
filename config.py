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

# ── Stock Universe ────────────────────────────────────────────────
MAX_MOVERS_TO_SCAN = 25             # shortlist size pulled from the movers feed
MIN_PRICE = 2.0                     # ignore penny stocks below this price
MIN_AVG_VOLUME = 500_000            # ignore illiquid names

# Tickers you always want scanned, regardless of whether they show up
# on the day's "movers" list. Add/remove freely.
PINNED_TICKERS = [
    # "AAPL", "TSLA",
]

# ── Futures ────────────────────────────────────────────────────────
# yfinance continuous futures tickers (free tier, no key needed).
# ES=F = E-mini S&P 500, NQ=F = E-mini Nasdaq-100.
FUTURES_ENABLED = True
FUTURES_TICKERS = ["ES=F", "NQ=F"]
# Futures data on the free tier can be a bit looser/delayed than stocks -
# this is a known tradeoff of not using a paid feed.

# ── Signal Thresholds ─────────────────────────────────────────────
VOLUME_SPIKE_MULTIPLIER = 1.5       # current volume must be >= 1.5x the recent average
BREAKOUT_BUFFER_PCT = 0.0005        # 0.05% buffer above/below range to avoid noise triggers

# ── Momentum / Trend Confirmation Filter ──────────────────────────
# A breakout only alerts if price is also on the "correct" side of a
# longer moving average - e.g. an UP breakout needs price above the MA,
# a DOWN breakout needs price below it. This cuts down on fakeouts,
# especially on fast-moving instruments like futures.
MOMENTUM_FILTER_ENABLED = True
MOMENTUM_MA_PERIOD = 20             # number of candles in the moving average

# ── BTC Settings ───────────────────────────────────────────────────
BTC_EXCHANGE = "coinbase"           # ccxt exchange id (no API key needed for public data)
BTC_SYMBOL = "BTC/USD"
BTC_CANDLE_TIMEFRAME = "1m"

# ── Cooldown (avoid spamming the same signal repeatedly) ──────────
ALERT_COOLDOWN_MINUTES = 15         # don't re-alert the same symbol+direction within this window

# ── Logging ────────────────────────────────────────────────────────
LOG_FILE = "bot.log"
