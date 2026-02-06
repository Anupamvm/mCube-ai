/**
 * Interactive Chart Component
 *
 * Reusable chart component for displaying price charts with technical indicators.
 * Used on suggestion detail page and manual triggers (Verify Trade, Strangle, Iron Condor).
 *
 * Features:
 * - Line/Candlestick toggle
 * - 20/50/100/200 DMA overlays
 * - S/R horizontal lines with labels
 * - Trade markers (entry, SL, target, strikes, breakevens)
 * - OI distribution bar chart (Chart.js)
 * - VIX indicator badge
 */

class InteractiveChart {
    /**
     * Initialize the interactive chart
     * @param {string} containerId - ID of the main chart container
     * @param {Object} options - Chart options
     * @param {number} options.suggestionId - Suggestion ID to fetch data for
     * @param {Object} options.contractData - Direct contract data (alternative to suggestionId)
     * @param {number} options.height - Chart height (default: 400)
     * @param {boolean} options.showOI - Show OI distribution chart (default: true)
     * @param {boolean} options.showLegend - Show legend controls (default: true)
     * @param {string} options.defaultChartType - 'line' or 'candlestick' (default: 'line')
     */
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.options = {
            suggestionId: options.suggestionId || null,
            contractData: options.contractData || null,
            height: options.height || 400,
            showOI: options.showOI !== false,
            showLegend: options.showLegend !== false,
            defaultChartType: options.defaultChartType || 'line',
            defaultDuration: options.defaultDuration || 90, // Default 3 months
            oiContainerId: options.oiContainerId || `${containerId}-oi`,
            vixBadgeId: options.vixBadgeId || `${containerId}-vix`,
            legendId: options.legendId || `${containerId}-legend`,
            compact: options.compact || false,
            ...options
        };

        this.chart = null;
        this.priceSeries = null;
        this.dmaLines = {};
        this.oiChart = null;
        this.chartData = null;
        this.currentChartType = this.options.defaultChartType;
        this.currentDuration = this.options.defaultDuration;
        this.isIntraday = false;
    }

    /**
     * Initialize the chart
     */
    async init() {
        try {
            console.log('[Chart] Initializing chart for container:', this.containerId);
            console.log('[Chart] Options:', this.options);
            this._showLoading();

            // Fetch or use provided chart data
            if (this.options.contractData) {
                console.log('[Chart] Fetching contract chart data...');
                this.chartData = await this._fetchContractChartData(this.options.contractData);
            } else if (this.options.suggestionId) {
                console.log('[Chart] Fetching suggestion chart data...');
                this.chartData = await this._fetchSuggestionChartData(this.options.suggestionId);
            } else {
                throw new Error('Either suggestionId or contractData must be provided');
            }

            console.log('[Chart] Chart data received:', this.chartData);

            if (!this.chartData.success) {
                this._showError(this.chartData.error || 'Failed to load chart data');
                return;
            }

            console.log('[Chart] Initializing main chart...');
            this._initMainChart();
            console.log('[Chart] Adding price series...');
            this._addPriceSeries();

            // Only add moving averages for non-intraday data
            if (!this.isIntraday) {
                console.log('[Chart] Adding moving averages...');
                this._addMovingAverages();
            } else {
                console.log('[Chart] Skipping moving averages for intraday data');
            }

            console.log('[Chart] Adding S/R lines...');
            this._addSupportResistanceLines();
            console.log('[Chart] Adding trade markers...');
            this._addTradeMarkers();

            if (this.options.showOI) {
                console.log('[Chart] Initializing OI chart...');
                this._initOIChart();
            }

            this._updateVIXBadge();

            if (this.options.showLegend) {
                this._setupEventHandlers();
            }

            this.chart.timeScale().fitContent();
            console.log('[Chart] Initialization complete!');

        } catch (error) {
            console.error('[Chart] Error initializing chart:', error);
            this._showError('Failed to initialize chart: ' + error.message);
        }
    }

    /**
     * Fetch chart data for a suggestion
     */
    async _fetchSuggestionChartData(suggestionId, days = null) {
        const daysParam = days || this.currentDuration;
        const url = `/trading/api/chart-data/${suggestionId}/?days=${daysParam}`;
        const response = await fetch(url);
        return await response.json();
    }

    /**
     * Fetch chart data for a contract (POST request)
     */
    async _fetchContractChartData(contractData, days = null) {
        const requestData = {
            ...contractData,
            days: days || this.currentDuration
        };
        const response = await fetch('/trading/api/chart-data/contract/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this._getCSRFToken()
            },
            body: JSON.stringify(requestData)
        });
        return await response.json();
    }

    /**
     * Get CSRF token from cookies
     */
    _getCSRFToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * Initialize main Lightweight Chart
     */
    _initMainChart() {
        const container = document.getElementById(this.containerId);
        if (!container) {
            throw new Error(`Container ${this.containerId} not found`);
        }

        container.innerHTML = '';

        // Determine if this is intraday data
        this.isIntraday = this.chartData?.data?.is_intraday || false;

        // Configure time scale based on duration
        const timeScaleOptions = {
            borderColor: '#cccccc',
            timeVisible: true,
            secondsVisible: false,
            rightOffset: 5,
        };

        // For intraday data, configure time formatting
        if (this.isIntraday) {
            timeScaleOptions.tickMarkFormatter = (time, tickMarkType, locale) => {
                const date = new Date(time * 1000);
                const hours = date.getHours().toString().padStart(2, '0');
                const minutes = date.getMinutes().toString().padStart(2, '0');

                // For 1 day view, show only time
                if (this.currentDuration === 1) {
                    return `${hours}:${minutes}`;
                }
                // For 5 day view, show day + time
                else if (this.currentDuration === 5) {
                    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
                    const dayName = days[date.getDay()];
                    return `${dayName} ${hours}:${minutes}`;
                }
                // For 1 month view, show date + time
                else {
                    const day = date.getDate();
                    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                    const month = months[date.getMonth()];
                    return `${day} ${month}`;
                }
            };
        }

        this.chart = LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: this.options.height,
            layout: {
                background: { type: 'solid', color: '#ffffff' },
                textColor: '#333',
            },
            grid: {
                vertLines: { color: '#f0f0f0' },
                horzLines: { color: '#f0f0f0' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: '#cccccc',
                scaleMargins: {
                    top: 0.1,    // 10% margin at top for labels
                    bottom: 0.1, // 10% margin at bottom for labels
                },
                minimumWidth: 80, // Ensure enough width for price labels
            },
            timeScale: timeScaleOptions,
            localization: {
                timeFormatter: (timestamp) => {
                    const date = new Date(timestamp * 1000);
                    if (this.isIntraday) {
                        const hours = date.getHours().toString().padStart(2, '0');
                        const minutes = date.getMinutes().toString().padStart(2, '0');
                        if (this.currentDuration === 1) {
                            return `${hours}:${minutes}`;
                        } else {
                            const day = date.getDate();
                            const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                            return `${day} ${months[date.getMonth()]} ${hours}:${minutes}`;
                        }
                    }
                    return date.toLocaleDateString();
                },
            },
        });

        const resizeObserver = new ResizeObserver(entries => {
            if (entries.length === 0 || entries[0].target !== container) return;
            const { width } = entries[0].contentRect;
            this.chart.applyOptions({ width });
        });
        resizeObserver.observe(container);
    }

    /**
     * Add price series (line or candlestick)
     */
    _addPriceSeries() {
        const data = this.chartData.data;
        const ohlc = data.historical?.ohlc || [];

        console.log('[Chart] Adding price series, OHLC records:', ohlc.length);
        console.log('[Chart] Is intraday:', this.isIntraday);
        if (ohlc.length > 0) {
            console.log('[Chart] First OHLC:', ohlc[0]);
            console.log('[Chart] Last OHLC:', ohlc[ohlc.length - 1]);
        }

        if (ohlc.length === 0) {
            console.warn('[Chart] No historical data available');
            // Show a message in the chart area
            const container = document.getElementById(this.containerId);
            if (container) {
                container.innerHTML = `
                    <div class="d-flex justify-content-center align-items-center" style="height: ${this.options.height}px; background: #fef3c7;">
                        <div class="text-center p-3">
                            <div style="font-size: 1.5rem; margin-bottom: 5px;">📊</div>
                            <div style="font-size: 0.9rem; color: #92400e;">No data available for this timeframe</div>
                            <div style="font-size: 0.75rem; color: #a1887f; margin-top: 5px;">
                                ${this.isIntraday ? 'Intraday data may only be available during market hours' : 'Try a different time period'}
                            </div>
                        </div>
                    </div>
                `;
            }
            return;
        }

        if (this.currentChartType === 'candlestick') {
            this.priceSeries = this.chart.addCandlestickSeries({
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderDownColor: '#ef5350',
                borderUpColor: '#26a69a',
                wickDownColor: '#ef5350',
                wickUpColor: '#26a69a',
            });

            this.priceSeries.setData(ohlc.map(d => ({
                time: d.time,
                open: d.open,
                high: d.high,
                low: d.low,
                close: d.close,
            })));
        } else {
            this.priceSeries = this.chart.addLineSeries({
                color: '#2962FF',
                lineWidth: 2,
            });

            this.priceSeries.setData(ohlc.map(d => ({
                time: d.time,
                value: d.close,
            })));
        }
    }

    /**
     * Add moving average lines
     */
    _addMovingAverages() {
        const ma = this.chartData.data.moving_averages;
        if (!ma) return;

        const dmaConfig = {
            dma_20: { color: '#FF9800', lineWidth: 1, title: '20 DMA' },
            dma_50: { color: '#9C27B0', lineWidth: 1, title: '50 DMA' },
            dma_100: { color: '#00BCD4', lineWidth: 1, title: '100 DMA' },
            dma_200: { color: '#2196F3', lineWidth: 2, title: '200 DMA' },
        };

        for (const [key, config] of Object.entries(dmaConfig)) {
            const data = ma[key];
            if (data && data.length > 0) {
                const series = this.chart.addLineSeries({
                    color: config.color,
                    lineWidth: config.lineWidth,
                    lineStyle: LightweightCharts.LineStyle.Solid,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    crosshairMarkerVisible: false,
                });

                series.setData(data.map(d => ({
                    time: d.time,
                    value: d.value,
                })));

                this.dmaLines[key] = series;
            }
        }
    }

    /**
     * Add support and resistance horizontal lines
     */
    _addSupportResistanceLines() {
        const sr = this.chartData.data.support_resistance;
        if (!sr || sr.error) return;

        // Support lines (green) - only S1 shows axis label
        ['s1', 's2', 's3'].forEach((key, i) => {
            const level = sr.support?.[key];
            if (level?.value) {
                const showLabel = (i === 0); // Only S1 shows label
                this._addHorizontalLine(level.value, '#4CAF50', `S${i+1}`, 'support', false, 1, showLabel);
            }
        });

        // Resistance lines (red) - only R1 shows axis label
        ['r1', 'r2', 'r3'].forEach((key, i) => {
            const level = sr.resistance?.[key];
            if (level?.value) {
                const showLabel = (i === 0); // Only R1 shows label
                this._addHorizontalLine(level.value, '#F44336', `R${i+1}`, 'resistance', false, 1, showLabel);
            }
        });

        // Pivot line (no axis label to reduce clutter)
        if (sr.pivot) {
            this._addHorizontalLine(sr.pivot, '#9E9E9E', 'Pivot', 'pivot', false, 1, false);
        }
    }

    /**
     * Add trade markers (entry, SL, target, strikes, breakevens)
     */
    _addTradeMarkers() {
        const markers = this.chartData.data.trade_markers;
        const chartType = this.chartData.data.chart_type;

        if (!markers) return;

        if (chartType === 'strangle') {
            // Strangle markers
            if (markers.call_strike) {
                this._addHorizontalLine(markers.call_strike, '#ef5350', 'CALL', 'marker', false, 2);
            }
            if (markers.put_strike) {
                this._addHorizontalLine(markers.put_strike, '#26a69a', 'PUT', 'marker', false, 2);
            }
            if (markers.breakeven_upper) {
                this._addHorizontalLine(markers.breakeven_upper, '#FF9800', 'BE↑', 'breakeven', true);
            }
            if (markers.breakeven_lower) {
                this._addHorizontalLine(markers.breakeven_lower, '#FF9800', 'BE↓', 'breakeven', true);
            }
            if (markers.entry_price) {
                this._addHorizontalLine(markers.entry_price, '#2962FF', 'Spot', 'spot', true);
            }
        } else if (chartType === 'iron_condor') {
            // Iron Condor markers (4 legs)
            if (markers.sold_call) {
                this._addHorizontalLine(markers.sold_call, '#ef5350', 'Sell CE', 'marker', false, 2);
            }
            if (markers.bought_call) {
                this._addHorizontalLine(markers.bought_call, '#ffcdd2', 'Buy CE', 'marker', true);
            }
            if (markers.sold_put) {
                this._addHorizontalLine(markers.sold_put, '#26a69a', 'Sell PE', 'marker', false, 2);
            }
            if (markers.bought_put) {
                this._addHorizontalLine(markers.bought_put, '#c8e6c9', 'Buy PE', 'marker', true);
            }
            if (markers.breakeven_upper) {
                this._addHorizontalLine(markers.breakeven_upper, '#FF9800', 'BE↑', 'breakeven', true);
            }
            if (markers.breakeven_lower) {
                this._addHorizontalLine(markers.breakeven_lower, '#FF9800', 'BE↓', 'breakeven', true);
            }
            if (markers.entry_price) {
                this._addHorizontalLine(markers.entry_price, '#2962FF', 'Spot', 'spot', true);
            }
        } else {
            // Futures markers
            if (markers.entry_price) {
                this._addHorizontalLine(markers.entry_price, '#2962FF', 'Entry', 'entry', false, 2);
            }
            if (markers.stop_loss) {
                this._addHorizontalLine(markers.stop_loss, '#F44336', 'SL', 'stoploss', false, 2);
            }
            if (markers.target) {
                this._addHorizontalLine(markers.target, '#4CAF50', 'Target', 'target', false, 2);
            }
        }
    }

    /**
     * Add a horizontal price line
     * @param {number} price - Price level
     * @param {string} color - Line color
     * @param {string} title - Label text
     * @param {string} type - Line type for identification
     * @param {boolean} dashed - Use dashed line style
     * @param {number} lineWidth - Line width
     * @param {boolean} axisLabelVisible - Show label on price axis (default: true)
     */
    _addHorizontalLine(price, color, title, type, dashed = false, lineWidth = 1, axisLabelVisible = true) {
        if (!this.priceSeries) return;

        this.priceSeries.createPriceLine({
            price: price,
            color: color,
            lineWidth: lineWidth,
            lineStyle: dashed ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Dotted,
            axisLabelVisible: axisLabelVisible,
            title: title,
        });
    }

    /**
     * Initialize OI distribution bar chart
     */
    _initOIChart() {
        const oiContainer = document.getElementById(this.options.oiContainerId);
        if (!oiContainer) return;

        const oi = this.chartData.data.oi_distribution;
        if (!oi || oi.error || !oi.strikes || oi.strikes.length === 0) {
            oiContainer.innerHTML = '<p class="text-muted text-center py-3" style="font-size: 0.8rem;">OI distribution not available</p>';
            return;
        }

        oiContainer.innerHTML = `<canvas id="${this.options.oiContainerId}-canvas"></canvas>`;
        const canvas = document.getElementById(`${this.options.oiContainerId}-canvas`);

        this.oiChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: oi.strikes.map(s => s.toString()),
                datasets: [
                    {
                        label: 'Call OI',
                        data: oi.call_oi,
                        backgroundColor: 'rgba(239, 83, 80, 0.7)',
                        borderColor: 'rgba(239, 83, 80, 1)',
                        borderWidth: 1,
                    },
                    {
                        label: 'Put OI',
                        data: oi.put_oi,
                        backgroundColor: 'rgba(38, 166, 154, 0.7)',
                        borderColor: 'rgba(38, 166, 154, 1)',
                        borderWidth: 1,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { font: { size: 10 } }
                    },
                    title: {
                        display: !this.options.compact,
                        text: `OI Distribution (${oi.expiry || 'N/A'})`,
                        font: { size: 11 }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const value = context.raw;
                                return `${context.dataset.label}: ${(value / 1000).toFixed(0)}K`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { font: { size: 9 } }
                    },
                    y: {
                        ticks: {
                            font: { size: 9 },
                            callback: function(value) {
                                return (value / 1000).toFixed(0) + 'K';
                            }
                        }
                    }
                }
            }
        });

        // Add max OI annotation
        if (!this.options.compact) {
            const annotationDiv = document.createElement('div');
            annotationDiv.className = 'text-center mt-1';
            annotationDiv.innerHTML = `
                <small class="text-muted">
                    <span style="color: #ef5350; font-weight: 500;">Max Call OI: ${oi.max_call_oi_strike || 'N/A'}</span>
                    <span class="mx-2">|</span>
                    <span style="color: #26a69a; font-weight: 500;">Max Put OI: ${oi.max_put_oi_strike || 'N/A'}</span>
                </small>
            `;
            oiContainer.appendChild(annotationDiv);
        }
    }

    /**
     * Update VIX badge
     */
    _updateVIXBadge() {
        const vixBadge = document.getElementById(this.options.vixBadgeId);
        if (!vixBadge) return;

        const vix = this.chartData.data.vix;
        if (!vix || vix.error) {
            vixBadge.innerHTML = '<span class="badge bg-secondary" style="font-size: 0.7rem;">VIX: N/A</span>';
            return;
        }

        vixBadge.innerHTML = `
            <span class="badge" style="background-color: ${vix.color}; font-size: 0.7rem;">
                VIX: ${vix.current?.toFixed(1) || 'N/A'} (${vix.status})
            </span>
        `;
    }

    /**
     * Setup event handlers
     */
    _setupEventHandlers() {
        // Chart type toggle
        const chartTypeSelect = document.getElementById(`${this.containerId}-chart-type`);
        if (chartTypeSelect) {
            chartTypeSelect.addEventListener('change', (e) => {
                this.toggleChartType(e.target.value);
            });
        }

        // Duration selector
        const durationSelect = document.getElementById(`${this.containerId}-duration`);
        if (durationSelect) {
            durationSelect.addEventListener('change', (e) => {
                this.changeDuration(parseInt(e.target.value));
            });
        }

        // DMA toggle checkboxes
        const container = document.getElementById(this.containerId)?.parentElement;
        if (container) {
            const dmaCheckboxes = container.querySelectorAll('.dma-toggle');
            dmaCheckboxes.forEach(checkbox => {
                checkbox.addEventListener('change', (e) => {
                    const dmaKey = e.target.dataset.dma;
                    this.toggleDMA(dmaKey, e.target.checked);
                });
            });
        }
    }

    /**
     * Toggle chart type between line and candlestick
     */
    toggleChartType(type) {
        if (type === this.currentChartType) return;
        this.currentChartType = type;

        if (this.priceSeries) {
            this.chart.removeSeries(this.priceSeries);
        }

        this._addPriceSeries();
        this._addSupportResistanceLines();
        this._addTradeMarkers();
    }

    /**
     * Toggle DMA line visibility
     */
    toggleDMA(dmaKey, visible) {
        const series = this.dmaLines[dmaKey];
        if (series) {
            series.applyOptions({ visible: visible });
        }
    }

    /**
     * Change chart duration and re-fetch data
     * @param {number} days - Number of days (1, 5, 30, 90, 180, 365, 1825)
     */
    async changeDuration(days) {
        if (days === this.currentDuration) return;

        this.currentDuration = days;
        const isIntraday = [1, 5, 30].includes(days);
        console.log(`[Chart] Changing duration to ${days} days, intraday=${isIntraday}`);

        // Show loading state in the chart container
        const container = document.getElementById(this.containerId);
        if (container) {
            const loadingMsg = isIntraday
                ? `Loading ${this._getDurationLabel(days)} intraday data...`
                : `Loading ${this._getDurationLabel(days)} data...`;
            container.innerHTML = `
                <div class="d-flex justify-content-center align-items-center" style="height: ${this.options.height}px; background: #f8f9fa;">
                    <div class="text-center">
                        <div class="spinner-border spinner-border-sm text-primary mb-2" role="status"></div>
                        <div style="font-size: 0.8rem; color: #6b7280;">${loadingMsg}</div>
                    </div>
                </div>
            `;
        }

        try {
            // Re-fetch data with new duration
            if (this.options.contractData) {
                this.chartData = await this._fetchContractChartData(this.options.contractData, days);
            } else if (this.options.suggestionId) {
                this.chartData = await this._fetchSuggestionChartData(this.options.suggestionId, days);
            }

            if (!this.chartData.success) {
                this._showError(this.chartData.error || 'Failed to load chart data');
                return;
            }

            // Update intraday flag
            this.isIntraday = this.chartData.data?.is_intraday || false;

            // Clear existing chart and DMA lines
            if (this.chart) {
                this.chart.remove();
                this.chart = null;
            }
            this.priceSeries = null;
            this.dmaLines = {};

            // Re-initialize chart with new data
            this._initMainChart();
            this._addPriceSeries();

            // Only add moving averages for non-intraday data (they don't make sense for 5-min candles)
            if (!this.isIntraday) {
                this._addMovingAverages();
            }

            this._addSupportResistanceLines();
            this._addTradeMarkers();
            this.chart.timeScale().fitContent();

        } catch (error) {
            console.error('Error changing duration:', error);
            this._showError('Failed to load data: ' + error.message);
        }
    }

    /**
     * Get human-readable duration label
     */
    _getDurationLabel(days) {
        const labels = {
            1: '1 day',
            5: '5 days',
            30: '1 month',
            90: '3 months',
            180: '6 months',
            365: '1 year',
            1825: '5 years'
        };
        return labels[days] || `${days} days`;
    }

    /**
     * Show loading state
     */
    _showLoading() {
        const container = document.getElementById(this.containerId);
        if (container) {
            container.innerHTML = `
                <div class="d-flex justify-content-center align-items-center" style="height: ${this.options.height}px; background: #f8f9fa;">
                    <div class="text-center">
                        <div class="spinner-border spinner-border-sm text-primary mb-2" role="status"></div>
                        <div style="font-size: 0.8rem; color: #6b7280;">Loading chart...</div>
                    </div>
                </div>
            `;
        }
    }

    /**
     * Show error state
     */
    _showError(message) {
        const container = document.getElementById(this.containerId);
        if (container) {
            container.innerHTML = `
                <div class="d-flex justify-content-center align-items-center" style="height: ${Math.min(this.options.height, 150)}px; background: #fef3c7; border-radius: 8px;">
                    <div class="text-center p-3">
                        <div style="font-size: 1.5rem; margin-bottom: 5px;">⚠️</div>
                        <div style="font-size: 0.8rem; color: #92400e;">${message}</div>
                    </div>
                </div>
            `;
        }
    }

    /**
     * Destroy chart instances
     */
    destroy() {
        if (this.chart) {
            this.chart.remove();
            this.chart = null;
        }
        if (this.oiChart) {
            this.oiChart.destroy();
            this.oiChart = null;
        }
    }

    /**
     * Static method to generate chart HTML template
     * @param {string} id - Unique identifier for this chart instance
     * @param {string} chartType - 'futures', 'strangle', or 'iron_condor'
     * @param {boolean} compact - Use compact layout
     * @returns {string} HTML template
     */
    static getChartHTML(id, chartType = 'futures', compact = false) {
        const height = compact ? 300 : 400;
        const oiHeight = compact ? 120 : 150;

        let markersLegend = '';
        if (chartType === 'strangle') {
            markersLegend = `
                <span style="color: #ef5350;">━ CALL</span>
                <span style="color: #26a69a;">━ PUT</span>
                <span style="color: #FF9800;">┄ Breakeven</span>
            `;
        } else if (chartType === 'iron_condor') {
            markersLegend = `
                <span style="color: #ef5350;">━ Sell CE</span>
                <span style="color: #ffcdd2;">┄ Buy CE</span>
                <span style="color: #26a69a;">━ Sell PE</span>
                <span style="color: #c8e6c9;">┄ Buy PE</span>
            `;
        } else {
            markersLegend = `
                <span style="color: #2962FF;">━ Entry</span>
                <span style="color: #F44336;">━ SL</span>
                <span style="color: #4CAF50;">━ Target</span>
            `;
        }

        return `
            <div class="chart-wrapper" style="background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                <!-- Chart Header -->
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; background: #f8f9fa; border-bottom: 1px solid #e5e7eb;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-weight: 600; font-size: 0.9rem;">📈 Price Chart</span>
                        <div id="${id}-vix"></div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <select id="${id}-duration" style="padding: 4px 8px; font-size: 0.75rem; border: 1px solid #d1d5db; border-radius: 4px;">
                            <option value="1">1D</option>
                            <option value="5">5D</option>
                            <option value="30">1M</option>
                            <option value="90" selected>3M</option>
                            <option value="180">6M</option>
                            <option value="365">1Y</option>
                            <option value="1825">5Y</option>
                        </select>
                        <select id="${id}-chart-type" style="padding: 4px 8px; font-size: 0.75rem; border: 1px solid #d1d5db; border-radius: 4px;">
                            <option value="line">Line</option>
                            <option value="candlestick">Candle</option>
                        </select>
                    </div>
                </div>

                <!-- Main Chart -->
                <div id="${id}" style="height: ${height}px;"></div>

                <!-- Legend -->
                <div style="display: flex; flex-wrap: wrap; gap: 12px; padding: 8px 15px; background: #f8f9fa; font-size: 0.7rem; border-top: 1px solid #e5e7eb;">
                    <span style="color: #FF9800;">━ 20 DMA</span>
                    <span style="color: #2196F3;">━ 200 DMA</span>
                    <span style="color: #4CAF50;">┄ Support</span>
                    <span style="color: #F44336;">┄ Resistance</span>
                    ${markersLegend}
                </div>

                <!-- OI Distribution -->
                <div id="${id}-oi" style="height: ${oiHeight}px; padding: 10px; background: #fafafa; border-top: 1px solid #e5e7eb;"></div>
            </div>
        `;
    }
}

// Export for global usage
window.InteractiveChart = InteractiveChart;
