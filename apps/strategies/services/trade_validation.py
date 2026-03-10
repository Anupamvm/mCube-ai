import logging

logger = logging.getLogger(__name__)


class TradeValidationLayer:
    """Post-score validation gate for futures trades."""

    def validate(self, analysis_result, regime='NORMAL', min_rr=1.5) -> dict:
        """
        Validate a trade suggestion after scoring.

        Args:
            analysis_result: dict from EnhancedFuturesAnalyzer.analyze() containing:
                - composite_score (int)
                - direction (str)
                - entry_params (dict with stop_loss, target_1, entry_price, risk_reward_ratio)
                - symbol (str)
            regime: str - market regime (TRENDING, RANGING, VOLATILE, BREAKOUT, NORMAL)
            min_rr: float - minimum risk:reward ratio (default 1.5)

        Returns:
            {
                'passed': bool,
                'adjusted_score': int,
                'rejection_reason': str or None,
                'rr_ratio': float,
                'warnings': list[str],
            }
        """
        warnings = []
        rejection_reason = None

        composite_score = analysis_result.get('composite_score', 0)
        entry_params = analysis_result.get('entry_params') or {}
        symbol = analysis_result.get('symbol', 'UNKNOWN')

        adjusted_score = composite_score

        # --- 1. R:R ratio check ---
        rr_ratio = self._compute_rr_ratio(entry_params)

        if rr_ratio is not None:
            if rr_ratio < 1.0:
                rejection_reason = "R:R below 1.0"
                logger.info("[%s] Trade rejected — R:R %.2f below 1.0", symbol, rr_ratio)
            elif rr_ratio < min_rr:
                warnings.append(f"R:R {rr_ratio:.2f} is below preferred minimum {min_rr}")
        else:
            warnings.append("Could not compute R:R ratio — missing entry params")

        # --- 2. Regime-appropriate direction ---
        if regime == 'RANGING':
            adjusted_score -= 10
            logger.debug("[%s] RANGING regime: applied -10 penalty (score %d -> %d)",
                         symbol, composite_score, adjusted_score)
        elif regime == 'VOLATILE':
            if composite_score < 75:
                rejection_reason = rejection_reason or (
                    f"Score {composite_score} below 75 threshold for VOLATILE regime"
                )
                logger.info("[%s] VOLATILE regime requires score >= 75, got %d",
                            symbol, composite_score)

        # --- 3. SL distance check ---
        entry_price = entry_params.get('entry_price')
        stop_loss = entry_params.get('stop_loss')

        if entry_price and stop_loss and entry_price != 0:
            sl_distance_pct = abs(entry_price - stop_loss) / entry_price * 100
            if sl_distance_pct < 0.5:
                warnings.append("SL too tight — may get stopped out on noise")
            elif sl_distance_pct > 5:
                warnings.append("SL too wide — excessive risk per trade")

        # --- 4. Target reachability ---
        target = entry_params.get('target_1')
        days_to_expiry = entry_params.get('days_to_expiry')

        if target and entry_price and days_to_expiry is not None and entry_price != 0:
            target_distance_pct = abs(target - entry_price) / entry_price * 100
            if target_distance_pct > 3 and days_to_expiry < 5:
                warnings.append("Target may be unreachable before expiry")

        # --- 5. Final passed check ---
        passed = (rejection_reason is None) and (adjusted_score >= 65)

        if not passed and rejection_reason is None:
            rejection_reason = f"Adjusted score {adjusted_score} below minimum 65"

        result = {
            'passed': passed,
            'adjusted_score': adjusted_score,
            'rejection_reason': rejection_reason,
            'rr_ratio': rr_ratio if rr_ratio is not None else 0.0,
            'warnings': warnings,
        }

        log_level = logging.INFO if not passed else logging.DEBUG
        logger.log(log_level, "[%s] Validation %s | score=%d adj=%d rr=%.2f warnings=%d reason=%s",
                   symbol, "PASSED" if passed else "FAILED",
                   composite_score, adjusted_score,
                   result['rr_ratio'], len(warnings), rejection_reason)

        return result

    @staticmethod
    def _compute_rr_ratio(entry_params: dict):
        """Compute risk:reward ratio from entry params. Returns None if data is missing."""
        # Prefer pre-computed ratio if available
        precomputed = entry_params.get('risk_reward_ratio')
        if precomputed is not None:
            try:
                return float(precomputed)
            except (TypeError, ValueError):
                pass

        # Calculate from price levels
        entry_price = entry_params.get('entry_price')
        stop_loss = entry_params.get('stop_loss')
        target = entry_params.get('target_1')

        if not all([entry_price, stop_loss, target]):
            return None

        risk = abs(entry_price - stop_loss)
        reward = abs(target - entry_price)

        if risk == 0:
            return None

        return round(reward / risk, 2)
