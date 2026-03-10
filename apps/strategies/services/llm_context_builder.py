"""
LLM Context Builder — builds enriched context strings for LLM trade validation.

Instead of passing only symbol + direction, this module assembles a structured
multi-section text block that gives the LLM full scoring, risk, signal, and
regime context so it can make better-informed validation decisions.
"""

import logging

logger = logging.getLogger(__name__)

# Max weights per scoring dimension (from EnhancedFuturesAnalyzer)
WEIGHTS = {
    'oi_fno': 45,
    'technical_momentum': 35,
    'trend_confirmation': 30,
    'volume_quality': 25,
    'institutional_flow': 25,
    'fundamental_quality': 20,
    'risk_adjustment': 30,
    'news_sentiment': 25,
    'analyst_consensus': 20,
    'research_reports': 15,
    'investor_calls': 10,
    'momentum_acceleration': 20,
}

# Human-readable labels for score keys
SCORE_LABELS = {
    'oi_fno': 'OI & F&O Analysis',
    'technical_momentum': 'Technical Momentum',
    'trend_confirmation': 'Trend Confirmation',
    'volume_quality': 'Volume Quality',
    'institutional_flow': 'Institutional Flow',
    'fundamental_quality': 'Fundamental Quality',
    'risk_adjustment': 'Risk Adjustment',
    'news_sentiment': 'News Sentiment',
    'analyst_consensus': 'Analyst Consensus',
    'research_reports': 'Research Reports',
    'investor_calls': 'Investor Calls',
    'momentum_acceleration': 'Momentum Acceleration',
}

# Regime descriptions for the LLM
REGIME_DESCRIPTIONS = {
    'TRENDING': 'Strong trend detected — use wider targets, tighter trailing SL',
    'RANGE_BOUND': 'Sideways market — prefer mean-reversion, tighter targets',
    'VOLATILE': 'High volatility — widen SL, reduce position size',
    'LOW_VOLATILITY': 'Low volatility — tighter ranges, watch for breakout',
    'NORMAL': 'Normal conditions — standard parameters apply',
}


def build_trade_context(analysis_result, regime='NORMAL', validation=None) -> str:
    """
    Build enriched context string for LLM trade validation.

    Args:
        analysis_result: dict from EnhancedFuturesAnalyzer.analyze() with:
            - symbol, direction, composite_score, scores (dict), entry_params, details
        regime: str - market regime (e.g. 'TRENDING', 'RANGE_BOUND', 'NORMAL')
        validation: dict from TradeValidationLayer.validate() (optional) with:
            - rr_ratio, warnings, adjusted_score

    Returns:
        str: Multi-section context string for LLM
    """
    if not analysis_result:
        logger.warning("build_trade_context called with empty analysis_result")
        return ""

    sections = []

    # --- 1. Market Regime ---
    regime_section = _build_regime_section(regime, analysis_result)
    if regime_section:
        sections.append(regime_section)

    # --- 2. Scoring Summary ---
    scoring_section = _build_scoring_section(analysis_result, validation)
    if scoring_section:
        sections.append(scoring_section)

    # --- 3. Risk Profile ---
    risk_section = _build_risk_section(analysis_result, validation)
    if risk_section:
        sections.append(risk_section)

    # --- 4. Key Signals ---
    signals_section = _build_signals_section(analysis_result)
    if signals_section:
        sections.append(signals_section)

    # --- 5. Warnings ---
    warnings_section = _build_warnings_section(analysis_result, validation)
    if warnings_section:
        sections.append(warnings_section)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_regime_section(regime, analysis_result):
    """Build the market regime section."""
    regime = regime or 'NORMAL'
    regime_upper = regime.upper()

    lines = ["=== MARKET REGIME ==="]

    # Try to extract confidence from analysis_result details
    confidence = None
    details = analysis_result.get('details', {})
    if isinstance(details, dict):
        regime_info = details.get('regime_info') or details.get('market_regime') or {}
        if isinstance(regime_info, dict):
            confidence = regime_info.get('confidence')

    if confidence is not None:
        lines.append(f"Regime: {regime_upper} (confidence: {confidence}%)")
    else:
        lines.append(f"Regime: {regime_upper}")

    description = REGIME_DESCRIPTIONS.get(regime_upper, REGIME_DESCRIPTIONS['NORMAL'])
    lines.append(f"Recommendation: {description}")

    return "\n".join(lines)


def _build_scoring_section(analysis_result, validation=None):
    """Build the scoring summary section with top strengths and key weaknesses."""
    scores = analysis_result.get('scores')
    composite = analysis_result.get('composite_score')

    if not scores and composite is None:
        return None

    lines = ["=== SCORING SUMMARY ==="]

    # Composite score — prefer adjusted if available
    display_score = composite
    if validation and isinstance(validation, dict):
        adjusted = validation.get('adjusted_score')
        if adjusted is not None:
            display_score = adjusted

    if display_score is not None:
        lines.append(f"Composite Score: {display_score}/100")

    if not scores or not isinstance(scores, dict):
        return "\n".join(lines)

    # Compute percentage for each score dimension
    scored_items = []
    for key, value in scores.items():
        max_weight = WEIGHTS.get(key)
        if max_weight and max_weight > 0 and value is not None:
            pct = round((value / max_weight) * 100)
            label = SCORE_LABELS.get(key, key.replace('_', ' ').title())
            scored_items.append((label, value, max_weight, pct))

    if not scored_items:
        return "\n".join(lines)

    # Sort by percentage descending
    scored_items.sort(key=lambda x: x[3], reverse=True)

    # Top 3 strengths
    strengths = scored_items[:3]
    if strengths:
        lines.append("Top Strengths:")
        for label, value, max_w, pct in strengths:
            lines.append(f"  - {label}: {value}/{max_w} ({pct}%)")

    # Bottom 2 weaknesses
    weaknesses = scored_items[-2:] if len(scored_items) > 3 else []
    if weaknesses:
        lines.append("Key Weaknesses:")
        for label, value, max_w, pct in weaknesses:
            lines.append(f"  - {label}: {value}/{max_w} ({pct}%)")

    return "\n".join(lines)


def _build_risk_section(analysis_result, validation=None):
    """Build the risk profile section from entry_params."""
    entry_params = analysis_result.get('entry_params')
    direction = analysis_result.get('direction')

    if not entry_params and not direction:
        return None

    lines = ["=== RISK PROFILE ==="]

    if direction:
        lines.append(f"Direction: {direction}")

    if not entry_params or not isinstance(entry_params, dict):
        return "\n".join(lines) if len(lines) > 1 else None

    entry = entry_params.get('entry') or entry_params.get('entry_price')
    sl = entry_params.get('stop_loss') or entry_params.get('sl')
    target = entry_params.get('target') or entry_params.get('target_price')

    if entry is not None:
        try:
            entry_val = float(entry)
            lines.append(f"Entry: \u20b9{entry_val:,.2f}")

            if sl is not None:
                sl_val = float(sl)
                sl_pct = abs((sl_val - entry_val) / entry_val) * 100
                lines.append(f"Stop-Loss: \u20b9{sl_val:,.2f} (-{sl_pct:.1f}%)")

            if target is not None:
                tgt_val = float(target)
                tgt_pct = abs((tgt_val - entry_val) / entry_val) * 100
                lines.append(f"Target: \u20b9{tgt_val:,.2f} (+{tgt_pct:.1f}%)")

            # Risk:Reward ratio
            rr = None
            if validation and isinstance(validation, dict):
                rr = validation.get('rr_ratio')
            if rr is None and sl is not None and target is not None:
                risk = abs(entry_val - float(sl))
                reward = abs(float(target) - entry_val)
                if risk > 0:
                    rr = round(reward / risk, 1)

            if rr is not None:
                lines.append(f"Risk:Reward: 1:{rr}")

            # SL distance percentage
            if sl is not None:
                sl_dist = abs((float(sl) - entry_val) / entry_val) * 100
                lines.append(f"SL Distance: {sl_dist:.1f}%")

        except (ValueError, TypeError, ZeroDivisionError):
            logger.debug("Could not parse numeric entry_params for risk section")

    return "\n".join(lines) if len(lines) > 1 else None


def _build_signals_section(analysis_result):
    """Build key signals section from algorithm_reasoning in details."""
    details = analysis_result.get('details')
    if not details or not isinstance(details, dict):
        return None

    reasoning = details.get('algorithm_reasoning') or details.get('signals') or {}
    if not reasoning or not isinstance(reasoning, dict):
        return None

    lines = ["=== KEY SIGNALS ==="]

    # Common signal keys to look for
    signal_labels = {
        'oi_signal': 'OI Signal',
        'dma_signal': 'DMA Signal',
        'sector_signal': 'Sector Signal',
        'volume_signal': 'Volume Signal',
        'trend_signal': 'Trend Signal',
        'momentum_signal': 'Momentum Signal',
        'institutional_signal': 'Institutional Signal',
        'news_signal': 'News Signal',
        'vwap_signal': 'VWAP Signal',
    }

    found = False
    for key, label in signal_labels.items():
        value = reasoning.get(key)
        if value is not None and value != '':
            lines.append(f"{label}: {value}")
            found = True

    # Include any other string-valued signals not in the standard set
    for key, value in reasoning.items():
        if key not in signal_labels and isinstance(value, str) and value:
            label = key.replace('_', ' ').title()
            lines.append(f"{label}: {value}")
            found = True

    return "\n".join(lines) if found else None


def _build_warnings_section(analysis_result, validation=None):
    """Build warnings section from validation warnings and entry_params checks."""
    warnings = []

    # Validation-layer warnings
    if validation and isinstance(validation, dict):
        val_warnings = validation.get('warnings')
        if isinstance(val_warnings, list):
            warnings.extend(val_warnings)
        elif isinstance(val_warnings, str) and val_warnings:
            warnings.append(val_warnings)

    # Derived warnings from entry_params
    entry_params = analysis_result.get('entry_params')
    if entry_params and isinstance(entry_params, dict):
        entry = entry_params.get('entry') or entry_params.get('entry_price')
        sl = entry_params.get('stop_loss') or entry_params.get('sl')
        if entry is not None and sl is not None:
            try:
                entry_val = float(entry)
                sl_val = float(sl)
                sl_dist = abs((sl_val - entry_val) / entry_val) * 100
                if sl_dist < 1.0:
                    tight_warn = f"SL distance below 1% ({sl_dist:.1f}%) \u2014 tight stop"
                    if tight_warn not in warnings:
                        warnings.append(tight_warn)
            except (ValueError, TypeError, ZeroDivisionError):
                pass

    if not warnings:
        return None

    lines = ["=== WARNINGS ==="]
    for w in warnings:
        lines.append(f"- {w}")

    return "\n".join(lines)
