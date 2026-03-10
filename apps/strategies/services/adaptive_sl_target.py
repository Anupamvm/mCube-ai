"""
Adaptive Stop-Loss & Target computation using a 3-tier fallback logic.

Tier 1: Structural S/R levels from the SR exit engine (ATR-buffered).
Tier 2: ATR-adaptive multipliers keyed by market regime.
Tier 3: Volatility-scaled percentage when no ATR is available.

After tier selection, S1/R1 tightening and dual-target stretch are applied.
A risk-reward gate flags trades that fall below the minimum R:R threshold.
"""

import logging
from typing import Optional

from apps.positions.services.sr_exit_engine import compute_initial_sl_target

logger = logging.getLogger(__name__)


def compute_adaptive_sl_target(
    symbol: str,
    price: float,
    direction: str,
    atr: Optional[float] = None,
    volatility_pct: Optional[float] = None,
    composite_score: float = 0,
    regime: str = "NORMAL",
    support_s1: Optional[float] = None,
    resistance_r1: Optional[float] = None,
    min_rr: float = 1.5,
) -> dict:
    """
    Compute adaptive stop-loss and target prices using a 3-tier fallback.

    Parameters
    ----------
    symbol : str
        Trading symbol (e.g. 'NIFTY', 'RELIANCE').
    price : float
        Current / entry price.
    direction : str
        'LONG' or 'SHORT'.
    atr : float, optional
        Average True Range value for the instrument.
    volatility_pct : float, optional
        Annualised or recent implied-volatility percentage (e.g. 25 for 25%).
    composite_score : float
        SR level confidence score (0-100). Used for ATR buffer sizing in Tier 1.
    regime : str
        Market regime — one of TRENDING, RANGING, VOLATILE, NORMAL, BREAKOUT.
    support_s1 : float, optional
        Nearest support level for SL tightening (LONG).
    resistance_r1 : float, optional
        Nearest resistance level for SL tightening (SHORT).
    min_rr : float
        Minimum acceptable risk-reward ratio. Trades below this are flagged.

    Returns
    -------
    dict
        stop_loss, target_1, target_2, sl_type, risk_reward_ratio,
        risk, reward, regime.  Optionally rr_rejected and rr_ratio_actual.
    """
    direction = direction.upper()
    regime = regime.upper() if regime else "NORMAL"
    is_long = direction == "LONG"

    stop_loss = None
    target = None
    sl_type = None

    # ------------------------------------------------------------------
    # Tier 1 — S/R-based
    # ------------------------------------------------------------------
    try:
        sr_result = compute_initial_sl_target(symbol, price, direction)
        sr_sl = sr_result.get("stop_loss")
        sr_tgt = sr_result.get("target")
        if sr_sl and sr_tgt:
            # ATR buffer: strong (score >= 76) → 0.3×ATR, else 0.5×ATR
            buffer = 0.0
            if atr is not None and atr > 0:
                buffer = atr * (0.3 if composite_score >= 76 else 0.5)

            if is_long:
                stop_loss = sr_sl - buffer
                target = sr_tgt + buffer
            else:
                stop_loss = sr_sl + buffer
                target = sr_tgt - buffer

            sl_type = "SR_BASED"
            logger.info(
                "%s Tier 1 (SR) applied — SL=%.2f  target=%.2f  buffer=%.4f",
                symbol, stop_loss, target, buffer,
            )
    except Exception:
        logger.warning("%s Tier 1 SR lookup failed, falling through", symbol, exc_info=True)

    # ------------------------------------------------------------------
    # Tier 2 — ATR-adaptive by regime
    # ------------------------------------------------------------------
    if stop_loss is None and atr is not None and atr > 0:
        regime_multipliers = {
            "TRENDING":  (1.5, 3.0),
            "RANGING":   (1.0, 2.0),
            "VOLATILE":  (2.0, 3.5),
            "NORMAL":    (2.0, 2.0),
            "BREAKOUT":  (1.2, 3.0),
        }
        sl_mult, tgt_mult = regime_multipliers.get(regime, (2.0, 2.0))

        if is_long:
            stop_loss = price - sl_mult * atr
            target = price + tgt_mult * atr
        else:
            stop_loss = price + sl_mult * atr
            target = price - tgt_mult * atr

        sl_type = "ATR_ADAPTIVE"
        logger.info(
            "%s Tier 2 (ATR) applied — regime=%s  SL=%.2f  target=%.2f",
            symbol, regime, stop_loss, target,
        )

    # ------------------------------------------------------------------
    # Tier 3 — Volatility-scaled percentage
    # ------------------------------------------------------------------
    if stop_loss is None:
        if volatility_pct is not None:
            scaled_pct = 2.0 * (volatility_pct / 30.0)
            sl_pct = max(1.5, min(scaled_pct, 3.5)) / 100.0
        else:
            sl_pct = 0.02  # flat 2%

        tgt_pct = sl_pct * 2  # target = 2× SL distance

        if is_long:
            stop_loss = price * (1 - sl_pct)
            target = price * (1 + tgt_pct)
        else:
            stop_loss = price * (1 + sl_pct)
            target = price * (1 - tgt_pct)

        sl_type = "VOLATILITY_SCALED"
        logger.info(
            "%s Tier 3 (Vol%%) applied — sl_pct=%.4f  SL=%.2f  target=%.2f",
            symbol, sl_pct, stop_loss, target,
        )

    # ------------------------------------------------------------------
    # S1 / R1 tightening
    # ------------------------------------------------------------------
    if is_long and support_s1 is not None and support_s1 > stop_loss:
        stop_loss = support_s1 * 0.995
        logger.debug("%s SL tightened to S1 vicinity: %.2f", symbol, stop_loss)

    if not is_long and resistance_r1 is not None and resistance_r1 < stop_loss:
        stop_loss = resistance_r1 * 1.005
        logger.debug("%s SL tightened to R1 vicinity: %.2f", symbol, stop_loss)

    # ------------------------------------------------------------------
    # Dual targets
    # ------------------------------------------------------------------
    target_1 = target
    target_2 = target_1 + (target_1 - price) * 0.5  # 1.5× stretch

    # ------------------------------------------------------------------
    # Risk / Reward
    # ------------------------------------------------------------------
    risk = abs(price - stop_loss)
    reward = abs(target_1 - price)
    rr_ratio = reward / risk if risk > 0 else 0.0

    result = {
        "stop_loss": round(stop_loss, 2),
        "target_1": round(target_1, 2),
        "target_2": round(target_2, 2),
        "sl_type": sl_type,
        "risk_reward_ratio": round(rr_ratio, 4),
        "risk": round(risk, 2),
        "reward": round(reward, 2),
        "regime": regime,
    }

    if rr_ratio < min_rr:
        result["rr_rejected"] = True
        result["rr_ratio_actual"] = round(rr_ratio, 4)
        logger.info(
            "%s R:R %.2f below min_rr %.2f — flagged for rejection",
            symbol, rr_ratio, min_rr,
        )

    return result
