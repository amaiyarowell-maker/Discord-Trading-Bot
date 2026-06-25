# Stock + BTC Discord Alert Bot

Scans a dynamic shortlist of actively-moving stocks plus BTC for breakouts confirmed by volume spikes, and posts alerts to Discord.

## How it works

- **Stocks:** Every minute, pulls a shortlist of ~25 currently active/moving tickers (so it never tries to brute-force scan the whole S&P 500). For each, checks if price has broken above/below the day's opening range AND volume is at least 1.5x the recent average.
- **BTC:** Since crypto trades 24/7, there's no single "opening range" — instead it uses a rolling 15-minute range that's always looking at the most recent 15 candles. Same breakout + volume logic applies.
- **Cooldown:** Once a symbol+direction alert fires, it won't fire again for 15 minutes, so you don't get spammed every cycle while a breakout is still playing out.
- **Resilience:** If Yahoo Finance throttles you or the movers feed fails, it falls back to a static watchlist of liquid large-caps instead of crashing.

## Setup

### 1. Install dependencies
```bash
pip install yfinance ccxt requests
```

### 2. Create your Discord webhooks
In Discord: go to the channel you want alerts in → **Channel Settings → Integrations → Webhooks → New Webhook** → copy the URL. Do this twice (once for a stocks channel, once for a BTC channel).

### 3. Set your webhook URLs
Either set environment variables (recommended, keeps secrets out of code):
```bash
export STOCK_WEBHOOK_URL="https://discord.com/api/webhooks/..."
export BTC_WEBHOOK_URL="https://discord.com/api/webhooks/..."
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

## Known limitations (free-tier reality check)

- **yfinance is unofficial and rate-limit prone.** It works well for a 25-ticker shortlist checked every minute, but if Yahoo throttles your IP, some cycles may silently return no data. The bot logs this and keeps running rather than crashing.
- **The "most active" screener can occasionally fail or return stale data.** When that happens, the bot automatically falls back to a static list of liquid large-caps (`FALLBACK_WATCHLIST` in `stock_scanner.py`) so alerts don't stop entirely.
- **ccxt's public BTC data depends on the exchange being reachable** from wherever you host this. Coinbase is the default; if it's geo-blocked or down, you can swap `BTC_EXCHANGE` in `config.py` to another ccxt-supported exchange like `"kraken"` or `"binanceus"`.
- **This bot only scans for breakouts — it does not place trades.** It's an alert system, not an execution system, by design.

## Deploying for 24/7 uptime

This script needs to run continuously, which your own laptop won't do reliably. Two solid free/cheap options:
- **Railway** — easiest setup, has a free trial credit then a small monthly cost.
- **Oracle Cloud Free Tier** — genuinely free forever, slightly more setup work.

Happy to walk through deploying to either once you've test-run this locally and I are happy with the alerts it's producing.
