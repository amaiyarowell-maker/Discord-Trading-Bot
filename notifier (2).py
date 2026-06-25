"""
Handles sending formatted alert messages to Discord via webhooks.
"""

import requests
import logging

logger = logging.getLogger("discord_notifier")


def send_discord_alert(webhook_url: str, embed: dict):
    """
    Sends a single embed message to a Discord webhook.
    Returns True on success, False on failure (never raises, so the
    main loop never crashes because Discord had a hiccup).
    """
    if not webhook_url or "PASTE_" in webhook_url:
        logger.warning("Webhook URL not configured - skipping send. Set it in config.py or as an env var.")
        return False

    payload = {"embeds": [embed]}

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code in (200, 204):
            return True
        logger.error(f"Discord webhook returned status {response.status_code}: {response.text[:200]}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Discord alert: {e}")
        return False


def build_breakout_embed(symbol: str, direction: str, price: float, range_high: float,
                          range_low: float, volume: float, avg_volume: float, asset_type: str) -> dict:
    """
    Builds a Discord embed dict for a breakout alert.
    direction: "UP" or "DOWN"
    asset_type: "stock", "crypto", or "futures"
    """
    color = 0x2ECC71 if direction == "UP" else 0xE74C3C  # green / red
    arrow = "🟢⬆️" if direction == "UP" else "🔴⬇️"
    vol_ratio = round(volume / avg_volume, 2) if avg_volume else 0

    embed = {
        "title": f"{arrow} {symbol} Breakout {direction}",
        "color": color,
        "fields": [
            {"name": "Price", "value": f"${price:,.2f}", "inline": True},
            {"name": "Range High", "value": f"${range_high:,.2f}", "inline": True},
            {"name": "Range Low", "value": f"${range_low:,.2f}", "inline": True},
            {"name": "Volume", "value": f"{volume:,.0f}", "inline": True},
            {"name": "Avg Volume", "value": f"{avg_volume:,.0f}", "inline": True},
            {"name": "Vol Multiple", "value": f"{vol_ratio}x", "inline": True},
        ],
        "footer": {"text": f"{asset_type.upper()} | Breakout + Volume Confirmation"},
    }
    return embed


def build_rejection_embed(symbol: str, direction: str, price: float, range_high: float,
                           range_low: float, volume: float, avg_volume: float, asset_type: str) -> dict:
    """
    Builds a Discord embed dict for a REJECTION alert - visually distinct
    from breakout alerts (different color/icon) so they're never confused
    in the channel. direction here means the LIKELY move after rejection
    (e.g. "DOWN" = rejected at the top, expect a move down).
    """
    # Amber/blue tones, deliberately different from breakout's green/red,
    # so rejection alerts are instantly recognizable at a glance.
    color = 0x3498DB if direction == "UP" else 0xF39C12  # blue / amber
    icon = "🔵↩️" if direction == "UP" else "🟠↩️"
    vol_ratio = round(volume / avg_volume, 2) if avg_volume else 0
    level_tested = "Top" if direction == "DOWN" else "Bottom"

    embed = {
        "title": f"{icon} {symbol} Rejection at {level_tested} → Expect {direction}",
        "color": color,
        "fields": [
            {"name": "Price", "value": f"${price:,.2f}", "inline": True},
            {"name": "Range High", "value": f"${range_high:,.2f}", "inline": True},
            {"name": "Range Low", "value": f"${range_low:,.2f}", "inline": True},
            {"name": "Volume", "value": f"{volume:,.0f}", "inline": True},
            {"name": "Avg Volume", "value": f"{avg_volume:,.0f}", "inline": True},
            {"name": "Vol Multiple", "value": f"{vol_ratio}x", "inline": True},
        ],
        "footer": {"text": f"{asset_type.upper()} | Rejection / Reversal Signal"},
    }
    return embed
