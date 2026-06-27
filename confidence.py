"""
Confidence scoring: combines volume strength, HTF trend agreement,
momentum alignment, and VIX context into a single 0-100 score per
signal, so alerts can be ranked by conviction rather than being a
flat pass/fail.

This is a transparent, additive point system (not a black box) so the
weighting can be tuned by adjusting the point values below if certain
inputs turn out to matter more or less in practice.
"""

import config

# Point allocation - these sum to 100 when every factor maxes out.
# Adjust individual weights here if, after running this for a while,
# one factor turns out to be more/less predictive than the others.
POINTS_VOLUME = 30          # weight for volume strength (vol_ratio)
POINTS_HTF_TREND = 25       # weight for higher-timeframe trend agreement
POINTS_MOMENTUM = 20        # weight for same-timeframe momentum alignment
POINTS_VIX_CONTEXT = 15     # weight for VIX/market sentiment context
POINTS_SIGNAL_TYPE = 10     # small bonus for signal types with extra confirmation built in


def score_volume(vol_ratio: float) -> float:
    """
    Scores volume strength on a curve: 1.2x (minimum threshold) scores
    low, scaling up to the full point value around 5x+ volume.
    """
    if vol_ratio is None or vol_ratio <= 1.0:
        return 0.0
    # Linear scale from 1.0x->0pts to 5.0x->full points, capped at full points
    scaled = min((vol_ratio - 1.0) / 4.0, 1.0)
    return round(scaled * POINTS_VOLUME, 1)


def score_htf_trend(htf_agrees: bool, htf_trend: str) -> float:
    """
    Full points if the higher timeframe trend actively agrees with the
    signal direction. Half points if HTF is FLAT/unknown (neutral, not
    contradicting). Zero if HTF filter is disabled or data unavailable.
    """
    if not config.HTF_FILTER_ENABLED or htf_trend is None:
        return POINTS_HTF_TREND * 0.5  # neutral - no info either way
    if htf_trend == "FLAT":
        return POINTS_HTF_TREND * 0.5
    return POINTS_HTF_TREND if htf_agrees else 0.0


def score_momentum(momentum_pass: bool) -> float:
    """Full points if same-timeframe momentum filter passed, else zero."""
    if not config.MOMENTUM_FILTER_ENABLED:
        return POINTS_MOMENTUM * 0.5  # neutral if filter is off
    return POINTS_MOMENTUM if momentum_pass else 0.0


def score_vix_context(vix_label: str, signal_direction: str) -> float:
    """
    VIX context scoring is direction-aware:
    - HIGH FEAR conditions historically favor sharp moves but with more
      noise/whipsaw risk - scored as moderate, not full, for either direction.
    - LOW FEAR (complacent) conditions tend to have cleaner, more
      sustained trends - scored as favorable for UP signals especially,
      since calm markets historically grind upward more often than down.
    - NORMAL conditions are treated as a neutral baseline.
    """
    if vix_label in (None, "UNKNOWN", "DISABLED"):
        return POINTS_VIX_CONTEXT * 0.5  # no info - neutral

    if vix_label == "HIGH FEAR":
        return POINTS_VIX_CONTEXT * 0.5
    if vix_label == "LOW FEAR":
        return POINTS_VIX_CONTEXT if signal_direction == "UP" else POINTS_VIX_CONTEXT * 0.6
    return POINTS_VIX_CONTEXT * 0.7  # NORMAL


def score_signal_type(signal_type: str) -> float:
    """
    Small bonus for signal types that already have extra built-in
    confirmation. Rejection and sweep signals require price to test
    AND reverse (two conditions), so they get a small edge over a
    plain breakout (one condition).
    """
    if signal_type in ("rejection", "liquidity_sweep"):
        return POINTS_SIGNAL_TYPE
    if signal_type == "fvg":
        return POINTS_SIGNAL_TYPE * 0.7
    return POINTS_SIGNAL_TYPE * 0.5  # breakout


def calculate_confidence_score(
    vol_ratio: float,
    htf_agrees: bool,
    htf_trend: str,
    momentum_pass: bool,
    vix_label: str,
    signal_direction: str,
    signal_type: str = "breakout",
) -> dict:
    """
    Combines all factors into a single 0-100 confidence score, and
    returns a breakdown dict so the alert embed can show the
    contributing factors, not just the final number.
    """
    vol_score = score_volume(vol_ratio)
    htf_score = score_htf_trend(htf_agrees, htf_trend)
    momentum_score = score_momentum(momentum_pass)
    vix_score = score_vix_context(vix_label, signal_direction)
    type_score = score_signal_type(signal_type)

    total = round(vol_score + htf_score + momentum_score + vix_score + type_score, 1)
    total = max(0.0, min(100.0, total))  # clamp, just in case

    return {
        "total": total,
        "breakdown": {
            "volume": vol_score,
            "htf_trend": htf_score,
            "momentum": momentum_score,
            "vix_context": vix_score,
            "signal_type": type_score,
        },
    }


def confidence_label(score: float) -> str:
    """Converts a numeric score into a human-readable conviction label."""
    if score >= 75:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "LOW"


# ── A+ Setup Criteria ──────────────────────────────────────────────
# A setup is tagged "A+" only when it clears ALL three bars below -
# not just a high score on its own. This is deliberately stricter than
# the HIGH confidence label (which only requires score >= 75), since
# "A+" is meant to flag the rare setup with everything aligned, not
# just a generally decent one. Thresholds are read from config.py so
# they're tunable without editing this file.


def is_a_plus_setup(confidence_total: float, htf_trend: str, htf_agrees: bool, risk_reward: float) -> bool:
    """
    Returns True only if a signal clears every A+ bar:
      1. Confidence score >= config.A_PLUS_MIN_CONFIDENCE
      2. HTF trend ACTIVELY agrees (not FLAT, not unknown/None) - this
         is stricter than the confidence score's own HTF component,
         which gives partial credit for a neutral HTF reading.
      3. Risk:Reward >= config.A_PLUS_MIN_RISK_REWARD

    Any missing/None input fails that criterion (does not default to
    passing), so an A+ tag only ever appears when every input was
    actually available and genuinely met the bar.
    """
    min_confidence = getattr(config, "A_PLUS_MIN_CONFIDENCE", 75)
    require_htf = getattr(config, "A_PLUS_REQUIRE_ACTIVE_HTF_AGREEMENT", True)
    min_rr = getattr(config, "A_PLUS_MIN_RISK_REWARD", 2.0)

    if confidence_total is None or confidence_total < min_confidence:
        return False

    if require_htf:
        htf_actively_agrees = htf_trend is not None and htf_trend != "FLAT" and htf_agrees
        if not htf_actively_agrees:
            return False

    if risk_reward is None or risk_reward < min_rr:
        return False

    return True
