"""
Strategy implementations for mCube Trading System

Available Strategies:
    - kotak_strangle: Short strangle on Nifty options (KotakStrangleStrategy)
    - kotak_broken_iron_condor: Strangle with protective put (KotakBrokenIronCondorStrategy)
    - icici_futures: LLM-validated futures trading (ICICIFuturesStrategy)

Usage:
    # Class-based (recommended)
    from apps.strategies.strategies.kotak_strangle import KotakStrangleStrategy
    strategy = KotakStrangleStrategy(account)
    result = strategy.execute_entry()

    # Function-based (backward compatible)
    from apps.strategies.strategies.kotak_strangle import execute_kotak_strangle_entry
    result = execute_kotak_strangle_entry(account)

Note: Import strategies directly from their modules to avoid circular imports.
"""

# Lazy imports to avoid circular dependency issues
__all__ = [
    'kotak_strangle',
    'kotak_broken_iron_condor',
    'icici_futures',
]
