"""
Chart Data Service

Aggregates data from multiple sources for interactive chart rendering.
Used on suggestion detail page and manual triggers (Verify Trade, Strangle, Iron Condor).

Combines historical prices, technical indicators, support/resistance levels,
and OI distribution for comprehensive chart visualization.
"""

import logging
import pytz
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, Optional, List, Any


from apps.brokers.models import HistoricalPrice
from apps.data.models import ContractData
from apps.trading.models import TradeSuggestion
from apps.strategies.services.consolidated_sr_calculator import ConsolidatedSRCalculator
from apps.strategies.services.oi_support_resistance import OISupportResistanceCalculator
from apps.brokers.integrations.breeze import get_india_vix

logger = logging.getLogger(__name__)


# ============================================================================
# BREEZE STOCK CODE RESOLUTION & HISTORICAL DATA FETCHING
# ============================================================================

def resolve_breeze_stock_code(symbol: str) -> str:
    """
    Resolve a stock symbol to its Breeze short code using the Breeze API.

    Args:
        symbol: Stock symbol (e.g., 'BAJFINANCE', 'RELIANCE')

    Returns:
        str: Breeze short code (e.g., 'BAJFI', 'RELIND')
    """
    # Index symbols - hardcoded (these don't change)
    index_map = {
        'NIFTY': 'NIFTY',
        'NIFTY50': 'NIFTY',
        'BANKNIFTY': 'CNXBAN',
        'FINNIFTY': 'NIFFIN',
        'MIDCPNIFTY': 'MIDCAP',
    }

    if symbol in index_map:
        return index_map[symbol]

    # Check if we already have historical data with this exact symbol
    exists = HistoricalPrice.objects.filter(
        stock_code=symbol,
        product_type='cash',
        interval='1day'
    ).exists()

    if exists:
        return symbol

    # Use Breeze API to resolve the stock code
    try:
        from apps.brokers.integrations.breeze import get_breeze_client
        breeze = get_breeze_client()

        result = breeze.get_names(exchange_code='NSE', stock_code=symbol)

        if result and result.get('isec_stock_code'):
            breeze_code = result['isec_stock_code']
            logger.info(f"Resolved {symbol} -> {breeze_code} via Breeze API")
            return breeze_code

    except Exception as e:
        logger.warning(f"Failed to resolve {symbol} via Breeze API: {e}")

    # Fallback to original symbol
    return symbol


def get_historical_data_for_symbol(symbol: str, days: int = 365, interval: str = '1day') -> Dict[str, Any]:
    """
    Get historical OHLCV data for a symbol.

    This is the shared helper function used by both ChartDataService and
    ContractChartDataService. If data doesn't exist in DB or is stale,
    fetches from Breeze API and saves it.

    Args:
        symbol: Stock symbol (e.g., 'RELIANCE', 'NIFTY')
        days: Number of days of historical data
        interval: Data interval ('1day', '5minute', '1minute', '30minute')

    Returns:
        dict: Historical data with 'ohlc' list and metadata
    """
    # For intraday intervals, always fetch fresh data from Breeze
    if interval in ['1minute', '5minute', '30minute']:
        return get_intraday_data_for_symbol(symbol, days, interval)

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        today = date.today()

        # Resolve the Breeze stock code
        stock_code = resolve_breeze_stock_code(symbol)
        logger.info(f"Resolved {symbol} -> {stock_code}")

        # Query existing historical data
        historical_qs = HistoricalPrice.objects.filter(
            stock_code=stock_code,
            product_type='cash',
            interval='1day',
            datetime__gte=start_date,
            datetime__lte=end_date
        ).order_by('datetime')

        record_count = historical_qs.count()

        # Check if we need to fetch fresh data:
        # 1. Insufficient data (< 10 records)
        # 2. Missing today's data (if market is/was open today - weekday)
        needs_fetch = False

        if record_count < 10:
            logger.info(f"Only {record_count} records found for {stock_code}, needs fetch")
            needs_fetch = True
        elif today.weekday() < 5:  # Monday=0 to Friday=4
            # Check if we have today's data
            today_start = datetime.combine(today, datetime.min.time())
            has_today = historical_qs.filter(datetime__gte=today_start).exists()
            if not has_today:
                logger.info(f"Missing today's data for {stock_code}, fetching fresh data...")
                needs_fetch = True

        if needs_fetch:
            fetch_and_save_historical_data(stock_code, days=days)

            # Re-query after fetching
            historical_qs = HistoricalPrice.objects.filter(
                stock_code=stock_code,
                product_type='cash',
                interval='1day',
                datetime__gte=start_date,
                datetime__lte=end_date
            ).order_by('datetime')

        ohlc_data = []
        for record in historical_qs:
            ohlc_data.append({
                'date': record.datetime.strftime('%Y-%m-%d'),
                'time': int(record.datetime.timestamp()),
                'open': float(record.open),
                'high': float(record.high),
                'low': float(record.low),
                'close': float(record.close),
                'volume': record.volume
            })

        logger.info(f"Retrieved {len(ohlc_data)} historical records for {stock_code}")

        return {
            'ohlc': ohlc_data,
            'stock_code': stock_code,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'count': len(ohlc_data),
            'interval': interval
        }

    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {e}")
        return {'ohlc': [], 'error': str(e)}


def get_intraday_data_for_symbol(symbol: str, days: int = 1, interval: str = '5minute') -> Dict[str, Any]:
    """
    Get intraday OHLCV data for a symbol directly from Breeze API.

    Always fetches fresh data for real-time charts. Does not cache to DB.

    Args:
        symbol: Stock symbol (e.g., 'RELIANCE', 'NIFTY')
        days: Number of days of data (1, 5, or 30)
        interval: Data interval ('1minute', '5minute', '30minute')

    Returns:
        dict: Intraday data with 'ohlc' list and metadata
    """
    try:
        from apps.brokers.integrations.breeze import get_breeze_client

        stock_code = resolve_breeze_stock_code(symbol)
        logger.info(f"Fetching intraday data for {stock_code}, days={days}, interval={interval}")

        breeze = get_breeze_client()

        # Calculate date range
        today = date.today()
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)

        # For intraday, use IST times
        # Note: Breeze API expects IST times but uses 'Z' suffix convention
        from_date = (today - timedelta(days=days)).strftime('%Y-%m-%dT09:15:00.000Z')
        to_date = now.strftime('%Y-%m-%dT%H:%M:%S.000Z')

        logger.info(f"Breeze intraday request: from={from_date}, to={to_date}, interval={interval}")

        resp = breeze.get_historical_data_v2(
            interval=interval,
            from_date=from_date,
            to_date=to_date,
            stock_code=stock_code,
            exchange_code='NSE',
            product_type='cash'
        )

        candles = resp.get('Success', [])
        if not candles:
            logger.warning(f"No intraday data returned from Breeze for {stock_code}")
            return {'ohlc': [], 'error': 'No data available', 'interval': interval}

        ohlc_data = []
        for candle in candles:
            try:
                # Parse datetime - Breeze returns IST times with 'Z' suffix
                dt_str = candle.get('datetime', '')
                if not dt_str:
                    continue

                # Remove Z suffix and parse as naive datetime (it's actually IST)
                dt_str_clean = dt_str.replace('Z', '').replace('.000', '')
                dt = datetime.fromisoformat(dt_str_clean)

                # Make aware in IST timezone
                dt = ist.localize(dt)

                ohlc_data.append({
                    'date': dt.strftime('%Y-%m-%d'),
                    'datetime': dt.strftime('%Y-%m-%d %H:%M'),
                    'time': int(dt.timestamp()),
                    'open': float(candle.get('open', 0)),
                    'high': float(candle.get('high', 0)),
                    'low': float(candle.get('low', 0)),
                    'close': float(candle.get('close', 0)),
                    'volume': int(candle.get('volume') or 0)
                })
            except Exception as e:
                logger.debug(f"Error parsing candle: {e}")
                continue

        logger.info(f"Retrieved {len(ohlc_data)} intraday records for {stock_code}")

        return {
            'ohlc': ohlc_data,
            'stock_code': stock_code,
            'start_date': (today - timedelta(days=days)).strftime('%Y-%m-%d'),
            'end_date': today.strftime('%Y-%m-%d'),
            'count': len(ohlc_data),
            'interval': interval,
            'is_intraday': True
        }

    except Exception as e:
        logger.error(f"Error fetching intraday data for {symbol}: {e}")
        return {'ohlc': [], 'error': str(e), 'interval': interval}


def fetch_and_save_historical_data(
    stock_code: str,
    days: int = 365,
    exchange_code: str = 'NSE',
    product_type: str = 'cash',
    interval: str = '1day'
) -> int:
    """
    Fetch historical data from Breeze API and save to database.

    Args:
        stock_code: Breeze stock code (e.g., 'BAJFI', 'RELIND')
        days: Number of days of historical data
        exchange_code: Exchange code (NSE, NFO)
        product_type: Product type (cash, futures, options)
        interval: Data interval (1day, 1hour, etc.)

    Returns:
        int: Number of records saved/updated
    """
    try:
        from apps.brokers.integrations.breeze import get_breeze_client
        breeze = get_breeze_client()

        today = date.today()
        # Note: Breeze API expects IST times but uses 'Z' suffix convention
        from_date = (today - timedelta(days=days)).strftime('%Y-%m-%dT07:00:00.000Z')
        to_date = today.strftime('%Y-%m-%dT16:00:00.000Z')

        logger.info(f"Fetching {days} days of historical data for {stock_code} from Breeze API (from={from_date}, to={to_date})...")

        resp = breeze.get_historical_data_v2(
            interval=interval,
            from_date=from_date,
            to_date=to_date,
            stock_code=stock_code,
            exchange_code=exchange_code,
            product_type=product_type
        )

        candles = resp.get('Success', [])
        if not candles:
            logger.warning(f"No historical data returned from Breeze for {stock_code}")
            return 0

        saved_count = 0
        today_date = date.today()

        for candle in candles:
            try:
                # Parse datetime - Breeze returns IST times with 'Z' suffix
                dt_str = candle.get('datetime', '')
                if not dt_str:
                    continue

                # Remove Z suffix and parse as naive datetime (it's actually IST)
                dt_str_clean = dt_str.replace('Z', '').replace('.000', '')
                dt = datetime.fromisoformat(dt_str_clean)

                # Make aware in IST timezone
                ist = pytz.timezone('Asia/Kolkata')
                dt = ist.localize(dt)

                # Check if record already exists
                existing = HistoricalPrice.objects.filter(
                    datetime=dt,
                    stock_code=stock_code,
                    exchange_code=exchange_code,
                    product_type=product_type,
                    interval=interval
                ).first()

                candle_data = {
                    'open': Decimal(str(candle.get('open', 0))),
                    'high': Decimal(str(candle.get('high', 0))),
                    'low': Decimal(str(candle.get('low', 0))),
                    'close': Decimal(str(candle.get('close', 0))),
                    'volume': int(candle.get('volume') or 0),
                    'open_interest': int(candle.get('open_interest') or 0),
                }

                if existing:
                    # Update today's record with latest data (intraday updates)
                    if dt.date() == today_date:
                        for key, value in candle_data.items():
                            setattr(existing, key, value)
                        existing.save()
                        saved_count += 1
                        logger.debug(f"Updated today's record for {stock_code} at {dt}")
                    # Skip older existing records
                    continue

                # Save new record
                HistoricalPrice.objects.create(
                    datetime=dt,
                    stock_code=stock_code,
                    exchange_code=exchange_code,
                    product_type=product_type,
                    interval=interval,
                    **candle_data
                )
                saved_count += 1

            except Exception as e:
                logger.debug(f"Error saving candle: {e}")
                continue

        logger.info(f"Saved/updated {saved_count} historical records for {stock_code}")
        return saved_count

    except Exception as e:
        logger.error(f"Error fetching historical data for {stock_code}: {e}")
        return 0


class ChartDataService:
    """
    Aggregates data from multiple sources for chart rendering.

    Combines:
    - Historical OHLCV data (1 year or intraday)
    - Moving averages (20/50/100/200 DMA) - only for daily data
    - Support/Resistance levels (Pivot + OI based)
    - OI distribution by strike
    - Trade markers (entry, SL, target, strikes)
    - VIX indicator
    """

    def __init__(self, suggestion: TradeSuggestion, days: int = 90, interval: str = '1day'):
        """
        Initialize chart data service for a suggestion.

        Args:
            suggestion: TradeSuggestion instance to build chart for
            days: Number of days of historical data
            interval: Data interval ('1day', '5minute', etc.)
        """
        self.suggestion = suggestion
        self.symbol = suggestion.instrument
        self.current_price = float(suggestion.spot_price) if suggestion.spot_price else None
        self.days = days
        self.interval = interval
        self.is_intraday = interval in ['1minute', '5minute', '30minute']

    def compile_chart_data(self) -> Dict[str, Any]:
        """
        Compile all chart data into a single response.

        Returns:
            dict: Complete chart data including historical, indicators, S/R, OI, markers
        """
        logger.info(f"Compiling chart data for suggestion {self.suggestion.id}, days={self.days}, interval={self.interval}")

        result = {
            'success': True,
            'data': {
                'symbol': self.symbol,
                'current_price': self.current_price,
                'chart_type': 'strangle' if self.suggestion.suggestion_type == 'OPTIONS' else 'futures',
                'suggestion_id': self.suggestion.id,
                'days': self.days,
                'interval': self.interval,
                'is_intraday': self.is_intraday,
            }
        }

        # Get historical data
        historical = self._get_historical_data()
        result['data']['historical'] = historical

        # Calculate moving averages from historical data (only for daily data)
        if not self.is_intraday and historical.get('ohlc'):
            result['data']['moving_averages'] = self._calculate_moving_averages(historical['ohlc'])
        else:
            result['data']['moving_averages'] = {'dma_20': [], 'dma_50': [], 'dma_100': [], 'dma_200': []}

        # Get support/resistance levels
        result['data']['support_resistance'] = self._get_support_resistance()

        # Get OI distribution
        result['data']['oi_distribution'] = self._get_oi_distribution()

        # Get trade markers based on suggestion type
        result['data']['trade_markers'] = self._get_trade_markers()

        # Get VIX data
        result['data']['vix'] = self._get_vix_data()

        return result

    def _get_historical_data(self) -> Dict[str, Any]:
        """
        Get historical OHLCV data for the symbol.
        Uses shared helper function that auto-fetches from Breeze if needed.
        """
        return get_historical_data_for_symbol(self.symbol, self.days, self.interval)

    def _map_symbol_to_stock_code(self) -> str:
        """Map symbol to Breeze stock_code format using the shared resolver."""
        return resolve_breeze_stock_code(self.symbol)

    def _calculate_moving_averages(self, ohlc_data: List[Dict]) -> Dict[str, List]:
        """
        Calculate moving averages from OHLCV data.

        Args:
            ohlc_data: List of OHLCV records

        Returns:
            dict: Moving average series for 20, 50, 100, 200 periods
        """
        if not ohlc_data:
            return {'dma_20': [], 'dma_50': [], 'dma_100': [], 'dma_200': []}

        closes = [d['close'] for d in ohlc_data]
        [d['date'] for d in ohlc_data]
        times = [d['time'] for d in ohlc_data]

        def calculate_sma(values: List[float], period: int) -> List[Optional[float]]:
            """Calculate Simple Moving Average"""
            result = []
            for i in range(len(values)):
                if i < period - 1:
                    result.append(None)
                else:
                    avg = sum(values[i - period + 1:i + 1]) / period
                    result.append(round(avg, 2))
            return result

        dma_20 = calculate_sma(closes, 20)
        dma_50 = calculate_sma(closes, 50)
        dma_100 = calculate_sma(closes, 100)
        dma_200 = calculate_sma(closes, 200)

        # Format output
        def format_ma_series(ma_values: List, period: int) -> List[Dict]:
            series = []
            for i, val in enumerate(ma_values):
                if val is not None:
                    series.append({
                        'time': times[i],
                        'value': val
                    })
            return series

        return {
            'dma_20': format_ma_series(dma_20, 20),
            'dma_50': format_ma_series(dma_50, 50),
            'dma_100': format_ma_series(dma_100, 100),
            'dma_200': format_ma_series(dma_200, 200)
        }

    def _get_support_resistance(self) -> Dict[str, Any]:
        """
        Get support and resistance levels from consolidated calculator.

        Returns:
            dict: S/R levels with sources
        """
        try:
            if not self.current_price:
                return {'error': 'No current price available'}

            calculator = ConsolidatedSRCalculator(symbol=self.symbol)
            sr_data = calculator.get_conservative_sr(self.current_price)

            # Format for chart display
            support = sr_data.get('conservative_support', {})
            resistance = sr_data.get('conservative_resistance', {})

            return {
                'support': {
                    's1': {
                        'value': support.get('s1'),
                        'source': support.get('s1_source', 'pivot')
                    },
                    's2': {
                        'value': support.get('s2'),
                        'source': support.get('s2_source', 'pivot')
                    },
                    's3': {
                        'value': support.get('s3'),
                        'source': support.get('s3_source', 'pivot')
                    }
                },
                'resistance': {
                    'r1': {
                        'value': resistance.get('r1'),
                        'source': resistance.get('r1_source', 'pivot')
                    },
                    'r2': {
                        'value': resistance.get('r2'),
                        'source': resistance.get('r2_source', 'pivot')
                    },
                    'r3': {
                        'value': resistance.get('r3'),
                        'source': resistance.get('r3_source', 'pivot')
                    }
                },
                'pivot': sr_data.get('all_methods', {}).get('pivot_based', {}).get('pivot'),
                'distance_to_s1_pct': sr_data.get('distance_to_s1_pct'),
                'distance_to_r1_pct': sr_data.get('distance_to_r1_pct'),
                'methods_used': sr_data.get('methods_used', [])
            }

        except Exception as e:
            logger.error(f"Error calculating S/R: {e}")
            return {'error': str(e)}

    def _get_oi_distribution(self) -> Dict[str, Any]:
        """
        Get OI distribution by strike for the symbol.

        Returns:
            dict: OI distribution data for call and put options
        """
        try:
            # Get nearest expiry
            oi_calculator = OISupportResistanceCalculator(symbol=self.symbol)
            expiry = oi_calculator._get_nearest_expiry()

            if not expiry:
                return {'error': 'No expiry data available'}

            # Get all strikes with OI for this expiry
            contracts = ContractData.objects.filter(
                symbol=self.symbol,
                expiry=expiry,
                option_type__in=['CE', 'PE'],
                oi__isnull=False,
                oi__gt=0
            ).order_by('strike_price')

            # Organize by strike
            strike_data = {}
            for contract in contracts:
                strike = contract.strike_price
                if strike not in strike_data:
                    strike_data[strike] = {'call_oi': 0, 'put_oi': 0}

                if contract.option_type == 'CE':
                    strike_data[strike]['call_oi'] = contract.oi or 0
                else:
                    strike_data[strike]['put_oi'] = contract.oi or 0

            # Convert to arrays for charting
            sorted_strikes = sorted(strike_data.keys())

            # Filter to relevant range (around current price)
            if self.current_price:
                price_range = self.current_price * 0.10  # 10% range
                sorted_strikes = [
                    s for s in sorted_strikes
                    if abs(s - self.current_price) <= price_range
                ]

            strikes = []
            call_oi = []
            put_oi = []

            for strike in sorted_strikes:
                strikes.append(strike)
                call_oi.append(strike_data[strike]['call_oi'])
                put_oi.append(strike_data[strike]['put_oi'])

            # Find max OI strikes
            max_call_oi_strike = None
            max_put_oi_strike = None

            if call_oi:
                max_call_idx = call_oi.index(max(call_oi))
                max_call_oi_strike = strikes[max_call_idx]

            if put_oi:
                max_put_idx = put_oi.index(max(put_oi))
                max_put_oi_strike = strikes[max_put_idx]

            return {
                'strikes': strikes,
                'call_oi': call_oi,
                'put_oi': put_oi,
                'expiry': expiry,
                'max_call_oi_strike': max_call_oi_strike,
                'max_put_oi_strike': max_put_oi_strike,
                'total_call_oi': sum(call_oi),
                'total_put_oi': sum(put_oi)
            }

        except Exception as e:
            logger.error(f"Error fetching OI distribution: {e}")
            return {'error': str(e)}

    def _get_trade_markers(self) -> Dict[str, Any]:
        """
        Get trade markers based on suggestion type.

        Returns:
            dict: Trade markers (entry, SL, target for futures; strikes for options)
        """
        position_details = self.suggestion.position_details or {}

        markers = {
            'entry_price': self.current_price,
        }

        if self.suggestion.suggestion_type == 'OPTIONS':
            # Strangle/Iron Condor markers
            markers.update({
                'call_strike': float(self.suggestion.call_strike) if self.suggestion.call_strike else None,
                'put_strike': float(self.suggestion.put_strike) if self.suggestion.put_strike else None,
                'breakeven_upper': float(self.suggestion.breakeven_upper) if self.suggestion.breakeven_upper else None,
                'breakeven_lower': float(self.suggestion.breakeven_lower) if self.suggestion.breakeven_lower else None,
                'call_premium': float(self.suggestion.call_premium) if self.suggestion.call_premium else None,
                'put_premium': float(self.suggestion.put_premium) if self.suggestion.put_premium else None,
            })
        else:
            # Futures markers
            markers.update({
                'stop_loss': position_details.get('stop_loss'),
                'target': position_details.get('target'),
                'direction': self.suggestion.direction,
            })

        return markers

    def _get_vix_data(self) -> Dict[str, Any]:
        """
        Get current India VIX with status classification.

        Returns:
            dict: VIX value and status
        """
        try:
            vix_value = get_india_vix()
            vix_float = float(vix_value)

            # Classify VIX status
            if vix_float <= 13:
                status = 'LOW'
                color = '#4CAF50'  # Green
            elif vix_float <= 18:
                status = 'NORMAL'
                color = '#2196F3'  # Blue
            elif vix_float <= 25:
                status = 'ELEVATED'
                color = '#FF9800'  # Orange
            else:
                status = 'HIGH'
                color = '#F44336'  # Red

            return {
                'current': vix_float,
                'status': status,
                'color': color,
                'suggestion_vix': float(self.suggestion.vix) if self.suggestion.vix else None
            }

        except Exception as e:
            logger.error(f"Error fetching VIX: {e}")
            # Use suggestion's stored VIX as fallback
            if self.suggestion.vix:
                return {
                    'current': float(self.suggestion.vix),
                    'status': 'CACHED',
                    'color': '#9E9E9E',
                    'error': str(e)
                }
            return {'error': str(e), 'current': None, 'status': 'UNAVAILABLE'}


class ContractChartDataService:
    """
    Chart data service for direct contract/symbol data.

    Used by manual triggers (Verify Trade, Strangle, Iron Condor) where
    we don't have a TradeSuggestion but have direct contract parameters.
    """

    def __init__(
        self,
        symbol: str,
        current_price: float,
        chart_type: str = 'futures',
        trade_markers: Optional[Dict] = None,
        days: int = 90,
        interval: str = '1day'
    ):
        """
        Initialize chart data service for a contract.

        Args:
            symbol: Symbol (NIFTY, RELIANCE, etc.)
            current_price: Current spot/entry price
            chart_type: 'futures', 'strangle', or 'iron_condor'
            trade_markers: Dict with entry, sl, target, strikes, breakevens
            days: Number of days of historical data (default: 90 for 3 months)
            interval: Data interval ('1day', '5minute', etc.)
        """
        self.symbol = symbol
        self.current_price = float(current_price) if current_price else None
        self.chart_type = chart_type
        self.trade_markers = trade_markers or {}
        self.days = days
        self.interval = interval

    def compile_chart_data(self) -> Dict[str, Any]:
        """Compile all chart data into a single response."""
        logger.info(f"Compiling chart data for {self.symbol} ({self.chart_type}), days={self.days}, interval={self.interval}")

        result = {
            'success': True,
            'data': {
                'symbol': self.symbol,
                'current_price': self.current_price,
                'chart_type': self.chart_type,
                'days': self.days,
                'interval': self.interval,
                'is_intraday': self.interval in ['1minute', '5minute', '30minute'],
            }
        }

        # Get historical data
        historical = self._get_historical_data(days=self.days, interval=self.interval)
        result['data']['historical'] = historical

        # Calculate moving averages
        if historical.get('ohlc'):
            result['data']['moving_averages'] = self._calculate_moving_averages(historical['ohlc'])
        else:
            result['data']['moving_averages'] = {'dma_20': [], 'dma_50': [], 'dma_100': [], 'dma_200': []}

        # Get support/resistance levels
        result['data']['support_resistance'] = self._get_support_resistance()

        # Get OI distribution
        result['data']['oi_distribution'] = self._get_oi_distribution()

        # Trade markers passed directly
        result['data']['trade_markers'] = self.trade_markers

        # Get VIX data
        result['data']['vix'] = self._get_vix_data()

        return result

    def _get_historical_data(self, days: int = 365, interval: str = '1day') -> Dict[str, Any]:
        """
        Get historical OHLCV data for the symbol.
        Uses shared helper function that auto-fetches from Breeze if needed.
        """
        return get_historical_data_for_symbol(self.symbol, days, interval)

    def _map_symbol_to_stock_code(self) -> str:
        """Map symbol to Breeze stock_code format using the shared resolver."""
        return resolve_breeze_stock_code(self.symbol)

    def _calculate_moving_averages(self, ohlc_data: List[Dict]) -> Dict[str, List]:
        """Calculate moving averages from OHLCV data."""
        if not ohlc_data:
            return {'dma_20': [], 'dma_50': [], 'dma_100': [], 'dma_200': []}

        closes = [d['close'] for d in ohlc_data]
        times = [d['time'] for d in ohlc_data]

        def calculate_sma(values: List[float], period: int) -> List[Optional[float]]:
            result = []
            for i in range(len(values)):
                if i < period - 1:
                    result.append(None)
                else:
                    avg = sum(values[i - period + 1:i + 1]) / period
                    result.append(round(avg, 2))
            return result

        dma_20 = calculate_sma(closes, 20)
        dma_50 = calculate_sma(closes, 50)
        dma_100 = calculate_sma(closes, 100)
        dma_200 = calculate_sma(closes, 200)

        def format_ma_series(ma_values: List) -> List[Dict]:
            series = []
            for i, val in enumerate(ma_values):
                if val is not None:
                    series.append({'time': times[i], 'value': val})
            return series

        return {
            'dma_20': format_ma_series(dma_20),
            'dma_50': format_ma_series(dma_50),
            'dma_100': format_ma_series(dma_100),
            'dma_200': format_ma_series(dma_200)
        }

    def _get_support_resistance(self) -> Dict[str, Any]:
        """Get support and resistance levels."""
        try:
            if not self.current_price:
                return {'error': 'No current price available'}

            calculator = ConsolidatedSRCalculator(symbol=self.symbol)
            sr_data = calculator.get_conservative_sr(self.current_price)

            support = sr_data.get('conservative_support', {})
            resistance = sr_data.get('conservative_resistance', {})

            return {
                'support': {
                    's1': {'value': support.get('s1'), 'source': support.get('s1_source', 'pivot')},
                    's2': {'value': support.get('s2'), 'source': support.get('s2_source', 'pivot')},
                    's3': {'value': support.get('s3'), 'source': support.get('s3_source', 'pivot')}
                },
                'resistance': {
                    'r1': {'value': resistance.get('r1'), 'source': resistance.get('r1_source', 'pivot')},
                    'r2': {'value': resistance.get('r2'), 'source': resistance.get('r2_source', 'pivot')},
                    'r3': {'value': resistance.get('r3'), 'source': resistance.get('r3_source', 'pivot')}
                },
                'pivot': sr_data.get('all_methods', {}).get('pivot_based', {}).get('pivot'),
                'distance_to_s1_pct': sr_data.get('distance_to_s1_pct'),
                'distance_to_r1_pct': sr_data.get('distance_to_r1_pct'),
                'methods_used': sr_data.get('methods_used', [])
            }

        except Exception as e:
            logger.error(f"Error calculating S/R: {e}")
            return {'error': str(e)}

    def _get_oi_distribution(self) -> Dict[str, Any]:
        """Get OI distribution by strike."""
        try:
            oi_calculator = OISupportResistanceCalculator(symbol=self.symbol)
            expiry = oi_calculator._get_nearest_expiry()

            if not expiry:
                return {'error': 'No expiry data available'}

            contracts = ContractData.objects.filter(
                symbol=self.symbol,
                expiry=expiry,
                option_type__in=['CE', 'PE'],
                oi__isnull=False,
                oi__gt=0
            ).order_by('strike_price')

            strike_data = {}
            for contract in contracts:
                strike = contract.strike_price
                if strike not in strike_data:
                    strike_data[strike] = {'call_oi': 0, 'put_oi': 0}
                if contract.option_type == 'CE':
                    strike_data[strike]['call_oi'] = contract.oi or 0
                else:
                    strike_data[strike]['put_oi'] = contract.oi or 0

            sorted_strikes = sorted(strike_data.keys())

            if self.current_price:
                price_range = self.current_price * 0.10
                sorted_strikes = [
                    s for s in sorted_strikes
                    if abs(s - self.current_price) <= price_range
                ]

            strikes = []
            call_oi = []
            put_oi = []

            for strike in sorted_strikes:
                strikes.append(strike)
                call_oi.append(strike_data[strike]['call_oi'])
                put_oi.append(strike_data[strike]['put_oi'])

            max_call_oi_strike = None
            max_put_oi_strike = None

            if call_oi:
                max_call_idx = call_oi.index(max(call_oi))
                max_call_oi_strike = strikes[max_call_idx]
            if put_oi:
                max_put_idx = put_oi.index(max(put_oi))
                max_put_oi_strike = strikes[max_put_idx]

            return {
                'strikes': strikes,
                'call_oi': call_oi,
                'put_oi': put_oi,
                'expiry': expiry,
                'max_call_oi_strike': max_call_oi_strike,
                'max_put_oi_strike': max_put_oi_strike,
                'total_call_oi': sum(call_oi),
                'total_put_oi': sum(put_oi)
            }

        except Exception as e:
            logger.error(f"Error fetching OI distribution: {e}")
            return {'error': str(e)}

    def _get_vix_data(self) -> Dict[str, Any]:
        """Get current India VIX with status classification."""
        try:
            vix_value = get_india_vix()
            vix_float = float(vix_value)

            if vix_float <= 13:
                status, color = 'LOW', '#4CAF50'
            elif vix_float <= 18:
                status, color = 'NORMAL', '#2196F3'
            elif vix_float <= 25:
                status, color = 'ELEVATED', '#FF9800'
            else:
                status, color = 'HIGH', '#F44336'

            return {'current': vix_float, 'status': status, 'color': color}

        except Exception as e:
            logger.error(f"Error fetching VIX: {e}")
            return {'error': str(e), 'current': None, 'status': 'UNAVAILABLE'}


def get_chart_data_for_suggestion(suggestion_id: int, days: int = 90, interval: str = '1day') -> Dict[str, Any]:
    """
    Convenience function to get chart data for a suggestion ID.

    Args:
        suggestion_id: ID of the TradeSuggestion
        days: Number of days of historical data
        interval: Data interval ('1day', '5minute', etc.)

    Returns:
        dict: Chart data or error
    """
    try:
        suggestion = TradeSuggestion.objects.get(id=suggestion_id)
        service = ChartDataService(suggestion, days=days, interval=interval)
        return service.compile_chart_data()
    except TradeSuggestion.DoesNotExist:
        return {
            'success': False,
            'error': f'Suggestion {suggestion_id} not found'
        }
    except Exception as e:
        logger.error(f"Error getting chart data for suggestion {suggestion_id}: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def get_chart_data_for_contract(
    symbol: str,
    current_price: float,
    chart_type: str = 'futures',
    trade_markers: Optional[Dict] = None,
    days: int = 90,
    interval: str = '1day'
) -> Dict[str, Any]:
    """
    Get chart data for a contract without a suggestion.

    Used by manual triggers (Verify Trade, Strangle, Iron Condor).

    Args:
        symbol: Symbol (NIFTY, RELIANCE, etc.)
        current_price: Current spot/entry price
        chart_type: 'futures', 'strangle', or 'iron_condor'
        trade_markers: Dict with entry, sl, target, strikes, breakevens
        days: Number of days of historical data (default: 90 for 3 months)
        interval: Data interval ('1day', '5minute', etc.)

    Returns:
        dict: Chart data or error
    """
    try:
        service = ContractChartDataService(
            symbol=symbol,
            current_price=current_price,
            chart_type=chart_type,
            trade_markers=trade_markers,
            days=days,
            interval=interval
        )
        return service.compile_chart_data()
    except Exception as e:
        logger.error(f"Error getting chart data for {symbol}: {e}")
        return {
            'success': False,
            'error': str(e)
        }
