/**
 * API Client Module
 * Centralized API communication layer for the trading application
 * Eliminates duplicate getCookie functions and standardizes all API calls
 */

const ApiClient = (function() {
    'use strict';

    // Single implementation of getCookie (was duplicated in lines 558 and 2014)
    function getCookie(name) {
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

    // Get CSRF token (retrieve fresh each time in case it changes)
    function getCSRFToken() {
        return getCookie('csrftoken');
    }

    // For backward compatibility
    const csrftoken = getCSRFToken();

    // Standardized POST request
    async function post(url, data = {}, options = {}) {
        try {
            // Get fresh CSRF token for each request
            const token = getCSRFToken();

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': token,
                    ...options.headers
                },
                body: JSON.stringify(data)
            });

            // Check if response is JSON
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                // Non-JSON response - likely a login redirect, CSRF error, or error page
                console.error('[ApiClient] Non-JSON response received:', contentType, 'Status:', response.status);

                // Get the response text once
                const text = await response.text();

                // Check for CSRF error (403)
                if (response.status === 403) {
                    if (text.includes('CSRF')) {
                        console.error('[ApiClient] CSRF error - token may be invalid or missing');
                        return { success: false, error: 'Security token expired. Please refresh the page.', csrf_error: true };
                    }
                    return { success: false, error: 'Access forbidden. Please refresh the page.', auth_required: true };
                }

                // Check for redirect
                if (response.status === 302 || response.redirected) {
                    return { success: false, error: 'Session expired. Please refresh the page.', auth_required: true };
                }

                // Check if it's HTML (login page redirect)
                if (text.includes('<!DOCTYPE') || text.includes('<html')) {
                    if (text.includes('CSRF')) {
                        return { success: false, error: 'Security token expired. Please refresh the page.', csrf_error: true };
                    }
                    return { success: false, error: 'Session expired. Please refresh the page.', auth_required: true };
                }
                return { success: false, error: 'Unexpected response from server' };
            }

            const result = await response.json();

            console.log('[ApiClient] POST response:', {
                url,
                success: result.success,
                auth_required: result.auth_required,
                authenticated: result.authenticated,
                hasError: !!result.error
            });

            // Handle authentication errors consistently
            // Check both auth_required (backend format) and authenticated===false (legacy format)
            // Only treat as auth error if explicitly marked, not just missing the field
            if ((result.auth_required === true || result.authenticated === false) && options.onAuthError) {
                console.log('[ApiClient] Triggering auth error handler');
                options.onAuthError(result);
                return null;
            }

            return result;
        } catch (error) {
            console.error('API POST Error:', error);
            if (options.onError) {
                options.onError(error);
            }
            throw error;
        }
    }

    // Standardized GET request
    async function get(url, options = {}) {
        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': csrftoken,
                    ...options.headers
                }
            });

            const result = await response.json();

            // Handle authentication errors consistently
            // Check both auth_required (backend format) and authenticated===false (legacy format)
            // Only treat as auth error if explicitly marked, not just missing the field
            if ((result.auth_required === true || result.authenticated === false) && options.onAuthError) {
                options.onAuthError(result);
                return null;
            }

            return result;
        } catch (error) {
            console.error('API GET Error:', error);
            if (options.onError) {
                options.onError(error);
            }
            throw error;
        }
    }

    // Handle authentication errors (Breeze/Neo session)
    function handleAuthError(data, requestType) {
        // Use the centralized BrokerAuth module
        if (window.BrokerAuth) {
            return window.BrokerAuth.handleAuthError(data, requestType);
        }

        // Fallback to basic handling
        // Check both auth_required (backend format) and authenticated===false (legacy format)
        // Only treat as auth error if explicitly marked, not just missing the field
        if (data.auth_required === true || data.authenticated === false) {
            console.error('Authentication failed:', data.message || data.error);

            // Show error message
            const errorElement = document.getElementById(`${requestType}Error`);
            if (errorElement) {
                errorElement.style.display = 'block';
                errorElement.innerHTML = `<span style="color: red;">❌ ${data.message || data.error || 'Please login to your broker first'}</span>`;
            }

            return true;
        }
        return false;
    }

    // Retry pending request after authentication
    function retryPendingRequest() {
        if (!window.TradingState?.pendingRequest) return;

        const request = window.TradingState.pendingRequest;
        window.TradingState.pendingRequest = null;

        switch(request.type) {
            case 'futures':
                if (window.runFuturesAlgorithm) {
                    window.runFuturesAlgorithm();
                }
                break;
            case 'strangle':
                if (window.runNiftyStrangle) {
                    window.runNiftyStrangle();
                }
                break;
            case 'verify':
                if (window.verifyFutureTrade) {
                    const btn = document.getElementById('btnVerify');
                    if (btn) window.verifyFutureTrade(btn);
                }
                break;
        }
    }

    // Trading-specific API endpoints
    const endpoints = {
        // Algorithm endpoints
        futures: '/trading/trigger/futures/',
        strangle: '/trading/trigger/strangle/',
        verify: '/trading/trigger/verify/',  // Verify future trade

        // Order endpoints
        placeFuturesOrder: '/trading/api/place-futures-order/',
        executeStrangle: '/trading/trigger/execute-strangle/',
        placeFutureOrder: '/trading/api/place-futures-order/',  // For verify trade execution

        // Data endpoints
        getContracts: '/trading/trigger/get-contracts/',
        startTrendlyneFetch: '/trading/trigger/start-trendlyne-fetch/',
        streamTrendlyneLogs: (sessionId) => `/trading/trigger/trendlyne-logs/${sessionId}/`,
        getSuggestion: (id) => `/trading/api/suggestions/${id}/`,
        listSuggestions: '/trading/api/suggestions/',
        updateSuggestion: '/trading/api/suggestions/update/',

        // Calculation endpoints
        calculatePosition: '/trading/api/calculate-position/',
        calculatePnl: '/trading/api/calculate-pnl/',
        getMargins: '/trading/api/get-margins/',
        getLotSize: (symbol) => `/trading/api/get-lot-size/?trading_symbol=${symbol}`,
        getContractDetails: (symbol, expiry) => `/trading/api/get-contract-details/?symbol=${symbol}&expiry=${expiry}`,

        // Auth endpoints
        updateBreezeSession: '/trading/trigger/update-breeze-session/',
        updateNeoSession: '/trading/trigger/update-neo-session/'
    };

    // Public API
    return {
        getCookie,
        csrftoken,
        post,
        get,
        handleAuthError,
        retryPendingRequest,
        endpoints
    };
})();

// Make available globally for backward compatibility during migration
window.ApiClient = ApiClient;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ApiClient;
}