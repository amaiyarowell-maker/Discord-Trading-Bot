"""
Main entry point for the Stock + BTC Discord Alert Bot.

Every SCAN_INTERVAL_SECONDS, this:
  1. Refreshes the stock movers shortlist
  2. Fetches market-wide VIX sentiment once (shared across all symbols this cycle)
  3. Scans stocks, futures, and BTC for breakout, rejection, liquidity sweep, and FVG signals
  4. Each qualifying signal is enriched with HTF trend, ATR-based risk levels, and a confidence score
  5. Sends any new (non-cooldown) signals to the appropriate Discord webhook

Run with:  python main.py
Stop with: Ctrl+C
"""

import time
import logging
import sys

import config
from cooldown import CooldownTracker
from notifier import (
    send_discord_alert,
    build_breakout_embed,
    build_rejection_embed,
    build_sweep_embed,
    build_fvg_embed,
)
from stock_scanner import get_movers_shortlist, scan_stocks, scan_futures
from btc_scanner import scan_btc
from market_hours import is_market_open
import sentiment

# ── Logging setup ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

cooldown = CooldownTracker()

MOVERS_REFRESH_EVERY_N_CYCLES = 5  # refresh the shortlist every 5 minutes instead of every cycle

# Maps each signal type to its embed builder. Centralizing this here
# means adding a new signal type in the future only requires one new
# entry, not new branching logic scattered through handle_signal.
EMBED_BUILDERS = {
    "breakout": build_breakout_embed,
    "rejection": build_rejection_embed,
    "liquidity_sweep": build_sweep_embed,
    "fvg": build_fvg_embed,
}


def handle_signal(signal: dict, webhook_url: str, asset_type: str, signal_type: str):
    """
    Sends the alert if not on cooldown, and marks cooldown if sent.
    Routes to the correct embed builder based on signal_type, and
    passes through risk_data/confidence/vix fields if present on the
    signal (added by the scanner's enrichment step).
    """
    symbol = signal["symbol"]
    direction = signal["direction"]

    if cooldown.is_on_cooldown(symbol, direction, signal_type):
        logger.info(f"[{symbol}] {direction} {signal_type} signal suppressed (cooldown active).")
        return

    embed_builder = EMBED_BUILDERS.get(signal_type, build_breakout_embed)
    risk_data = signal.get("risk_data")
    confidence = signal.get("confidence")
    vix_data = signal.get("vix_data")

    if signal_type == "liquidity_sweep":
        embed = embed_builder(
            symbol=symbol,
            direction=direction,
            price=signal["price"],
            swept_level=signal["swept_level"],
            volume=signal["volume"],
            avg_volume=signal["avg_volume"],
            asset_type=asset_type,
            risk_data=risk_data,
            confidence=confidence,
            vix_data=vix_data,
        )
    elif signal_type == "fvg":
        embed = embed_builder(
            symbol=symbol,
            direction=direction,
            price=signal["price"],
            gap_top=signal["gap_top"],
            gap_bottom=signal["gap_bottom"],
            gap_pct=signal["gap_pct"],
            asset_type=asset_type,
            confidence=confidence,
            vix_data=vix_data,
        )
    else:  # breakout or rejection - same field shape
        embed = embed_builder(
            symbol=symbol,
            direction=direction,
            price=signal["price"],
            range_high=signal["range_high"],
            range_low=signal["range_low"],
            volume=signal["volume"],
            avg_volume=signal["avg_volume"],
            asset_type=asset_type,
            risk_data=risk_data,
            confidence=confidence,
            vix_data=vix_data,
        )

    sent = send_discord_alert(webhook_url, embed)
    if sent:
        cooldown.mark_alerted(symbol, direction, signal_type)
        logger.info(f"[{symbol}] {direction} {signal_type} alert sent.")
    else:
        logger.warning(f"[{symbol}] {direction} {signal_type} detected but Discord send failed.")


def _handle_results(results: dict, webhook_url: str, asset_type: str, vix_data: dict):
    """Iterates over all 4 signal-type lists in a scan result and dispatches each to handle_signal."""
    type_map = {
        "breakout": "breakout",
        "rejection": "rejection",
        "sweep": "liquidity_sweep",
        "fvg": "fvg",
    }
    for result_key, signal_type in type_map.items():
        for sig in results.get(result_key, []):
            sig["vix_data"] = vix_data
            handle_signal(sig, webhook_url, asset_type=asset_type, signal_type=signal_type)


def run_cycle(watchlist: list):
    """Runs one full scan cycle across stocks, futures, and BTC."""
    market_open = is_market_open()

    vix_data = sentiment.fetch_vix() if getattr(config, "SENTIMENT_ENABLED", False) else None
    if vix_data and getattr(config, "DEBUG_SIGNAL_LOGGING", False):
        logger.info(f"VIX: {vix_data.get('value')} ({vix_data.get('label')})")

    # Stocks - skipped outside market hours if MARKET_HOURS_ONLY is on
    if market_open:
        try:
            results = scan_stocks(watchlist, vix_data=vix_data)
            _handle_results(results, config.STOCK_WEBHOOK_URL, "stock", vix_data)
        except Exception as e:
            logger.error(f"Stock scan cycle failed: {e}")
    else:
        logger.info("Market closed - skipping stock scan this cycle.")

    # Futures - same market-hours gate as stocks
    if market_open:
        try:
            results = scan_futures(vix_data=vix_data)
            futures_webhook = config.FUTURES_WEBHOOK_URL or config.STOCK_WEBHOOK_URL
            _handle_results(results, futures_webhook, "futures", vix_data)
        except Exception as e:
            logger.error(f"Futures scan cycle failed: {e}")
    else:
        logger.info("Market closed - skipping futures scan this cycle.")

    # BTC - always runs, 24/7, regardless of market hours
    try:
        results = scan_btc(vix_data=vix_data)
        _handle_results(results, config.BTC_WEBHOOK_URL, "crypto", vix_data)
    except Exception as e:
        logger.error(f"BTC scan cycle failed: {e}")


def main():
    logger.info("Starting Stock + BTC Discord Alert Bot...")
    logger.info(
        f"Scan interval: {config.SCAN_INTERVAL_SECONDS}s | "
        f"Opening range: {config.OPENING_RANGE_MINUTES}m | "
        f"Volume multiplier: {config.VOLUME_SPIKE_MULTIPLIER}x | "
        f"Futures: {'on' if config.FUTURES_ENABLED else 'off'} | "
        f"Momentum filter: {'on' if config.MOMENTUM_FILTER_ENABLED else 'off'} | "
        f"Rejection signals: {'on' if config.REJECTION_SIGNALS_ENABLED else 'off'} | "
        f"Market hours only: {'on' if config.MARKET_HOURS_ONLY else 'off'} | "
        f"HTF filter: {'on' if config.HTF_FILTER_ENABLED else 'off'} | "
        f"SMC signals: {'on' if config.SMC_SIGNALS_ENABLED else 'off'} | "
        f"Sentiment (VIX): {'on' if config.SENTIMENT_ENABLED else 'off'} | "
        f"Confidence scoring: {'on' if config.CONFIDENCE_SCORING_ENABLED else 'off'}"
    )

    watchlist = get_movers_shortlist()
    logger.info(f"Initial watchlist ({len(watchlist)}): {watchlist}")

    cycle_count = 0
    while True:
        try:
            if (
                is_market_open()
                and cycle_count % MOVERS_REFRESH_EVERY_N_CYCLES == 0
                and cycle_count != 0
            ):
                watchlist = get_movers_shortlist()
                logger.info(f"Refreshed watchlist ({len(watchlist)}): {watchlist}")

            run_cycle(watchlist)

        except Exception as e:
            # Catch-all so one bad cycle never kills the whole bot.
            logger.error(f"Unhandled error in main loop: {e}")

        cycle_count += 1
        time.sleep(config.SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
