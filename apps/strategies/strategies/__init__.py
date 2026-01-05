"""
Strategy implementations for mCube Trading System

Available Strategies:
    - kotak_strangle: Short strangle on Nifty options
    - kotak_broken_iron_condor: Strangle with protective put (insurance)
    - icici_futures: LLM-validated futures trading

Note: Import strategies directly from their modules to avoid circular imports:
    from apps.strategies.strategies.kotak_broken_iron_condor import calculate_strikes
"""

# Lazy imports to avoid circular dependency issues
__all__ = [
    'kotak_strangle',
    'kotak_broken_iron_condor',
]
