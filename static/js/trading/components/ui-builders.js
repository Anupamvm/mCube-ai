/**
 * UI Builders Module
 * Reusable UI component builders for consistent interface elements
 * Consolidates repeated HTML patterns and display logic
 */

const UIBuilders = (function() {
    'use strict';

    /**
     * Build a result grid component
     * Used in 15+ places for displaying key-value pairs
     * @param {Array} items - Array of {label, value, className} objects
     * @returns {string} HTML string
     */
    function buildResultGrid(items) {
        return `
            <div class="result-grid">
                ${items.map(item => `
                    <div class="result-item ${item.className || ''}">
                        <div class="result-item-label">${item.label}</div>
                        <div class="result-item-value">${item.value}</div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    /**
     * Build a trigger card component
     * Standardizes the 3 main trigger cards
     * @param {Object} config - Card configuration
     * @returns {string} HTML string
     */
    function buildTriggerCard(config) {
        return `
            <div class="trigger-card" id="${config.id}Card">
                <div class="trigger-header">
                    <span class="trigger-icon">${config.icon}</span>
                    <h2 class="trigger-title">${config.title}</h2>
                </div>
                <p class="trigger-description">${config.description}</p>
                ${config.content ? `<div class="trigger-content">${config.content}</div>` : ''}
                <button class="btn btn-primary"
                        onclick="${config.action}"
                        id="${config.buttonId}">
                    ${config.buttonText}
                </button>
                <div class="loading-spinner" id="${config.id}Loading" style="display: none;">
                    <div>⏳ ${config.loadingText || 'Processing...'}</div>
                </div>
                ${config.error ? `
                    <div class="error-message" id="${config.id}Error" style="display: none;"></div>
                ` : ''}
            </div>
        `;
    }

    /**
     * Build a loading spinner
     * @param {string} text - Loading text
     * @returns {string} HTML string
     */
    function buildLoadingSpinner(text = 'Loading...') {
        return `
            <div class="loading-spinner">
                <div class="spinner"></div>
                <div>⏳ ${text}</div>
            </div>
        `;
    }

    /**
     * Build an error message component
     * @param {string} message - Error message
     * @returns {string} HTML string
     */
    function buildErrorMessage(message) {
        return `
            <div class="error-message">
                <span class="error-icon">❌</span>
                <span class="error-text">${message}</span>
            </div>
        `;
    }

    /**
     * Build a success message component
     * @param {string} message - Success message
     * @returns {string} HTML string
     */
    function buildSuccessMessage(message) {
        return `
            <div class="success-message">
                <span class="success-icon">✅</span>
                <span class="success-text">${message}</span>
            </div>
        `;
    }

    /**
     * Build execution log component
     * @param {Array} logs - Array of log entries
     * @returns {string} HTML string
     */
    function buildExecutionLog(logs) {
        if (!logs || logs.length === 0) {
            return '<div class="execution-log-empty">No execution logs available</div>';
        }

        return `
            <div class="execution-log">
                <h4>📋 Execution Log</h4>
                <div class="log-entries">
                    ${logs.map(log => `
                        <div class="log-entry ${log.type}">
                            <span class="log-time">${log.timestamp || new Date().toLocaleTimeString()}</span>
                            <span class="log-message">${log.message}</span>
                            ${log.details ? `<div class="log-details">${log.details}</div>` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    /**
     * Build margin card component
     * @param {Object} marginData - Margin information
     * @returns {string} HTML string
     */
    function buildMarginCard(marginData) {
        const utilizationPercent = (marginData.used / marginData.available) * 100;
        const utilizationColor = utilizationPercent > 90 ? '#ef4444' :
                               utilizationPercent > 70 ? '#f59e0b' : '#10b981';

        return `
            <div class="margin-card">
                <h4>💰 Margin Details</h4>
                <div class="margin-grid">
                    <div class="margin-item">
                        <span class="margin-label">Available:</span>
                        <span class="margin-value">${TradingUtils.formatCurrency(marginData.available)}</span>
                    </div>
                    <div class="margin-item">
                        <span class="margin-label">Used:</span>
                        <span class="margin-value">${TradingUtils.formatCurrency(marginData.used)}</span>
                    </div>
                    <div class="margin-item">
                        <span class="margin-label">Required:</span>
                        <span class="margin-value">${TradingUtils.formatCurrency(marginData.required)}</span>
                    </div>
                    <div class="margin-item">
                        <span class="margin-label">Utilization:</span>
                        <span class="margin-value">${utilizationPercent.toFixed(1)}%</span>
                    </div>
                </div>
                <div class="utilization-bar-container">
                    <div class="utilization-bar"
                         style="width: ${Math.min(utilizationPercent, 100)}%; background: ${utilizationColor};">
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Build contract details card
     * @param {Object} contract - Contract information
     * @returns {string} HTML string
     */
    function buildContractCard(contract) {
        return `
            <div class="contract-card">
                <div class="contract-header">
                    <h4>${contract.symbol}</h4>
                    <span class="contract-type ${contract.type}">${contract.type}</span>
                </div>
                <div class="contract-details">
                    ${buildResultGrid([
                        { label: 'Expiry', value: TradingUtils.formatDate(contract.expiry, 'expiry') },
                        { label: 'Lot Size', value: contract.lotSize },
                        { label: 'Price', value: TradingUtils.formatCurrency(contract.price, 2) },
                        { label: 'Volume', value: (contract.volume || 0).toLocaleString() },
                        { label: 'OI', value: (contract.openInterest || 0).toLocaleString() },
                        { label: 'Token', value: contract.token || 'N/A' }
                    ])}
                </div>
            </div>
        `;
    }

    /**
     * Build action button group
     * @param {Array} buttons - Array of button configurations
     * @returns {string} HTML string
     */
    function buildActionButtons(buttons) {
        return `
            <div class="action-buttons">
                ${buttons.map(btn => `
                    <button class="btn ${btn.className || 'btn-primary'}"
                            onclick="${btn.onclick}"
                            ${btn.disabled ? 'disabled' : ''}
                            ${btn.id ? `id="${btn.id}"` : ''}>
                        ${btn.icon ? `<span class="btn-icon">${btn.icon}</span>` : ''}
                        <span class="btn-text">${btn.text}</span>
                    </button>
                `).join('')}
            </div>
        `;
    }

    /**
     * Build a modal dialog
     * @param {Object} config - Modal configuration
     * @returns {string} HTML string
     */
    function buildModal(config) {
        return `
            <div class="modal" id="${config.id}" style="display: none;">
                <div class="modal-overlay" onclick="${config.closeOnOverlay ? `UIBuilders.closeModal('${config.id}')` : ''}"></div>
                <div class="modal-content">
                    ${config.title ? `
                        <div class="modal-header">
                            <h3 class="modal-title">${config.title}</h3>
                            ${config.closable !== false ? `
                                <button class="modal-close" onclick="UIBuilders.closeModal('${config.id}')">×</button>
                            ` : ''}
                        </div>
                    ` : ''}
                    <div class="modal-body">
                        ${config.content}
                    </div>
                    ${config.footer ? `
                        <div class="modal-footer">
                            ${config.footer}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    /**
     * Build a tabbed interface
     * @param {Object} config - Tab configuration
     * @returns {string} HTML string
     */
    function buildTabs(config) {
        return `
            <div class="tabs-container" id="${config.id}">
                <div class="tabs-header">
                    ${config.tabs.map((tab, index) => `
                        <button class="tab-button ${index === 0 ? 'active' : ''}"
                                onclick="UIBuilders.switchTab('${config.id}', '${tab.id}')"
                                data-tab="${tab.id}">
                            ${tab.icon ? `<span class="tab-icon">${tab.icon}</span>` : ''}
                            <span class="tab-label">${tab.label}</span>
                        </button>
                    `).join('')}
                </div>
                <div class="tabs-content">
                    ${config.tabs.map((tab, index) => `
                        <div class="tab-pane ${index === 0 ? 'active' : ''}"
                             id="${tab.id}"
                             style="${index !== 0 ? 'display: none;' : ''}">
                            ${tab.content}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    /**
     * Build a progress indicator
     * @param {Object} config - Progress configuration
     * @returns {string} HTML string
     */
    function buildProgress(config) {
        const percentage = (config.current / config.total) * 100;
        return `
            <div class="progress-container">
                ${config.label ? `<div class="progress-label">${config.label}</div>` : ''}
                <div class="progress-bar">
                    <div class="progress-fill"
                         style="width: ${percentage}%; background: ${config.color || '#2563eb'};">
                    </div>
                </div>
                <div class="progress-text">${config.current} / ${config.total}</div>
            </div>
        `;
    }

    /**
     * Build a stat card
     * @param {Object} stat - Statistic configuration
     * @returns {string} HTML string
     */
    function buildStatCard(stat) {
        return `
            <div class="stat-card ${stat.trend ? `trend-${stat.trend}` : ''}">
                <div class="stat-header">
                    ${stat.icon ? `<span class="stat-icon">${stat.icon}</span>` : ''}
                    <span class="stat-label">${stat.label}</span>
                </div>
                <div class="stat-value">${stat.value}</div>
                ${stat.change ? `
                    <div class="stat-change ${stat.change > 0 ? 'positive' : 'negative'}">
                        ${stat.change > 0 ? '↑' : '↓'} ${Math.abs(stat.change)}%
                    </div>
                ` : ''}
                ${stat.subtitle ? `<div class="stat-subtitle">${stat.subtitle}</div>` : ''}
            </div>
        `;
    }

    // Modal management functions
    function showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
        }
    }

    function closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }
    }

    // Tab management functions
    function switchTab(containerId, tabId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        // Update tab buttons
        container.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
        });

        // Update tab panes
        container.querySelectorAll('.tab-pane').forEach(pane => {
            pane.style.display = pane.id === tabId ? 'block' : 'none';
            pane.classList.toggle('active', pane.id === tabId);
        });
    }

    /**
     * Show a notification
     * @param {Object} config - Notification configuration
     * @param {string} config.type - Type: success, error, warning, info
     * @param {string} config.message - Message to display
     * @param {string} config.icon - Icon to display
     * @param {number} config.timeout - Auto-close timeout in ms (false for persistent, default 5000 for success/info, persistent for error/warning)
     */
    function showNotification(config) {
        const notification = document.createElement('div');
        notification.className = `notification ${config.type || 'info'}`;

        // Error and warning notifications are persistent by default
        const isPersistent = config.timeout === false || config.type === 'error' || config.type === 'warning';

        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            border-radius: 8px;
            background: white;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            z-index: 10000;
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 320px;
            max-width: 500px;
            animation: slideIn 0.3s ease-out;
        `;

        // Set background color based on type
        const colors = {
            success: '#d1fae5',
            error: '#fee2e2',
            warning: '#fef3c7',
            info: '#dbeafe'
        };
        notification.style.background = colors[config.type] || colors.info;

        // Convert newlines to <br> tags for proper multi-line display
        const formattedMessage = config.message.replace(/\n/g, '<br>');

        notification.innerHTML = `
            ${config.icon ? `<span style="font-size: 1.5rem; flex-shrink: 0; align-self: flex-start;">${config.icon}</span>` : ''}
            <span style="flex: 1; color: #1f2937; word-wrap: break-word; line-height: 1.5; white-space: pre-wrap;">${formattedMessage}</span>
            <button onclick="this.parentElement.remove()"
                    style="background: none; border: none; font-size: 1.5rem; cursor: pointer; padding: 0 5px; color: #6b7280; flex-shrink: 0; line-height: 1; align-self: flex-start;">×</button>
        `;

        // Add to body
        document.body.appendChild(notification);

        // Auto-remove after timeout (unless persistent)
        if (!isPersistent) {
            const timeout = config.timeout || 5000;
            setTimeout(() => {
                notification.style.animation = 'slideOut 0.3s ease-out';
                setTimeout(() => notification.remove(), 300);
            }, timeout);
        }
    }

    // Public API
    return {
        buildResultGrid,
        buildTriggerCard,
        buildLoadingSpinner,
        buildErrorMessage,
        buildSuccessMessage,
        buildExecutionLog,
        buildMarginCard,
        buildContractCard,
        buildActionButtons,
        buildModal,
        buildTabs,
        buildProgress,
        buildStatCard,
        showModal,
        closeModal,
        switchTab,
        showNotification
    };
})();

// Make available globally
window.UIBuilders = UIBuilders;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UIBuilders;
}