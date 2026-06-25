# Stock + BTC Discord Alert Bot

Scans a dynamic shortlist of actively-moving stocks plus BTC for breakouts confirmed by volume spikes, and posts alerts to Discord.

## How it works

- **Stocks:** Every minute, pulls a shortlist of ~25 currently active/moving tickers (so it never tries to brute-force scan the whole S&P 500), plus any tickers you've pinned in `config.py`. For each, checks if price has broken above/below the day's opening range AND volume is at least 1.5x the recent average AND (if enabled) price is trend-aligned via a moving average filter.
- **Futures (ES/NQ):** Same breakout + volume + momentum logic, applied to the E-mini S&P 500 (`ES=F`) and E-mini Nasdaq-100 (`NQ=F`) continuous contracts via yfinance's free tier.
- **BTC:** Since crypto trades 24/7, there's no single "opening range" — instead it uses a rolling 15-minute range that's always looking at the most recent 15 candles. Same breakout + volume + momentum logic applies.
- **Momentum/trend filter:** A breakout only counts if price is also on the correct side of a 20-period moving average (above it for UP breakouts, below it for DOWN breakouts). This filters out a lot of fakeouts, especially on fast-moving instruments like futures.
- **Rejection/reversal signals:** A separate signal type from breakout. Instead of "price broke through the level," this catches "price tested the level and got rejected back," confirmed by volume. Posts as a visually distinct alert (different color/icon, clearly labeled "Rejection") so it's never confused with a breakout alert. Applies to stocks, futures, and BTC.
- **Market hours only:** By default, stock and futures scanning pauses outside regular US market hours (9:30 AM–4:00 PM Eastern, Mon–Fri), saving API calls and avoiding stale-data noise overnight. BTC keeps scanning 24/7 regardless, since crypto markets never close. Toggle via `MARKET_HOURS_ONLY` in `config.py`.
- **Pinned tickers:** Add any symbols to `PINNED_TICKERS` in `config.py` to have them always scanned, regardless of whether they show up on the day's "movers" list. Currently set to SPY and TSLA.
- **Cooldown:** Once a symbol+direction+signal-type alert fires, it won't fire again for 15 minutes, so you don't get spammed every cycle while a setup is still playing out. Breakout and rejection track separately, so one type firing doesn't suppress the other.
- **Resilience:** If Yahoo Finance throttles you or the movers feed fails, it falls back to a static watchlist of liquid large-caps instead of crashing.

## Setup

### 1. Install dependencies
```bash
pip install yfinance ccxt requests
```

### 2. Create your Discord webhooks
In Discord: go to the channel you want alerts in → **Channel Settings → Integrations → Webhooks → New Webhook** → copy the URL. Do this for a stocks channel and a BTC channel (and optionally a third for futures — if you skip this, futures alerts post to the stock channel by default).

### 3. Set your webhook URLs
Either set environment variables (recommended, keeps secrets out of code):
```bash
export STOCK_WEBHOOK_URL="https://discord.com/api/webhooks/..."
export BTC_WEBHOOK_URL="https://discord.com/api/webhooks/..."
export FUTURES_WEBHOOK_URL="https://discord.com/api/webhooks/..."   # optional
```
...or paste them directly into `config.py` in place of the placeholder strings.

### 4. Run it
```bash
python main.py
```

You'll see log output in the terminal and in `bot.log`. Press `Ctrl+C` to stop.

## Tuning

All thresholds live in `config.py`:

| Setting | What it controls |
|---|---|
| `SCAN_INTERVAL_SECONDS` | How often the loop runs (default: 60s) |
| `OPENING_RANGE_MINUTES` | Range window size for breakout detection (default: 15) |
| `MAX_MOVERS_TO_SCAN` | Size of the dynamic stock shortlist (default: 25) |
| `VOLUME_SPIKE_MULTIPLIER` | How much above average volume must be to confirm a breakout (default: 1.5x) |
| `BREAKOUT_BUFFER_PCT` | Buffer added to the range edge to filter out noise (default: 0.05%) |
| `ALERT_COOLDOWN_MINUTES` | Minimum time between repeat alerts for the same symbol+direction (default: 15) |
| `MIN_PRICE` / `MIN_AVG_VOLUME` | Filters out illiquid/penny names |
| `PINNED_TICKERS` | Symbols always scanned, regardless of the day's movers list |
| `FUTURES_ENABLED` / `FUTURES_TICKERS` | Toggle and list of futures contracts to scan (default: ES=F, NQ=F) |
| `MOMENTUM_FILTER_ENABLED` / `MOMENTUM_MA_PERIOD` | Toggle and lookback period for the trend-confirmation filter |
| `REJECTION_SIGNALS_ENABLED` / `REJECTION_PROXIMITY_PCT` | Toggle and how close price must get to a range edge to count as "testing" it |
| `MARKET_HOURS_ONLY` / `MARKET_OPEN_HOUR` / `MARKET_CLOSE_HOUR` | Toggle and window for when stock/futures scanning is active |

## Known limitations (free-tier reality check)

- **yfinance is unofficial and rate-limit prone.** It works well for a 25-ticker shortlist checked every minute, but if Yahoo throttles your IP, some cycles may silently return no data. The bot logs this and keeps running rather than crashing.
- **The "most active" screener can occasionally fail or return stale data.** When that happens, the bot automatically falls back to a static list of liquid large-caps (`FALLBACK_WATCHLIST` in `stock_scanner.py`) so alerts don't stop entirely.
- **ccxt's public BTC data depends on the exchange being reachable** from wherever you host this. Coinbase is the default; if it's geo-blocked or down, you can swap `BTC_EXCHANGE` in `config.py` to another ccxt-supported exchange like `"kraken"` or `"binanceus"`.
- **Futures data (ES=F, NQ=F) on yfinance's free tier is looser than equities** — slightly more delay, occasional gaps. It's usable for alerting, not for split-second execution timing.
- **This bot only scans for breakouts — it does not place trades.** It's an alert system, not an execution system, by design.

## Deploying for 24/7 uptime

This script needs to run continuously, which your own laptop won't do reliably. Two solid free/cheap options:
- **Railway** — easiest setup, has a free trial credit then a small monthly cost.
- **Oracle Cloud Free Tier** — genuinely free forever, slightly more setup work.

Happy to walk through deploying to either once you've test-run this locally and are happy with the alerts it's producing.
