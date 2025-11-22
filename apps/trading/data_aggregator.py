"""
Trendlyne Data Aggregator for Deep-Dive Analysis

This module aggregates all available Trendlyne data for comprehensive analysis
"""

import os
import logging
import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime

from django.conf import settings
from apps.data.models import TLStockData, ContractStockData, ContractData

logger = logging.getLogger(__name__)


class TrendlyneDataAggregator:
    """
    Aggregates all Trendlyne data sources for a stock symbol

    Data sources:
    - TLStockData: 80+ fundamental and technical fields
    - ContractStockData: F&O aggregated metrics
    - ContractData: Individual contract data
    - Forecaster CSVs: Analyst consensus and estimates
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.forecaster_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata', 'forecaster')

    def fetch_all_data(self) -> Dict:
        """
        Fetch and aggregate all available data for the symbol

        Returns:
            dict: Comprehensive data package
        """
        logger.info(f"Fetching all Trendlyne data for {self.symbol}")

        data = {
            'symbol': self.symbol,
            'timestamp': datetime.now(),
            'fundamentals': self.get_fundamentals(),
            'contract_stock': self.get_contract_stock_data(),
            'forecaster': self.get_forecaster_data(),
            'contracts': self.get_contracts_data(),
            'data_completeness': {}
        }

        # Track data completeness
        data['data_completeness'] = {
            'fundamentals': data['fundamentals'] is not None,
            'contract_stock': data['contract_stock'] is not None,
            'forecaster': len(data['forecaster']) > 0,
            'contracts': len(data['contracts']) > 0
        }

        return data

    def get_fundamentals(self) -> Optional[TLStockData]:
        """Get fundamental data from TLStockData"""
        try:
            stock_data = TLStockData.objects.filter(nsecode=self.symbol).first()
            if stock_data:
                logger.info(f"✅ Found fundamental data for {self.symbol}")
                return stock_data
            else:
                logger.warning(f"⚠️  No fundamental data found for {self.symbol}")
                return None
        except Exception as e:
            logger.error(f"Error fetching fundamentals: {e}")
            return None

    def get_contract_stock_data(self) -> Optional[ContractStockData]:
        """Get F&O aggregated data from ContractStockData"""
        try:
            contract_stock = ContractStockData.objects.filter(nse_code=self.symbol).first()
            if contract_stock:
                logger.info(f"✅ Found contract stock data for {self.symbol}")
                return contract_stock
            else:
                logger.warning(f"⚠️  No contract stock data found for {self.symbol}")
                return None
        except Exception as e:
            logger.error(f"Error fetching contract stock data: {e}")
            return None

    def get_contracts_data(self) -> List[ContractData]:
        """Get individual contracts data"""
        try:
            contracts = list(ContractData.objects.filter(symbol=self.symbol).order_by('-expiry', '-oi')[:50])
            logger.info(f"✅ Found {len(contracts)} contracts for {self.symbol}")
            return contracts
        except Exception as e:
            logger.error(f"Error fetching contracts: {e}")
            return []

    def get_forecaster_data(self) -> Dict:
        """
        Load all forecaster CSV files and check if symbol appears in them

        Returns:
            dict: Forecaster data organized by category
        """
        forecaster_data = {
            'bullish_sentiment': {},
            'bearish_sentiment': {},
            'earnings_surprises': {},
            'growth_estimates': {},
            'analyst_activity': {}
        }

        # Define forecaster files and their categories
        forecaster_files = {
            'bullish_sentiment': [
                'trendlyne_High_Bullishness.csv',
            ],
            'bearish_sentiment': [
                'trendlyne_High_Bearishness.csv',
            ],
            'earnings_surprises': [
                'trendlyne_Beat_Annual_EPS_Estimates.csv',
                'trendlyne_Missed_Annual_EPS_Estimates.csv',
                'trendlyne_Beat_Quarter_EPS_Estimates.csv',
                'trendlyne_Missed_Quarter_EPS_Estimates.csv',
                'trendlyne_Beat_Annual_Revenue_Estimates.csv',
                'trendlyne_Missed_Annual_Revenue_Estimates.csv',
                'trendlyne_Beat_Quarter_Revenue_Estimates.csv',
                'trendlyne_Missed_Quarter_Revenue_Estimates.csv',
                'trendlyne_Beat_Annual_Net_Income_Estimates.csv',
                'trendlyne_Missed_Annual_Net_Income_Estimates.csv',
                'trendlyne_Beat_Quarter_Net_Income_Estimates.csv',
                'trendlyne_Missed_Quarter_Net_Income_Estimates.csv',
            ],
            'growth_estimates': [
                'trendlyne_Highest_Forward_12Mth_Upside_pct.csv',
                'trendlyne_Highest_Forward_Annual_EPS_Growth.csv',
                'trendlyne_Lowest_Forward_Annual_EPS_Growth.csv',
                'trendlyne_Highest_Forward_Annual_Revenue_Growth.csv',
                'trendlyne_Highest_Forward_Annual_Capex_Growth.csv',
                'trendlyne_Highest_Dividend_Yield.csv',
            ],
            'analyst_activity': [
                'trendlyne_Highest_3Mth_Analyst_Upgrades.csv',
            ]
        }

        for category, files in forecaster_files.items():
            for filename in files:
                filepath = os.path.join(self.forecaster_dir, filename)
                if os.path.exists(filepath):
                    try:
                        df = pd.read_csv(filepath)
                        # Check if symbol appears in this file
                        if 'Stock' in df.columns:
                            stock_row = df[df['Stock'].str.upper().str.contains(self.symbol.upper(), na=False)]
                            if not stock_row.empty:
                                forecaster_data[category][filename] = stock_row.to_dict('records')[0]
                                logger.info(f"✅ Found {self.symbol} in {filename}")
                    except Exception as e:
                        logger.warning(f"Error reading {filename}: {e}")

        return forecaster_data

    def get_stock_from_forecaster_file(self, filename: str) -> Optional[Dict]:
        """Get stock data from a specific forecaster file"""
        filepath = os.path.join(self.forecaster_dir, filename)
        if not os.path.exists(filepath):
            return None

        try:
            df = pd.read_csv(filepath)
            if 'Stock' in df.columns:
                stock_row = df[df['Stock'].str.upper().str.contains(self.symbol.upper(), na=False)]
                if not stock_row.empty:
                    return stock_row.to_dict('records')[0]
        except Exception as e:
            logger.error(f"Error reading {filename}: {e}")

        return None
