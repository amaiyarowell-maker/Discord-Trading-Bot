# Stock + BTC Discord Alert Bot

Scans a dynamic shortlist of actively-moving stocks, futures, and BTC for four kinds of setups — breakouts, rejections, liquidity sweeps, and fair value gaps — each enriched with higher-timeframe trend context, ATR-based risk levels, market sentiment (VIX), and a 0-100 confidence score, then posts alerts to Discord.

**This bot is an alert/research tool, not a financial advisor and not an execution system.** Entry/stop/target/confidence numbers are suggestions calculated from volatility and pattern confirmation - not guarantees. You decide position sizing and whether to take any trade.

## How it works

### Signal types (4, each visually distinct in Discord)
- **Breakout** (green/red): price breaks above/below the session's opening range, confirmed by a volume spike, optionally confirmed by same-timeframe momentum and higher-timeframe trend.
- **Rejection** (blue/amber): the opposite read - price tests a range high/low and gets pushed back, confirmed by volume. Catches "tested and held" setups.
- **Liquidity Sweep** (purple): price wicks beyond a recent swing high/low (where stop orders likely cluster) then closes back on the other side - a Smart Money Concepts (SMC) pattern, similar shape to rejection but measured against recent swing points instead of the session range.
- **Fair Value Gap / FVG** (teal): a 3-candle imbalance where price leaves a gap that often gets revisited later. Flagged as a zone to watch, not a trade trigger - no ATR-based stop/target on these.

### Context layered onto every signal
- **Higher timeframe (HTF) trend filter:** pulls 15-min candles alongside the 1-min signal data. If the 15-min trend actively disagrees with a signal's direction, the alert is blocked outright - this is a hard gate, not just a score adjustment. A flat/unclear HTF trend is treated as neutral and doesn't block anything.
- **ATR-based stops & targets:** every breakout/rejection/sweep alert includes a suggested Entry, Stop Loss, Take Profit, and Risk:Reward ratio, calculated from Average True Range (volatility) rather than a fixed dollar or percent distance.
- **VIX sentiment:** fetched once per cycle (it's market-wide, not per-symbol) and shown on every alert as context - elevated VIX ("HIGH FEAR") flags choppier conditions where breakouts are historically less reliable.
- **Confidence score (0-100):** combines volume strength, HTF agreement, same-timeframe momentum, VIX context, and signal-type into a single transparent score, shown with a HIGH/MEDIUM/LOW label. Alerts scoring below `MIN_CONFIDENCE_TO_ALERT` are suppressed as low-conviction.

### Coverage
- **Stocks:** every minute, pulls a shortlist of ~25 currently active/moving tickers (so it never tries to brute-force scan the whole S&P 500), plus any tickers pinned in `config.py` (currently SPY and TSLA).
- **Futures (ES/NQ):** same full signal stack, applied to the E-mini S&P 500 (`ES=F`) and E-mini Nasdaq-100 (`NQ=F`) continuous contracts via yfinance's free tier.
- **BTC:** since crypto trades 24/7, there's no single "opening range" - it uses a rolling 15-minute range that's always looking at the most recent candles. Same full signal stack applies.

### Operational details
- **Market hours only:** stock and futures scanning pauses outside regular US market hours (9:30 AM–4:00 PM Eastern, Mon–Fri). BTC keeps scanning 24/7 regardless. Toggle via `MARKET_HOURS_ONLY`.
- **Cooldown:** once a symbol+direction+signal-type alert fires, it won't fire again for 15 minutes. All 4 signal types track cooldown independently, so one type firing doesn't suppress another.
- **Resilience:** handles zero-volume "still forming" candles, Yahoo throttling, and movers-feed failures gracefully (logs and continues) rather than crashing or missing data silently.

## Setup

### 1. Install dependencies
```bash
pip install yfinance ccxt requests pytz pandas
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
| `HTF_FILTER_ENABLED` / `HTF_INTERVAL` / `HTF_MA_PERIOD` | Toggle, candle interval (default 15m), and MA period for the higher-timeframe trend gate |
| `SMC_SIGNALS_ENABLED` | Toggle for liquidity sweep + FVG detection |
| `SWING_LOOKBACK_CANDLES` / `SWEEP_PROXIMITY_PCT` | How far back to look for swing points, and how close price must wick beyond one to count as a sweep |
| `FVG_MIN_GAP_PCT` | Minimum gap size (as % of price) for an FVG to be flagged as notable |
| `ATR_PERIOD` / `ATR_STOP_MULTIPLIER` / `ATR_TARGET_MULTIPLIER` | ATR lookback period and the multipliers used to set suggested stop/target distance |
| `SENTIMENT_ENABLED` / `VIX_HIGH_FEAR_THRESHOLD` / `VIX_LOW_FEAR_THRESHOLD` | Toggle and thresholds for VIX-based market sentiment context |
| `CONFIDENCE_SCORING_ENABLED` / `MIN_CONFIDENCE_TO_ALERT` | Toggle and the minimum score (0-100) required to actually send an alert |
| `DEBUG_SIGNAL_LOGGING` | When `True`, logs the exact computed values for every check, every cycle - very chatty, meant for troubleshooting, not normal use |

## Known limitations (free-tier reality check)

- **yfinance is unofficial and rate-limit prone.** It works well for a 25-ticker shortlist checked every minute, but if Yahoo throttles your IP, some cycles may silently return no data. The bot logs this and keeps running rather than crashing.
- **The "most active" screener can occasionally fail or return stale data.** When that happens, the bot automatically falls back to a static list of liquid large-caps (`FALLBACK_WATCHLIST` in `stock_scanner.py`) so alerts don't stop entirely.
- **ccxt's public BTC data depends on the exchange being reachable** from wherever you host this. Coinbase is the default; if it's geo-blocked or down, you can swap `BTC_EXCHANGE` in `config.py` to another ccxt-supported exchange like `"kraken"` or `"binanceus"`.
- **Futures data (ES=F, NQ=F) on yfinance's free tier is looser than equities** — slightly more delay, occasional gaps. It's usable for alerting, not for split-second execution timing.
- **The HTF trend filter and confidence score are both heuristics, not predictions.** A 15-min MA-based trend read and an additive point system are reasonable, transparent signals - not a guarantee that a high-confidence alert will work out, or that a low-confidence one won't.
- **VIX is fetched as a daily close**, not real-time intraday, since that's what's reliably free on yfinance. It's directional market context, not a live fear gauge.
- **ATR-based stops/targets are suggestions based on recent volatility**, not personalized risk management - they don't know your account size, risk tolerance, or how many other positions you're holding. Use them as a starting point, not a final answer.
- **This bot only scans for setups — it does not place trades.** It's an alert/research system, not an execution system, by design.

## Deploying for 24/7 uptime

This script needs to run continuously, which your own laptop won't do reliably. Two solid free/cheap options:
- **Railway** — easiest setup, has a free trial credit then a small monthly cost.
- **Oracle Cloud Free Tier** — genuinely free forever, slightly more setup work.

Happy to walk through deploying to either once you've test-run this locally and are happy with the alerts it's producing.
