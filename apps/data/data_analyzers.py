"""
Trendlyne Data Analyzers

Analyzes Trendlyne data to generate trading signals based on:
- Open Interest (OI) patterns
- Volume analysis
- DMA (Daily Moving Averages)
- Trendlyne scores
- F&O metrics
"""

from django.db.models import Avg, Sum, Q
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from .models import TLStockData, ContractData, ContractStockData


class TrendlyneScoreAnalyzer:
    """Analyze Trendlyne proprietary scores"""

    @staticmethod
    def get_stock_scores(symbol: str) -> Optional[Dict]:
        """
        Get Trendlyne scores for a stock

        Returns:
            dict: {
                'durability': float,
                'valuation': float,
                'momentum': float,
                'overall_rating': str
            }
        """
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock:
            return None

        durability = stock.trendlyne_durability_score or 0
        valuation = stock.trendlyne_valuation_score or 0
        momentum = stock.trendlyne_momentum_score or 0

        # Calculate overall rating
        avg_score = (durability + valuation + momentum) / 3

        if avg_score >= 70:
            rating = "STRONG_BUY"
        elif avg_score >= 60:
            rating = "BUY"
        elif avg_score >= 50:
            rating = "HOLD"
        elif avg_score >= 40:
            rating = "SELL"
        else:
            rating = "STRONG_SELL"

        return {
            'durability': durability,
            'valuation': valuation,
            'momentum': momentum,
            'average': avg_score,
            'overall_rating': rating,
            'normalized_momentum': stock.normalized_momentum_score
        }

    @staticmethod
    def validate_entry(symbol: str, min_durability=50, min_valuation=40, min_momentum=50) -> Tuple[bool, str]:
        """
        Validate if stock meets minimum score criteria

        Args:
            symbol: Stock NSE code
            min_durability: Minimum quality/durability score
            min_valuation: Minimum valuation score
            min_momentum: Minimum momentum score

        Returns:
            (approved, reason)
        """
        scores = TrendlyneScoreAnalyzer.get_stock_scores(symbol)
        if not scores:
            return False, "Stock data not found"

        if scores['durability'] < min_durability:
            return False, f"Low durability: {scores['durability']}"

        if scores['valuation'] < min_valuation:
            return False, f"Poor valuation: {scores['valuation']}"

        if scores['momentum'] < min_momentum:
            return False, f"Weak momentum: {scores['momentum']}"

        return True, "All scores meet criteria"


class OpenInterestAnalyzer:
    """Analyze Open Interest patterns for options and futures"""

    @staticmethod
    def get_pcr_ratio(symbol: str) -> Optional[Dict]:
        """
        Get Put-Call Ratio (PCR) for a stock

        PCR > 1: More puts than calls (bearish sentiment)
        PCR < 1: More calls than puts (bullish sentiment)
        """
        stock_data = ContractStockData.objects.filter(nse_code=symbol).first()
        if not stock_data:
            return None

        return {
            'pcr_oi': stock_data.fno_pcr_oi,
            'pcr_vol': stock_data.fno_pcr_vol,
            'pcr_oi_change': stock_data.fno_pcr_oi_change_pct,
            'interpretation': 'BULLISH' if stock_data.fno_pcr_oi > 1.2 else 'BEARISH' if stock_data.fno_pcr_oi < 0.8 else 'NEUTRAL',
            'total_oi': stock_data.fno_total_oi,
            'call_oi': stock_data.fno_total_call_oi,
            'put_oi': stock_data.fno_total_put_oi
        }

    @staticmethod
    def analyze_oi_buildup(symbol: str, expiry: str) -> Dict:
        """
        Analyze OI buildup patterns

        Returns:
            dict with buildup analysis:
            - Long Build Up: Price ↑, OI ↑
            - Short Build Up: Price ↓, OI ↑
            - Long Unwinding: Price ↓, OI ↓
            - Short Covering: Price ↑, OI ↓
        """
        contracts = ContractData.objects.filter(
            symbol=symbol,
            expiry=expiry
        )

        if not contracts.exists():
            return {"error": "No contracts found"}

        # Analyze futures contract
        futures = contracts.filter(option_type__in=['FUT', 'FUTURES', 'FUTURE']).first()

        if not futures:
            return {"error": "No futures contract found"}

        price_change = futures.pct_day_change
        oi_change = futures.pct_oi_change

        # Determine buildup type
        if price_change > 0 and oi_change > 0:
            buildup = "LONG_BUILDUP"
            sentiment = "BULLISH"
        elif price_change < 0 and oi_change > 0:
            buildup = "SHORT_BUILDUP"
            sentiment = "BEARISH"
        elif price_change < 0 and oi_change < 0:
            buildup = "LONG_UNWINDING"
            sentiment = "BEARISH"
        elif price_change > 0 and oi_change < 0:
            buildup = "SHORT_COVERING"
            sentiment = "BULLISH"
        else:
            buildup = "NEUTRAL"
            sentiment = "NEUTRAL"

        return {
            'buildup_type': buildup,
            'sentiment': sentiment,
            'price_change_pct': price_change,
            'oi_change_pct': oi_change,
            'current_oi': futures.oi,
            'volume': futures.traded_contracts,
            'interpretation': f"{sentiment} - {buildup.replace('_', ' ')}"
        }

    @staticmethod
    def find_max_pain(symbol: str, expiry: str) -> Optional[float]:
        """
        Calculate Max Pain strike price

        Max Pain is where option buyers lose most money (where total loss is maximum)
        """
        contracts = ContractData.objects.filter(
            symbol=symbol,
            expiry=expiry,
            option_type__in=['CE', 'PE', 'CALL', 'PUT']
        )

        if not contracts.exists():
            return None

        strikes = contracts.values_list('strike_price', flat=True).distinct()
        max_pain_strike = None
        min_total_value = float('inf')

        for strike in strikes:
            # Calculate total value of calls + puts at this strike
            call_value = 0
            put_value = 0

            for contract in contracts:
                if contract.strike_price <= strike:
                    # Calls are ITM, calculate intrinsic value * OI
                    if contract.option_type in ['CE', 'CALL']:
                        call_value += max(0, strike - contract.strike_price) * contract.oi
                else:
                    # Puts are ITM
                    if contract.option_type in ['PE', 'PUT']:
                        put_value += max(0, contract.strike_price - strike) * contract.oi

            total_value = call_value + put_value

            if total_value < min_total_value:
                min_total_value = total_value
                max_pain_strike = strike

        return max_pain_strike

    @staticmethod
    def get_strike_distribution(symbol: str, expiry: str) -> Dict:
        """Get OI distribution across strikes"""
        contracts = ContractData.objects.filter(
            symbol=symbol,
            expiry=expiry
        ).order_by('strike_price')

        call_oi_by_strike = {}
        put_oi_by_strike = {}

        for contract in contracts:
            strike = float(contract.strike_price)

            if contract.option_type in ['CE', 'CALL']:
                call_oi_by_strike[strike] = contract.oi
            elif contract.option_type in ['PE', 'PUT']:
                put_oi_by_strike[strike] = contract.oi

        # Find strikes with highest OI
        max_call_strike = max(call_oi_by_strike, key=call_oi_by_strike.get) if call_oi_by_strike else None
        max_put_strike = max(put_oi_by_strike, key=put_oi_by_strike.get) if put_oi_by_strike else None

        return {
            'call_oi_by_strike': call_oi_by_strike,
            'put_oi_by_strike': put_oi_by_strike,
            'max_call_oi_strike': max_call_strike,
            'max_put_oi_strike': max_put_strike,
            'resistance_level': max_call_strike,
            'support_level': max_put_strike
        }


class VolumeAnalyzer:
    """Analyze volume patterns"""

    @staticmethod
    def analyze_volume_surge(symbol: str) -> Dict:
        """
        Detect volume surges

        Volume surge = Current volume significantly above average
        """
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock:
            return {"error": "Stock not found"}

        current_vol = stock.day_volume or 0
        avg_week_vol = stock.week_volume_avg or 1
        avg_month_vol = stock.month_volume_avg or 1

        week_ratio = current_vol / avg_week_vol if avg_week_vol > 0 else 0
        month_ratio = current_vol / avg_month_vol if avg_month_vol > 0 else 0

        # Determine surge level
        if week_ratio > 3:
            surge_level = "VERY_HIGH"
        elif week_ratio > 2:
            surge_level = "HIGH"
        elif week_ratio > 1.5:
            surge_level = "MODERATE"
        else:
            surge_level = "NORMAL"

        return {
            'current_volume': current_vol,
            'week_avg_volume': avg_week_vol,
            'month_avg_volume': avg_month_vol,
            'volume_ratio_week': week_ratio,
            'volume_ratio_month': month_ratio,
            'surge_level': surge_level,
            'is_surge': week_ratio > 1.5,
            'delivery_pct': stock.delivery_volume_pct_eod
        }

    @staticmethod
    def analyze_delivery_percentage(symbol: str) -> Dict:
        """
        Analyze delivery percentage

        High delivery % = Strong hands, genuine buying/selling
        Low delivery % = Speculation/intraday trading
        """
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock:
            return {"error": "Stock not found"}

        delivery_pct = stock.delivery_volume_pct_eod or 0
        avg_delivery = stock.delivery_volume_avg_week or 0

        if delivery_pct > 70:
            strength = "VERY_STRONG"
            interpretation = "Strong institutional buying/selling"
        elif delivery_pct > 50:
            strength = "STRONG"
            interpretation = "Above average delivery"
        elif delivery_pct > 30:
            strength = "MODERATE"
            interpretation = "Mixed delivery and speculation"
        else:
            strength = "WEAK"
            interpretation = "High speculation/intraday trading"

        return {
            'delivery_pct': delivery_pct,
            'avg_delivery_pct': avg_delivery,
            'strength': strength,
            'interpretation': interpretation,
            'is_strong_hands': delivery_pct > 50
        }


class DMAAnalyzer:
    """Analyze Daily Moving Averages"""

    @staticmethod
    def get_dma_position(symbol: str) -> Dict:
        """
        Get current price position relative to DMAs

        Returns DMA crossovers and trends
        """
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock:
            return {"error": "Stock not found"}

        price = stock.current_price or 0

        dmas = {
            'sma_5': stock.day5_sma,
            'sma_30': stock.day30_sma,
            'sma_50': stock.day50_sma,
            'sma_100': stock.day100_sma,
            'sma_200': stock.day200_sma,
            'ema_12': stock.day12_ema,
            'ema_20': stock.day20_ema,
            'ema_50': stock.day50_ema,
            'ema_100': stock.day100_ema
        }

        # Determine trend
        above_count = sum(1 for dma in dmas.values() if dma and price > dma)
        total_dmas = sum(1 for dma in dmas.values() if dma is not None)

        if total_dmas == 0:
            trend = "UNKNOWN"
        elif above_count >= total_dmas * 0.8:
            trend = "STRONG_UPTREND"
        elif above_count >= total_dmas * 0.6:
            trend = "UPTREND"
        elif above_count >= total_dmas * 0.4:
            trend = "SIDEWAYS"
        elif above_count >= total_dmas * 0.2:
            trend = "DOWNTREND"
        else:
            trend = "STRONG_DOWNTREND"

        # Check golden/death cross
        golden_cross = None
        death_cross = None

        if stock.day50_sma and stock.day200_sma:
            if stock.day50_sma > stock.day200_sma:
                golden_cross = True
                death_cross = False
            elif stock.day50_sma < stock.day200_sma:
                golden_cross = False
                death_cross = True

        return {
            'current_price': price,
            'dmas': dmas,
            'trend': trend,
            'above_dma_count': above_count,
            'total_dmas': total_dmas,
            'golden_cross': golden_cross,
            'death_cross': death_cross,
            'above_sma_200': price > stock.day200_sma if stock.day200_sma else None,
            'above_sma_50': price > stock.day50_sma if stock.day50_sma else None
        }

    @staticmethod
    def detect_dma_crossover(symbol: str) -> Dict:
        """
        Detect recent DMA crossovers

        This is a simplified version - in production you'd compare with previous day's data
        """
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock:
            return {"error": "Stock not found"}

        signals = []

        # EMA 12/20 crossover (short-term)
        if stock.day12_ema and stock.day20_ema:
            if stock.day12_ema > stock.day20_ema:
                signals.append({
                    'type': 'BULLISH_CROSSOVER',
                    'dmas': 'EMA12/EMA20',
                    'signal': 'BUY',
                    'timeframe': 'SHORT_TERM'
                })
            elif stock.day12_ema < stock.day20_ema:
                signals.append({
                    'type': 'BEARISH_CROSSOVER',
                    'dmas': 'EMA12/EMA20',
                    'signal': 'SELL',
                    'timeframe': 'SHORT_TERM'
                })

        # SMA 50/200 crossover (long-term)
        if stock.day50_sma and stock.day200_sma:
            if stock.day50_sma > stock.day200_sma:
                signals.append({
                    'type': 'GOLDEN_CROSS',
                    'dmas': 'SMA50/SMA200',
                    'signal': 'STRONG_BUY',
                    'timeframe': 'LONG_TERM'
                })
            elif stock.day50_sma < stock.day200_sma:
                signals.append({
                    'type': 'DEATH_CROSS',
                    'dmas': 'SMA50/SMA200',
                    'signal': 'STRONG_SELL',
                    'timeframe': 'LONG_TERM'
                })

        return {
            'signals': signals,
            'has_signals': len(signals) > 0
        }


class TechnicalIndicatorAnalyzer:
    """Analyze technical indicators from Trendlyne"""

    @staticmethod
    def get_rsi_signal(symbol: str) -> Dict:
        """
        Get RSI-based signals

        RSI < 30: Oversold (potential buy)
        RSI > 70: Overbought (potential sell)
        """
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock or not stock.day_rsi:
            return {"error": "RSI data not available"}

        rsi = stock.day_rsi

        if rsi < 30:
            signal = "BUY"
            condition = "OVERSOLD"
        elif rsi > 70:
            signal = "SELL"
            condition = "OVERBOUGHT"
        elif rsi < 40:
            signal = "WEAK_BUY"
            condition = "APPROACHING_OVERSOLD"
        elif rsi > 60:
            signal = "WEAK_SELL"
            condition = "APPROACHING_OVERBOUGHT"
        else:
            signal = "NEUTRAL"
            condition = "NORMAL"

        return {
            'rsi': rsi,
            'signal': signal,
            'condition': condition,
            'is_oversold': rsi < 30,
            'is_overbought': rsi > 70
        }

    @staticmethod
    def get_macd_signal(symbol: str) -> Dict:
        """
        Get MACD-based signals

        MACD > Signal: Bullish
        MACD < Signal: Bearish
        """
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock or not stock.day_macd or not stock.day_macd_signal_line:
            return {"error": "MACD data not available"}

        macd = stock.day_macd
        signal_line = stock.day_macd_signal_line

        if macd > signal_line:
            signal = "BUY"
            condition = "BULLISH"
        elif macd < signal_line:
            signal = "SELL"
            condition = "BEARISH"
        else:
            signal = "NEUTRAL"
            condition = "NEUTRAL"

        return {
            'macd': macd,
            'signal_line': signal_line,
            'signal': signal,
            'condition': condition,
            'histogram': macd - signal_line
        }

    @staticmethod
    def get_support_resistance(symbol: str) -> Dict:
        """Get support and resistance levels"""
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock:
            return {"error": "Stock not found"}

        return {
            'current_price': stock.current_price,
            'pivot_point': stock.pivot_point,
            'resistance': {
                'r1': stock.first_resistance_r1,
                'r2': stock.second_resistance_r2,
                'r3': stock.third_resistance_r3
            },
            'support': {
                's1': stock.first_support_s1,
                's2': stock.second_support_s2,
                's3': stock.third_support_s3
            },
            'nearest_resistance': stock.first_resistance_r1,
            'nearest_support': stock.first_support_s1,
            'r1_distance_pct': stock.first_resistance_r1_to_price_diff_pct,
            's1_distance_pct': stock.first_support_s1_to_price_diff_pct
        }


class HoldingPatternAnalyzer:
    """Analyze institutional holding patterns"""

    @staticmethod
    def analyze_holdings(symbol: str) -> Dict:
        """
        Analyze holding patterns for institutional confidence

        Returns insights on promoter, FII, MF holdings
        """
        stock = TLStockData.objects.filter(nsecode=symbol).first()
        if not stock:
            return {"error": "Stock not found"}

        # Promoter analysis
        promoter_holding = stock.promoter_holding_latest_pct or 0
        promoter_change_qoq = stock.promoter_holding_change_qoq_pct or 0

        promoter_signal = "POSITIVE" if promoter_change_qoq > 0 else "NEGATIVE" if promoter_change_qoq < 0 else "NEUTRAL"

        # FII analysis
        fii_holding = stock.fii_holding_current_qtr_pct or 0
        fii_change = stock.fii_holding_change_qoq_pct or 0

        fii_signal = "ACCUMULATING" if fii_change > 0.5 else "DISTRIBUTING" if fii_change < -0.5 else "STABLE"

        # MF analysis
        mf_holding = stock.mf_holding_current_qtr_pct or 0
        mf_change = stock.mf_holding_change_qoq_pct or 0

        mf_signal = "ACCUMULATING" if mf_change > 0.5 else "DISTRIBUTING" if mf_change < -0.5 else "STABLE"

        # Overall assessment
        positive_signals = sum([
            promoter_change_qoq > 0,
            fii_change > 0,
            mf_change > 0,
            promoter_holding > 50
        ])

        if positive_signals >= 3:
            overall = "STRONG_CONFIDENCE"
        elif positive_signals >= 2:
            overall = "MODERATE_CONFIDENCE"
        else:
            overall = "WEAK_CONFIDENCE"

        return {
            'promoter': {
                'holding_pct': promoter_holding,
                'change_qoq': promoter_change_qoq,
                'signal': promoter_signal,
                'pledge_pct': stock.promoter_pledge_pct_qtr
            },
            'fii': {
                'holding_pct': fii_holding,
                'change_qoq': fii_change,
                'signal': fii_signal
            },
            'mf': {
                'holding_pct': mf_holding,
                'change_qoq': mf_change,
                'signal': mf_signal
            },
            'institutional_total': stock.institutional_holding_current_qtr_pct,
            'overall_confidence': overall,
            'positive_signals': positive_signals
        }
