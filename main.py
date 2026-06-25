"""
Main entry point for the Stock + BTC Discord Alert Bot.

Every SCAN_INTERVAL_SECONDS, this:
  1. Refreshes the stock movers shortlist
  2. Scans that shortlist for breakout + volume signals
  3. Scans BTC for the same kind of signal
  4. Sends any new (non-cooldown) signals to the appropriate Discord webhook

Run with:  python main.py
Stop with: Ctrl+C
"""

import time
import logging
import sys

import config
from cooldown import CooldownTracker
from notifier import send_discord_alert, build_breakout_embed, build_rejection_embed
from stock_scanner import get_movers_shortlist, scan_stocks, scan_futures
from btc_scanner import check_btc_breakout, check_btc_rejection, _fetch_btc_ohlcv
from market_hours import is_market_open

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


def handle_signal(signal: dict, webhook_url: str, asset_type: str, signal_type: str = "breakout"):
    """
    Sends the alert if not on cooldown, and marks cooldown if sent.
    signal_type: "breakout" or "rejection" - determines which embed
    style is used and tracks cooldown separately per type.
    """
    symbol = signal["symbol"]
    direction = signal["direction"]

    if cooldown.is_on_cooldown(symbol, direction, signal_type):
        logger.info(f"[{symbol}] {direction} {signal_type} signal suppressed (cooldown active).")
        return

    embed_builder = build_rejection_embed if signal_type == "rejection" else build_breakout_embed
    embed = embed_builder(
        symbol=symbol,
        direction=direction,
        price=signal["price"],
        range_high=signal["range_high"],
        range_low=signal["range_low"],
        volume=signal["volume"],
        avg_volume=signal["avg_volume"],
        asset_type=asset_type,
    )

    sent = send_discord_alert(webhook_url, embed)
    if sent:
        cooldown.mark_alerted(symbol, direction, signal_type)
        logger.info(f"[{symbol}] {direction} {signal_type} alert sent.")
    else:
        logger.warning(f"[{symbol}] {direction} {signal_type} detected but Discord send failed.")


def run_cycle(watchlist: list):
    """Runs one full scan cycle across stocks, futures, and BTC."""
    market_open = is_market_open()

    # Stocks - skipped outside market hours if MARKET_HOURS_ONLY is on
    if market_open:
        try:
            results = scan_stocks(watchlist)
            for sig in results["breakout"]:
                handle_signal(sig, config.STOCK_WEBHOOK_URL, asset_type="stock", signal_type="breakout")
            for sig in results["rejection"]:
                handle_signal(sig, config.STOCK_WEBHOOK_URL, asset_type="stock", signal_type="rejection")
        except Exception as e:
            logger.error(f"Stock scan cycle failed: {e}")
    else:
        logger.info("Market closed - skipping stock scan this cycle.")

    # Futures - same market-hours gate as stocks
    if market_open:
        try:
            results = scan_futures()
            futures_webhook = config.FUTURES_WEBHOOK_URL or config.STOCK_WEBHOOK_URL
            for sig in results["breakout"]:
                handle_signal(sig, futures_webhook, asset_type="futures", signal_type="breakout")
            for sig in results["rejection"]:
                handle_signal(sig, futures_webhook, asset_type="futures", signal_type="rejection")
        except Exception as e:
            logger.error(f"Futures scan cycle failed: {e}")
    else:
        logger.info("Market closed - skipping futures scan this cycle.")

    # BTC - always runs, 24/7, regardless of market hours
    try:
        ohlcv = _fetch_btc_ohlcv()
        if ohlcv is not None:
            btc_breakout = check_btc_breakout(ohlcv=ohlcv)
            if btc_breakout:
                handle_signal(btc_breakout, config.BTC_WEBHOOK_URL, asset_type="crypto", signal_type="breakout")
            btc_rejection = check_btc_rejection(ohlcv=ohlcv)
            if btc_rejection:
                handle_signal(btc_rejection, config.BTC_WEBHOOK_URL, asset_type="crypto", signal_type="rejection")
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
        f"Market hours only: {'on' if config.MARKET_HOURS_ONLY else 'off'}"
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
