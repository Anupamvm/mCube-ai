"""
Lightweight pre-filter for futures contracts before the full analysis pipeline.

Uses existing TLStockData model data (no API calls) to remove obvious
non-setups and reduce analysis load.
"""

import logging

from apps.data.models import TLStockData

logger = logging.getLogger(__name__)


def prefilter_contracts(contracts_qs, max_count=50) -> list:
    """
    Lightweight pre-filter for futures contracts using TLStockData.

    Removes obvious non-setups to reduce analysis load.
    No API calls — purely database-based.

    Filters applied:
    1. ADX > 15 (some directional movement)
    2. Volume > 30-day average (active trading)
    3. RSI not in dead zone (45-55) — no clear momentum
    4. Not at BOTH 52-week extremes simultaneously (data error)

    Args:
        contracts_qs: QuerySet of ContractData objects
        max_count: Maximum contracts to return (default 50)

    Returns:
        list: Filtered list of ContractData IDs
    """
    symbols = list(contracts_qs.values_list("symbol", flat=True).distinct())

    if not symbols:
        logger.info("contract_prefilter: no symbols in queryset, returning empty list")
        return []

    stock_data = {
        sd.nsecode: sd
        for sd in TLStockData.objects.filter(nsecode__in=symbols)
    }

    passed_symbols = set()
    reject_reasons = {
        "low_adx": 0,
        "low_volume": 0,
        "rsi_dead_zone": 0,
        "extreme_data_error": 0,
    }

    for symbol in symbols:
        sd = stock_data.get(symbol)

        if sd is None:
            # No TLStockData available — don't reject, let it through
            passed_symbols.add(symbol)
            continue

        rejected = False

        # 1. ADX filter — reject if directional movement is too weak
        if sd.day_adx is not None and sd.day_adx < 15:
            reject_reasons["low_adx"] += 1
            rejected = True

        # 2. Volume filter — reject if below 30-day average
        if (
            not rejected
            and sd.day_volume is not None
            and sd.consolidated_30day_avg_eod_volume is not None
            and sd.day_volume < sd.consolidated_30day_avg_eod_volume
        ):
            reject_reasons["low_volume"] += 1
            rejected = True

        # 3. RSI dead zone — no clear momentum
        if not rejected and sd.day_rsi is not None and 45 <= sd.day_rsi <= 55:
            reject_reasons["rsi_dead_zone"] += 1
            rejected = True

        # 4. 52-week extreme data error check
        if (
            not rejected
            and sd.one_year_high is not None
            and sd.one_year_low is not None
            and sd.current_price is not None
            and sd.one_year_high > 0
            and sd.one_year_low > 0
        ):
            near_high = abs(sd.current_price - sd.one_year_high) / sd.one_year_high <= 0.01
            near_low = abs(sd.current_price - sd.one_year_low) / sd.one_year_low <= 0.01
            if near_high and near_low:
                reject_reasons["extreme_data_error"] += 1
                rejected = True

        if not rejected:
            passed_symbols.add(symbol)

    filtered_ids = list(
        contracts_qs.filter(symbol__in=passed_symbols).values_list("id", flat=True)[:max_count]
    )

    total = len(symbols)
    passed = len(passed_symbols)
    filtered_out = total - passed

    logger.info(
        "contract_prefilter: %d/%d symbols passed (filtered %d) — "
        "low_adx=%d, low_volume=%d, rsi_dead_zone=%d, data_error=%d | "
        "returning %d contract IDs (max %d)",
        passed,
        total,
        filtered_out,
        reject_reasons["low_adx"],
        reject_reasons["low_volume"],
        reject_reasons["rsi_dead_zone"],
        reject_reasons["extreme_data_error"],
        len(filtered_ids),
        max_count,
    )

    return filtered_ids
