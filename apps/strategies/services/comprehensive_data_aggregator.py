"""
Comprehensive Data Aggregator for Trading Algorithms

This service aggregates ALL available data from multiple sources:
1. Trendlyne Scores (Durability, Valuation, Momentum)
2. Technical Indicators (RSI, MACD, MFI, ATR, ADX)
3. Moving Averages (SMA 50/200, EMA 20/50)
4. Option Greeks (Delta, Vega, Gamma, Theta, Rho)
5. Implied Volatility data
6. Historical data and calculations

NO ASSUMPTIONS - If data is missing, it's marked as unavailable.
"""

import logging
from decimal import Decimal
from typing import Dict, Optional, List
from datetime import datetime, date

from apps.data.models import TLStockData, ContractData
from apps.brokers.integrations.breeze import get_india_vix
from apps.strategies.services.historical_analysis import analyze_nifty_historical

logger = logging.getLogger(__name__)


class ComprehensiveDataAggregator:
    """
    Aggregates ALL available data for intelligent trading decisions

    No assumptions, no fallbacks, no guessing.
    Missing data is explicitly marked as unavailable.
    """

    def __init__(self, symbol: str, current_price: float, contract_symbol: str = None):
        """
        Initialize data aggregator

        Args:
            symbol: Stock symbol (e.g., 'NIFTY', 'RELIANCE')
            current_price: Current market price
            contract_symbol: Contract symbol for options Greeks (optional)
        """
        self.symbol = symbol
        self.current_price = current_price
        self.contract_symbol = contract_symbol

        self.data = {
            'symbol': symbol,
            'current_price': current_price,
            'timestamp': datetime.now().isoformat(),
        }

    def aggregate_all_data(self) -> Dict:
        """
        Aggregate ALL available data from all sources

        Returns:
            dict: Complete data package with availability flags
        """
        logger.info(f"Starting comprehensive data aggregation for {self.symbol}")

        # 1. Trendlyne Fundamental Scores
        trendlyne_scores = self._get_trendlyne_scores()

        # 2. Technical Indicators
        technical_indicators = self._get_technical_indicators()

        # 3. Moving Averages (from historical data)
        moving_averages = self._get_moving_averages()

        # 4. Option Greeks (if contract specified)
        option_greeks = self._get_option_greeks() if self.contract_symbol else None

        # 5. Implied Volatility
        implied_volatility = self._get_implied_volatility()

        # 6. India VIX (market-wide volatility)
        india_vix = self._get_india_vix()

        # 7. Historical analysis (extreme movements, 20 DMA, etc.)
        historical_analysis = self._get_historical_analysis()

        # Build comprehensive data package
        self.data.update({
            'trendlyne_scores': trendlyne_scores,
            'technical_indicators': technical_indicators,
            'moving_averages': moving_averages,
            'option_greeks': option_greeks,
            'implied_volatility': implied_volatility,
            'india_vix': india_vix,
            'historical_analysis': historical_analysis,
            'data_availability_summary': self._build_availability_summary(
                trendlyne_scores,
                technical_indicators,
                moving_averages,
                option_greeks,
                implied_volatility,
                india_vix,
                historical_analysis
            )
        })

        logger.info(f"Data aggregation complete. Availability: {self.data['data_availability_summary']['overall_score']}%")
        return self.data

    def _get_trendlyne_scores(self) -> Dict:
        """
        Get Trendlyne fundamental scores

        Returns:
            dict: Durability, Valuation, Momentum scores with availability flags
        """
        try:
            tl_data = TLStockData.objects.filter(nsecode__iexact=self.symbol).first()

            if not tl_data:
                return {
                    'available': False,
                    'reason': f'No Trendlyne data found for {self.symbol}'
                }

            return {
                'available': True,
                'source': 'Trendlyne TLStockData table',
                'scores': {
                    'durability': {
                        'value': float(tl_data.trendlyne_durability_score) if tl_data.trendlyne_durability_score else None,
                        'available': tl_data.trendlyne_durability_score is not None,
                        'interpretation': self._interpret_score(tl_data.trendlyne_durability_score, 'durability')
                    },
                    'valuation': {
                        'value': float(tl_data.trendlyne_valuation_score) if tl_data.trendlyne_valuation_score else None,
                        'available': tl_data.trendlyne_valuation_score is not None,
                        'interpretation': self._interpret_score(tl_data.trendlyne_valuation_score, 'valuation')
                    },
                    'momentum': {
                        'value': float(tl_data.trendlyne_momentum_score) if tl_data.trendlyne_momentum_score else None,
                        'available': tl_data.trendlyne_momentum_score is not None,
                        'interpretation': self._interpret_score(tl_data.trendlyne_momentum_score, 'momentum')
                    },
                    'normalized_momentum': {
                        'value': float(tl_data.normalized_momentum_score) if tl_data.normalized_momentum_score else None,
                        'available': tl_data.normalized_momentum_score is not None
                    }
                },
                'fundamentals': {
                    'pe_ttm': {
                        'value': float(tl_data.pe_ttm_price_to_earnings) if tl_data.pe_ttm_price_to_earnings else None,
                        'available': tl_data.pe_ttm_price_to_earnings is not None
                    },
                    'peg_ttm': {
                        'value': float(tl_data.peg_ttm_pe_to_growth) if tl_data.peg_ttm_pe_to_growth else None,
                        'available': tl_data.peg_ttm_pe_to_growth is not None
                    },
                    'price_to_book': {
                        'value': float(tl_data.price_to_book_value) if tl_data.price_to_book_value else None,
                        'available': tl_data.price_to_book_value is not None
                    },
                    'roe': {
                        'value': float(tl_data.roe_annual_pct) if tl_data.roe_annual_pct else None,
                        'available': tl_data.roe_annual_pct is not None
                    },
                    'roa': {
                        'value': float(tl_data.roa_annual_pct) if tl_data.roa_annual_pct else None,
                        'available': tl_data.roa_annual_pct is not None
                    },
                    'piotroski_score': {
                        'value': int(tl_data.piotroski_score) if tl_data.piotroski_score else None,
                        'available': tl_data.piotroski_score is not None,
                        'interpretation': self._interpret_piotroski(tl_data.piotroski_score)
                    }
                }
            }

        except Exception as e:
            logger.error(f"Error fetching Trendlyne scores: {e}")
            return {
                'available': False,
                'error': str(e)
            }

    def _get_technical_indicators(self) -> Dict:
        """
        Get technical indicators from Trendlyne

        Returns:
            dict: RSI, MACD, MFI, ATR, ADX with interpretations
        """
        try:
            tl_data = TLStockData.objects.filter(nsecode__iexact=self.symbol).first()

            if not tl_data:
                return {
                    'available': False,
                    'reason': f'No technical indicators found for {self.symbol}'
                }

            return {
                'available': True,
                'source': 'Trendlyne TLStockData table',
                'indicators': {
                    'rsi': {
                        'value': float(tl_data.day_rsi) if tl_data.day_rsi else None,
                        'available': tl_data.day_rsi is not None,
                        'interpretation': self._interpret_rsi(tl_data.day_rsi),
                        'signal': self._get_rsi_signal(tl_data.day_rsi)
                    },
                    'macd': {
                        'value': float(tl_data.day_macd) if tl_data.day_macd else None,
                        'available': tl_data.day_macd is not None,
                        'interpretation': self._interpret_macd(tl_data.day_macd)
                    },
                    'mfi': {
                        'value': float(tl_data.day_mfi) if tl_data.day_mfi else None,
                        'available': tl_data.day_mfi is not None,
                        'interpretation': self._interpret_mfi(tl_data.day_mfi),
                        'signal': self._get_mfi_signal(tl_data.day_mfi)
                    },
                    'atr': {
                        'value': float(tl_data.day_atr) if tl_data.day_atr else None,
                        'available': tl_data.day_atr is not None,
                        'interpretation': self._interpret_atr(tl_data.day_atr, self.current_price)
                    },
                    'adx': {
                        'value': float(tl_data.day_adx) if tl_data.day_adx else None,
                        'available': tl_data.day_adx is not None,
                        'interpretation': self._interpret_adx(tl_data.day_adx),
                        'trend_strength': self._get_adx_trend_strength(tl_data.day_adx)
                    }
                }
            }

        except Exception as e:
            logger.error(f"Error fetching technical indicators: {e}")
            return {
                'available': False,
                'error': str(e)
            }

    def _get_moving_averages(self) -> Dict:
        """
        Get moving averages from Trendlyne and historical calculation

        Returns:
            dict: All MAs with source tracking
        """
        try:
            tl_data = TLStockData.objects.filter(nsecode__iexact=self.symbol).first()

            if not tl_data:
                # Fall back to historical calculation
                logger.info(f"No Trendlyne MAs, calculating from historical data")
                from apps.strategies.services.historical_analysis import HistoricalAnalyzer
                analyzer = HistoricalAnalyzer(self.symbol, days_to_fetch=365)
                if analyzer.ensure_historical_data():
                    analyzer.load_historical_data(days=250)
                    return analyzer.calculate_all_moving_averages()
                else:
                    return {
                        'available': False,
                        'reason': 'Could not fetch historical data for MA calculation'
                    }

            return {
                'available': True,
                'source': 'Trendlyne TLStockData table',
                'sma': {
                    'sma_50': {
                        'value': float(tl_data.day50_sma) if tl_data.day50_sma else None,
                        'available': tl_data.day50_sma is not None,
                        'vs_current': self._calculate_ma_distance(self.current_price, tl_data.day50_sma)
                    },
                    'sma_200': {
                        'value': float(tl_data.day200_sma) if tl_data.day200_sma else None,
                        'available': tl_data.day200_sma is not None,
                        'vs_current': self._calculate_ma_distance(self.current_price, tl_data.day200_sma)
                    }
                },
                'ema': {
                    'ema_20': {
                        'value': float(tl_data.day20_ema) if tl_data.day20_ema else None,
                        'available': tl_data.day20_ema is not None,
                        'vs_current': self._calculate_ma_distance(self.current_price, tl_data.day20_ema)
                    },
                    'ema_50': {
                        'value': float(tl_data.day50_ema) if tl_data.day50_ema else None,
                        'available': tl_data.day50_ema is not None,
                        'vs_current': self._calculate_ma_distance(self.current_price, tl_data.day50_ema)
                    }
                },
                'trend_analysis': self._analyze_ma_trend(
                    self.current_price,
                    tl_data.day20_ema,
                    tl_data.day50_ema,
                    tl_data.day50_sma,
                    tl_data.day200_sma
                )
            }

        except Exception as e:
            logger.error(f"Error fetching moving averages: {e}")
            return {
                'available': False,
                'error': str(e)
            }

    def _get_option_greeks(self) -> Dict:
        """
        Get real option Greeks from ContractData

        Returns:
            dict: Delta, Vega, Gamma, Theta, Rho
        """
        if not self.contract_symbol:
            return {
                'available': False,
                'reason': 'No contract symbol provided'
            }

        try:
            contract = ContractData.objects.filter(symbol=self.contract_symbol).first()

            if not contract:
                return {
                    'available': False,
                    'reason': f'Contract {self.contract_symbol} not found in ContractData'
                }

            return {
                'available': True,
                'source': 'ContractData table',
                'contract_symbol': self.contract_symbol,
                'greeks': {
                    'delta': {
                        'value': float(contract.delta) if contract.delta else None,
                        'available': contract.delta is not None,
                        'interpretation': self._interpret_delta(contract.delta, contract.option_type)
                    },
                    'vega': {
                        'value': float(contract.vega) if contract.vega else None,
                        'available': contract.vega is not None,
                        'interpretation': self._interpret_vega(contract.vega)
                    },
                    'gamma': {
                        'value': float(contract.gamma) if contract.gamma else None,
                        'available': contract.gamma is not None,
                        'interpretation': self._interpret_gamma(contract.gamma)
                    },
                    'theta': {
                        'value': float(contract.theta) if contract.theta else None,
                        'available': contract.theta is not None,
                        'interpretation': self._interpret_theta(contract.theta)
                    },
                    'rho': {
                        'value': float(contract.rho) if contract.rho else None,
                        'available': contract.rho is not None
                    }
                },
                'option_type': contract.option_type,
                'strike': float(contract.strike) if contract.strike else None
            }

        except Exception as e:
            logger.error(f"Error fetching option Greeks: {e}")
            return {
                'available': False,
                'error': str(e)
            }

    def _get_implied_volatility(self) -> Dict:
        """
        Get implied volatility data from ContractData

        Returns:
            dict: IV, IV change percentage
        """
        if not self.contract_symbol:
            return {
                'available': False,
                'reason': 'No contract symbol provided'
            }

        try:
            contract = ContractData.objects.filter(symbol=self.contract_symbol).first()

            if not contract:
                return {
                    'available': False,
                    'reason': f'Contract {self.contract_symbol} not found'
                }

            return {
                'available': True,
                'source': 'ContractData table',
                'prev_day_iv': {
                    'value': float(contract.prev_day_iv) if contract.prev_day_iv else None,
                    'available': contract.prev_day_iv is not None
                },
                'pct_iv_change': {
                    'value': float(contract.pct_iv_change) if contract.pct_iv_change else None,
                    'available': contract.pct_iv_change is not None,
                    'interpretation': self._interpret_iv_change(contract.pct_iv_change)
                }
            }

        except Exception as e:
            logger.error(f"Error fetching implied volatility: {e}")
            return {
                'available': False,
                'error': str(e)
            }

    def _get_india_vix(self) -> Dict:
        """
        Get India VIX from Breeze API

        Returns:
            dict: VIX value with interpretation
        """
        try:
            vix = get_india_vix()

            return {
                'available': True,
                'source': 'Breeze API - Live',
                'value': float(vix),
                'interpretation': self._interpret_vix(float(vix)),
                'market_regime': self._get_vix_regime(float(vix))
            }

        except Exception as e:
            logger.error(f"Error fetching India VIX: {e}")
            return {
                'available': False,
                'error': str(e),
                'reason': 'Could not fetch from Breeze API'
            }

    def _get_historical_analysis(self) -> Dict:
        """
        Get historical analysis (extreme movements, 20 DMA, etc.)

        Returns:
            dict: Complete historical analysis
        """
        try:
            analysis = analyze_nifty_historical(
                current_price=self.current_price,
                days_to_fetch=365
            )

            if analysis.get('status') == 'SUCCESS':
                return {
                    'available': True,
                    'source': 'HistoricalPrice table',
                    **analysis
                }
            else:
                return {
                    'available': False,
                    'reason': analysis.get('error', 'Unknown error'),
                    'status': analysis.get('status')
                }

        except Exception as e:
            logger.error(f"Error in historical analysis: {e}")
            return {
                'available': False,
                'error': str(e)
            }

    # Interpretation methods

    def _interpret_score(self, score: Optional[float], score_type: str) -> Optional[str]:
        """Interpret Trendlyne scores (0-100 scale)"""
        if score is None:
            return None

        if score >= 70:
            return f"Excellent {score_type} (Top 30%)"
        elif score >= 50:
            return f"Good {score_type} (Above average)"
        elif score >= 30:
            return f"Average {score_type}"
        else:
            return f"Weak {score_type} (Bottom 30%)"

    def _interpret_piotroski(self, score: Optional[int]) -> Optional[str]:
        """Interpret Piotroski score (0-9)"""
        if score is None:
            return None

        if score >= 7:
            return "Strong financial health"
        elif score >= 5:
            return "Moderate financial health"
        else:
            return "Weak financial health"

    def _interpret_rsi(self, rsi: Optional[float]) -> Optional[str]:
        """Interpret RSI (0-100)"""
        if rsi is None:
            return None

        if rsi >= 70:
            return "Overbought - bearish signal"
        elif rsi >= 60:
            return "Strong uptrend"
        elif rsi >= 40:
            return "Neutral range"
        elif rsi >= 30:
            return "Oversold approaching"
        else:
            return "Oversold - bullish signal"

    def _get_rsi_signal(self, rsi: Optional[float]) -> Optional[str]:
        """Get trading signal from RSI"""
        if rsi is None:
            return None

        if rsi >= 70:
            return "SELL"
        elif rsi <= 30:
            return "BUY"
        else:
            return "HOLD"

    def _interpret_macd(self, macd: Optional[float]) -> Optional[str]:
        """Interpret MACD"""
        if macd is None:
            return None

        if macd > 0:
            return "Bullish momentum"
        elif macd < 0:
            return "Bearish momentum"
        else:
            return "Neutral"

    def _interpret_mfi(self, mfi: Optional[float]) -> Optional[str]:
        """Interpret Money Flow Index (0-100)"""
        if mfi is None:
            return None

        if mfi >= 80:
            return "Overbought - selling pressure likely"
        elif mfi >= 20:
            return "Normal money flow"
        else:
            return "Oversold - buying opportunity"

    def _get_mfi_signal(self, mfi: Optional[float]) -> Optional[str]:
        """Get trading signal from MFI"""
        if mfi is None:
            return None

        if mfi >= 80:
            return "SELL"
        elif mfi <= 20:
            return "BUY"
        else:
            return "HOLD"

    def _interpret_atr(self, atr: Optional[float], price: float) -> Optional[str]:
        """Interpret Average True Range"""
        if atr is None or price == 0:
            return None

        atr_pct = (atr / price) * 100

        if atr_pct > 2.0:
            return f"High volatility ({atr_pct:.2f}% daily range)"
        elif atr_pct > 1.0:
            return f"Normal volatility ({atr_pct:.2f}% daily range)"
        else:
            return f"Low volatility ({atr_pct:.2f}% daily range)"

    def _interpret_adx(self, adx: Optional[float]) -> Optional[str]:
        """Interpret Average Directional Index"""
        if adx is None:
            return None

        if adx >= 50:
            return "Very strong trend"
        elif adx >= 25:
            return "Strong trend"
        elif adx >= 20:
            return "Developing trend"
        else:
            return "Weak/no trend - ranging market"

    def _get_adx_trend_strength(self, adx: Optional[float]) -> Optional[str]:
        """Get trend strength from ADX"""
        if adx is None:
            return None

        if adx >= 25:
            return "TRENDING"
        else:
            return "RANGING"

    def _interpret_delta(self, delta: Optional[float], option_type: str) -> Optional[str]:
        """Interpret option Delta"""
        if delta is None:
            return None

        abs_delta = abs(delta)

        if abs_delta >= 0.7:
            return f"Deep {'ITM' if option_type == 'CE' else 'ITM'} - behaves like stock"
        elif abs_delta >= 0.5:
            return "ATM - balanced risk/reward"
        elif abs_delta >= 0.3:
            return "Moderate OTM - good for selling"
        else:
            return "Deep OTM - low probability"

    def _interpret_vega(self, vega: Optional[float]) -> Optional[str]:
        """Interpret option Vega"""
        if vega is None:
            return None

        if vega > 0.5:
            return "High IV sensitivity - volatile option"
        elif vega > 0.2:
            return "Moderate IV sensitivity"
        else:
            return "Low IV sensitivity"

    def _interpret_gamma(self, gamma: Optional[float]) -> Optional[str]:
        """Interpret option Gamma"""
        if gamma is None:
            return None

        if gamma > 0.01:
            return "High gamma - delta changes rapidly"
        elif gamma > 0.005:
            return "Moderate gamma"
        else:
            return "Low gamma - delta stable"

    def _interpret_theta(self, theta: Optional[float]) -> Optional[str]:
        """Interpret option Theta"""
        if theta is None:
            return None

        if theta < -2:
            return "High time decay - losing ₹{abs(theta):.2f}/day"
        elif theta < -1:
            return "Moderate time decay - losing ₹{abs(theta):.2f}/day"
        else:
            return "Low time decay - losing ₹{abs(theta):.2f}/day"

    def _interpret_iv_change(self, pct_change: Optional[float]) -> Optional[str]:
        """Interpret IV percentage change"""
        if pct_change is None:
            return None

        if pct_change > 10:
            return f"IV spiked {pct_change:.1f}% - market fear increasing"
        elif pct_change > 5:
            return f"IV rising {pct_change:.1f}% - volatility increasing"
        elif pct_change > -5:
            return f"IV stable ({pct_change:+.1f}%)"
        elif pct_change > -10:
            return f"IV falling {abs(pct_change):.1f}% - volatility decreasing"
        else:
            return f"IV crashed {abs(pct_change):.1f}% - market calming"

    def _interpret_vix(self, vix: float) -> str:
        """Interpret India VIX"""
        if vix > 30:
            return "Extreme fear - very high volatility"
        elif vix > 20:
            return "Elevated fear - high volatility"
        elif vix > 15:
            return "Moderate volatility"
        elif vix > 10:
            return "Low volatility - calm market"
        else:
            return "Very low volatility - complacent market"

    def _get_vix_regime(self, vix: float) -> str:
        """Get market regime from VIX"""
        if vix > 25:
            return "PANIC"
        elif vix > 20:
            return "FEAR"
        elif vix > 15:
            return "CAUTION"
        else:
            return "CALM"

    def _calculate_ma_distance(self, price: float, ma: Optional[float]) -> Optional[Dict]:
        """Calculate distance from MA"""
        if ma is None or ma == 0:
            return None

        diff = price - ma
        diff_pct = (diff / ma) * 100

        return {
            'points': round(diff, 2),
            'pct': round(diff_pct, 2),
            'position': 'ABOVE' if diff > 0 else 'BELOW'
        }

    def _analyze_ma_trend(self, price: float, ema20: Optional[float],
                          ema50: Optional[float], sma50: Optional[float],
                          sma200: Optional[float]) -> Dict:
        """Analyze trend from multiple MAs"""
        trend_signals = []

        if ema20:
            if price > ema20:
                trend_signals.append("Above EMA20 (bullish short-term)")
            else:
                trend_signals.append("Below EMA20 (bearish short-term)")

        if ema50:
            if price > ema50:
                trend_signals.append("Above EMA50 (bullish medium-term)")
            else:
                trend_signals.append("Below EMA50 (bearish medium-term)")

        if sma200:
            if price > sma200:
                trend_signals.append("Above SMA200 (bullish long-term)")
            else:
                trend_signals.append("Below SMA200 (bearish long-term)")

        # Determine overall bias
        bullish_signals = sum(1 for s in trend_signals if 'bullish' in s)
        total_signals = len(trend_signals)

        if total_signals == 0:
            return {
                'bias': 'UNKNOWN',
                'strength': 'UNKNOWN',
                'signals': []
            }

        bullish_pct = (bullish_signals / total_signals) * 100

        if bullish_pct >= 75:
            bias = 'STRONG BULLISH'
        elif bullish_pct >= 50:
            bias = 'MODERATELY BULLISH'
        elif bullish_pct >= 25:
            bias = 'MODERATELY BEARISH'
        else:
            bias = 'STRONG BEARISH'

        return {
            'bias': bias,
            'bullish_signals': bullish_signals,
            'total_signals': total_signals,
            'bullish_pct': round(bullish_pct, 1),
            'signals': trend_signals
        }

    def _build_availability_summary(self, *data_sections) -> Dict:
        """Build data availability summary"""
        total_sections = len(data_sections)
        available_sections = sum(1 for section in data_sections if section and section.get('available'))

        availability_pct = (available_sections / total_sections * 100) if total_sections > 0 else 0

        return {
            'total_data_sources': total_sections,
            'available_sources': available_sections,
            'unavailable_sources': total_sections - available_sections,
            'overall_score': round(availability_pct, 1),
            'data_quality': 'EXCELLENT' if availability_pct >= 80 else (
                'GOOD' if availability_pct >= 60 else (
                    'FAIR' if availability_pct >= 40 else 'POOR'
                )
            )
        }


def aggregate_comprehensive_data(symbol: str, current_price: float,
                                 contract_symbol: str = None) -> Dict:
    """
    Convenience function to aggregate all available data

    Args:
        symbol: Stock symbol (e.g., 'NIFTY')
        current_price: Current market price
        contract_symbol: Contract symbol for Greeks (optional)

    Returns:
        dict: Complete data package
    """
    aggregator = ComprehensiveDataAggregator(symbol, current_price, contract_symbol)
    return aggregator.aggregate_all_data()
