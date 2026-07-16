/**
 * JS mirror of apps/hedging/services/payoff_engine.py.
 *
 * Function-for-function port so the Cover Position modal's payoff graph
 * updates instantly on every strike/quantity slider tick without a
 * network round trip (the "today" mark-to-market curve is the one
 * exception — it needs live Greeks, so it's fetched from the backend on
 * a debounce instead of computed here).
 *
 * Keep this in sync with payoff_engine.py by hand; both are covered by
 * the shared JSON fixture referenced in that module's tests.
 */

function calculateEffectiveBreakeven(futuresAvgPrice, lotsCovered, lotSize, netPremiumCollected) {
    const coveredShares = lotsCovered * lotSize;
    if (coveredShares <= 0) {
        return futuresAvgPrice;
    }
    return futuresAvgPrice - (netPremiumCollected / coveredShares);
}

function _callLegPnlAtSpot(spot, callStrike, callPremium, callLots, lotSize) {
    if (callLots <= 0) {
        return 0.0;
    }
    let payoffPerShare;
    if (spot <= callStrike) {
        payoffPerShare = callPremium;
    } else {
        payoffPerShare = callPremium - (spot - callStrike);
    }
    return payoffPerShare * callLots * lotSize;
}

function calculatePayoffAtExpiry(spotRange, futuresAvgPrice, futuresLots, lotSize, callStrike, callPremium, callLots) {
    return spotRange.map((spot) => {
        const futuresPnl = (spot - futuresAvgPrice) * futuresLots * lotSize;
        const callPnl = _callLegPnlAtSpot(spot, callStrike, callPremium, callLots, lotSize);
        return { spot, futures_pnl: futuresPnl, call_pnl: callPnl, total_pnl: futuresPnl + callPnl };
    });
}

function isFullyCapped(futuresLots, callLots) {
    return callLots >= futuresLots && futuresLots > 0;
}

function calculateMaxProfit(futuresAvgPrice, futuresLots, lotSize, callStrike, callPremium, callLots) {
    if (!isFullyCapped(futuresLots, callLots)) {
        return null;
    }
    const futuresPnlAtStrike = (callStrike - futuresAvgPrice) * futuresLots * lotSize;
    const callPnlAtStrike = _callLegPnlAtSpot(callStrike, callStrike, callPremium, callLots, lotSize);
    return futuresPnlAtStrike + callPnlAtStrike;
}

function calculateCappedUpsidePrice(futuresLots, callStrike, callLots) {
    if (!isFullyCapped(futuresLots, callLots)) {
        return null;
    }
    return callStrike;
}

function calculateProtectionMetrics(futuresAvgPrice, currentSpot, netPremiumCollected, lotsCovered, lotSize) {
    const coveredShares = lotsCovered * lotSize;
    const openLossPerShare = Math.max(futuresAvgPrice - currentSpot, 0.0);
    const premiumPerShare = coveredShares > 0 ? (netPremiumCollected / coveredShares) : 0.0;
    let protectionPct = null;
    if (openLossPerShare > 0) {
        protectionPct = Math.min(premiumPerShare / openLossPerShare, 1.0) * 100.0;
    }
    return { open_loss_per_share: openLossPerShare, premium_per_share: premiumPerShare, protection_pct: protectionPct };
}

function findZeroCrossings(curve) {
    const crossings = [];
    for (let i = 0; i < curve.length - 1; i++) {
        const prevPoint = curve[i];
        const currPoint = curve[i + 1];
        const prevPnl = prevPoint.total_pnl;
        const currPnl = currPoint.total_pnl;
        if (prevPnl === 0) {
            crossings.push(prevPoint.spot);
            continue;
        }
        if ((prevPnl < 0) !== (currPnl < 0)) {
            const fraction = prevPnl / (prevPnl - currPnl);
            crossings.push(prevPoint.spot + fraction * (currPoint.spot - prevPoint.spot));
        }
    }
    return crossings;
}

/** Builds a symmetric spot range around the current spot, e.g. ±20% in 41 steps. */
function buildSpotRange(currentSpot, spreadPct = 0.20, steps = 40) {
    const lo = currentSpot * (1 - spreadPct);
    const hi = currentSpot * (1 + spreadPct);
    const stepSize = (hi - lo) / steps;
    const range = [];
    for (let i = 0; i <= steps; i++) {
        range.push(lo + i * stepSize);
    }
    return range;
}

// Exposed as a single namespace to avoid polluting globals in view_trades.html.
window.HedgingPayoffCalculator = {
    calculateEffectiveBreakeven,
    calculatePayoffAtExpiry,
    isFullyCapped,
    calculateMaxProfit,
    calculateCappedUpsidePrice,
    calculateProtectionMetrics,
    findZeroCrossings,
    buildSpotRange,
};
