"""
S/R Risk Management Interface

Provides adaptive SL placement and early-warning escalation based on
the LevelConfidenceScorer output.

Public API:
    AdaptiveSLPlacer.compute_sl(direction, level, atr, level_score, vacuums) -> float | None
    StructuralPressureMonitor.check(position, sr_result, tracker) -> dict
    PartialCloseAdvisor.should_suggest_partial(position, sr_result) -> dict

Design:
    - All methods are pure (no DB writes, no Telegram calls).
    - The caller (SRExitEngine or tasks.py) decides what to do with the output.
    - Never raises — all methods return safe defaults on error.

3-Stage Warning System:
    STAGE 1 — NEAR_SL:           existing warning (buffer < 1%, in tasks.py)
    STAGE 2 — STRUCTURAL_PRESSURE: new — price within 0.5% of S/R level,
                                   Condition A met but not Condition B yet.
                                   Gives trader ~5 min lead time.
    STAGE 3 — TRIGGER:            existing sl_triggered (full conditions met).
"""

import logging

logger = logging.getLogger(__name__)

# Structural pressure stage 2 notif cooldown (minutes)
STRUCTURAL_PRESSURE_COOLDOWN_MINUTES = 10


class AdaptiveSLPlacer:
    """
    Computes confidence-adjusted SL distance from a structural level.

    Current engine uses fixed `support - 0.5 × ATR`.
    This class adjusts the ATR multiplier based on:
        - Level confidence score (strong = tighter, weak = wider)
        - Liquidity vacuum proximity (wider if price near vacuum)
    """

    @staticmethod
    def compute_sl(
        direction: str,
        level: float,
        atr: float,
        level_score: int = 50,
        vacuums: list = None,
        price: float = 0.0,
    ) -> float | None:
        """
        Compute adaptive ATR-buffered SL price.

        Args:
            direction:   'LONG' | 'SHORT'
            level:       Structural support (LONG) or resistance (SHORT)
            atr:         Current ATR value
            level_score: LevelConfidenceScorer score (0–100), default 50
            vacuums:     List of liquidity vacuum dicts from detect_liquidity_gaps()
            price:       Current price (for vacuum proximity check)

        Returns:
            SL price as float, or None if inputs invalid.
        """
        try:
            if not level or not atr or level <= 0:
                return None

            # ATR multiplier based on level confidence
            if level_score > 70:
                multiplier = 0.3   # tight — high-confidence level, precise SL
            elif level_score > 40:
                multiplier = 0.5   # standard (existing behaviour)
            else:
                multiplier = 0.8   # wide — noisy level, give room

            # Vacuum proximity bonus (widen further if price near vacuum)
            vacuum_factor = AdaptiveSLPlacer._vacuum_proximity_factor(
                level, vacuums or [], price
            )
            multiplier += vacuum_factor

            if direction == 'LONG':
                return level - multiplier * atr
            elif direction == 'SHORT':
                return level + multiplier * atr
            return None

        except Exception as e:
            logger.debug(f"AdaptiveSLPlacer.compute_sl error: {e}")
            return None

    @staticmethod
    def _vacuum_proximity_factor(level: float, vacuums: list, price: float) -> float:
        """
        Returns additional ATR multiplier when price is near a liquidity vacuum.
        Logic: vacuum below support = fast-move risk on breakout = wider SL.
        """
        if not vacuums or not level:
            return 0.0

        for vac in vacuums:
            vac_low = float(vac.get('low', 0))
            vac_high = float(vac.get('high', 0))
            vac_score = float(vac.get('vacuum_score', 1))

            # Check if the level is at the edge of a vacuum (level inside vacuum zone)
            if vac_low <= level <= vac_high:
                # Full vacuum — very fast moves possible
                return min(0.5, vac_score * 0.05)

            # Level is just above vacuum (vacuum below support)
            if vac_high < level and (level - vac_high) / level < 0.01:
                return min(0.3, vac_score * 0.03)

        return 0.0


class StructuralPressureMonitor:
    """
    Stage 2 warning: Condition A met but not Condition B.

    Called from SLTriggerChecker BEFORE the full trigger is evaluated.
    Returns a signal dict that tasks.py can use to send a Telegram warning.
    """

    @staticmethod
    def check(
        position,
        cond_a_met: bool,
        cond_b_met: bool,
        level: float,
        level_score: int,
        tracker,
    ) -> dict:
        """
        Check if structural pressure warning should be emitted.

        Args:
            position:     Position instance
            cond_a_met:   True if Condition A (price breach) is satisfied
            cond_b_met:   True if Condition B (session extreme) is satisfied
            level:        The S/R level being evaluated
            level_score:  Level confidence score
            tracker:      IntraDayTracker instance

        Returns:
            {
                'should_warn': bool,
                'reason':      str,
                'level':       float,
                'score':       int,
            }
        """
        try:
            if not (cond_a_met and not cond_b_met):
                return {'should_warn': False, 'reason': '', 'level': level, 'score': level_score}

            # Check cooldown: emit stage-2 warning at most once per 10 min
            from datetime import datetime, timezone as dt_timezone
            now = datetime.now(tz=dt_timezone.utc)
            last_stage2_key = f'structural_pressure_warned_at_{position.id}'
            last_warned_str = tracker.get(last_stage2_key)

            if last_warned_str:
                try:
                    last_warned = datetime.fromisoformat(last_warned_str)
                    if last_warned.tzinfo is None:
                        last_warned = last_warned.replace(tzinfo=dt_timezone.utc)
                    age_min = (now - last_warned).total_seconds() / 60
                    if age_min < STRUCTURAL_PRESSURE_COOLDOWN_MINUTES:
                        return {'should_warn': False, 'reason': 'COOLDOWN', 'level': level, 'score': level_score}
                except Exception:
                    pass

            # Record warning time
            tracker.set(last_stage2_key, now.isoformat())

            direction = getattr(position, 'direction', '')
            price = float(getattr(position, 'current_price', 0) or 0)

            if direction == 'LONG':
                reason = (
                    f"⚠️ STRUCTURAL PRESSURE\n"
                    f"Price {price:.2f} breached support {level:.2f} (Cond A met)\n"
                    f"Session low hasn't confirmed yet (Cond B pending)\n"
                    f"Level strength: {level_score}/100 — SL may trigger next candle"
                )
            elif direction == 'SHORT':
                reason = (
                    f"⚠️ STRUCTURAL PRESSURE\n"
                    f"Price {price:.2f} breached resistance {level:.2f} (Cond A met)\n"
                    f"Session high hasn't confirmed yet (Cond B pending)\n"
                    f"Level strength: {level_score}/100 — SL may trigger next candle"
                )
            else:
                reason = (
                    f"⚠️ STRUCTURAL PRESSURE\n"
                    f"Level {level:.2f} breached (Cond A met, Cond B pending)\n"
                    f"Level strength: {level_score}/100"
                )

            return {
                'should_warn': True,
                'reason': reason,
                'level': level,
                'score': level_score,
            }

        except Exception as e:
            logger.debug(f"StructuralPressureMonitor.check error: {e}")
            return {'should_warn': False, 'reason': '', 'level': 0.0, 'score': 0}


class PartialCloseAdvisor:
    """
    Suggests partial close (50%) when approaching a moderately-strong level.

    Rationale:
        - Level strength 40–60 (uncertain): not strong enough for full exit,
          but risky enough to reduce position
        - Condition A met: price has breached the level
        - Condition B not yet met: structural confirmation pending
    """

    @staticmethod
    def should_suggest_partial(
        position,
        cond_a_met: bool,
        cond_b_met: bool,
        level_score: int,
        tracker,
    ) -> dict:
        """
        Returns:
            {
                'suggest': bool,
                'close_pct': float — fraction to close (0.5 = 50%)
                'rationale': str
            }
        """
        try:
            # Only suggest partial close in the "uncertain zone"
            if not cond_a_met:
                return {'suggest': False, 'close_pct': 0.0, 'rationale': ''}

            if cond_b_met:
                # Both conditions met — full exit is appropriate
                return {'suggest': False, 'close_pct': 0.0, 'rationale': ''}

            if not (40 <= level_score <= 60):
                return {'suggest': False, 'close_pct': 0.0, 'rationale': ''}

            # Check dedup: only suggest once per position per day
            partial_key = f'partial_close_suggested_{position.id}'
            if tracker.get(partial_key):
                return {'suggest': False, 'close_pct': 0.0, 'rationale': 'ALREADY_SUGGESTED'}

            tracker.set(partial_key, True)

            direction = getattr(position, 'direction', '')
            price = float(getattr(position, 'current_price', 0) or 0)

            rationale = (
                f"Level strength {level_score}/100 (moderate) — "
                f"partial close reduces risk while preserving upside. "
                f"Price {price:.2f} breached level (Cond A), "
                f"full structural confirmation pending (Cond B)."
            )

            return {
                'suggest': True,
                'close_pct': 0.5,
                'rationale': rationale,
            }

        except Exception as e:
            logger.debug(f"PartialCloseAdvisor.should_suggest_partial error: {e}")
            return {'suggest': False, 'close_pct': 0.0, 'rationale': ''}
