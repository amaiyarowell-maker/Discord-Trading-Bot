"""
Generates entry guidance text for each signal type: a concrete entry
tactic, what invalidates the setup, and what to watch for as
confirmation. This is NOT financial advice - it's a transparent,
rule-based description of how each signal type's pattern typically
gets traded, written with the actual numbers from that specific alert
rather than generic boilerplate.

Each signal type has a fundamentally different shape, so the entry
tactic differs by design:
- Breakout: the move already happened - guidance addresses the
  chase-vs-retest tradeoff honestly rather than pretending timing is clean.
- Rejection / Liquidity Sweep: the reaction candle itself is close to
  the entry trigger - these are closer to "real-time" signals.
- FVG: no risk math exists for these (it's a zone, not a trade trigger)
  - guidance focuses on waiting for price to return to the zone.
- Early Momentum: already in motion - guidance is explicit about the
  chase risk, since this is the fastest, least-confirmed signal type.
"""


def breakout_guidance(direction: str, price: float, range_high: float, range_low: float) -> dict:
    """Entry guidance for a breakout signal - honest about the chase-vs-retest tradeoff."""
    level = range_high if direction == "UP" else range_low
    opposite_level = range_low if direction == "UP" else range_high
    move_word = "above" if direction == "UP" else "below"

    return {
        "entry_tactic": (
            f"The breakout already happened - price is at ${price:,.2f}, {move_word} the "
            f"${level:,.2f} level. Two honest options: enter now and accept you're chasing "
            f"the move, or wait for a retest of ${level:,.2f} holding as new "
            f"{'support' if direction == 'UP' else 'resistance'} before entering on the bounce."
        ),
        "invalidation": (
            f"Setup is invalidated if price closes back {'below' if direction == 'UP' else 'above'} "
            f"${level:,.2f} - that would mean the breakout failed and you're back inside the old range."
        ),
        "confirmation_to_watch": (
            f"Watch for a retest of ${level:,.2f} that holds (doesn't break back through), "
            f"or continued volume on the next 1-2 candles in the {direction} direction."
        ),
    }


def rejection_guidance(direction: str, price: float, range_high: float, range_low: float) -> dict:
    """Entry guidance for a rejection signal - the rejection candle itself is close to the entry trigger."""
    tested_level = range_high if direction == "DOWN" else range_low
    level_name = "top" if direction == "DOWN" else "bottom"

    return {
        "entry_tactic": (
            f"The rejection candle near ${tested_level:,.2f} is close to the entry trigger itself - "
            f"current price (${price:,.2f}) is where this setup suggests entering, in the {direction} direction."
        ),
        "invalidation": (
            f"Setup is invalidated if price breaks back through ${tested_level:,.2f} "
            f"(the level that was just tested and supposedly held)."
        ),
        "confirmation_to_watch": (
            f"Watch the next 1-2 candles for continued movement {direction.lower()} away from "
            f"${tested_level:,.2f} - that follow-through is what separates a real rejection from a brief pause."
        ),
    }


def sweep_guidance(direction: str, price: float, swept_level: float) -> dict:
    """Entry guidance for a liquidity sweep signal - similar shape to rejection, framed around the swept level."""
    level_type = "swing high" if direction == "DOWN" else "swing low"

    return {
        "entry_tactic": (
            f"Price already swept the {level_type} at ${swept_level:,.2f} and closed back inside - "
            f"current price (${price:,.2f}) is roughly where this setup suggests entering, in the {direction} direction."
        ),
        "invalidation": (
            f"Setup is invalidated if price reclaims ${swept_level:,.2f} and keeps going that way - "
            f"that would mean the sweep was a real breakout, not a stop-hunt."
        ),
        "confirmation_to_watch": (
            f"Watch for a follow-through candle in the {direction} direction with volume holding up, "
            f"not fading back toward ${swept_level:,.2f}."
        ),
    }


def fvg_guidance(direction: str, price: float, gap_top: float, gap_bottom: float) -> dict:
    """
    Entry guidance for a Fair Value Gap - no risk math exists for these
    (it's a zone to watch, not an immediate trade trigger), so guidance
    focuses on waiting for price to return to the zone rather than
    chasing the current price.
    """
    return {
        "entry_tactic": (
            f"This is a zone to watch, not an immediate entry. The gap sits between "
            f"${gap_bottom:,.2f} and ${gap_top:,.2f} - the typical approach is waiting for price "
            f"to return into that zone, then watching how it reacts there, rather than entering at "
            f"the current price (${price:,.2f}) right now."
        ),
        "invalidation": (
            f"If price returns to the zone and closes straight through the far side "
            f"(past ${gap_top if direction == 'DOWN' else gap_bottom:,.2f}) without reacting, "
            f"the gap likely isn't acting as support/resistance this time."
        ),
        "confirmation_to_watch": (
            f"Watch for a reaction at the ${gap_bottom:,.2f}-${gap_top:,.2f} zone when price gets back there - "
            f"a wick or reversal candle in that area is what would make this zone worth acting on."
        ),
    }


def early_momentum_guidance(direction: str, price: float, price_accel_ratio: float) -> dict:
    """
    Entry guidance for an early momentum signal - explicit about chase
    risk, since this is the fastest, least-confirmed signal type and
    skips the confirmation steps the other signal types require.
    """
    accel_text = f"{price_accel_ratio}x" if price_accel_ratio else "a multiple of"

    return {
        "entry_tactic": (
            f"This is already moving - price just accelerated at {accel_text} its recent pace. "
            f"Entering now means chasing a fast move with the least confirmation of any signal type "
            f"this bot produces. If you act on this, a smaller position size than usual is worth considering, "
            f"given how little confirmation this signal type requires to fire."
        ),
        "invalidation": (
            f"Setup is invalidated quickly if the next 1-2 candles stall or reverse - "
            f"this signal has no range or trend backing it up, so it can fail fast."
        ),
        "confirmation_to_watch": (
            f"Watch for continued same-direction candles with volume holding up over the next few minutes. "
            f"If momentum fades immediately, that's the signal not following through."
        ),
    }
