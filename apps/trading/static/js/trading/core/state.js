/**
 * State Manager Module
 * Centralizes all global state variables that were scattered throughout window object
 * Provides a clean interface for state management
 */

const TradingState = (function() {
    'use strict';

    // Private state object
    const state = {
        // Strangle-related state
        currentStrangleData: null,
        currentSuggestionId: null,

        // Position sizing state
        currentPositionData: null,
        lastMarginData: null,
        futuresPositionData: null,

        // Algorithm state
        futuresAlgoSuggestionIds: [],
        futuresAlgoContracts: [],
        algoFuturesData: {}, // Stores data for each algo result by index

        // Contract state
        contractData: null,
        positionData: null,

        // Authentication state
        pendingRequest: null,

        // UI state
        activeTab: 'futures', // 'futures', 'strangle', or 'verify'
        isLoading: {
            futures: false,
            strangle: false,
            verify: false
        },

        // Cache for frequently accessed data
        cache: {
            lotSizes: new Map(),
            contractDetails: new Map(),
            margins: null,
            marginsTimestamp: null
        }
    };

    // State getters
    function get(key) {
        const keys = key.split('.');
        let value = state;
        for (const k of keys) {
            value = value[k];
            if (value === undefined) return null;
        }
        return value;
    }

    // State setters
    function set(key, value) {
        const keys = key.split('.');
        let obj = state;
        for (let i = 0; i < keys.length - 1; i++) {
            if (!obj[keys[i]]) {
                obj[keys[i]] = {};
            }
            obj = obj[keys[i]];
        }
        obj[keys[keys.length - 1]] = value;

        // Trigger state change event for reactive UI updates
        dispatchStateChange(key, value);
    }

    // Clear specific state
    function clear(key) {
        set(key, null);
    }

    // Reset all state
    function reset() {
        Object.keys(state).forEach(key => {
            if (key === 'cache') {
                state.cache.lotSizes.clear();
                state.cache.contractDetails.clear();
                state.cache.margins = null;
                state.cache.marginsTimestamp = null;
            } else if (typeof state[key] === 'object' && state[key] !== null) {
                if (Array.isArray(state[key])) {
                    state[key] = [];
                } else {
                    state[key] = {};
                }
            } else {
                state[key] = null;
            }
        });
    }

    // Cache management
    const cache = {
        setLotSize(symbol, size) {
            state.cache.lotSizes.set(symbol, {
                size,
                timestamp: Date.now()
            });
        },

        getLotSize(symbol) {
            const cached = state.cache.lotSizes.get(symbol);
            // Cache for 5 minutes
            if (cached && (Date.now() - cached.timestamp) < 300000) {
                return cached.size;
            }
            return null;
        },

        setContractDetails(key, details) {
            state.cache.contractDetails.set(key, {
                details,
                timestamp: Date.now()
            });
        },

        getContractDetails(key) {
            const cached = state.cache.contractDetails.get(key);
            // Cache for 10 minutes
            if (cached && (Date.now() - cached.timestamp) < 600000) {
                return cached.details;
            }
            return null;
        },

        setMargins(margins) {
            state.cache.margins = margins;
            state.cache.marginsTimestamp = Date.now();
        },

        getMargins() {
            // Cache margins for 2 minutes
            if (state.cache.margins &&
                state.cache.marginsTimestamp &&
                (Date.now() - state.cache.marginsTimestamp) < 120000) {
                return state.cache.margins;
            }
            return null;
        }
    };

    // Loading state management
    function setLoading(feature, isLoading) {
        state.isLoading[feature] = isLoading;

        // Update UI loading indicators
        const loadingElement = document.getElementById(`${feature}Loading`);
        if (loadingElement) {
            loadingElement.style.display = isLoading ? 'block' : 'none';
        }
    }

    // Tab management
    function setActiveTab(tab) {
        state.activeTab = tab;
        dispatchStateChange('activeTab', tab);
    }

    // Event dispatching for state changes
    function dispatchStateChange(key, value) {
        const event = new CustomEvent('tradingStateChange', {
            detail: { key, value }
        });
        window.dispatchEvent(event);
    }

    // Subscribe to state changes
    function subscribe(callback) {
        window.addEventListener('tradingStateChange', callback);
        return () => window.removeEventListener('tradingStateChange', callback);
    }

    // Algo-specific state management
    function setAlgoData(index, data) {
        state.algoFuturesData[`algo${index}`] = data;
    }

    function getAlgoData(index) {
        return state.algoFuturesData[`algo${index}`] || null;
    }

    // Migrate existing window variables (for backward compatibility)
    function migrateWindowVariables() {
        // Migrate existing window variables if they exist
        if (typeof window.currentStrangleData !== 'undefined') {
            state.currentStrangleData = window.currentStrangleData;
        }
        if (typeof window.currentSuggestionId !== 'undefined') {
            state.currentSuggestionId = window.currentSuggestionId;
        }
        if (typeof window.currentPositionData !== 'undefined') {
            state.currentPositionData = window.currentPositionData;
        }
        if (typeof window.contractData !== 'undefined') {
            state.contractData = window.contractData;
        }
        if (typeof window.positionData !== 'undefined') {
            state.positionData = window.positionData;
        }
        if (typeof window.pendingRequest !== 'undefined') {
            state.pendingRequest = window.pendingRequest;
        }
    }

    // Public API
    return {
        get,
        set,
        clear,
        reset,
        cache,
        setLoading,
        setActiveTab,
        getActiveTab: () => state.activeTab,
        subscribe,
        setAlgoData,
        getAlgoData,
        migrateWindowVariables,

        // Direct state access for migration period
        state: state
    };
})();

// Make available globally
window.TradingState = TradingState;

// Initialize by migrating existing variables
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        TradingState.migrateWindowVariables();
    });
} else {
    TradingState.migrateWindowVariables();
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TradingState;
}