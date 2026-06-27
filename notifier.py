"""
Handles sending formatted alert messages to Discord via webhooks.
"""

import requests
import logging

logger = logging.getLogger("discord_notifier")


def _risk_fields(risk_data: dict) -> list:
    """
    Builds the Discord embed fields for suggested entry/stop/target/R:R.
    Returns an empty list if risk_data is missing or incomplete (e.g.
    not enough candles yet to compute ATR), so alerts still send
    cleanly without this section rather than showing blank/error values.
    """
    if not risk_data or risk_data.get("stop") is None:
        return []

    rr_display = f"{risk_data['risk_reward']}:1" if risk_data.get("risk_reward") else "N/A"
    return [
        {"name": "Entry", "value": f"${risk_data['entry']:,.2f}", "inline": True},
        {"name": "Stop Loss", "value": f"${risk_data['stop']:,.2f}", "inline": True},
        {"name": "Take Profit", "value": f"${risk_data['target']:,.2f}", "inline": True},
        {"name": "Risk:Reward", "value": rr_display, "inline": True},
    ]


def _confidence_fields(confidence: dict) -> list:
    """
    Builds the Discord embed field for the confidence score. Returns
    an empty list if confidence data is missing, so alerts still send
    cleanly if scoring is disabled or failed for some reason.
    """
    if not confidence:
        return []

    from confidence import confidence_label
    label = confidence_label(confidence["total"])
    return [
        {"name": "Confidence", "value": f"{confidence['total']}/100 ({label})", "inline": True},
    ]


def _vix_field(vix_data: dict) -> list:
    """Builds the Discord embed field for VIX/sentiment context, if available."""
    if not vix_data or vix_data.get("value") is None:
        return []
    return [
        {"name": "VIX", "value": f"{vix_data['value']} ({vix_data['label']})", "inline": True},
    ]


def _a_plus_prefix(is_a_plus: bool) -> str:
    """Returns a title prefix badge for A+ setups, or an empty string otherwise."""
    return "⭐ A+ SETUP — " if is_a_plus else ""


def _a_plus_field(is_a_plus: bool) -> list:
    """
    Adds an explicit A+ field so it's visible even if someone only
    skims the field list and misses the title prefix. Only added when
    True - non-A+ alerts don't get a "Not A+" field, since that would
    just be noise on the majority of (normal) alerts.
    """
    if not is_a_plus:
        return []
    return [{"name": "⭐ Setup Grade", "value": "A+ (all criteria met)", "inline": True}]


def _guidance_fields(guidance: dict) -> list:
    """
    Builds the Discord embed fields for entry guidance (tactic,
    invalidation, confirmation to watch). Returns an empty list if
    guidance is missing, so alerts still send cleanly if this couldn't
    be generated for some reason. Fields are NOT inline - this text is
    long enough that inline formatting would make it unreadable.
    """
    if not guidance:
        return []
    return [
        {"name": "📍 Entry Tactic", "value": guidance["entry_tactic"], "inline": False},
        {"name": "❌ Invalidation", "value": guidance["invalidation"], "inline": False},
        {"name": "👀 Confirmation to Watch", "value": guidance["confirmation_to_watch"], "inline": False},
    ]


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
                          range_low: float, volume: float, avg_volume: float, asset_type: str,
                          risk_data: dict = None, confidence: dict = None, vix_data: dict = None,
                          is_a_plus: bool = False) -> dict:
    """
    Builds a Discord embed dict for a breakout alert.
    direction: "UP" or "DOWN"
    asset_type: "stock", "crypto", or "futures"
    risk_data/confidence/vix_data are optional - if not provided (or
    incomplete), those fields are simply omitted from the embed rather
    than showing blank or error values.
    is_a_plus: when True, adds a "⭐ A+ SETUP" badge to the title and
    an explicit field - reserved for signals meeting the strict
    confidence + HTF agreement + risk:reward bar in confidence.py.
    """
    color = 0x2ECC71 if direction == "UP" else 0xE74C3C  # green / red
    arrow = "🟢⬆️" if direction == "UP" else "🔴⬇️"
    vol_ratio = round(volume / avg_volume, 2) if avg_volume else 0

    import entry_guidance
    guidance = entry_guidance.breakout_guidance(direction, price, range_high, range_low)

    fields = [
        {"name": "Price", "value": f"${price:,.2f}", "inline": True},
        {"name": "Range High", "value": f"${range_high:,.2f}", "inline": True},
        {"name": "Range Low", "value": f"${range_low:,.2f}", "inline": True},
        {"name": "Volume", "value": f"{volume:,.0f}", "inline": True},
        {"name": "Avg Volume", "value": f"{avg_volume:,.0f}", "inline": True},
        {"name": "Vol Multiple", "value": f"{vol_ratio}x", "inline": True},
    ]
    fields += _risk_fields(risk_data)
    fields += _confidence_fields(confidence)
    fields += _vix_field(vix_data)
    fields += _a_plus_field(is_a_plus)
    fields += _guidance_fields(guidance)

    embed = {
        "title": f"{_a_plus_prefix(is_a_plus)}{arrow} {symbol} Breakout {direction}",
        "color": color,
        "fields": fields,
        "footer": {"text": f"{asset_type.upper()} | Breakout + Volume Confirmation | Not financial advice"},
    }
    return embed


def build_rejection_embed(symbol: str, direction: str, price: float, range_high: float,
                           range_low: float, volume: float, avg_volume: float, asset_type: str,
                           risk_data: dict = None, confidence: dict = None, vix_data: dict = None,
                           is_a_plus: bool = False) -> dict:
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

    import entry_guidance
    guidance = entry_guidance.rejection_guidance(direction, price, range_high, range_low)

    fields = [
        {"name": "Price", "value": f"${price:,.2f}", "inline": True},
        {"name": "Range High", "value": f"${range_high:,.2f}", "inline": True},
        {"name": "Range Low", "value": f"${range_low:,.2f}", "inline": True},
        {"name": "Volume", "value": f"{volume:,.0f}", "inline": True},
        {"name": "Avg Volume", "value": f"{avg_volume:,.0f}", "inline": True},
        {"name": "Vol Multiple", "value": f"{vol_ratio}x", "inline": True},
    ]
    fields += _risk_fields(risk_data)
    fields += _confidence_fields(confidence)
    fields += _vix_field(vix_data)
    fields += _a_plus_field(is_a_plus)
    fields += _guidance_fields(guidance)

    embed = {
        "title": f"{_a_plus_prefix(is_a_plus)}{icon} {symbol} Rejection at {level_tested} → Expect {direction}",
        "color": color,
        "fields": fields,
        "footer": {"text": f"{asset_type.upper()} | Rejection / Reversal Signal | Not financial advice"},
    }
    return embed


def build_sweep_embed(symbol: str, direction: str, price: float, swept_level: float,
                       volume: float, avg_volume: float, asset_type: str,
                       risk_data: dict = None, confidence: dict = None, vix_data: dict = None,
                       is_a_plus: bool = False) -> dict:
    """
    Builds a Discord embed for a liquidity sweep alert - a third,
    visually distinct alert type (purple) from breakout and rejection.
    direction here means the LIKELY move after the sweep.
    """
    color = 0x9B59B6  # purple, distinct from breakout (green/red) and rejection (blue/amber)
    icon = "🟣⚡"
    vol_ratio = round(volume / avg_volume, 2) if avg_volume else 0
    level_label = "Swing High" if direction == "DOWN" else "Swing Low"

    import entry_guidance
    guidance = entry_guidance.sweep_guidance(direction, price, swept_level)

    fields = [
        {"name": "Price", "value": f"${price:,.2f}", "inline": True},
        {"name": level_label + " Swept", "value": f"${swept_level:,.2f}", "inline": True},
        {"name": "Volume", "value": f"{volume:,.0f}", "inline": True},
        {"name": "Avg Volume", "value": f"{avg_volume:,.0f}", "inline": True},
        {"name": "Vol Multiple", "value": f"{vol_ratio}x", "inline": True},
    ]
    fields += _risk_fields(risk_data)
    fields += _confidence_fields(confidence)
    fields += _vix_field(vix_data)
    fields += _a_plus_field(is_a_plus)
    fields += _guidance_fields(guidance)

    embed = {
        "title": f"{_a_plus_prefix(is_a_plus)}{icon} {symbol} Liquidity Sweep → Expect {direction}",
        "color": color,
        "fields": fields,
        "footer": {"text": f"{asset_type.upper()} | Liquidity Sweep / SMC Signal | Not financial advice"},
    }
    return embed


def build_early_momentum_embed(symbol: str, direction: str, price: float, volume: float,
                                avg_volume: float, price_accel_ratio: float, asset_type: str,
                                risk_data: dict = None, confidence: dict = None, vix_data: dict = None) -> dict:
    """
    Builds a Discord embed for an EARLY MOMENTUM alert - the fastest,
    least-confirmed signal type, visually distinct (orange/yellow) from
    all other signal types. No is_a_plus parameter: early momentum is
    intentionally excluded from the A+ badge since it has a different,
    faster, less-confirmed risk profile than the other signal types.
    """
    color = 0xFFA500  # orange, distinct from all other signal types
    arrow = "🟡⚡" if direction == "UP" else "🟠⚡"
    vol_ratio = round(volume / avg_volume, 2) if avg_volume else 0

    import entry_guidance
    guidance = entry_guidance.early_momentum_guidance(direction, price, price_accel_ratio)

    fields = [
        {"name": "Price", "value": f"${price:,.2f}", "inline": True},
        {"name": "Volume", "value": f"{volume:,.0f}", "inline": True},
        {"name": "Avg Volume", "value": f"{avg_volume:,.0f}", "inline": True},
        {"name": "Vol Multiple", "value": f"{vol_ratio}x", "inline": True},
        {"name": "Price Accel", "value": f"{price_accel_ratio}x baseline" if price_accel_ratio else "N/A", "inline": True},
    ]
    fields += _risk_fields(risk_data)
    fields += _confidence_fields(confidence)
    fields += _vix_field(vix_data)
    fields += _guidance_fields(guidance)

    embed = {
        "title": f"{arrow} {symbol} Early Momentum {direction}",
        "color": color,
        "fields": fields,
        "footer": {"text": f"{asset_type.upper()} | Early Momentum - fast, less-confirmed signal | Not financial advice"},
    }
    return embed


def build_fvg_embed(symbol: str, direction: str, price: float, gap_top: float,
                     gap_bottom: float, gap_pct: float, asset_type: str,
                     confidence: dict = None, vix_data: dict = None) -> dict:
    """
    Builds a Discord embed for a Fair Value Gap alert - a fourth,
    visually distinct alert type (teal). No volume/ATR-based risk
    fields here since an FVG is a zone, not a breakout/rejection trade
    trigger - it's flagged as a level worth watching for a later fill.
    """
    color = 0x1ABC9C  # teal, distinct from the other three alert types
    icon = "🟦📍"

    import entry_guidance
    guidance = entry_guidance.fvg_guidance(direction, price, gap_top, gap_bottom)

    fields = [
        {"name": "Price", "value": f"${price:,.2f}", "inline": True},
        {"name": "Gap Top", "value": f"${gap_top:,.2f}", "inline": True},
        {"name": "Gap Bottom", "value": f"${gap_bottom:,.2f}", "inline": True},
        {"name": "Gap Size", "value": f"{gap_pct}%", "inline": True},
    ]
    fields += _confidence_fields(confidence)
    fields += _vix_field(vix_data)
    fields += _guidance_fields(guidance)

    embed = {
        "title": f"{icon} {symbol} Fair Value Gap ({direction} bias)",
        "color": color,
        "fields": fields,
        "footer": {"text": f"{asset_type.upper()} | Fair Value Gap / SMC Signal | Not financial advice"},
    }
    return embed
