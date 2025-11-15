"""
Trade Validators using Trendlyne Data

Validates trade setups before execution using comprehensive checks
"""

from typing import Tuple, Dict, Optional, List
from dataclasses import dataclass

from .analyzers import (
    TrendlyneScoreAnalyzer,
    OpenInterestAnalyzer,
    VolumeAnalyzer,
    DMAAnalyzer,
    TechnicalIndicatorAnalyzer,
    HoldingPatternAnalyzer
)
from .models import TLStockData


@dataclass
class ValidationResult:
    """Trade validation result"""
    approved: bool
    confidence: float  # 0-100
    reasons: List[str]
    warnings: List[str]
    metrics: Dict


class TradeValidator:
    """Validates trades before execution"""

    def __init__(self):
        self.score_analyzer = TrendlyneScoreAnalyzer()
        self.oi_analyzer = OpenInterestAnalyzer()
        self.volume_analyzer = VolumeAnalyzer()
        self.dma_analyzer = DMAAnalyzer()
        self.technical_analyzer = TechnicalIndicatorAnalyzer()
        self.holding_analyzer = HoldingPatternAnalyzer()

    def validate_futures_long(
        self,
        symbol: str,
        expiry: str,
        min_durability: float = 50,
        min_momentum: float = 50,
        min_valuation: float = 40
    ) -> ValidationResult:
        """
        Validate LONG futures position

        Checks:
        - Trendlyne scores meet minimum criteria
        - Positive OI buildup
        - Good volume
        - Uptrend in DMAs
        - No overbought conditions
        """
        reasons = []
        warnings = []
        metrics = {}
        score = 100  # Start with 100, deduct for failures

        # 1. Trendlyne Scores Validation
        approved, reason = self.score_analyzer.validate_entry(
            symbol,
            min_durability=min_durability,
            min_valuation=min_valuation,
            min_momentum=min_momentum
        )

        scores = self.score_analyzer.get_stock_scores(symbol)
        if scores:
            metrics['trendlyne_scores'] = scores

            if not approved:
                score -= 30
                warnings.append(f"⚠️ {reason}")
            else:
                reasons.append(f"✓ {reason}")

        # 2. OI Buildup Check
        oi_buildup = self.oi_analyzer.analyze_oi_buildup(symbol, expiry)
        if 'buildup_type' in oi_buildup:
            metrics['oi_buildup'] = oi_buildup

            buildup = oi_buildup['buildup_type']
            if buildup == 'LONG_BUILDUP':
                reasons.append("✓ Long buildup detected - Price and OI both rising")
            elif buildup == 'SHORT_BUILDUP':
                score -= 40
                warnings.append("⚠️ SHORT buildup detected - Bearish pattern")
            elif buildup == 'LONG_UNWINDING':
                score -= 30
                warnings.append("⚠️ Long unwinding - Longs are exiting")
            elif buildup == 'SHORT_COVERING':
                reasons.append("✓ Short covering - Bullish")
                score -= 10  # Temporary bullishness

        # 3. DMA Trend Check
        dma_position = self.dma_analyzer.get_dma_position(symbol)
        if 'trend' in dma_position:
            metrics['dma'] = dma_position

            trend = dma_position['trend']
            if trend in ['STRONG_UPTREND', 'UPTREND']:
                reasons.append(f"✓ {trend.replace('_', ' ').title()}")
            elif trend == 'SIDEWAYS':
                score -= 10
                warnings.append("⚠️ Sideways trend - Limited upside potential")
            else:
                score -= 30
                warnings.append(f"⚠️ {trend.replace('_', ' ').title()} - Not suitable for long")

            if dma_position.get('death_cross'):
                score -= 20
                warnings.append("⚠️ Death cross detected (50 SMA < 200 SMA)")

        # 4. RSI Check (Avoid Overbought)
        rsi_signal = self.technical_analyzer.get_rsi_signal(symbol)
        if 'rsi' in rsi_signal:
            metrics['rsi'] = rsi_signal

            if rsi_signal['is_overbought']:
                score -= 25
                warnings.append(f"⚠️ RSI overbought ({rsi_signal['rsi']:.1f})")
            elif rsi_signal['is_oversold']:
                reasons.append(f"✓ RSI oversold ({rsi_signal['rsi']:.1f}) - Good entry")
            else:
                reasons.append(f"✓ RSI normal ({rsi_signal['rsi']:.1f})")

        # 5. Volume Check
        volume_data = self.volume_analyzer.analyze_volume_surge(symbol)
        if 'surge_level' in volume_data:
            metrics['volume'] = volume_data

            if volume_data['is_surge']:
                reasons.append(f"✓ Volume surge ({volume_data['surge_level']})")
            else:
                score -= 5
                warnings.append("⚠️ Normal volume - Wait for confirmation")

        # 6. Holding Pattern Check
        holdings = self.holding_analyzer.analyze_holdings(symbol)
        if 'overall_confidence' in holdings:
            metrics['holdings'] = holdings

            conf = holdings['overall_confidence']
            if conf in ['STRONG_CONFIDENCE', 'MODERATE_CONFIDENCE']:
                reasons.append(f"✓ {conf.replace('_', ' ').title()}")
            else:
                score -= 10
                warnings.append("⚠️ Weak institutional confidence")

        # Final decision
        approved = score >= 50
        confidence = min(100, max(0, score))

        return ValidationResult(
            approved=approved,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
            metrics=metrics
        )

    def validate_futures_short(
        self,
        symbol: str,
        expiry: str,
        max_durability: float = 70
    ) -> ValidationResult:
        """
        Validate SHORT futures position

        Checks:
        - Weak Trendlyne scores
        - Negative OI buildup
        - Downtrend
        - Not oversold
        """
        reasons = []
        warnings = []
        metrics = {}
        score = 100

        # 1. Trendlyne Scores (Want low scores for short)
        scores = self.score_analyzer.get_stock_scores(symbol)
        if scores:
            metrics['trendlyne_scores'] = scores

            if scores['average'] < 40:
                reasons.append(f"✓ Weak Trendlyne scores ({scores['average']:.1f})")
            elif scores['average'] > max_durability:
                score -= 30
                warnings.append(f"⚠️ High quality stock (avg: {scores['average']:.1f}) - risky short")

        # 2. OI Buildup (Want short buildup or long unwinding)
        oi_buildup = self.oi_analyzer.analyze_oi_buildup(symbol, expiry)
        if 'buildup_type' in oi_buildup:
            metrics['oi_buildup'] = oi_buildup

            buildup = oi_buildup['buildup_type']
            if buildup == 'SHORT_BUILDUP':
                reasons.append("✓ Short buildup - Bears are adding positions")
            elif buildup == 'LONG_UNWINDING':
                reasons.append("✓ Long unwinding - Bulls are exiting")
            elif buildup == 'LONG_BUILDUP':
                score -= 40
                warnings.append("⚠️ LONG buildup - Bullish pattern, avoid short")

        # 3. DMA Trend (Want downtrend)
        dma_position = self.dma_analyzer.get_dma_position(symbol)
        if 'trend' in dma_position:
            metrics['dma'] = dma_position

            trend = dma_position['trend']
            if trend in ['STRONG_DOWNTREND', 'DOWNTREND']:
                reasons.append(f"✓ {trend.replace('_', ' ').title()}")
            elif trend in ['STRONG_UPTREND', 'UPTREND']:
                score -= 40
                warnings.append(f"⚠️ {trend.replace('_', ' ').title()} - Not suitable for short")

        # 4. RSI Check (Avoid Oversold)
        rsi_signal = self.technical_analyzer.get_rsi_signal(symbol)
        if 'rsi' in rsi_signal:
            metrics['rsi'] = rsi_signal

            if rsi_signal['is_oversold']:
                score -= 25
                warnings.append(f"⚠️ RSI oversold ({rsi_signal['rsi']:.1f}) - Bounce risk")
            elif rsi_signal['is_overbought']:
                reasons.append(f"✓ RSI overbought ({rsi_signal['rsi']:.1f}) - Good for short")

        approved = score >= 50
        confidence = min(100, max(0, score))

        return ValidationResult(
            approved=approved,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
            metrics=metrics
        )

    def validate_options_call_buy(
        self,
        symbol: str,
        strike: float,
        expiry: str
    ) -> ValidationResult:
        """Validate buying call options"""
        reasons = []
        warnings = []
        metrics = {}
        score = 100

        # Get current price
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock:
            return ValidationResult(False, 0, ["Stock data not found"], [], {})

        current_price = stock.current_price

        # 1. Strike Selection
        distance_pct = ((strike - current_price) / current_price) * 100

        if distance_pct > 10:
            score -= 30
            warnings.append(f"⚠️ Strike {distance_pct:.1f}% OTM - Low probability")
        elif distance_pct > 5:
            score -= 15
            warnings.append(f"⚠️ Strike {distance_pct:.1f}% OTM")
        elif -2 <= distance_pct <= 2:
            reasons.append(f"✓ ATM strike - Good delta")
        else:
            reasons.append(f"✓ Strike selection appropriate ({distance_pct:.1f}%)")

        # 2. Momentum Check
        scores = self.score_analyzer.get_stock_scores(symbol)
        if scores:
            if scores['momentum'] >= 60:
                reasons.append(f"✓ Strong momentum ({scores['momentum']:.1f})")
            else:
                score -= 20
                warnings.append(f"⚠️ Weak momentum ({scores['momentum']:.1f})")

        # 3. Trend Check
        dma_position = self.dma_analyzer.get_dma_position(symbol)
        if dma_position and dma_position.get('trend') in ['DOWNTREND', 'STRONG_DOWNTREND']:
            score -= 25
            warnings.append("⚠️ Downtrend - Against trend trade")

        # 4. Support/Resistance
        sr_levels = self.technical_analyzer.get_support_resistance(symbol)
        if sr_levels and sr_levels.get('nearest_resistance'):
            resistance = sr_levels['nearest_resistance']
            if strike > resistance:
                reasons.append(f"✓ Strike above resistance ({resistance})")
            elif current_price < resistance < strike:
                warnings.append(f"⚠️ Resistance at {resistance} between price and strike")

        approved = score >= 50
        confidence = min(100, max(0, score))

        return ValidationResult(
            approved=approved,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
            metrics=metrics
        )

    def validate_trade(
        self,
        trade_type: str,
        symbol: str,
        expiry: str = None,
        strike: float = None
    ) -> ValidationResult:
        """
        Universal trade validator

        Args:
            trade_type: 'FUTURES_LONG', 'FUTURES_SHORT', 'CALL_BUY', 'PUT_BUY'
            symbol: Stock NSE code
            expiry: Contract expiry
            strike: Option strike price
        """
        if trade_type == 'FUTURES_LONG':
            return self.validate_futures_long(symbol, expiry)
        elif trade_type == 'FUTURES_SHORT':
            return self.validate_futures_short(symbol, expiry)
        elif trade_type == 'CALL_BUY':
            return self.validate_options_call_buy(symbol, strike, expiry)
        else:
            return ValidationResult(
                False,
                0,
                ["Unknown trade type"],
                [],
                {}
            )


class RiskValidator:
    """Additional risk-based validation"""

    @staticmethod
    def validate_position_sizing(
        account_size: float,
        position_value: float,
        max_position_pct: float = 10
    ) -> Tuple[bool, str]:
        """
        Validate position size relative to account

        Args:
            account_size: Total account value
            position_value: Value of proposed position
            max_position_pct: Maximum % of account for single position
        """
        position_pct = (position_value / account_size) * 100

        if position_pct > max_position_pct:
            return False, f"Position size {position_pct:.1f}% exceeds max {max_position_pct}%"

        return True, f"Position size OK ({position_pct:.1f}%)"

    @staticmethod
    def validate_sector_concentration(
        symbol: str,
        existing_positions: List[str],
        max_sector_exposure: float = 30
    ) -> Tuple[bool, str]:
        """Validate sector concentration risk"""
        # Get sector of new position
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock:
            return True, "Unable to check sector"

        sector = stock.sector_name

        # Count existing positions in same sector
        sector_count = 0
        for pos_symbol in existing_positions:
            pos_stock = TLStockData.objects.filter(nsecode=pos_symbol).first()
            if pos_stock and pos_stock.sector_name == sector:
                sector_count += 1

        sector_pct = (sector_count / len(existing_positions)) * 100 if existing_positions else 0

        if sector_pct > max_sector_exposure:
            return False, f"Sector exposure {sector_pct:.1f}% exceeds max {max_sector_exposure}%"

        return True, f"Sector exposure OK ({sector_pct:.1f}%)"
