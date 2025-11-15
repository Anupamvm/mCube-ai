"""
Trading Signal Generators using Trendlyne Data

Generates actionable trading signals by combining:
- Open Interest analysis
- Volume patterns
- DMA trends
- Trendlyne scores
- Technical indicators
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from .analyzers import (
    TrendlyneScoreAnalyzer,
    OpenInterestAnalyzer,
    VolumeAnalyzer,
    DMAAnalyzer,
    TechnicalIndicatorAnalyzer,
    HoldingPatternAnalyzer
)
from .models import TLStockData


class SignalStrength(Enum):
    STRONG_BUY = 5
    BUY = 4
    WEAK_BUY = 3
    NEUTRAL = 2
    WEAK_SELL = 1
    SELL = 0
    STRONG_SELL = -1


@dataclass
class TradingSignal:
    """Trading signal with reasoning"""
    symbol: str
    signal: SignalStrength
    confidence: float  # 0-100
    reasons: List[str]
    metrics: Dict
    trade_type: str  # 'FUTURES' or 'OPTIONS'
    recommended_action: str


class SignalGenerator:
    """Main signal generator combining multiple indicators"""

    def __init__(self):
        self.score_analyzer = TrendlyneScoreAnalyzer()
        self.oi_analyzer = OpenInterestAnalyzer()
        self.volume_analyzer = VolumeAnalyzer()
        self.dma_analyzer = DMAAnalyzer()
        self.technical_analyzer = TechnicalIndicatorAnalyzer()
        self.holding_analyzer = HoldingPatternAnalyzer()

    def generate_futures_signal(self, symbol: str, expiry: str) -> TradingSignal:
        """
        Generate trading signal for futures contract

        Combines:
        - OI buildup analysis
        - Volume surge
        - DMA trend
        - Trendlyne scores
        - Technical indicators
        """
        reasons = []
        score = 0
        metrics = {}

        # 1. Trendlyne Scores (Weight: 30%)
        scores = self.score_analyzer.get_stock_scores(symbol)
        if scores:
            metrics['trendlyne_scores'] = scores

            avg_score = scores['average']
            if avg_score >= 70:
                score += 30
                reasons.append(f"Strong Trendlyne scores (avg: {avg_score:.1f})")
            elif avg_score >= 60:
                score += 20
                reasons.append(f"Good Trendlyne scores (avg: {avg_score:.1f})")
            elif avg_score >= 50:
                score += 10
                reasons.append(f"Moderate Trendlyne scores (avg: {avg_score:.1f})")
            else:
                score -= 10
                reasons.append(f"Weak Trendlyne scores (avg: {avg_score:.1f})")

        # 2. OI Buildup Analysis (Weight: 25%)
        oi_buildup = self.oi_analyzer.analyze_oi_buildup(symbol, expiry)
        if 'buildup_type' in oi_buildup:
            metrics['oi_buildup'] = oi_buildup

            buildup_type = oi_buildup['buildup_type']
            if buildup_type == 'LONG_BUILDUP':
                score += 25
                reasons.append(f"Long buildup detected (Price↑ {oi_buildup['price_change_pct']:.1f}%, OI↑ {oi_buildup['oi_change_pct']:.1f}%)")
            elif buildup_type == 'SHORT_COVERING':
                score += 20
                reasons.append("Short covering detected")
            elif buildup_type == 'SHORT_BUILDUP':
                score -= 25
                reasons.append(f"Short buildup detected (Price↓ {oi_buildup['price_change_pct']:.1f}%, OI↑ {oi_buildup['oi_change_pct']:.1f}%)")
            elif buildup_type == 'LONG_UNWINDING':
                score -= 20
                reasons.append("Long unwinding detected")

        # 3. Volume Analysis (Weight: 15%)
        volume_surge = self.volume_analyzer.analyze_volume_surge(symbol)
        if 'surge_level' in volume_surge:
            metrics['volume'] = volume_surge

            surge_level = volume_surge['surge_level']
            if surge_level == 'VERY_HIGH':
                score += 15
                reasons.append(f"Very high volume surge ({volume_surge['volume_ratio_week']:.1f}x avg)")
            elif surge_level == 'HIGH':
                score += 10
                reasons.append(f"High volume ({volume_surge['volume_ratio_week']:.1f}x avg)")
            elif surge_level == 'MODERATE':
                score += 5
                reasons.append("Moderate volume increase")

        # 4. DMA Trend (Weight: 20%)
        dma_position = self.dma_analyzer.get_dma_position(symbol)
        if 'trend' in dma_position:
            metrics['dma'] = dma_position

            trend = dma_position['trend']
            if trend == 'STRONG_UPTREND':
                score += 20
                reasons.append("Strong uptrend (above most DMAs)")
            elif trend == 'UPTREND':
                score += 15
                reasons.append("Uptrend")
            elif trend == 'SIDEWAYS':
                score += 5
                reasons.append("Sideways trend")
            elif trend == 'DOWNTREND':
                score -= 15
                reasons.append("Downtrend")
            elif trend == 'STRONG_DOWNTREND':
                score -= 20
                reasons.append("Strong downtrend")

            # Golden/Death cross
            if dma_position.get('golden_cross'):
                score += 10
                reasons.append("Golden cross (50 SMA > 200 SMA)")
            elif dma_position.get('death_cross'):
                score -= 10
                reasons.append("Death cross (50 SMA < 200 SMA)")

        # 5. Technical Indicators (Weight: 10%)
        rsi_signal = self.technical_analyzer.get_rsi_signal(symbol)
        if 'rsi' in rsi_signal:
            metrics['rsi'] = rsi_signal

            if rsi_signal['is_oversold']:
                score += 10
                reasons.append(f"RSI oversold ({rsi_signal['rsi']:.1f})")
            elif rsi_signal['is_overbought']:
                score -= 10
                reasons.append(f"RSI overbought ({rsi_signal['rsi']:.1f})")

        # Determine signal strength
        if score >= 70:
            signal = SignalStrength.STRONG_BUY
            action = f"STRONG BUY {symbol} Futures (Expiry: {expiry})"
        elif score >= 50:
            signal = SignalStrength.BUY
            action = f"BUY {symbol} Futures (Expiry: {expiry})"
        elif score >= 30:
            signal = SignalStrength.WEAK_BUY
            action = f"WEAK BUY {symbol} Futures (Consider entry)"
        elif score >= -30:
            signal = SignalStrength.NEUTRAL
            action = f"HOLD - No clear signal for {symbol}"
        elif score >= -50:
            signal = SignalStrength.WEAK_SELL
            action = f"WEAK SELL {symbol} Futures"
        elif score >= -70:
            signal = SignalStrength.SELL
            action = f"SELL {symbol} Futures"
        else:
            signal = SignalStrength.STRONG_SELL
            action = f"STRONG SELL {symbol} Futures"

        confidence = min(100, max(0, abs(score)))

        return TradingSignal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            reasons=reasons,
            metrics=metrics,
            trade_type='FUTURES',
            recommended_action=action
        )

    def generate_options_signal(self, symbol: str, expiry: str, strategy_type: str = 'DIRECTIONAL') -> TradingSignal:
        """
        Generate trading signal for options

        Args:
            strategy_type: 'DIRECTIONAL', 'STRADDLE', 'STRANGLE', 'IRON_CONDOR'

        Combines:
        - PCR analysis
        - IV analysis
        - Strike distribution (max pain)
        - Volume and OI
        - Trendlyne scores
        """
        reasons = []
        score = 0
        metrics = {}

        # 1. PCR Analysis (Weight: 30%)
        pcr_data = self.oi_analyzer.get_pcr_ratio(symbol)
        if pcr_data:
            metrics['pcr'] = pcr_data

            pcr_oi = pcr_data['pcr_oi']
            interpretation = pcr_data['interpretation']

            if strategy_type == 'DIRECTIONAL':
                if interpretation == 'BULLISH':
                    score += 30
                    reasons.append(f"Bullish PCR ({pcr_oi:.2f} - More puts than calls)")
                elif interpretation == 'BEARISH':
                    score -= 30
                    reasons.append(f"Bearish PCR ({pcr_oi:.2f} - More calls than puts)")
                else:
                    score += 5
                    reasons.append(f"Neutral PCR ({pcr_oi:.2f})")

            elif strategy_type in ['STRADDLE', 'STRANGLE']:
                # For volatility strategies, extreme PCR is good
                if abs(pcr_oi - 1.0) > 0.3:
                    score += 25
                    reasons.append(f"High PCR imbalance ({pcr_oi:.2f}) - Good for volatility trades")

        # 2. Strike Distribution & Max Pain (Weight: 20%)
        strike_dist = self.oi_analyzer.get_strike_distribution(symbol, expiry)
        if 'max_call_oi_strike' in strike_dist:
            metrics['strike_distribution'] = strike_dist

            stock = TLStockData.objects.filter(nsecode=symbol).first()
            if stock and stock.current_price:
                resistance = strike_dist['resistance_level']
                support = strike_dist['support_level']

                if resistance:
                    distance_to_resistance = ((resistance - stock.current_price) / stock.current_price) * 100
                    if distance_to_resistance > 5:
                        score += 10
                        reasons.append(f"Price well below resistance at {resistance}")
                    elif distance_to_resistance < -5:
                        score -= 10
                        reasons.append(f"Price above resistance at {resistance}")

                if support:
                    distance_to_support = ((stock.current_price - support) / stock.current_price) * 100
                    if distance_to_support > 5:
                        score += 10
                        reasons.append(f"Price well above support at {support}")

        # 3. Trendlyne Scores (Weight: 25%)
        scores = self.score_analyzer.get_stock_scores(symbol)
        if scores:
            metrics['trendlyne_scores'] = scores

            momentum = scores['momentum']
            if strategy_type == 'DIRECTIONAL':
                if momentum >= 70:
                    score += 25
                    reasons.append(f"Strong momentum score ({momentum:.1f})")
                elif momentum >= 60:
                    score += 15
                elif momentum <= 40:
                    score -= 15
                    reasons.append(f"Weak momentum ({momentum:.1f})")

        # 4. Volume & Delivery (Weight: 15%)
        volume_data = self.volume_analyzer.analyze_volume_surge(symbol)
        delivery_data = self.volume_analyzer.analyze_delivery_percentage(symbol)

        if volume_data and 'is_surge' in volume_data:
            metrics['volume'] = volume_data

            if volume_data['is_surge']:
                score += 10
                reasons.append(f"Volume surge detected ({volume_data['surge_level']})")

        if delivery_data and 'is_strong_hands' in delivery_data:
            metrics['delivery'] = delivery_data

            if delivery_data['is_strong_hands']:
                score += 5
                reasons.append(f"Strong hands ({delivery_data['delivery_pct']:.1f}% delivery)")

        # 5. Technical Indicators (Weight: 10%)
        rsi_signal = self.technical_analyzer.get_rsi_signal(symbol)
        if 'rsi' in rsi_signal:
            metrics['rsi'] = rsi_signal

            if strategy_type == 'DIRECTIONAL':
                if rsi_signal['is_oversold']:
                    score += 10
                    reasons.append(f"RSI oversold - Consider calls")
                elif rsi_signal['is_overbought']:
                    score -= 10
                    reasons.append(f"RSI overbought - Consider puts")

        # Determine signal and strategy
        if strategy_type == 'DIRECTIONAL':
            if score >= 60:
                signal = SignalStrength.STRONG_BUY
                action = f"BUY Call Options on {symbol}"
            elif score >= 40:
                signal = SignalStrength.BUY
                action = f"BUY Call Options on {symbol} (moderate conviction)"
            elif score <= -60:
                signal = SignalStrength.STRONG_SELL
                action = f"BUY Put Options on {symbol}"
            elif score <= -40:
                signal = SignalStrength.SELL
                action = f"BUY Put Options on {symbol} (moderate conviction)"
            else:
                signal = SignalStrength.NEUTRAL
                action = f"No clear directional signal for {symbol}"

        elif strategy_type == 'STRADDLE':
            if score >= 40:
                signal = SignalStrength.BUY
                action = f"BUY Straddle on {symbol} - Expecting volatility"
            else:
                signal = SignalStrength.NEUTRAL
                action = f"Straddle not recommended on {symbol}"

        else:
            signal = SignalStrength.NEUTRAL
            action = f"Strategy {strategy_type} analysis for {symbol}"

        confidence = min(100, max(0, abs(score)))

        return TradingSignal(
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            reasons=reasons,
            metrics=metrics,
            trade_type='OPTIONS',
            recommended_action=action
        )

    def scan_for_opportunities(self, min_confidence: float = 60) -> List[TradingSignal]:
        """
        Scan all stocks in database for trading opportunities

        Returns signals with confidence >= min_confidence
        """
        opportunities = []

        # Get all stocks with data
        stocks = TLStockData.objects.exclude(
            nsecode__isnull=True
        ).exclude(
            current_price__isnull=True
        )[:50]  # Limit to top 50 for performance

        for stock in stocks:
            try:
                # Generate futures signal
                # Note: You'll need to determine the current expiry dynamically
                expiry = "CURRENT_MONTH"  # Placeholder

                signal = self.generate_futures_signal(stock.nsecode, expiry)

                if signal.confidence >= min_confidence:
                    opportunities.append(signal)

            except Exception as e:
                print(f"Error scanning {stock.nsecode}: {e}")
                continue

        # Sort by confidence
        opportunities.sort(key=lambda x: x.confidence, reverse=True)

        return opportunities


class OptionsStrategyRecommender:
    """Recommend specific options strategies based on market conditions"""

    def __init__(self):
        self.signal_generator = SignalGenerator()

    def recommend_strategy(self, symbol: str, expiry: str) -> Dict:
        """
        Recommend best options strategy for current market conditions

        Returns:
            dict with strategy recommendation and reasoning
        """
        # Get market analysis
        scores = TrendlyneScoreAnalyzer.get_stock_scores(symbol)
        dma_position = DMAAnalyzer.get_dma_position(symbol)
        rsi_signal = TechnicalIndicatorAnalyzer.get_rsi_signal(symbol)
        volume_data = VolumeAnalyzer.analyze_volume_surge(symbol)

        strategies = []

        # Directional strategies
        if scores and scores['momentum'] >= 70:
            strategies.append({
                'strategy': 'LONG_CALL',
                'confidence': 80,
                'reason': 'Strong momentum - Buy calls'
            })

        if scores and scores['momentum'] <= 30:
            strategies.append({
                'strategy': 'LONG_PUT',
                'confidence': 80,
                'reason': 'Weak momentum - Buy puts'
            })

        # Volatility strategies
        if volume_data and volume_data.get('surge_level') == 'VERY_HIGH':
            strategies.append({
                'strategy': 'LONG_STRADDLE',
                'confidence': 70,
                'reason': 'High volume surge - expecting big move'
            })

        # Neutral strategies
        if dma_position and dma_position.get('trend') == 'SIDEWAYS':
            if rsi_signal and 40 <= rsi_signal.get('rsi', 0) <= 60:
                strategies.append({
                    'strategy': 'IRON_CONDOR',
                    'confidence': 65,
                    'reason': 'Sideways market - range-bound trading'
                })

        # Conservative strategies
        if scores and scores['valuation'] >= 70:
            strategies.append({
                'strategy': 'COVERED_CALL',
                'confidence': 60,
                'reason': 'Good valuation - generate income'
            })

        if not strategies:
            strategies.append({
                'strategy': 'WAIT',
                'confidence': 50,
                'reason': 'No clear opportunity - wait for better setup'
            })

        # Sort by confidence
        strategies.sort(key=lambda x: x['confidence'], reverse=True)

        return {
            'recommended_strategy': strategies[0],
            'alternative_strategies': strategies[1:3] if len(strategies) > 1 else [],
            'market_conditions': {
                'momentum': scores['momentum'] if scores else None,
                'trend': dma_position.get('trend') if dma_position else None,
                'rsi': rsi_signal.get('rsi') if rsi_signal else None,
                'volume_level': volume_data.get('surge_level') if volume_data else None
            }
        }
