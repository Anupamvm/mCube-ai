"""
Yahoo Finance Utilities

Provides market data from Yahoo Finance including:
- VIX (Volatility Index)
- Index quotes
- Historical data
- Market summaries

Usage:
    from tools.yahoofin import get_nse_vix
    
    symbol, vix_value = get_nse_vix()
"""

import requests
from typing import Tuple, Optional, Dict
import pandas as pd
from datetime import datetime, timedelta


def get_nse_vix() -> Tuple[str, float]:
    """
    Get current India VIX from NSE
    
    Returns:
        tuple: (symbol, vix_value)
            e.g., ('^INDIAVIX', 15.25)
    """
    try:
        # Try multiple sources for VIX
        
        # Method 1: NSE Website (primary)
        try:
            vix = _get_vix_from_nse()
            if vix > 0:
                return ('^INDIAVIX', vix)
        except:
            pass
        
        # Method 2: Yahoo Finance (fallback)
        try:
            vix = _get_vix_from_yahoo()
            if vix > 0:
                return ('^INDIAVIX', vix)
        except:
            pass
        
        # Default fallback
        print("⚠️  Could not fetch VIX, using default value")
        return ('^INDIAVIX', 15.0)
        
    except Exception as e:
        print(f"Error fetching VIX: {e}")
        return ('^INDIAVIX', 15.0)


def _get_vix_from_nse() -> float:
    """Get VIX from NSE website"""
    try:
        url = "https://www.nseindia.com/api/allIndices"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Find India VIX in the data
            for index in data.get('data', []):
                if index.get('index') == 'INDIA VIX':
                    vix_value = float(index.get('last', 0))
                    return vix_value
        
        return 0.0
        
    except Exception as e:
        print(f"NSE VIX fetch failed: {e}")
        return 0.0


def _get_vix_from_yahoo() -> float:
    """Get VIX from Yahoo Finance (fallback)"""
    try:
        import yfinance as yf
        
        ticker = yf.Ticker("^INDIAVIX")
        data = ticker.history(period="1d")
        
        if not data.empty:
            vix_value = float(data['Close'].iloc[-1])
            return vix_value
        
        return 0.0
        
    except Exception as e:
        print(f"Yahoo VIX fetch failed: {e}")
        return 0.0


def get_nifty_quote() -> Optional[Dict]:
    """
    Get current NIFTY 50 quote
    
    Returns:
        dict: Quote data with price, change, etc.
    """
    try:
        url = "https://www.nseindia.com/api/allIndices"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            for index in data.get('data', []):
                if index.get('index') == 'NIFTY 50':
                    return {
                        'symbol': 'NIFTY',
                        'price': float(index.get('last', 0)),
                        'change': float(index.get('change', 0)),
                        'pct_change': float(index.get('percentChange', 0)),
                        'open': float(index.get('open', 0)),
                        'high': float(index.get('high', 0)),
                        'low': float(index.get('low', 0)),
                        'prev_close': float(index.get('previousClose', 0)),
                    }
        
        return None
        
    except Exception as e:
        print(f"Error fetching NIFTY quote: {e}")
        return None


def fetch_nifty50_data(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch historical NIFTY 50 data
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    
    Returns:
        DataFrame: OHLCV data
    """
    try:
        import yfinance as yf
        
        nifty = yf.Ticker("^NSEI")
        data = nifty.history(start=start_date, end=end_date)
        
        return data
        
    except Exception as e:
        print(f"Error fetching NIFTY data: {e}")
        return pd.DataFrame()


def get_sgx_nifty() -> Tuple[float, float]:
    """
    Get SGX Nifty (Singapore Exchange) for pre-market sentiment
    
    Returns:
        tuple: (price, change_pct)
    """
    try:
        # SGX Nifty futures (CN)
        # Note: This requires a proper data source
        # Placeholder implementation
        
        return (0.0, 0.0)
        
    except Exception as e:
        print(f"Error fetching SGX Nifty: {e}")
        return (0.0, 0.0)


def get_market_summary() -> Dict:
    """
    Get overall market summary
    
    Returns:
        dict: Market summary with major indices
    """
    try:
        url = "https://www.nseindia.com/api/allIndices"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            summary = {}
            
            indices_to_track = [
                'NIFTY 50',
                'NIFTY BANK',
                'NIFTY FIN SERVICE',
                'NIFTY IT',
                'INDIA VIX'
            ]
            
            for index_data in data.get('data', []):
                index_name = index_data.get('index')
                
                if index_name in indices_to_track:
                    summary[index_name] = {
                        'price': float(index_data.get('last', 0)),
                        'change': float(index_data.get('change', 0)),
                        'pct_change': float(index_data.get('percentChange', 0)),
                    }
            
            return summary
        
        return {}
        
    except Exception as e:
        print(f"Error fetching market summary: {e}")
        return {}


def is_market_hours() -> bool:
    """
    Check if it's within market hours (9:15 AM - 3:30 PM IST)
    
    Returns:
        bool: True if within market hours
    """
    import pytz
    
    IST = pytz.timezone('Asia/Kolkata')
    now = datetime.now(IST)
    
    # Check if weekday
    if now.weekday() >= 5:
        return False
    
    # Check market hours
    market_open = now.replace(hour=9, minute=15, second=0)
    market_close = now.replace(hour=15, minute=30, second=0)
    
    return market_open <= now <= market_close


def is_pre_market() -> bool:
    """
    Check if it's pre-market hours (9:00 AM - 9:15 AM IST)
    
    Returns:
        bool: True if in pre-market hours
    """
    import pytz
    
    IST = pytz.timezone('Asia/Kolkata')
    now = datetime.now(IST)
    
    # Check if weekday
    if now.weekday() >= 5:
        return False
    
    # Check pre-market hours
    pre_market_start = now.replace(hour=9, minute=0, second=0)
    pre_market_end = now.replace(hour=9, minute=15, second=0)
    
    return pre_market_start <= now < pre_market_end


def get_market_status() -> str:
    """
    Get current market status
    
    Returns:
        str: 'PRE_MARKET', 'OPEN', 'CLOSED'
    """
    if is_pre_market():
        return 'PRE_MARKET'
    elif is_market_hours():
        return 'OPEN'
    else:
        return 'CLOSED'
