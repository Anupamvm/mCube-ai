"""
Nifty Data Fetcher Service

Fetches comprehensive Nifty market data from multiple sources:
- Breeze API (spot price, option chain, VIX)
- Trendlyne (DMAs, OI analysis, historical data)
- Global markets data
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


class NiftyDataFetcher:
    """
    Comprehensive Nifty data fetcher

    Fetches:
    1. Nifty spot price and OHLC
    2. Option chain (all strikes with Greeks)
    3. India VIX
    4. Global markets (SGX, Dow, Nasdaq, S&P500)
    5. DMAs from Trendlyne
    6. OI analysis
    """

    def __init__(self):
        self.data = {}
        self.errors = []

    def fetch_all_data(self):
        """
        Fetch all required data for strangle strategy

        Returns:
            dict: Comprehensive market data or None if critical data missing
        """
        logger.info("Starting comprehensive Nifty data fetch")

        # Step 1: Fetch Nifty spot data from Breeze
        spot_data = self.fetch_spot_data()
        if not spot_data:
            logger.error("Failed to fetch spot data - cannot proceed")
            return None

        # Step 2: Fetch India VIX
        vix_data = self.fetch_vix()

        # Step 3: Fetch option chain
        option_chain = self.fetch_option_chain(spot_data['spot_price'])
        if not option_chain:
            logger.error("Failed to fetch option chain - cannot proceed")
            return None

        # Step 4: Fetch global markets data
        global_data = self.fetch_global_markets()

        # Step 5: Fetch Trendlyne DMAs and technical data
        technical_data = self.fetch_technical_indicators()

        # Step 6: Fetch OI analysis from Trendlyne
        oi_data = self.fetch_oi_analysis()

        # Combine all data
        self.data = {
            **spot_data,
            **vix_data,
            'option_chain': option_chain,
            **global_data,
            **technical_data,
            **oi_data,
            'data_timestamp': timezone.now(),
            'data_source': 'breeze_trendlyne',
            'is_fresh': True
        }

        logger.info("Successfully fetched all Nifty data")
        return self.data

    def fetch_spot_data(self):
        """
        Fetch Nifty spot price and OHLC from Breeze

        Returns:
            dict: {spot_price, open, high, low, prev_close, change_points, change_percent}
        """
        try:
            from apps.brokers.integrations.breeze import get_nifty_quote

            quote = get_nifty_quote()

            if not quote:
                self.errors.append("Breeze API returned no data for Nifty")
                return None

            spot_price = Decimal(str(quote.get('ltp', 0)))
            open_price = Decimal(str(quote.get('open', 0)))
            high_price = Decimal(str(quote.get('high', 0)))
            low_price = Decimal(str(quote.get('low', 0)))
            prev_close = Decimal(str(quote.get('prev_close', 0)))

            change_points = spot_price - prev_close
            change_percent = (change_points / prev_close * 100) if prev_close > 0 else Decimal('0')

            data = {
                'spot_price': spot_price,
                'open_price': open_price,
                'high_price': high_price,
                'low_price': low_price,
                'prev_close': prev_close,
                'change_points': change_points,
                'change_percent': change_percent,
                'total_volume': quote.get('volume', 0),
                'total_turnover': Decimal(str(quote.get('turnover', 0))) if quote.get('turnover') else None,
            }

            logger.info(f"Fetched Nifty spot: {spot_price} ({change_percent:+.2f}%)")
            return data

        except Exception as e:
            logger.error(f"Error fetching Nifty spot data: {e}", exc_info=True)
            self.errors.append(f"Spot data fetch error: {str(e)}")
            return None

    def fetch_vix(self):
        """
        Fetch India VIX from Breeze

        Returns:
            dict: {india_vix, vix_change_percent}
        """
        try:
            from apps.brokers.integrations.breeze import get_india_vix

            vix_data = get_india_vix()

            if not vix_data:
                logger.warning("Could not fetch VIX data")
                return {'india_vix': Decimal('15.0'), 'vix_change_percent': None}  # Default VIX

            vix = Decimal(str(vix_data.get('ltp', 15.0)))
            prev_vix = Decimal(str(vix_data.get('prev_close', vix)))
            vix_change = ((vix - prev_vix) / prev_vix * 100) if prev_vix > 0 else Decimal('0')

            logger.info(f"Fetched India VIX: {vix} ({vix_change:+.2f}%)")

            return {
                'india_vix': vix,
                'vix_change_percent': vix_change
            }

        except Exception as e:
            logger.error(f"Error fetching VIX: {e}")
            self.errors.append(f"VIX fetch error: {str(e)}")
            return {'india_vix': Decimal('15.0'), 'vix_change_percent': None}

    def fetch_option_chain(self, spot_price):
        """
        Fetch Nifty option chain from Breeze with Greeks

        Fetches strikes from spot ± 1000 points (approx 20 strikes each side)

        Args:
            spot_price: Current Nifty spot price

        Returns:
            list: List of NiftyOptionChain model objects
        """
        try:
            from apps.brokers.integrations.breeze import get_breeze_client, get_next_nifty_expiry
            from apps.brokers.models import NiftyOptionChain
            from datetime import datetime

            # Get current weekly expiry from NSE (handles holidays)
            try:
                expiry_str = get_next_nifty_expiry(next_expiry=False)
            except Exception as e:
                logger.warning(f"Could not fetch expiry from NSE: {e}, using fallback")
                # Fallback: Calculate next Tuesday (NIFTY expiries are on Tuesdays as of 2025)
                from datetime import date, timedelta
                today = date.today()
                days_until_tuesday = (1 - today.weekday()) % 7
                if days_until_tuesday == 0 and datetime.now().hour >= 15:  # After 3 PM on Tuesday
                    days_until_tuesday = 7
                expiry = today + timedelta(days=days_until_tuesday)
                expiry_str = expiry.strftime('%d-%b-%Y').upper()

            logger.info(f"Fetching option chain for expiry: {expiry_str}")

            # Convert expiry to date object
            expiry_date_obj = datetime.strptime(expiry_str, "%d-%b-%Y").date()

            # Get Breeze client
            breeze = get_breeze_client()

            # Round spot to nearest 50 (Nifty strikes are in multiples of 50)
            atm_strike = round(float(spot_price) / 50) * 50

            # Filter strikes within ±1000 points from ATM
            min_strike = atm_strike - 1000
            max_strike = atm_strike + 1000

            logger.info(f"Fetching strikes from {min_strike} to {max_strike} (ATM: {atm_strike})")

            # Fetch CALL options from Breeze
            calls_resp = breeze.get_option_chain_quotes(
                stock_code="NIFTY",
                exchange_code="NFO",
                product_type="options",
                expiry_date=expiry_str,
                right="call",
            )

            # Fetch PUT options from Breeze
            puts_resp = breeze.get_option_chain_quotes(
                stock_code="NIFTY",
                exchange_code="NFO",
                product_type="options",
                expiry_date=expiry_str,
                right="put",
            )

            if not calls_resp or not puts_resp:
                logger.error("Breeze returned empty option chain")
                self.errors.append("Breeze API returned no option chain data")
                return None

            calls_data = calls_resp.get("Success", [])
            puts_data = puts_resp.get("Success", [])

            logger.info(f"Received {len(calls_data)} calls and {len(puts_data)} puts from Breeze")

            # Build strike-wise dictionary
            strike_data = {}

            # Process calls
            for call in calls_data:
                strike = float(call.get('strike_price', 0))
                if min_strike <= strike <= max_strike:
                    if strike not in strike_data:
                        strike_data[strike] = {'expiry': expiry_date_obj}

                    strike_data[strike]['call_ltp'] = Decimal(str(call.get('ltp', 0)))
                    strike_data[strike]['call_oi'] = int(call.get('open_interest', 0))
                    strike_data[strike]['call_volume'] = int(call.get('total_quantity_traded', 0))
                    strike_data[strike]['call_bid'] = Decimal(str(call.get('best_bid_price', 0)))
                    strike_data[strike]['call_ask'] = Decimal(str(call.get('best_offer_price', 0)))

                    # Note: Breeze API doesn't provide Greeks directly
                    # We'll need to calculate them or fetch from another source
                    # For now, set to None and we'll calculate in the algorithm
                    strike_data[strike]['call_delta'] = None
                    strike_data[strike]['call_gamma'] = None
                    strike_data[strike]['call_theta'] = None
                    strike_data[strike]['call_vega'] = None
                    strike_data[strike]['call_iv'] = None

            # Process puts
            for put in puts_data:
                strike = float(put.get('strike_price', 0))
                if min_strike <= strike <= max_strike:
                    if strike not in strike_data:
                        strike_data[strike] = {'expiry': expiry_date_obj}

                    strike_data[strike]['put_ltp'] = Decimal(str(put.get('ltp', 0)))
                    strike_data[strike]['put_oi'] = int(put.get('open_interest', 0))
                    strike_data[strike]['put_volume'] = int(put.get('total_quantity_traded', 0))
                    strike_data[strike]['put_bid'] = Decimal(str(put.get('best_bid_price', 0)))
                    strike_data[strike]['put_ask'] = Decimal(str(put.get('best_offer_price', 0)))

                    strike_data[strike]['put_delta'] = None
                    strike_data[strike]['put_gamma'] = None
                    strike_data[strike]['put_theta'] = None
                    strike_data[strike]['put_vega'] = None
                    strike_data[strike]['put_iv'] = None

            # Import Greeks calculator
            from apps.strategies.services.greeks_calculator import calculate_all_greeks

            # Get India VIX for IV calculation (if available from self.data)
            india_vix = self.data.get('india_vix') if hasattr(self, 'data') else None

            # Create option chain objects (return list, don't save yet)
            option_chain_list = []
            for strike, data in sorted(strike_data.items()):
                # Calculate PCR if we have both call and put OI
                call_oi = data.get('call_oi', 0)
                put_oi = data.get('put_oi', 0)
                pcr_oi = (Decimal(put_oi) / Decimal(call_oi)) if call_oi > 0 else None

                call_vol = data.get('call_volume', 0)
                put_vol = data.get('put_volume', 0)
                pcr_volume = (Decimal(put_vol) / Decimal(call_vol)) if call_vol > 0 else None

                # Calculate Greeks using Black-Scholes model
                call_ltp = data.get('call_ltp', Decimal('0'))
                put_ltp = data.get('put_ltp', Decimal('0'))

                greeks = {}
                if call_ltp > 0 and put_ltp > 0:
                    try:
                        greeks = calculate_all_greeks(
                            spot_price=spot_price,
                            strike_price=Decimal(str(strike)),
                            expiry_date=expiry_date_obj,
                            call_ltp=call_ltp,
                            put_ltp=put_ltp,
                            india_vix=india_vix
                        )
                        logger.debug(f"Calculated Greeks for strike {strike}: "
                                   f"Call Delta={greeks.get('call_delta')}, Put Delta={greeks.get('put_delta')}")
                    except Exception as e:
                        logger.warning(f"Failed to calculate Greeks for strike {strike}: {e}")
                        greeks = {}

                option_data = {
                    'expiry_date': data['expiry'],
                    'strike_price': Decimal(str(strike)),
                    'option_type': 'CE',  # We'll store both CE and PE separately in the model
                    'spot_price': spot_price,

                    # Call data
                    'call_ltp': call_ltp,
                    'call_oi': call_oi,
                    'call_volume': data.get('call_volume', 0),
                    'call_bid': data.get('call_bid', Decimal('0')),
                    'call_ask': data.get('call_ask', Decimal('0')),
                    'call_delta': greeks.get('call_delta'),
                    'call_gamma': greeks.get('call_gamma'),
                    'call_theta': greeks.get('call_theta'),
                    'call_vega': greeks.get('call_vega'),
                    'call_iv': greeks.get('call_iv'),

                    # Put data
                    'put_ltp': put_ltp,
                    'put_oi': put_oi,
                    'put_volume': data.get('put_volume', 0),
                    'put_bid': data.get('put_bid', Decimal('0')),
                    'put_ask': data.get('put_ask', Decimal('0')),
                    'put_delta': greeks.get('put_delta'),
                    'put_gamma': greeks.get('put_gamma'),
                    'put_theta': greeks.get('put_theta'),
                    'put_vega': greeks.get('put_vega'),
                    'put_iv': greeks.get('put_iv'),

                    # PCR and helper fields
                    'pcr_oi': pcr_oi,
                    'pcr_volume': pcr_volume,
                    'is_atm': (strike == atm_strike),
                    'distance_from_spot': Decimal(str(strike - float(spot_price))),
                }

                option_chain_list.append(option_data)

            logger.info(f"Processed {len(option_chain_list)} strikes around ATM {atm_strike}")
            return option_chain_list

        except Exception as e:
            logger.error(f"Error fetching option chain: {e}", exc_info=True)
            self.errors.append(f"Option chain fetch error: {str(e)}")
            return None

    def fetch_global_markets(self):
        """
        Fetch global markets data for sentiment analysis

        Returns:
            dict: {sgx_nifty, dow_jones, nasdaq, sp500, gift_nifty}
        """
        try:
            # TODO: Implement actual global markets API
            # For now, return placeholder values
            # In production, fetch from:
            # - SGX Nifty from investing.com API
            # - US markets from Yahoo Finance or Alpha Vantage
            # - GIFT Nifty from NSE

            global_data = {
                'sgx_nifty': None,
                'dow_jones': None,
                'nasdaq': None,
                'sp500': None,
                'gift_nifty': None,
            }

            logger.info("Global markets data fetch (placeholder)")
            return global_data

        except Exception as e:
            logger.error(f"Error fetching global markets: {e}")
            return {}

    def fetch_technical_indicators(self):
        """
        Fetch technical indicators (DMAs) from Trendlyne

        Returns:
            dict: {dma_5, dma_10, dma_20, dma_50, dma_200}
        """
        try:
            from apps.data.models import StockData

            # Get Nifty 50 data from Trendlyne (stored in StockData)
            nifty_data = StockData.objects.filter(
                symbol='NIFTY',
                is_nifty_50=True
            ).order_by('-updated_at').first()

            if nifty_data:
                technical_data = {
                    'dma_5': nifty_data.dma_5 if hasattr(nifty_data, 'dma_5') else None,
                    'dma_10': nifty_data.dma_10 if hasattr(nifty_data, 'dma_10') else None,
                    'dma_20': nifty_data.dma_20 if hasattr(nifty_data, 'dma_20') else None,
                    'dma_50': nifty_data.dma_50 if hasattr(nifty_data, 'dma_50') else None,
                    'dma_200': nifty_data.dma_200 if hasattr(nifty_data, 'dma_200') else None,
                }
                logger.info("Fetched DMAs from Trendlyne data")
            else:
                technical_data = {
                    'dma_5': None,
                    'dma_10': None,
                    'dma_20': None,
                    'dma_50': None,
                    'dma_200': None,
                }
                logger.warning("No Trendlyne DMA data available")

            return technical_data

        except Exception as e:
            logger.error(f"Error fetching technical indicators: {e}")
            return {}

    def fetch_oi_analysis(self):
        """
        Fetch Open Interest analysis from Trendlyne

        Returns:
            dict: OI analysis data
        """
        try:
            from apps.data.models import ContractData

            # Get Nifty F&O OI data from Trendlyne
            nifty_oi = ContractData.objects.filter(
                symbol='NIFTY',
                segment='FUT'
            ).order_by('-updated_at').first()

            if nifty_oi:
                oi_data = {
                    'futures_oi': nifty_oi.oi if hasattr(nifty_oi, 'oi') else None,
                    'futures_oi_change': nifty_oi.oi_change if hasattr(nifty_oi, 'oi_change') else None,
                    'pcr_oi': nifty_oi.pcr if hasattr(nifty_oi, 'pcr') else None,
                }
                logger.info("Fetched OI data from Trendlyne")
            else:
                oi_data = {}
                logger.warning("No Trendlyne OI data available")

            return oi_data

        except Exception as e:
            logger.error(f"Error fetching OI analysis: {e}")
            return {}

    def get_errors(self):
        """Return list of errors encountered during fetch"""
        return self.errors
