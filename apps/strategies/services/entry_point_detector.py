"""
Entry Point Detector for ICICI Futures Strategy

Monitors candidates and detects optimal entry points based on:
- Price action (breakouts, pullbacks, consolidation exits)
- Volume confirmation
- Support/Resistance levels
- Momentum indicators
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from django.utils import timezone

from apps.data.analyzers import (
    TechnicalIndicatorAnalyzer,
    VolumeAnalyzer,
    DMAAnalyzer,
)
from apps.data.models import ContractStockData

logger = logging.getLogger(__name__)


class EntryPointDetector:
    """
    Detects optimal entry points for futures trades

    Entry Signal Types:
    1. BREAKOUT - Price breaks above resistance with volume
    2. PULLBACK - Price pulls back to support after uptrend
    3. CONSOLIDATION_EXIT - Price exits consolidation range
    4. MOMENTUM_SURGE - Strong momentum with volume confirmation
    """

    def __init__(self):
        self.technical_analyzer = TechnicalIndicatorAnalyzer()
        self.volume_analyzer = VolumeAnalyzer()
        self.dma_analyzer = DMAAnalyzer()

    def detect_entry_point(
        self,
        symbol: str,
        direction: str,
        current_price: Decimal,
        support: Optional[Decimal] = None,
        resistance: Optional[Decimal] = None
    ) -> Dict:
        """
        Detect if current price action presents a good entry point

        Args:
            symbol: Stock symbol
            direction: LONG or SHORT
            current_price: Current market price
            support: Support level (optional)
            resistance: Resistance level (optional)

        Returns:
            dict: {
                'entry_signal': bool,
                'signal_type': str,
                'signal_strength': float (0-1),
                'entry_price': Decimal,
                'reasoning': str,
                'indicators': dict
            }
        """

        logger.info(f"Detecting entry point for {symbol} ({direction})")
        logger.info(f"Current Price: ₹{current_price:,.2f}")

        # Get technical indicators
        indicators = self._get_technical_indicators(symbol, current_price)

        # Get volume analysis
        volume_data = self._get_volume_analysis(symbol)

        # Detect entry signals based on direction
        if direction == 'LONG':
            entry_result = self._detect_long_entry(
                symbol=symbol,
                current_price=current_price,
                support=support,
                resistance=resistance,
                indicators=indicators,
                volume_data=volume_data
            )
        else:  # SHORT
            entry_result = self._detect_short_entry(
                symbol=symbol,
                current_price=current_price,
                support=support,
                resistance=resistance,
                indicators=indicators,
                volume_data=volume_data
            )

        logger.info(f"Entry Signal: {entry_result['entry_signal']}")
        if entry_result['entry_signal']:
            logger.info(f"Signal Type: {entry_result['signal_type']}")
            logger.info(f"Signal Strength: {entry_result['signal_strength']:.2f}")
            logger.info(f"Reasoning: {entry_result['reasoning']}")

        return entry_result

    def _get_technical_indicators(self, symbol: str, current_price: Decimal) -> Dict:
        """Get current technical indicators"""

        indicators = {}

        try:
            # RSI
            rsi_data = self.technical_analyzer.calculate_rsi(symbol, period=14)
            if rsi_data:
                indicators['rsi'] = rsi_data.get('rsi', 50)
                indicators['rsi_signal'] = rsi_data.get('signal', 'NEUTRAL')

            # MACD
            macd_data = self.technical_analyzer.calculate_macd(symbol)
            if macd_data:
                indicators['macd_signal'] = macd_data.get('signal', 'NEUTRAL')
                indicators['macd_histogram'] = macd_data.get('histogram', 0)

            # DMAs
            dma_data = self.dma_analyzer.get_dma_signals(symbol)
            if dma_data:
                indicators['above_20dma'] = dma_data.get('above_20dma', False)
                indicators['above_50dma'] = dma_data.get('above_50dma', False)
                indicators['above_200dma'] = dma_data.get('above_200dma', False)
                indicators['golden_cross'] = dma_data.get('golden_cross', False)
                indicators['death_cross'] = dma_data.get('death_cross', False)

        except Exception as e:
            logger.error(f"Error getting technical indicators: {e}")

        return indicators

    def _get_volume_analysis(self, symbol: str) -> Dict:
        """Get volume analysis"""

        volume_data = {}

        try:
            vol_analysis = self.volume_analyzer.detect_breakouts(symbol)
            if vol_analysis:
                volume_data['volume_breakout'] = vol_analysis.get('volume_breakout', False)
                volume_data['volume_ratio'] = vol_analysis.get('volume_ratio', 1.0)
                volume_data['delivery_pct'] = vol_analysis.get('delivery_pct', 0)

        except Exception as e:
            logger.error(f"Error getting volume analysis: {e}")

        return volume_data

    def _detect_long_entry(
        self,
        symbol: str,
        current_price: Decimal,
        support: Optional[Decimal],
        resistance: Optional[Decimal],
        indicators: Dict,
        volume_data: Dict
    ) -> Dict:
        """Detect LONG entry signals"""

        entry_signal = False
        signal_type = None
        signal_strength = 0.0
        reasoning = ""

        # SIGNAL 1: Breakout Above Resistance
        if resistance and current_price > resistance:
            # Check volume confirmation
            if volume_data.get('volume_breakout', False):
                entry_signal = True
                signal_type = 'BREAKOUT'
                signal_strength = 0.9
                reasoning = (
                    f"Price broke above resistance ₹{resistance:,.2f} with strong volume. "
                    f"Volume ratio: {volume_data.get('volume_ratio', 1.0):.2f}x"
                )
            elif current_price > resistance * Decimal('1.005'):  # 0.5% above resistance
                entry_signal = True
                signal_type = 'BREAKOUT'
                signal_strength = 0.7
                reasoning = f"Price broke above resistance ₹{resistance:,.2f} by 0.5%"

        # SIGNAL 2: Pullback to Support
        if support and not entry_signal:
            pullback_zone_upper = support * Decimal('1.01')  # 1% above support
            pullback_zone_lower = support * Decimal('0.99')  # 1% below support

            if pullback_zone_lower <= current_price <= pullback_zone_upper:
                # Check if RSI shows oversold
                rsi = indicators.get('rsi', 50)
                if rsi < 40:  # Oversold
                    entry_signal = True
                    signal_type = 'PULLBACK'
                    signal_strength = 0.8
                    reasoning = (
                        f"Price pulled back to support zone ₹{support:,.2f} "
                        f"with RSI {rsi:.1f} (oversold)"
                    )

        # SIGNAL 3: Momentum Surge
        if not entry_signal:
            # Check for strong bullish indicators
            above_dmas = (
                indicators.get('above_20dma', False) and
                indicators.get('above_50dma', False)
            )
            macd_bullish = indicators.get('macd_signal') == 'BULLISH'
            rsi_bullish = 50 < indicators.get('rsi', 50) < 70

            if above_dmas and macd_bullish and rsi_bullish:
                entry_signal = True
                signal_type = 'MOMENTUM_SURGE'
                signal_strength = 0.75
                reasoning = (
                    f"Strong bullish momentum - Price above 20/50 DMAs, "
                    f"MACD bullish, RSI {indicators.get('rsi', 50):.1f}"
                )

        # SIGNAL 4: Golden Cross
        if not entry_signal and indicators.get('golden_cross', False):
            entry_signal = True
            signal_type = 'GOLDEN_CROSS'
            signal_strength = 0.85
            reasoning = "Golden Cross detected - 50 DMA crossed above 200 DMA"

        return {
            'entry_signal': entry_signal,
            'signal_type': signal_type or 'NO_SIGNAL',
            'signal_strength': signal_strength,
            'entry_price': current_price,
            'reasoning': reasoning or "No clear entry signal detected",
            'indicators': indicators,
            'volume_data': volume_data
        }

    def _detect_short_entry(
        self,
        symbol: str,
        current_price: Decimal,
        support: Optional[Decimal],
        resistance: Optional[Decimal],
        indicators: Dict,
        volume_data: Dict
    ) -> Dict:
        """Detect SHORT entry signals"""

        entry_signal = False
        signal_type = None
        signal_strength = 0.0
        reasoning = ""

        # SIGNAL 1: Breakdown Below Support
        if support and current_price < support:
            # Check volume confirmation
            if volume_data.get('volume_breakout', False):
                entry_signal = True
                signal_type = 'BREAKDOWN'
                signal_strength = 0.9
                reasoning = (
                    f"Price broke below support ₹{support:,.2f} with strong volume. "
                    f"Volume ratio: {volume_data.get('volume_ratio', 1.0):.2f}x"
                )
            elif current_price < support * Decimal('0.995'):  # 0.5% below support
                entry_signal = True
                signal_type = 'BREAKDOWN'
                signal_strength = 0.7
                reasoning = f"Price broke below support ₹{support:,.2f} by 0.5%"

        # SIGNAL 2: Rejection at Resistance
        if resistance and not entry_signal:
            rejection_zone_upper = resistance * Decimal('1.01')  # 1% above resistance
            rejection_zone_lower = resistance * Decimal('0.99')  # 1% below resistance

            if rejection_zone_lower <= current_price <= rejection_zone_upper:
                # Check if RSI shows overbought
                rsi = indicators.get('rsi', 50)
                if rsi > 60:  # Overbought
                    entry_signal = True
                    signal_type = 'RESISTANCE_REJECTION'
                    signal_strength = 0.8
                    reasoning = (
                        f"Price rejected at resistance zone ₹{resistance:,.2f} "
                        f"with RSI {rsi:.1f} (overbought)"
                    )

        # SIGNAL 3: Bearish Momentum
        if not entry_signal:
            # Check for strong bearish indicators
            below_dmas = (
                not indicators.get('above_20dma', True) and
                not indicators.get('above_50dma', True)
            )
            macd_bearish = indicators.get('macd_signal') == 'BEARISH'
            rsi_bearish = 30 < indicators.get('rsi', 50) < 50

            if below_dmas and macd_bearish and rsi_bearish:
                entry_signal = True
                signal_type = 'BEARISH_MOMENTUM'
                signal_strength = 0.75
                reasoning = (
                    f"Strong bearish momentum - Price below 20/50 DMAs, "
                    f"MACD bearish, RSI {indicators.get('rsi', 50):.1f}"
                )

        # SIGNAL 4: Death Cross
        if not entry_signal and indicators.get('death_cross', False):
            entry_signal = True
            signal_type = 'DEATH_CROSS'
            signal_strength = 0.85
            reasoning = "Death Cross detected - 50 DMA crossed below 200 DMA"

        return {
            'entry_signal': entry_signal,
            'signal_type': signal_type or 'NO_SIGNAL',
            'signal_strength': signal_strength,
            'entry_price': current_price,
            'reasoning': reasoning or "No clear entry signal detected",
            'indicators': indicators,
            'volume_data': volume_data
        }

    def monitor_for_entry(
        self,
        candidates: List[Dict],
        max_monitoring_hours: int = 4
    ) -> Optional[Dict]:
        """
        Monitor a list of candidates and return the first one with entry signal

        Args:
            candidates: List of candidate dictionaries from screening
            max_monitoring_hours: Maximum hours to monitor before giving up

        Returns:
            dict: Candidate with entry signal, or None if no entry detected
        """

        logger.info(f"Monitoring {len(candidates)} candidates for entry points")
        logger.info(f"Max monitoring time: {max_monitoring_hours} hours")

        start_time = timezone.now()
        cutoff_time = start_time + timedelta(hours=max_monitoring_hours)

        for candidate in candidates:
            symbol = candidate['symbol']
            direction = candidate['direction']

            try:
                # Get current price
                # TODO: Fetch actual live price from broker
                stock = ContractStockData.objects.filter(nse_code=symbol).first()
                if not stock:
                    continue

                current_price = stock.close_price  # Placeholder - use live price

                # Detect entry point
                entry_result = self.detect_entry_point(
                    symbol=symbol,
                    direction=direction,
                    current_price=current_price,
                    support=candidate.get('technical_analysis', {}).get('support'),
                    resistance=candidate.get('technical_analysis', {}).get('resistance')
                )

                if entry_result['entry_signal']:
                    logger.info(f"✅ Entry signal detected for {symbol}")

                    # Add entry result to candidate
                    candidate['entry_point'] = entry_result
                    candidate['current_price'] = current_price

                    return candidate

            except Exception as e:
                logger.error(f"Error monitoring {symbol}: {e}")
                continue

        logger.info("No entry signals detected for any candidate")
        return None
