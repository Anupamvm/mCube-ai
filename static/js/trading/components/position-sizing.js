/**
 * Position Sizing Module
 * Consolidates all position sizing calculations and UI builders
 * Eliminates duplicate fetchPositionSizing, updatePositionSize functions
 */

const PositionSizing = (function() {
    'use strict';

    /**
     * Fetch position sizing data from API
     * Consolidates duplicate implementations from lines 2034 and 2320
     * @param {Object} contract - Contract object with symbol, expiry, direction
     * @returns {Promise<Object>} Position sizing data
     */
    async function fetchPositionSizing(contract) {
        try {
            // Extract required fields
            const symbol = contract.symbol;
            const expiry = contract.expiry_date || contract.expiry; // Prefer YYYY-MM-DD format
            const direction = contract.direction || 'LONG';

            // Validate required fields
            if (!symbol || !expiry) {
                console.error('Missing required fields:', { symbol, expiry, contract });
                throw new Error('Symbol and expiry are required');
            }

            console.log('Fetching position sizing for:', { symbol, expiry, direction });

            const response = await ApiClient.post(ApiClient.endpoints.calculatePosition, {
                symbol: symbol,
                expiry: expiry,
                direction: direction,
                custom_lots: null
            });

            if (!response.success) {
                throw new Error(response.error || 'Failed to calculate position sizing');
            }

            // Cache the position data
            if (window.TradingState) {
                TradingState.set('currentPositionData', response);
            }

            return response;
        } catch (error) {
            console.error('Error fetching position sizing:', error);
            TradingUtils.showError('Failed to load position sizing: ' + error.message);
            throw error;
        }
    }

    /**
     * Update position size calculations
     * Consolidates duplicate implementations from lines 2102 and 2399
     * @param {number} newLots - New lot quantity
     * @param {Object} positionData - Position data object
     * @param {string} elementPrefix - Prefix for element IDs
     */
    async function updatePositionSize(newLots, positionData = null, elementPrefix = '') {
        try {
            // Use provided data or get from state
            const data = positionData || TradingState.get('currentPositionData');
            if (!data) {
                console.error('No position data available');
                return;
            }

            const lots = parseInt(newLots);
            if (isNaN(lots) || lots < 1) {
                console.error('Invalid lot quantity:', newLots);
                return;
            }

            // Update lot quantity display
            const lotDisplay = document.getElementById(`${elementPrefix}lotDisplay`);
            if (lotDisplay) {
                lotDisplay.textContent = lots;
            }

            // Calculate values
            const totalQuantity = lots * data.lot_size;
            const marginRequired = lots * data.margin_per_lot;
            const marginUtilization = (marginRequired / data.available_margin) * 100;
            const positionValue = totalQuantity * (data.current_price || data.futures_price || 0);

            // Update displays
            updateDisplay(`${elementPrefix}totalQuantity`, totalQuantity.toLocaleString());
            updateDisplay(`${elementPrefix}marginRequired`, TradingUtils.formatCurrency(marginRequired));
            updateDisplay(`${elementPrefix}marginUtilization`, `${marginUtilization.toFixed(1)}%`);
            updateDisplay(`${elementPrefix}positionValue`, TradingUtils.formatCurrency(positionValue));

            // Update utilization bar if exists
            const utilizationBar = document.getElementById(`${elementPrefix}utilizationBar`);
            if (utilizationBar) {
                utilizationBar.style.width = `${Math.min(marginUtilization, 100)}%`;
                utilizationBar.style.background =
                    marginUtilization > 90 ? '#ef4444' :
                    marginUtilization > 70 ? '#f59e0b' : '#10b981';
            }

            // Calculate P&L scenarios
            const pnlScenarios = calculatePnLScenarios(data, lots);
            if (pnlScenarios) {
                updatePnLTable(pnlScenarios, elementPrefix);
            }

            // Update averaging strategy if applicable
            if (data.averaging_strategy) {
                updateAveragingStrategy(data.averaging_strategy, elementPrefix);
            }

            return {
                lots,
                totalQuantity,
                marginRequired,
                marginUtilization,
                positionValue
            };
        } catch (error) {
            console.error('Error updating position size:', error);
        }
    }

    /**
     * Calculate P&L scenarios
     * @param {Object} data - Position data
     * @param {number} lots - Number of lots
     * @returns {Array} P&L scenarios
     */
    function calculatePnLScenarios(data, lots) {
        const scenarios = [];
        const entryPrice = data.current_price || data.futures_price || 0;
        const lotSize = data.lot_size || 1;
        const totalQuantity = lots * lotSize;

        // Define percentage moves
        const moves = [-5, -3, -2, -1, 1, 2, 3, 5];

        for (const move of moves) {
            const exitPrice = entryPrice * (1 + move / 100);
            const priceChange = exitPrice - entryPrice;
            const pnl = priceChange * totalQuantity * (data.direction === 'SHORT' ? -1 : 1);

            scenarios.push({
                move: `${move > 0 ? '+' : ''}${move}%`,
                exitPrice: exitPrice.toFixed(2),
                pnl: pnl,
                pnlFormatted: TradingUtils.formatCurrency(pnl),
                isProfit: pnl > 0
            });
        }

        return scenarios;
    }

    /**
     * Update P&L table display
     * Consolidates duplicate implementations from lines 2162 and 2464
     * @param {Array} scenarios - P&L scenarios
     * @param {string} elementPrefix - Prefix for element IDs
     */
    function updatePnLTable(scenarios, elementPrefix = '') {
        const tableBody = document.getElementById(`${elementPrefix}pnlTableBody`);
        if (!tableBody) return;

        tableBody.innerHTML = scenarios.map(scenario => `
            <tr>
                <td>${scenario.move}</td>
                <td>₹${scenario.exitPrice}</td>
                <td style="color: ${scenario.isProfit ? 'green' : 'red'}; font-weight: bold;">
                    ${scenario.pnlFormatted}
                </td>
            </tr>
        `).join('');
    }

    /**
     * Update averaging strategy display
     * Consolidates duplicate implementations from lines 2188 and 2495
     * @param {Object} strategy - Averaging strategy data
     * @param {string} elementPrefix - Prefix for element IDs
     */
    function updateAveragingStrategy(strategy, elementPrefix = '') {
        if (!strategy) return;

        // Update Level 1
        updateDisplay(`${elementPrefix}avg1Trigger`, `₹${strategy.level1.trigger_price.toFixed(2)}`);
        updateDisplay(`${elementPrefix}avg1Lots`, strategy.level1.lots_to_add);
        updateDisplay(`${elementPrefix}avg1Price`, `₹${strategy.level1.new_average.toFixed(2)}`);
        updateDisplay(`${elementPrefix}avg1Target`, `₹${strategy.level1.new_target.toFixed(2)}`);

        // Update Level 2
        updateDisplay(`${elementPrefix}avg2Trigger`, `₹${strategy.level2.trigger_price.toFixed(2)}`);
        updateDisplay(`${elementPrefix}avg2Lots`, strategy.level2.lots_to_add);
        updateDisplay(`${elementPrefix}avg2Price`, `₹${strategy.level2.new_average.toFixed(2)}`);
        updateDisplay(`${elementPrefix}avg2Target`, `₹${strategy.level2.new_target.toFixed(2)}`);

        // Update Level 3
        updateDisplay(`${elementPrefix}avg3Trigger`, `₹${strategy.level3.trigger_price.toFixed(2)}`);
        updateDisplay(`${elementPrefix}avg3Lots`, strategy.level3.lots_to_add);
        updateDisplay(`${elementPrefix}avg3Price`, `₹${strategy.level3.new_average.toFixed(2)}`);
        updateDisplay(`${elementPrefix}avg3StopLoss`, `₹${strategy.level3.stop_loss.toFixed(2)}`);
    }

    /**
     * Build position sizing UI component
     * @param {Object} data - Position data
     * @param {string} elementPrefix - Prefix for element IDs
     * @returns {string} HTML string
     */
    function buildPositionSizingUI(data, elementPrefix = '') {
        return `
            <div class="position-sizing-container">
                <h3 style="color: #1E40AF; margin-bottom: 1rem;">📊 Position Sizing</h3>

                <div class="position-grid">
                    <div class="position-item">
                        <div class="position-label">Margin Per Lot</div>
                        <div class="position-value">${TradingUtils.formatCurrency(data.margin_per_lot)}</div>
                    </div>
                    <div class="position-item">
                        <div class="position-label">Available Margin</div>
                        <div class="position-value">${TradingUtils.formatCurrency(data.available_margin)}</div>
                    </div>
                    <div class="position-item">
                        <div class="position-label">Max Affordable Lots</div>
                        <div class="position-value">${data.max_lots}</div>
                    </div>
                    <div class="position-item">
                        <div class="position-label">Recommended Lots (50%)</div>
                        <div class="position-value">${data.suggested_lots}</div>
                    </div>
                </div>

                <div class="lot-selector" style="margin-top: 1.5rem;">
                    <label style="display: block; margin-bottom: 0.5rem; font-weight: bold;">
                        Select Lot Quantity:
                        <span id="${elementPrefix}lotDisplay" style="color: #2563EB; font-size: 1.2em;">
                            ${data.suggested_lots}
                        </span>
                    </label>
                    <div style="display: flex; align-items: center; gap: 1rem;">
                        <button onclick="PositionSizing.adjustLots(-1, '${elementPrefix}')"
                                class="btn-adjust">−</button>
                        <input type="range"
                               id="${elementPrefix}lotSlider"
                               min="1"
                               max="${data.max_lots}"
                               value="${data.suggested_lots}"
                               oninput="PositionSizing.handleSliderChange(this.value, '${elementPrefix}')"
                               style="flex: 1;">
                        <button onclick="PositionSizing.adjustLots(1, '${elementPrefix}')"
                                class="btn-adjust">+</button>
                    </div>
                </div>

                <div class="position-calculations" style="margin-top: 1.5rem;">
                    <div class="calc-item">
                        <span>Total Quantity:</span>
                        <span id="${elementPrefix}totalQuantity">${(data.suggested_lots * data.lot_size).toLocaleString()}</span>
                    </div>
                    <div class="calc-item">
                        <span>Margin Required:</span>
                        <span id="${elementPrefix}marginRequired">${TradingUtils.formatCurrency(data.suggested_lots * data.margin_per_lot)}</span>
                    </div>
                    <div class="calc-item">
                        <span>Margin Utilization:</span>
                        <span id="${elementPrefix}marginUtilization">
                            ${((data.suggested_lots * data.margin_per_lot / data.available_margin) * 100).toFixed(1)}%
                        </span>
                    </div>
                </div>

                <div class="utilization-bar-container" style="margin-top: 1rem;">
                    <div id="${elementPrefix}utilizationBar" class="utilization-bar"></div>
                </div>
            </div>
        `;
    }

    /**
     * Handle lot adjustment
     * Consolidates adjustLots, adjustFuturesLots, adjustAlgoLots functions
     * @param {number} change - Change amount (-1 or 1)
     * @param {string} elementPrefix - Prefix for element IDs
     */
    function adjustLots(change, elementPrefix = '') {
        const slider = document.getElementById(`${elementPrefix}lotSlider`);
        if (!slider) return;

        const currentValue = parseInt(slider.value);
        const newValue = currentValue + change;

        if (newValue >= parseInt(slider.min) && newValue <= parseInt(slider.max)) {
            slider.value = newValue;
            handleSliderChange(newValue, elementPrefix);
        }
    }

    /**
     * Handle slider change
     * @param {number} value - New slider value
     * @param {string} elementPrefix - Prefix for element IDs
     */
    function handleSliderChange(value, elementPrefix = '') {
        const lots = parseInt(value);
        const display = document.getElementById(`${elementPrefix}lotDisplay`);
        if (display) {
            display.textContent = lots;
        }

        // Update calculations
        updatePositionSize(lots, null, elementPrefix);

        // Store the adjusted value in state
        if (window.TradingState) {
            TradingState.set(`adjustedLots.${elementPrefix}`, lots);
        }
    }

    /**
     * Helper function to update display elements
     * @param {string} elementId - Element ID
     * @param {string} value - Value to display
     */
    function updateDisplay(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
        }
    }

    /**
     * Toggle averaging strategy display
     * Consolidates duplicate implementations from lines 2218 and 2608
     * @param {string} elementPrefix - Prefix for element IDs
     */
    function toggleAveraging(elementPrefix = '') {
        const panel = document.getElementById(`${elementPrefix}averagingPanel`);
        const button = document.getElementById(`${elementPrefix}toggleAveragingBtn`);

        if (panel && button) {
            const isVisible = panel.style.display !== 'none';
            panel.style.display = isVisible ? 'none' : 'block';
            button.textContent = isVisible ? 'Show Averaging Strategy' : 'Hide Averaging Strategy';
        }
    }

    // Public API
    return {
        fetchPositionSizing,
        updatePositionSize,
        calculatePnLScenarios,
        updatePnLTable,
        updateAveragingStrategy,
        buildPositionSizingUI,
        adjustLots,
        handleSliderChange,
        toggleAveraging
    };
})();

// Make available globally
window.PositionSizing = PositionSizing;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PositionSizing;
}