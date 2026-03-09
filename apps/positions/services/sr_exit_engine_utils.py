"""
S/R Exit Engine — Pure Math Utilities

No Django imports — trivially unit-testable.

Functions:
    calculate_atr(ohlcv_list, period=14) -> float
    calculate_vwap(candles) -> tuple[vwap, ub1, lb1, ub2, lb2]
    calculate_swing_hl(candles, window=20) -> tuple[high, low]
    detect_hvn_levels(candles, n_levels=3, bucket_pct=0.001) -> list
    cluster_levels(levels, cluster_pct=0.003) -> list
    interpolate_target_offset(atr_pct, min_pct=0.003, max_pct=0.005) -> float
"""


def calculate_atr(ohlcv_list: list, period: int = 14) -> float:
    """
    Calculate Average True Range (ATR) over `period` bars.

    Args:
        ohlcv_list: list of dicts with keys 'high', 'low', 'close'
                    ordered oldest → newest
        period: ATR smoothing period (default 14)

    Returns:
        ATR as float, or 0.0 if insufficient data
    """
    if len(ohlcv_list) < 2:
        return 0.0

    true_ranges = []
    for i in range(1, len(ohlcv_list)):
        h = float(ohlcv_list[i]['high'])
        l = float(ohlcv_list[i]['low'])
        prev_c = float(ohlcv_list[i - 1]['close'])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        true_ranges.append(tr)

    if not true_ranges:
        return 0.0

    # Use the last `period` true ranges
    recent = true_ranges[-period:]
    return sum(recent) / len(recent)


def calculate_vwap(candles: list) -> tuple:
    """
    Calculate VWAP and ±1σ / ±2σ bands from intraday candles.

    Args:
        candles: list of dicts with keys 'high', 'low', 'close', 'volume'
                 ordered oldest → newest (today's session candles)

    Returns:
        tuple: (vwap, upper_band_1, lower_band_1, upper_band_2, lower_band_2)
               All floats.  Returns (0.0, 0.0, 0.0, 0.0, 0.0) on empty input.
    """
    if not candles:
        return (0.0, 0.0, 0.0, 0.0, 0.0)

    cum_tp_vol = 0.0
    cum_vol = 0.0
    cum_tp2_vol = 0.0  # for variance

    for c in candles:
        tp = (float(c['high']) + float(c['low']) + float(c['close'])) / 3.0
        v = float(c['volume']) or 1.0
        cum_tp_vol += tp * v
        cum_vol += v
        cum_tp2_vol += tp * tp * v

    if cum_vol == 0:
        return (0.0, 0.0, 0.0, 0.0, 0.0)

    vwap = cum_tp_vol / cum_vol
    variance = (cum_tp2_vol / cum_vol) - (vwap ** 2)
    std_dev = variance ** 0.5 if variance > 0 else 0.0

    return (
        vwap,
        vwap + std_dev,       # upper band 1σ
        vwap - std_dev,       # lower band 1σ
        vwap + 2 * std_dev,   # upper band 2σ
        vwap - 2 * std_dev,   # lower band 2σ
    )


def calculate_swing_hl(candles: list, window: int = 20) -> tuple:
    """
    Calculate swing high and swing low over the last `window` candles.

    Args:
        candles: list of dicts with keys 'high', 'low', ordered oldest → newest
        window: number of recent bars to scan (default 20)

    Returns:
        tuple: (swing_high, swing_low) as floats.
               Returns (0.0, 0.0) on insufficient data.
    """
    recent = candles[-window:] if len(candles) >= window else candles
    if not recent:
        return (0.0, 0.0)

    highs = [float(c['high']) for c in recent]
    lows = [float(c['low']) for c in recent]
    return (max(highs), min(lows))


def detect_hvn_levels(candles: list, n_levels: int = 3, bucket_pct: float = 0.001) -> list:
    """
    Detect High Volume Nodes (HVN) — price buckets with above-average traded volume.

    Volume is distributed proportionally across the H-L range of each candle.

    Args:
        candles: list of dicts with keys 'high', 'low', 'close', 'volume'
        n_levels: number of top HVN levels to return (default 3)
        bucket_pct: bucket width as fraction of price (default 0.1%)

    Returns:
        list of dicts: [{'price': float, 'volume': float, 'score': float}, ...]
                       sorted by volume descending, up to n_levels items.
                       Returns [] if no candles.
    """
    if not candles:
        return []

    # Build price buckets
    all_prices = [float(c['close']) for c in candles]
    if not all_prices:
        return []

    avg_price = sum(all_prices) / len(all_prices)
    bucket_width = avg_price * bucket_pct

    volume_map: dict = {}

    for c in candles:
        h = float(c['high'])
        l = float(c['low'])
        v = float(c['volume']) or 0.0
        price_range = h - l
        if price_range <= 0:
            # Single tick — attribute all volume to close bucket
            bucket_key = round(float(c['close']) / bucket_width) * bucket_width
            volume_map[bucket_key] = volume_map.get(bucket_key, 0.0) + v
            continue

        # Distribute volume across price range
        n_buckets = max(1, int(price_range / bucket_width))
        vol_per_bucket = v / n_buckets
        for k in range(n_buckets):
            price_point = l + (k + 0.5) * bucket_width
            bucket_key = round(price_point / bucket_width) * bucket_width
            volume_map[bucket_key] = volume_map.get(bucket_key, 0.0) + vol_per_bucket

    if not volume_map:
        return []

    total_vol = sum(volume_map.values())
    avg_vol = total_vol / len(volume_map)

    # Filter above-average buckets
    hvn_candidates = [
        {'price': price, 'volume': vol, 'score': vol / avg_vol}
        for price, vol in volume_map.items()
        if vol > avg_vol
    ]
    hvn_candidates.sort(key=lambda x: x['volume'], reverse=True)
    return hvn_candidates[:n_levels]


def cluster_levels(levels: list, cluster_pct: float = 0.003) -> list:
    """
    Merge S/R levels that are within `cluster_pct` of each other.

    When two levels are within 0.3% of each other, they represent the
    same structural zone — their scores are summed and the weighted
    average price is used.

    Args:
        levels: list of dicts: [{'price': float, 'score': float, 'source': str}, ...]
        cluster_pct: merge threshold as fraction of price (default 0.3%)

    Returns:
        list of merged dicts sorted by score descending.
        Returns [] on empty input.
    """
    if not levels:
        return []

    # Sort by price ascending to make adjacency detection easy
    sorted_levels = sorted(levels, key=lambda x: x['price'])
    merged = []
    current_cluster = [sorted_levels[0]]

    for level in sorted_levels[1:]:
        ref_price = current_cluster[0]['price']
        if abs(level['price'] - ref_price) / ref_price <= cluster_pct:
            current_cluster.append(level)
        else:
            merged.append(_collapse_cluster(current_cluster))
            current_cluster = [level]

    merged.append(_collapse_cluster(current_cluster))
    merged.sort(key=lambda x: x['score'], reverse=True)
    return merged


def _collapse_cluster(cluster: list) -> dict:
    """Collapse a list of nearby levels into one weighted-average entry."""
    total_score = sum(l['score'] for l in cluster)
    if total_score == 0:
        avg_price = sum(l['price'] for l in cluster) / len(cluster)
    else:
        avg_price = sum(l['price'] * l['score'] for l in cluster) / total_score
    sources = list({l.get('source', '') for l in cluster})
    return {'price': avg_price, 'score': total_score, 'source': '+'.join(filter(None, sources))}


def scale_sl_conditions(atr_pct: float) -> tuple:
    """
    Return ATR-adaptive Condition A/B thresholds for the two-condition SL rule.

    Fixed 0.5%/1.0% thresholds are too tight on high-ATR days (ATR=1.5–2%)
    and too generous on low-ATR days (ATR=0.3%).  Scaling to ATR prevents
    false triggers on volatile days and catches real breaks on calm days.

    Args:
        atr_pct: ATR as fraction of spot price (e.g. 0.008 = 0.8%)
                 Pass 0.0 for backward-compatible defaults.

    Returns:
        (cond_a_pct, cond_b_pct) — Condition A and B breach thresholds as fractions.
        cond_a_pct ∈ [0.003, 0.010]
        cond_b_pct ∈ [0.006, 0.020]   always 2× cond_a

    Backward compat: atr_pct=0 → (0.005, 0.010) — existing hardcoded defaults.
    """
    if not atr_pct or atr_pct <= 0:
        return (0.005, 0.010)  # legacy defaults

    cond_a = 0.3 * atr_pct
    cond_a = max(0.003, min(0.010, cond_a))
    cond_b = 2.0 * cond_a
    return (cond_a, cond_b)


def detect_liquidity_gaps(candles: list, gap_pct: float = 0.005) -> list:
    """
    Identify price zones where very little volume traded — "thin air" zones.

    Once price enters a liquidity vacuum it tends to move quickly because
    there are no resting orders to absorb the move.  The SL trigger can use
    this to escalate Condition A (trigger faster) when price is inside a vacuum.

    Algorithm:
        1. Compute average volume per 0.1% price bucket across all candles.
        2. Find contiguous price bands where EVERY bucket has volume < 10% of avg.
        3. Return those bands as vacuum zones with a score (depth of thinness).

    Args:
        candles:  list of dicts with keys 'high', 'low', 'close', 'volume'
                  ordered oldest → newest
        gap_pct:  bucket width as fraction of price for detection (default 0.5%)

    Returns:
        list of dicts: [{'low': float, 'high': float, 'vacuum_score': float}, ...]
        vacuum_score is the ratio of (avg_volume / max_bucket_vol_in_zone) —
        higher score means thinner zone (less volume relative to average).
        Returns [] if insufficient data.
    """
    if len(candles) < 5:
        return []

    all_prices = [float(c['close']) for c in candles if c.get('close')]
    if not all_prices:
        return []

    avg_price = sum(all_prices) / len(all_prices)
    if avg_price <= 0:
        return []

    bucket_width = avg_price * 0.001  # 0.1% buckets for resolution
    volume_map: dict = {}

    for c in candles:
        h = float(c['high'])
        l = float(c['low'])
        v = float(c['volume']) if c.get('volume') else 0.0
        price_range = h - l
        if price_range <= 0:
            bk = round(float(c['close']) / bucket_width) * bucket_width
            volume_map[bk] = volume_map.get(bk, 0.0) + v
            continue
        n_buckets = max(1, int(price_range / bucket_width))
        vol_per = v / n_buckets
        for k in range(n_buckets):
            price_point = l + (k + 0.5) * bucket_width
            bk = round(price_point / bucket_width) * bucket_width
            volume_map[bk] = volume_map.get(bk, 0.0) + vol_per

    if not volume_map:
        return []

    total_vol = sum(volume_map.values())
    avg_vol = total_vol / len(volume_map)
    if avg_vol <= 0:
        return []

    VACUUM_THRESHOLD = 0.10  # bucket must have < 10% of avg vol to be "thin"

    # Find price range spanned by candles
    all_highs = [float(c['high']) for c in candles]
    all_lows = [float(c['low']) for c in candles]
    price_min = min(all_lows)
    price_max = max(all_highs)

    gap_bucket_count = max(1, int(gap_pct * avg_price / bucket_width))

    vacuums = []
    in_vacuum = False
    vacuum_start = None
    vacuum_buckets = []

    # Walk sorted buckets; treat missing buckets as volume=0 (true vacuum)
    sorted_prices = []
    p = price_min
    while p <= price_max + bucket_width:
        bk = round(p / bucket_width) * bucket_width
        sorted_prices.append(bk)
        p += bucket_width

    for bk in sorted_prices:
        vol = volume_map.get(bk, 0.0)
        is_thin = vol < avg_vol * VACUUM_THRESHOLD

        if is_thin:
            if not in_vacuum:
                in_vacuum = True
                vacuum_start = bk
                vacuum_buckets = []
            vacuum_buckets.append((bk, vol))
        else:
            if in_vacuum and len(vacuum_buckets) >= gap_bucket_count:
                # Close out a qualifying vacuum zone
                zone_vol_max = max(v for _, v in vacuum_buckets) if vacuum_buckets else 0
                vacuum_score = avg_vol / (zone_vol_max + 1e-9)
                vacuum_score = min(vacuum_score, 10.0)
                vacuums.append({
                    'low': vacuum_start,
                    'high': bk,
                    'vacuum_score': round(vacuum_score, 2),
                })
            in_vacuum = False
            vacuum_start = None
            vacuum_buckets = []

    # Close final vacuum if at edge of range
    if in_vacuum and vacuum_buckets and len(vacuum_buckets) >= gap_bucket_count:
        zone_vol_max = max(v for _, v in vacuum_buckets) if vacuum_buckets else 0
        vacuum_score = avg_vol / (zone_vol_max + 1e-9)
        vacuum_score = min(vacuum_score, 10.0)
        vacuums.append({
            'low': vacuum_start,
            'high': vacuum_start + len(vacuum_buckets) * bucket_width,
            'vacuum_score': round(vacuum_score, 2),
        })

    return vacuums


def interpolate_target_offset(atr_pct: float, min_pct: float = 0.003, max_pct: float = 0.005) -> float:
    """
    Interpolate resistance target offset between min_pct and max_pct
    based on current ATR volatility.

    Low ATR  (≤ 0.5%) → use min_pct (0.3%) — less buffer needed
    High ATR (≥ 2.0%) → use max_pct (0.5%) — more buffer needed

    Args:
        atr_pct: ATR as fraction of spot price (e.g. 0.008 = 0.8%)
        min_pct: minimum offset (default 0.3%)
        max_pct: maximum offset (default 0.5%)

    Returns:
        offset as fraction (e.g. 0.0035 = 0.35%)
    """
    LOW_ATR = 0.005   # 0.5% daily ATR = calm market
    HIGH_ATR = 0.020  # 2.0% daily ATR = volatile market

    if atr_pct <= LOW_ATR:
        return min_pct
    if atr_pct >= HIGH_ATR:
        return max_pct

    # Linear interpolation
    t = (atr_pct - LOW_ATR) / (HIGH_ATR - LOW_ATR)
    return min_pct + t * (max_pct - min_pct)
