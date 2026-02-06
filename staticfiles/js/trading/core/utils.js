/**
 * Utilities Module
 * Common utility functions for formatting, validation, and calculations
 */

const TradingUtils = (function() {
    'use strict';

    /**
     * Format number in Indian numbering system
     * Extracted from duplicate implementations at lines 4730-4747
     * @param {number} num - Number to format
     * @returns {string} Formatted number string
     */
    function formatIndianNumber(num) {
        if (!num && num !== 0) return '0';

        const absNum = Math.abs(num);
        const sign = num < 0 ? '-' : '';

        // Handle decimal places
        const parts = absNum.toString().split('.');
        let integerPart = parts[0];
        const decimalPart = parts[1] || '';

        // Indian numbering pattern
        let lastThree = integerPart.substring(integerPart.length - 3);
        const otherNumbers = integerPart.substring(0, integerPart.length - 3);

        if (otherNumbers !== '') {
            lastThree = ',' + lastThree;
        }

        const result = otherNumbers.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + lastThree;

        return sign + result + (decimalPart ? '.' + decimalPart : '');
    }

    /**
     * Format currency in Indian Rupees
     * @param {number} amount - Amount to format
     * @param {number} decimals - Number of decimal places (default: 0)
     * @returns {string} Formatted currency string
     */
    function formatCurrency(amount, decimals = 0) {
        const formatted = formatIndianNumber(Math.abs(amount));
        const parts = formatted.split('.');

        if (decimals > 0) {
            const decimalPart = (parts[1] || '').padEnd(decimals, '0').substring(0, decimals);
            return `₹${parts[0]}.${decimalPart}`;
        }

        return `₹${parts[0]}`;
    }

    /**
     * Format percentage
     * @param {number} value - Value to format as percentage
     * @param {number} decimals - Number of decimal places (default: 2)
     * @returns {string} Formatted percentage string
     */
    function formatPercentage(value, decimals = 2) {
        return `${value.toFixed(decimals)}%`;
    }

    /**
     * Parse date from various formats
     * @param {string} dateStr - Date string to parse
     * @returns {Date|null} Parsed date or null
     */
    function parseDate(dateStr) {
        if (!dateStr) return null;

        // Try YYYY-MM-DD format
        if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
            return new Date(dateStr);
        }

        // Try DD-MMM-YYYY format (e.g., 26-DEC-2024)
        if (/^\d{2}-[A-Z]{3}-\d{4}$/.test(dateStr)) {
            const months = {
                'JAN': 0, 'FEB': 1, 'MAR': 2, 'APR': 3, 'MAY': 4, 'JUN': 5,
                'JUL': 6, 'AUG': 7, 'SEP': 8, 'OCT': 9, 'NOV': 10, 'DEC': 11
            };
            const parts = dateStr.split('-');
            const month = months[parts[1]];
            if (month !== undefined) {
                return new Date(parts[2], month, parts[0]);
            }
        }

        // Try parsing as regular date string
        const date = new Date(dateStr);
        return isNaN(date.getTime()) ? null : date;
    }

    /**
     * Format date for display
     * @param {Date|string} date - Date to format
     * @param {string} format - Format type ('short', 'long', 'expiry')
     * @returns {string} Formatted date string
     */
    function formatDate(date, format = 'short') {
        if (typeof date === 'string') {
            date = parseDate(date);
        }
        if (!date || isNaN(date.getTime())) return '';

        switch(format) {
            case 'expiry': // DD-MMM-YYYY format
                const months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
                              'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
                const day = date.getDate().toString().padStart(2, '0');
                const month = months[date.getMonth()];
                const year = date.getFullYear();
                return `${day}-${month}-${year}`;

            case 'long':
                return date.toLocaleDateString('en-IN', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                });

            case 'short':
            default:
                return date.toISOString().split('T')[0]; // YYYY-MM-DD
        }
    }

    /**
     * Calculate days between two dates
     * @param {Date|string} date1 - First date
     * @param {Date|string} date2 - Second date
     * @returns {number} Number of days between dates
     */
    function daysBetween(date1, date2) {
        const d1 = typeof date1 === 'string' ? parseDate(date1) : date1;
        const d2 = typeof date2 === 'string' ? parseDate(date2) : date2;

        if (!d1 || !d2) return 0;

        const diffTime = Math.abs(d2 - d1);
        return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    }

    /**
     * Validate lot input
     * Consolidates duplicate validateLotInput from lines 2231 and 2527
     * @param {HTMLElement} input - Input element to validate
     * @returns {boolean} True if valid
     */
    function validateLotInput(input) {
        const value = parseInt(input.value);
        const min = parseInt(input.min) || 1;
        const max = parseInt(input.max) || 999;

        if (isNaN(value) || value < min) {
            input.value = min;
            return false;
        }

        if (value > max) {
            input.value = max;
            return false;
        }

        return true;
    }

    /**
     * Debounce function execution
     * @param {Function} func - Function to debounce
     * @param {number} wait - Wait time in milliseconds
     * @returns {Function} Debounced function
     */
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * Throttle function execution
     * @param {Function} func - Function to throttle
     * @param {number} limit - Time limit in milliseconds
     * @returns {Function} Throttled function
     */
    function throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }

    /**
     * Calculate percentage change
     * @param {number} oldValue - Original value
     * @param {number} newValue - New value
     * @returns {number} Percentage change
     */
    function calculatePercentageChange(oldValue, newValue) {
        if (oldValue === 0) return newValue === 0 ? 0 : 100;
        return ((newValue - oldValue) / Math.abs(oldValue)) * 100;
    }

    /**
     * Calculate risk-reward ratio
     * @param {number} entry - Entry price
     * @param {number} stopLoss - Stop loss price
     * @param {number} target - Target price
     * @returns {string} Risk-reward ratio
     */
    function calculateRiskReward(entry, stopLoss, target) {
        const risk = Math.abs(entry - stopLoss);
        const reward = Math.abs(target - entry);

        if (risk === 0) return 'N/A';

        const ratio = reward / risk;
        return `1:${ratio.toFixed(2)}`;
    }

    /**
     * Show error message in UI
     * @param {string} message - Error message to display
     * @param {string} containerId - Container element ID
     */
    function showError(message, containerId = null) {
        console.error(message);

        if (containerId) {
            const container = document.getElementById(containerId);
            if (container) {
                container.innerHTML = `
                    <div class="error-message" style="padding: 10px; background: #fee; border: 1px solid #fcc; color: #c00; border-radius: 4px; margin: 10px 0;">
                        ❌ ${message}
                    </div>
                `;
            }
        } else {
            alert(`Error: ${message}`);
        }
    }

    /**
     * Show success message in UI
     * @param {string} message - Success message to display
     * @param {string} containerId - Container element ID
     */
    function showSuccess(message, containerId = null) {
        console.log(message);

        if (containerId) {
            const container = document.getElementById(containerId);
            if (container) {
                container.innerHTML = `
                    <div class="success-message" style="padding: 10px; background: #efe; border: 1px solid #cfc; color: #060; border-radius: 4px; margin: 10px 0;">
                        ✅ ${message}
                    </div>
                `;
            }
        }
    }

    /**
     * Copy text to clipboard
     * @param {string} text - Text to copy
     * @returns {Promise<boolean>} Success status
     */
    async function copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (err) {
            console.error('Failed to copy:', err);
            return false;
        }
    }

    /**
     * Generate unique ID
     * @returns {string} Unique identifier
     */
    function generateId() {
        return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Sleep/delay function
     * @param {number} ms - Milliseconds to sleep
     * @returns {Promise} Promise that resolves after delay
     */
    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Public API
    return {
        formatIndianNumber,
        formatCurrency,
        formatPercentage,
        parseDate,
        formatDate,
        daysBetween,
        validateLotInput,
        debounce,
        throttle,
        calculatePercentageChange,
        calculateRiskReward,
        showError,
        showSuccess,
        copyToClipboard,
        generateId,
        sleep
    };
})();

// Make available globally
window.TradingUtils = TradingUtils;

// For backward compatibility, also expose formatIndianNumber directly
window.formatIndianNumber = TradingUtils.formatIndianNumber;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TradingUtils;
}