"""
Option Greeks Calculator

Calculates option Greeks (Delta, Gamma, Theta, Vega) using Black-Scholes model
and estimates Implied Volatility using Newton-Raphson method.
"""

import math
import logging
from decimal import Decimal
from datetime import date
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def calculate_days_to_expiry(expiry_date: date) -> float:
    """
    Calculate number of days to expiry from today.

    Args:
        expiry_date: Option expiry date

    Returns:
        float: Days to expiry (minimum 0.001 to avoid division by zero)
    """
    from datetime import date as dt_date
    today = dt_date.today()
    days = (expiry_date - today).days
    return max(days, 0.001)  # Avoid zero days


def normal_cdf(x: float) -> float:
    """
    Cumulative distribution function for standard normal distribution.

    Args:
        x: Input value

    Returns:
        float: CDF value
    """
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def normal_pdf(x: float) -> float:
    """
    Probability density function for standard normal distribution.

    Args:
        x: Input value

    Returns:
        float: PDF value
    """
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def calculate_d1_d2(spot: float, strike: float, time_to_expiry: float,
                   risk_free_rate: float, volatility: float) -> Tuple[float, float]:
    """
    Calculate d1 and d2 for Black-Scholes model.

    Args:
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate (annualized)
        volatility: Implied volatility (annualized, as decimal e.g., 0.15 for 15%)

    Returns:
        tuple: (d1, d2)
    """
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / \
         (volatility * math.sqrt(time_to_expiry))
    d2 = d1 - volatility * math.sqrt(time_to_expiry)
    return d1, d2


def black_scholes_call_price(spot: float, strike: float, time_to_expiry: float,
                             risk_free_rate: float, volatility: float) -> float:
    """
    Calculate call option price using Black-Scholes model.

    Args:
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate (annualized)
        volatility: Implied volatility (annualized)

    Returns:
        float: Call option theoretical price
    """
    d1, d2 = calculate_d1_d2(spot, strike, time_to_expiry, risk_free_rate, volatility)
    call_price = spot * normal_cdf(d1) - strike * math.exp(-risk_free_rate * time_to_expiry) * normal_cdf(d2)
    return call_price


def black_scholes_put_price(spot: float, strike: float, time_to_expiry: float,
                            risk_free_rate: float, volatility: float) -> float:
    """
    Calculate put option price using Black-Scholes model.

    Args:
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate (annualized)
        volatility: Implied volatility (annualized)

    Returns:
        float: Put option theoretical price
    """
    d1, d2 = calculate_d1_d2(spot, strike, time_to_expiry, risk_free_rate, volatility)
    put_price = strike * math.exp(-risk_free_rate * time_to_expiry) * normal_cdf(-d2) - spot * normal_cdf(-d1)
    return put_price


def calculate_call_delta(spot: float, strike: float, time_to_expiry: float,
                         risk_free_rate: float, volatility: float) -> float:
    """
    Calculate delta for call option.

    Delta measures the rate of change of option price with respect to spot price.
    Call delta ranges from 0 to 1.

    Args:
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate
        volatility: Implied volatility

    Returns:
        float: Call delta (0 to 1)
    """
    d1, _ = calculate_d1_d2(spot, strike, time_to_expiry, risk_free_rate, volatility)
    return normal_cdf(d1)


def calculate_put_delta(spot: float, strike: float, time_to_expiry: float,
                        risk_free_rate: float, volatility: float) -> float:
    """
    Calculate delta for put option.

    Put delta ranges from -1 to 0.

    Args:
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate
        volatility: Implied volatility

    Returns:
        float: Put delta (-1 to 0)
    """
    d1, _ = calculate_d1_d2(spot, strike, time_to_expiry, risk_free_rate, volatility)
    return normal_cdf(d1) - 1


def calculate_gamma(spot: float, strike: float, time_to_expiry: float,
                    risk_free_rate: float, volatility: float) -> float:
    """
    Calculate gamma (same for both call and put).

    Gamma measures the rate of change of delta with respect to spot price.

    Args:
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate
        volatility: Implied volatility

    Returns:
        float: Gamma
    """
    d1, _ = calculate_d1_d2(spot, strike, time_to_expiry, risk_free_rate, volatility)
    gamma = normal_pdf(d1) / (spot * volatility * math.sqrt(time_to_expiry))
    return gamma


def calculate_vega(spot: float, strike: float, time_to_expiry: float,
                   risk_free_rate: float, volatility: float) -> float:
    """
    Calculate vega (same for both call and put).

    Vega measures the sensitivity to volatility.

    Args:
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate
        volatility: Implied volatility

    Returns:
        float: Vega (per 1% change in volatility)
    """
    d1, _ = calculate_d1_d2(spot, strike, time_to_expiry, risk_free_rate, volatility)
    vega = spot * normal_pdf(d1) * math.sqrt(time_to_expiry) / 100  # Divide by 100 for 1% change
    return vega


def calculate_call_theta(spot: float, strike: float, time_to_expiry: float,
                         risk_free_rate: float, volatility: float) -> float:
    """
    Calculate theta for call option.

    Theta measures time decay (usually negative).

    Args:
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate
        volatility: Implied volatility

    Returns:
        float: Call theta (per day)
    """
    d1, d2 = calculate_d1_d2(spot, strike, time_to_expiry, risk_free_rate, volatility)

    theta = (-spot * normal_pdf(d1) * volatility / (2 * math.sqrt(time_to_expiry)) -
             risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * normal_cdf(d2))

    return theta / 365  # Convert to per-day theta


def calculate_put_theta(spot: float, strike: float, time_to_expiry: float,
                        risk_free_rate: float, volatility: float) -> float:
    """
    Calculate theta for put option.

    Args:
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate
        volatility: Implied volatility

    Returns:
        float: Put theta (per day)
    """
    d1, d2 = calculate_d1_d2(spot, strike, time_to_expiry, risk_free_rate, volatility)

    theta = (-spot * normal_pdf(d1) * volatility / (2 * math.sqrt(time_to_expiry)) +
             risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * normal_cdf(-d2))

    return theta / 365  # Convert to per-day theta


def estimate_iv_newton_raphson(option_price: float, spot: float, strike: float,
                               time_to_expiry: float, risk_free_rate: float,
                               option_type: str = 'call', max_iterations: int = 100,
                               tolerance: float = 0.0001) -> Optional[float]:
    """
    Estimate implied volatility using Newton-Raphson method.

    Args:
        option_price: Market price of the option
        spot: Current spot price
        strike: Strike price
        time_to_expiry: Time to expiry in years
        risk_free_rate: Risk-free interest rate
        option_type: 'call' or 'put'
        max_iterations: Maximum iterations
        tolerance: Convergence tolerance

    Returns:
        float: Implied volatility (as decimal, e.g., 0.15 for 15%) or None if failed
    """
    # Initial guess: ATM volatility around 15-20%
    iv = 0.2

    for i in range(max_iterations):
        try:
            # Calculate option price with current IV estimate
            if option_type.lower() == 'call':
                calc_price = black_scholes_call_price(spot, strike, time_to_expiry, risk_free_rate, iv)
            else:
                calc_price = black_scholes_put_price(spot, strike, time_to_expiry, risk_free_rate, iv)

            # Calculate vega (derivative of price with respect to volatility)
            vega = calculate_vega(spot, strike, time_to_expiry, risk_free_rate, iv) * 100  # Scale back

            # Newton-Raphson update
            price_diff = calc_price - option_price

            if abs(price_diff) < tolerance:
                return iv

            if vega < 1e-10:  # Avoid division by very small numbers
                logger.warning(f"Vega too small for IV calculation: {vega}")
                return None

            iv = iv - price_diff / vega

            # Keep IV in reasonable bounds
            if iv < 0.01:
                iv = 0.01
            elif iv > 5.0:  # 500% IV is unreasonable
                iv = 5.0

        except (ValueError, ZeroDivisionError) as e:
            logger.warning(f"Error in IV calculation iteration {i}: {e}")
            return None

    logger.warning(f"IV calculation did not converge after {max_iterations} iterations")
    return None


def calculate_all_greeks(spot_price: Decimal, strike_price: Decimal, expiry_date: date,
                        call_ltp: Decimal, put_ltp: Decimal,
                        risk_free_rate: float = 0.065,  # 6.5% as of 2024-25
                        india_vix: Optional[Decimal] = None) -> dict:
    """
    Calculate all Greeks for both call and put options at a given strike.

    Args:
        spot_price: Current Nifty spot price
        strike_price: Strike price
        expiry_date: Option expiry date
        call_ltp: Call option market price
        put_ltp: Put option market price
        risk_free_rate: Risk-free rate (default 6.5%)
        india_vix: India VIX value (if available, used as initial IV guess)

    Returns:
        dict: Dictionary containing all Greeks and IVs
    """
    try:
        # Convert to float
        spot = float(spot_price)
        strike = float(strike_price)
        call_price = float(call_ltp)
        put_price = float(put_ltp)

        # Calculate time to expiry in years
        days = calculate_days_to_expiry(expiry_date)
        time_to_expiry = days / 365.0

        # Use India VIX as initial guess if available, otherwise use 15%
        if india_vix and india_vix > 0:
            initial_iv = float(india_vix) / 100  # Convert from percentage to decimal
        else:
            initial_iv = 0.15  # 15% default

        # Estimate implied volatility for call and put
        call_iv = estimate_iv_newton_raphson(
            call_price, spot, strike, time_to_expiry, risk_free_rate, 'call'
        ) or initial_iv

        put_iv = estimate_iv_newton_raphson(
            put_price, spot, strike, time_to_expiry, risk_free_rate, 'put'
        ) or initial_iv

        # Use average IV for Greeks calculation (better estimate)
        avg_iv = (call_iv + put_iv) / 2

        # Calculate Greeks
        call_delta = calculate_call_delta(spot, strike, time_to_expiry, risk_free_rate, avg_iv)
        put_delta = calculate_put_delta(spot, strike, time_to_expiry, risk_free_rate, avg_iv)
        gamma = calculate_gamma(spot, strike, time_to_expiry, risk_free_rate, avg_iv)
        vega = calculate_vega(spot, strike, time_to_expiry, risk_free_rate, avg_iv)
        call_theta = calculate_call_theta(spot, strike, time_to_expiry, risk_free_rate, avg_iv)
        put_theta = calculate_put_theta(spot, strike, time_to_expiry, risk_free_rate, avg_iv)

        return {
            'call_delta': Decimal(str(round(call_delta, 4))),
            'call_gamma': Decimal(str(round(gamma, 6))),
            'call_theta': Decimal(str(round(call_theta, 4))),
            'call_vega': Decimal(str(round(vega, 4))),
            'call_iv': Decimal(str(round(call_iv * 100, 2))),  # Convert to percentage

            'put_delta': Decimal(str(round(put_delta, 4))),
            'put_gamma': Decimal(str(round(gamma, 6))),
            'put_theta': Decimal(str(round(put_theta, 4))),
            'put_vega': Decimal(str(round(vega, 4))),
            'put_iv': Decimal(str(round(put_iv * 100, 2))),  # Convert to percentage
        }

    except Exception as e:
        logger.error(f"Error calculating Greeks for strike {strike_price}: {e}")
        # Return None values on error
        return {
            'call_delta': None,
            'call_gamma': None,
            'call_theta': None,
            'call_vega': None,
            'call_iv': None,
            'put_delta': None,
            'put_gamma': None,
            'put_theta': None,
            'put_vega': None,
            'put_iv': None,
        }
