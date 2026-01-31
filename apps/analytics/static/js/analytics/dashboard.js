/**
 * Dashboard JavaScript for mCube Analytics
 * Handles chart rendering and data fetching for the analytics dashboard
 */

// Global state
const DashboardState = {
    account: null,
    period: 'FY',
    fy: null,  // Financial year filter (e.g., '2024-25')
    benchmark: 'NIFTY50',
    granularity: 'daily',
    charts: {}
};

// API endpoints
const API = {
    summary: '/analytics/api/dashboard/summary/',
    pnlChart: '/analytics/api/dashboard/pnl-chart/',
    cumulativeReturns: '/analytics/api/dashboard/cumulative-returns/',
    winLossDistribution: '/analytics/api/dashboard/win-loss-distribution/',
    strategyPerformance: '/analytics/api/dashboard/strategy-performance/',
    benchmarkComparison: '/analytics/api/dashboard/benchmark-comparison/',
    bestWorstTrades: '/analytics/api/dashboard/best-worst-trades/'
};

// Color palette
const Colors = {
    primary: '#4F46E5',
    success: '#10B981',
    danger: '#EF4444',
    warning: '#F59E0B',
    gray: '#6B7280',
    light: '#F3F4F6'
};

// Utility functions
function formatCurrency(value) {
    if (value === null || value === undefined) return '--';
    const formatted = new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0
    }).format(Math.abs(value));
    return value < 0 ? `-${formatted}` : formatted;
}

function formatPercent(value) {
    if (value === null || value === undefined) return '--';
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function formatNumber(value, decimals = 2) {
    if (value === null || value === undefined) return '--';
    return value.toFixed(decimals);
}

function showLoading(containerId) {
    const el = document.getElementById(containerId);
    if (el) el.style.display = 'flex';
}

function hideLoading(containerId) {
    const el = document.getElementById(containerId);
    if (el) el.style.display = 'none';
}

function getQueryParams() {
    const params = new URLSearchParams();
    if (DashboardState.account) params.append('account_id', DashboardState.account);
    if (DashboardState.fy) params.append('fy', DashboardState.fy);
    params.append('period', DashboardState.period);
    return params.toString();
}

// API calls
async function fetchJSON(url) {
    try {
        const response = await fetch(url);
        const data = await response.json();
        if (!data.success) {
            console.error('API error:', data.error);
            return null;
        }
        return data.data;
    } catch (error) {
        console.error('Fetch error:', error);
        return null;
    }
}

// Dashboard initialization
async function initDashboard() {
    await Promise.all([
        loadSummary(),
        loadPnLChart(),
        loadEquityChart(),
        loadStrategyChart(),
        loadDistributionChart(),
        loadBenchmarkComparison(),
        loadBestWorstTrades()
    ]);
}

// Load summary metrics
async function loadSummary() {
    const data = await fetchJSON(`${API.summary}?${getQueryParams()}`);
    if (!data) return;

    // Update summary cards
    const totalPnl = document.getElementById('total-pnl');
    totalPnl.textContent = formatCurrency(data.total_pnl);
    totalPnl.className = `summary-card-value ${data.total_pnl >= 0 ? 'positive' : 'negative'}`;

    document.getElementById('win-rate').textContent = `${formatNumber(data.win_rate, 1)}%`;
    document.getElementById('total-trades').textContent = data.total_trades || '--';
    document.getElementById('profit-factor').textContent = formatNumber(data.profit_factor);
    document.getElementById('sharpe-ratio').textContent = formatNumber(data.sharpe_ratio);

    const maxDD = document.getElementById('max-drawdown');
    maxDD.textContent = `${formatNumber(data.max_drawdown_pct)}%`;
    maxDD.className = 'summary-card-value negative';
}

// Load P&L chart
async function loadPnLChart() {
    showLoading('pnl-loading');

    const params = new URLSearchParams();
    if (DashboardState.account) params.append('account_id', DashboardState.account);
    if (DashboardState.fy) params.append('fy', DashboardState.fy);
    params.append('period', DashboardState.period);
    params.append('granularity', DashboardState.granularity);

    const data = await fetchJSON(`${API.pnlChart}?${params.toString()}`);
    hideLoading('pnl-loading');
    if (!data) return;

    // Destroy existing chart
    if (DashboardState.charts.pnl) {
        DashboardState.charts.pnl.destroy();
    }

    const ctx = document.getElementById('pnl-chart').getContext('2d');
    DashboardState.charts.pnl = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'P&L',
                data: data.realized_pnl,
                backgroundColor: data.realized_pnl.map(v => v >= 0 ? Colors.success : Colors.danger),
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    ticks: {
                        callback: value => formatCurrency(value)
                    }
                }
            }
        }
    });
}

// Load equity curve
async function loadEquityChart() {
    showLoading('equity-loading');
    const data = await fetchJSON(`${API.cumulativeReturns}?${getQueryParams()}`);
    hideLoading('equity-loading');
    if (!data) return;

    if (DashboardState.charts.equity) {
        DashboardState.charts.equity.destroy();
    }

    const ctx = document.getElementById('equity-chart').getContext('2d');
    DashboardState.charts.equity = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Portfolio Value',
                data: data.equity,
                borderColor: Colors.primary,
                backgroundColor: `${Colors.primary}20`,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    ticks: {
                        callback: value => formatCurrency(value)
                    }
                }
            }
        }
    });
}

// Load strategy performance chart
async function loadStrategyChart() {
    showLoading('strategy-loading');
    const data = await fetchJSON(`${API.strategyPerformance}?${getQueryParams()}`);
    hideLoading('strategy-loading');
    if (!data || !data.strategies) return;

    if (DashboardState.charts.strategy) {
        DashboardState.charts.strategy.destroy();
    }

    const strategies = data.strategies;
    const ctx = document.getElementById('strategy-chart').getContext('2d');
    DashboardState.charts.strategy = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: strategies.map(s => s.strategy),
            datasets: [{
                label: 'P&L',
                data: strategies.map(s => s.total_pnl),
                backgroundColor: strategies.map(s => s.total_pnl >= 0 ? Colors.success : Colors.danger),
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    ticks: {
                        callback: value => formatCurrency(value)
                    }
                }
            }
        }
    });
}

// Load distribution chart
async function loadDistributionChart() {
    showLoading('distribution-loading');
    const data = await fetchJSON(`${API.winLossDistribution}?${getQueryParams()}`);
    hideLoading('distribution-loading');
    if (!data || !data.histogram) return;

    if (DashboardState.charts.distribution) {
        DashboardState.charts.distribution.destroy();
    }

    const histogram = data.histogram;
    const ctx = document.getElementById('distribution-chart').getContext('2d');
    DashboardState.charts.distribution = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: histogram.labels,
            datasets: [{
                label: 'Trade Count',
                data: histogram.counts,
                backgroundColor: Colors.primary,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// Load benchmark comparison
async function loadBenchmarkComparison() {
    showLoading('benchmark-loading');

    const params = new URLSearchParams();
    if (DashboardState.account) params.append('account_id', DashboardState.account);
    if (DashboardState.fy) params.append('fy', DashboardState.fy);
    params.append('period', DashboardState.period);
    params.append('benchmark', DashboardState.benchmark);

    const data = await fetchJSON(`${API.benchmarkComparison}?${params.toString()}`);
    hideLoading('benchmark-loading');
    if (!data) return;

    // Update stats
    const portfolioReturn = document.getElementById('portfolio-return');
    portfolioReturn.textContent = formatPercent(data.portfolio_return);
    portfolioReturn.className = `benchmark-value ${data.portfolio_return >= 0 ? 'pnl-positive' : 'pnl-negative'}`;

    const benchmarkReturn = document.getElementById('benchmark-return');
    benchmarkReturn.textContent = formatPercent(data.benchmark_return);
    benchmarkReturn.className = `benchmark-value ${data.benchmark_return >= 0 ? 'pnl-positive' : 'pnl-negative'}`;

    const excessReturn = document.getElementById('excess-return');
    excessReturn.textContent = formatPercent(data.excess_return);
    excessReturn.className = `benchmark-value ${data.excess_return >= 0 ? 'pnl-positive' : 'pnl-negative'}`;

    document.getElementById('beta-value').textContent = formatNumber(data.beta);

    const alphaValue = document.getElementById('alpha-value');
    alphaValue.textContent = formatPercent(data.alpha);
    if (data.alpha !== null) {
        alphaValue.className = `benchmark-value ${data.alpha >= 0 ? 'pnl-positive' : 'pnl-negative'}`;
    }

    // Render chart if series data available
    if (data.portfolio_series && data.benchmark_series) {
        if (DashboardState.charts.benchmark) {
            DashboardState.charts.benchmark.destroy();
        }

        const ctx = document.getElementById('benchmark-chart').getContext('2d');
        DashboardState.charts.benchmark = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.portfolio_series.map(p => p.date),
                datasets: [
                    {
                        label: 'Portfolio',
                        data: data.portfolio_series.map(p => p.value),
                        borderColor: Colors.primary,
                        tension: 0.4,
                        fill: false
                    },
                    {
                        label: DashboardState.benchmark,
                        data: data.benchmark_series.map(p => p.value),
                        borderColor: Colors.gray,
                        tension: 0.4,
                        fill: false,
                        borderDash: [5, 5]
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top'
                    }
                },
                scales: {
                    y: {
                        title: {
                            display: true,
                            text: 'Normalized Value (100 = Start)'
                        }
                    }
                }
            }
        });
    }
}

// Load best/worst trades
async function loadBestWorstTrades() {
    const params = new URLSearchParams();
    if (DashboardState.account) params.append('account_id', DashboardState.account);
    if (DashboardState.fy) params.append('fy', DashboardState.fy);
    params.append('limit', '5');

    const data = await fetchJSON(`${API.bestWorstTrades}?${params.toString()}`);
    if (!data) return;

    // Populate best trades table
    const bestTableBody = document.querySelector('#best-trades tbody');
    bestTableBody.innerHTML = (data.best_trades || []).map(trade => `
        <tr>
            <td>${trade.instrument}</td>
            <td>${trade.strategy}</td>
            <td class="pnl-positive">${formatCurrency(trade.net_pnl)}</td>
        </tr>
    `).join('');

    // Populate worst trades table
    const worstTableBody = document.querySelector('#worst-trades tbody');
    worstTableBody.innerHTML = (data.worst_trades || []).map(trade => `
        <tr>
            <td>${trade.instrument}</td>
            <td>${trade.strategy}</td>
            <td class="pnl-negative">${formatCurrency(trade.net_pnl)}</td>
        </tr>
    `).join('');
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Initialize FY from URL or dropdown
    const fyFilter = document.getElementById('fy-filter');
    if (fyFilter) {
        DashboardState.fy = fyFilter.value === 'ALL' ? null : fyFilter.value;
    }

    // Initialize dashboard
    initDashboard();

    // FY filter
    if (fyFilter) {
        fyFilter.addEventListener('change', (e) => {
            DashboardState.fy = e.target.value === 'ALL' ? null : e.target.value;
            initDashboard();
        });
    }

    // Account filter
    document.getElementById('account-filter').addEventListener('change', (e) => {
        DashboardState.account = e.target.value || null;
        initDashboard();
    });

    // Period filter
    document.getElementById('period-filter').addEventListener('change', (e) => {
        DashboardState.period = e.target.value;
        initDashboard();
    });

    // P&L granularity
    document.getElementById('pnl-granularity').addEventListener('change', (e) => {
        DashboardState.granularity = e.target.value;
        loadPnLChart();
    });

    // Benchmark select
    document.getElementById('benchmark-select').addEventListener('change', (e) => {
        DashboardState.benchmark = e.target.value;
        loadBenchmarkComparison();
    });

    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', () => {
        initDashboard();
    });
});
