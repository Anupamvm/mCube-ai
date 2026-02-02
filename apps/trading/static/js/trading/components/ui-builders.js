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
     * Show a loading overlay
     * @param {Object} config - Overlay configuration
     * @param {string} config.title - Title text
     * @param {string} config.message - Message text
     */
    function showLoadingOverlay(config) {
        // Remove existing overlay if any
        hideLoadingOverlay();

        const overlay = document.createElement('div');
        overlay.id = 'loadingOverlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 10001;
        `;

        overlay.innerHTML = `
            <div style="
                background: white;
                padding: 30px 40px;
                border-radius: 12px;
                text-align: center;
                max-width: 400px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            ">
                <div style="
                    width: 50px;
                    height: 50px;
                    border: 4px solid #e5e7eb;
                    border-top-color: #2563eb;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 20px;
                "></div>
                <h3 style="margin: 0 0 10px; color: #1f2937; font-size: 1.25rem;">${config.title || 'Loading...'}</h3>
                <p style="margin: 0; color: #6b7280; font-size: 0.9rem;">${config.message || 'Please wait...'}</p>
            </div>
        `;

        // Add keyframes for spinner animation if not already present
        if (!document.getElementById('loadingOverlayStyles')) {
            const style = document.createElement('style');
            style.id = 'loadingOverlayStyles';
            style.textContent = `
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';
    }

    /**
     * Hide the loading overlay
     */
    function hideLoadingOverlay() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.remove();
            document.body.style.overflow = '';
        }
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

    /**
     * Build a horizontal accordion item
     * Clean, modern design with step numbers and status indicators
     * @param {Object} options - Accordion configuration
     * @param {string} options.id - Unique identifier
     * @param {number} options.step - Step number (1, 2, 3...)
     * @param {string} options.title - Section title
     * @param {string} options.summary - Summary text shown in header
     * @param {string} options.icon - Icon emoji (optional, shown after step number)
     * @param {boolean} options.expanded - Whether section starts expanded
     * @param {string} options.content - HTML content of the section
     * @param {string} options.status - Status: 'pass', 'fail', 'warning', 'info', or ''
     * @param {string} options.statusText - Custom status text (optional)
     * @returns {string} HTML string
     */
    function buildAccordionItem(options) {
        const {
            id,
            step = null,
            title,
            summary = '',
            icon = '',
            expanded = false,
            content = '',
            status = '',
            statusText = ''
        } = options;

        const expandedClass = expanded ? 'expanded' : '';
        const statusClass = status ? `status-${status}` : '';
        const contentClass = expanded ? 'expanded' : '';

        // Determine status badge text
        const badgeText = statusText || (status === 'pass' ? 'PASS' : status === 'fail' ? 'FAIL' : status === 'warning' ? 'WARNING' : '');

        return `
            <div class="accordion-item ${expandedClass} ${statusClass}" data-section="${id}">
                <div class="accordion-header" onclick="UIBuilders.toggleSection('${id}')">
                    ${step !== null ? `<span class="accordion-step">${step}</span>` : ''}
                    ${icon ? `<span class="accordion-icon">${icon}</span>` : ''}
                    <div class="accordion-title-group">
                        <h4 class="accordion-title">${title}</h4>
                        ${summary ? `<span class="accordion-summary">${summary}</span>` : ''}
                    </div>
                    ${status ? `<span class="accordion-status status-${status}">${badgeText}</span>` : ''}
                    <span class="accordion-toggle">▼</span>
                </div>
                <div class="accordion-content ${contentClass}">
                    <div class="accordion-content-inner">
                        ${content}
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Build a container for multiple accordion items
     * @param {Array} items - Array of accordion options objects
     * @returns {string} HTML string
     */
    function buildAccordionContainer(items) {
        return `
            <div class="accordion-container">
                ${items.map((item, index) => buildAccordionItem({
                    ...item,
                    step: item.step !== undefined ? item.step : index + 1
                })).join('')}
            </div>
        `;
    }

    /**
     * Build a collapsible section component (legacy support + improved design)
     * Used for organizing content into expandable/collapsible groups
     * @param {Object} options - Section configuration
     * @param {string} options.id - Unique section identifier
     * @param {string} options.title - Section title
     * @param {string} options.summary - Summary text shown in collapsed state
     * @param {string} options.icon - Icon emoji or HTML
     * @param {boolean} options.expanded - Whether section starts expanded
     * @param {string} options.content - HTML content of the section
     * @param {string} options.statusBadge - Optional status badge ('status-pass', 'status-fail', 'status-warning', 'status-info')
     * @param {string} options.statusText - Text for the status badge
     * @param {number} options.step - Optional step number
     * @returns {string} HTML string
     */
    function buildCollapsibleSection(options) {
        const {
            id,
            title,
            summary = '',
            icon = '',
            expanded = false,
            content = '',
            statusBadge = '',
            statusText = '',
            step = null
        } = options;

        const expandedClass = expanded ? 'expanded' : '';
        const contentClass = expanded ? 'expanded' : 'collapsed';

        // Determine status class from statusBadge
        const statusClass = statusBadge ? statusBadge.replace('status-', '') : '';
        const itemStatusClass = statusClass ? `status-${statusClass}` : '';

        return `
            <div class="collapsible-section ${expandedClass} ${itemStatusClass}" data-section="${id}">
                <div class="collapsible-header" onclick="UIBuilders.toggleSection('${id}')">
                    <div class="header-left">
                        ${step !== null ? `<span class="accordion-step">${step}</span>` : ''}
                        ${icon ? `<span class="section-icon">${icon}</span>` : ''}
                        <div style="display: flex; flex-direction: column; gap: 2px; min-width: 0;">
                            <h3 class="section-title">${title}</h3>
                            ${summary ? `<span class="section-summary" style="display: block;">${summary}</span>` : ''}
                        </div>
                    </div>
                    <div class="header-right">
                        ${statusBadge ? `<span class="status-badge ${statusBadge}">${statusText}</span>` : ''}
                        <span class="toggle-icon">▼</span>
                    </div>
                </div>
                <div class="collapsible-content ${contentClass}">
                    <div style="padding: 20px;">
                        ${content}
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Toggle a collapsible section's expanded state
     * Works for both accordion-item and collapsible-section
     * @param {string} sectionId - The section ID to toggle
     */
    function toggleSection(sectionId) {
        const section = document.querySelector(`[data-section="${sectionId}"]`);
        if (!section) return;

        // Find content element (works for both accordion and collapsible)
        const content = section.querySelector('.collapsible-content, .accordion-content');
        if (!content) return;

        const isExpanded = section.classList.contains('expanded');

        if (isExpanded) {
            section.classList.remove('expanded');
            content.classList.remove('expanded');
            content.classList.add('collapsed');
        } else {
            section.classList.add('expanded');
            content.classList.remove('collapsed');
            content.classList.add('expanded');
        }
    }

    /**
     * Expand all collapsible sections in a container
     * @param {string} containerId - Optional container ID to limit scope
     */
    function expandAllSections(containerId) {
        const container = containerId ? document.getElementById(containerId) : document;
        if (!container) return;

        container.querySelectorAll('.collapsible-section').forEach(section => {
            section.classList.add('expanded');
            const content = section.querySelector('.collapsible-content');
            if (content) {
                content.classList.remove('collapsed');
                content.classList.add('expanded');
            }
        });
    }

    /**
     * Collapse all collapsible sections in a container
     * @param {string} containerId - Optional container ID to limit scope
     */
    function collapseAllSections(containerId) {
        const container = containerId ? document.getElementById(containerId) : document;
        if (!container) return;

        container.querySelectorAll('.collapsible-section').forEach(section => {
            section.classList.remove('expanded');
            const content = section.querySelector('.collapsible-content');
            if (content) {
                content.classList.remove('expanded');
                content.classList.add('collapsed');
            }
        });
    }

    /**
     * Build a collapsible card for contract/trade results
     * @param {Object} options - Card configuration
     * @param {string} options.id - Unique card identifier
     * @param {string} options.symbol - Symbol name
     * @param {string} options.expiry - Expiry date
     * @param {string} options.verdict - 'PASS', 'FAIL', or 'WARNING'
     * @param {number} options.score - Composite score
     * @param {string} options.direction - 'LONG' or 'SHORT'
     * @param {Array} options.quickStats - Array of {label, value} for quick stats
     * @param {Array} options.sections - Array of collapsible section configs
     * @param {string} options.actionButton - HTML for action button (optional)
     * @returns {string} HTML string
     */
    function buildCollapsibleCard(options) {
        const {
            id,
            symbol,
            expiry,
            verdict = 'FAIL',
            score = 0,
            direction = 'NEUTRAL',
            quickStats = [],
            sections = [],
            actionButton = ''
        } = options;

        // Determine styling based on verdict
        const verdictStyles = {
            'PASS': { color: '#10b981', bg: '#d1fae5', icon: '✅', borderClass: 'verdict-pass' },
            'FAIL': { color: '#ef4444', bg: '#fee2e2', icon: '❌', borderClass: 'verdict-fail' },
            'WARNING': { color: '#f59e0b', bg: '#fef3c7', icon: '⚠️', borderClass: 'verdict-warning' },
            'HIST_FAIL': { color: '#f59e0b', bg: '#fef3c7', icon: '⚠️', borderClass: 'verdict-warning' },
            'HARD REJECT': { color: '#7c3aed', bg: '#ede9fe', icon: '🚫', borderClass: 'verdict-reject' },
            'BLOCKED': { color: '#dc2626', bg: '#fef2f2', icon: '🛑', borderClass: 'verdict-blocked' }
        };
        const style = verdictStyles[verdict] || verdictStyles['FAIL'];

        const directionColor = direction === 'LONG' ? '#10b981' : direction === 'SHORT' ? '#ef4444' : '#6b7280';

        // Build quick stats HTML
        const quickStatsHtml = quickStats.length > 0 ? `
            <div class="quick-stats-row">
                ${quickStats.map(stat => `
                    <div class="quick-stat">
                        <div class="stat-label">${stat.label}</div>
                        <div class="stat-value" ${stat.color ? `style="color: ${stat.color}"` : ''}>${stat.value}</div>
                    </div>
                `).join('')}
            </div>
        ` : '';

        // Build sections HTML
        const sectionsHtml = sections.map(section => buildCollapsibleSection(section)).join('');

        return `
            <div class="collapsible-card ${style.borderClass}" data-card="${id}">
                <div class="card-header" onclick="UIBuilders.toggleCard('${id}')">
                    <div class="header-main">
                        <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                            <h3 style="margin: 0; font-size: 1.5rem; color: #1f2937;">${symbol}</h3>
                            <span style="background: ${style.bg}; color: ${style.color}; padding: 4px 12px; border-radius: 20px; font-size: 0.875rem; font-weight: 600;">
                                ${style.icon} ${verdict === 'HIST_FAIL' ? 'HIST FAIL' : verdict}
                            </span>
                            <span style="color: ${directionColor}; font-weight: 600;">${direction}</span>
                        </div>
                        <div style="color: #6b7280; font-size: 0.875rem; margin-top: 5px;">Expiry: ${expiry}</div>
                        ${quickStatsHtml}
                    </div>
                    <div class="header-score">
                        <div style="font-size: 2rem; font-weight: 700; color: ${style.color};">${score}</div>
                        <div style="color: #6b7280; font-size: 0.875rem;">Score</div>
                    </div>
                </div>
                ${sections.length > 0 || actionButton ? `
                    <div class="card-content" style="display: none;">
                        ${sectionsHtml}
                        ${actionButton ? `<div style="padding: 20px;">${actionButton}</div>` : ''}
                    </div>
                ` : ''}
            </div>
        `;
    }

    /**
     * Toggle a collapsible card's expanded state
     * @param {string} cardId - The card ID to toggle
     */
    function toggleCard(cardId) {
        const card = document.querySelector(`[data-card="${cardId}"]`);
        if (!card) return;

        const content = card.querySelector('.card-content');
        if (!content) return;

        const isVisible = content.style.display !== 'none';
        content.style.display = isVisible ? 'none' : 'block';
    }

    /**
     * Build Enhanced Analysis Score Card
     * Displays the multi-factor scoring breakdown for Futures/Strangle analysis
     * @param {Object} analysis - Enhanced analysis result
     * @param {string} type - 'FUTURES' or 'STRANGLE'
     * @returns {string} HTML string
     */
    function buildEnhancedScoreCard(analysis, type = 'FUTURES') {
        if (!analysis || !analysis.scores) {
            return '<div class="score-card-empty">No enhanced analysis data available</div>';
        }

        const compositeScore = analysis.composite_score || 0;
        const recommendation = analysis.recommendation || 'UNKNOWN';
        const scores = analysis.scores || {};
        const details = analysis.details || {};

        // Determine score color
        const getScoreColor = (score) => {
            if (score >= 80) return '#10b981';  // Green
            if (score >= 65) return '#3b82f6';  // Blue
            if (score >= 50) return '#f59e0b';  // Yellow
            return '#ef4444';                    // Red
        };

        const scoreColor = getScoreColor(compositeScore);

        // Get weights based on type
        const weights = type === 'STRANGLE' ? {
            'vix_regime': 35,
            'global_markets': 30,
            'market_breadth': 25,
            'news_sentiment': 30,
            'pcr_analysis': 25,
            'oi_patterns': 25,
            'event_proximity': 20,
            'gap_movement': 25,
            'recent_nifty_momentum': 25,
            'fii_dii_flow': 20,
            'technical_structure': 15
        } : {
            'oi_fno': 45,
            'technical_momentum': 35,
            'trend_confirmation': 30,
            'volume_quality': 25,
            'institutional_flow': 25,
            'fundamental_quality': 20,
            'risk_adjustment': 30,
            'news_sentiment': 25,
            'analyst_consensus': 20,
            'research_reports': 15,
            'investor_calls': 10,
            'momentum_acceleration': 20
        };

        // Build score bars
        const scoreBarsHtml = Object.entries(scores).map(([key, value]) => {
            const maxScore = weights[key] || 25;
            const percentage = Math.min(100, (value / maxScore) * 100);
            const barColor = percentage >= 70 ? '#10b981' : percentage >= 50 ? '#f59e0b' : '#ef4444';
            const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

            return `
                <div class="score-bar-row" style="margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                        <span style="font-size: 0.8rem; color: #4b5563;">${label}</span>
                        <span style="font-size: 0.8rem; font-weight: 600; color: ${barColor};">${value}/${maxScore}</span>
                    </div>
                    <div style="background: #e5e7eb; border-radius: 4px; height: 8px; overflow: hidden;">
                        <div style="background: ${barColor}; width: ${percentage}%; height: 100%; border-radius: 4px; transition: width 0.3s;"></div>
                    </div>
                </div>
            `;
        }).join('');

        // Build hard reject status if available
        let hardRejectHtml = '';
        if (analysis.hard_reject) {
            hardRejectHtml = `
                <div style="background: #fee2e2; border: 1px solid #fca5a5; border-radius: 8px; padding: 12px; margin-bottom: 16px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 1.2rem;">🚫</span>
                        <span style="color: #dc2626; font-weight: 600;">HARD REJECT</span>
                    </div>
                    <div style="color: #991b1b; margin-top: 8px; font-size: 0.875rem;">${analysis.reject_reason || 'Entry blocked by hard filter'}</div>
                </div>
            `;
        }

        // Build delta adjustments for strangle
        let deltaAdjustmentsHtml = '';
        if (type === 'STRANGLE' && analysis.delta_adjustments) {
            const da = analysis.delta_adjustments;
            deltaAdjustmentsHtml = `
                <div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 12px; margin-top: 16px;">
                    <div style="font-weight: 600; color: #166534; margin-bottom: 8px;">📐 Delta Adjustments</div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 0.875rem;">
                        <div>
                            <span style="color: #6b7280;">Call Multiplier:</span>
                            <span style="font-weight: 600; color: ${da.call_multiplier > 1 ? '#dc2626' : '#166534'};">${da.call_multiplier?.toFixed(2) || '1.00'}x</span>
                        </div>
                        <div>
                            <span style="color: #6b7280;">Put Multiplier:</span>
                            <span style="font-weight: 600; color: ${da.put_multiplier > 1 ? '#dc2626' : '#166534'};">${da.put_multiplier?.toFixed(2) || '1.00'}x</span>
                        </div>
                    </div>
                    ${da.is_asymmetric ? '<div style="color: #15803d; font-size: 0.75rem; margin-top: 8px;">⚡ Asymmetric strike adjustment applied</div>' : ''}
                </div>
            `;
        }

        // Build entry bias for strangle
        let entryBiasHtml = '';
        if (type === 'STRANGLE' && analysis.entry_bias) {
            const biasColors = {
                'SYMMETRIC': '#6b7280',
                'WIDEN_CALL': '#dc2626',
                'WIDEN_PUT': '#2563eb'
            };
            entryBiasHtml = `
                <div style="display: inline-block; background: ${biasColors[analysis.entry_bias] || '#6b7280'}15; color: ${biasColors[analysis.entry_bias] || '#6b7280'}; padding: 4px 12px; border-radius: 16px; font-size: 0.8rem; font-weight: 600; margin-top: 8px;">
                    Entry Bias: ${analysis.entry_bias}
                </div>
            `;
        }

        return `
            <div class="enhanced-score-card" style="background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; margin-bottom: 20px;">
                <!-- Header with Composite Score -->
                <div style="background: linear-gradient(135deg, ${scoreColor}15, ${scoreColor}05); padding: 20px; border-bottom: 1px solid #e5e7eb;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <div style="font-size: 0.875rem; color: #6b7280; margin-bottom: 4px;">Enhanced ${type === 'STRANGLE' ? 'Strangle' : 'Futures'} Analysis</div>
                            <div style="font-size: 1.5rem; font-weight: 700; color: #1f2937;">
                                <span style="color: ${scoreColor};">${recommendation}</span>
                            </div>
                            ${entryBiasHtml}
                        </div>
                        <div style="text-align: center;">
                            <div style="font-size: 3rem; font-weight: 800; color: ${scoreColor}; line-height: 1;">${compositeScore}</div>
                            <div style="font-size: 0.875rem; color: #6b7280;">/100</div>
                        </div>
                    </div>
                </div>

                <!-- Body with Score Breakdown -->
                <div style="padding: 20px;">
                    ${hardRejectHtml}

                    <div style="font-weight: 600; color: #1f2937; margin-bottom: 12px; font-size: 0.95rem;">
                        📊 Component Scores (${type === 'STRANGLE' ? '11' : '12'}-Factor Analysis)
                    </div>

                    <div style="max-height: 350px; overflow-y: auto; padding-right: 8px;">
                        ${scoreBarsHtml}
                    </div>

                    ${deltaAdjustmentsHtml}
                </div>
            </div>
        `;
    }

    /**
     * Build Enhanced Analysis Summary (compact version for lists)
     * @param {Object} analysis - Enhanced analysis result
     * @returns {string} HTML string
     */
    function buildEnhancedScoreBadge(analysis) {
        if (!analysis) return '';

        const score = analysis.composite_score || 0;
        const recommendation = analysis.recommendation || '';

        const getScoreColor = (s) => {
            if (s >= 80) return '#10b981';
            if (s >= 65) return '#3b82f6';
            if (s >= 50) return '#f59e0b';
            return '#ef4444';
        };

        const color = getScoreColor(score);

        return `
            <div class="enhanced-score-badge" style="display: inline-flex; align-items: center; gap: 8px; background: ${color}15; padding: 6px 12px; border-radius: 20px; border: 1px solid ${color}30;">
                <span style="font-size: 1.1rem; font-weight: 700; color: ${color};">${score}</span>
                <span style="font-size: 0.75rem; color: ${color}; font-weight: 500;">${recommendation}</span>
            </div>
        `;
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
        buildAccordionItem,
        buildAccordionContainer,
        buildCollapsibleSection,
        buildCollapsibleCard,
        buildEnhancedScoreCard,
        buildEnhancedScoreBadge,
        showModal,
        closeModal,
        switchTab,
        toggleSection,
        toggleCard,
        expandAllSections,
        collapseAllSections,
        showNotification,
        showLoadingOverlay,
        hideLoadingOverlay
    };
})();

// Make available globally
window.UIBuilders = UIBuilders;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UIBuilders;
}