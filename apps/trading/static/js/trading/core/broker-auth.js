/**
 * Broker Authentication Module
 * Centralized authentication handling for Breeze and Neo brokers
 * Eliminates duplicate code and provides unified authentication workflow
 */

const BrokerAuth = (function() {
    'use strict';

    // Configuration
    const config = {
        breeze: {
            modalId: 'breezeAuthModal',
            endpoint: '/trading/trigger/update-breeze-session/',
            tokenFieldId: 'breezeSessionToken',
            name: 'ICICI Breeze',
            icon: '🏦',
            helpText: 'Get your session token from the Breeze web platform after logging in.',
            tokenPlaceholder: 'Enter your Breeze session token',
            loginUrl: 'https://api.icicidirect.com/breezeapi/apptoken'
        },
        neo: {
            modalId: 'neoAuthModal',
            endpoint: '/trading/trigger/update-neo-session/',
            tokenFieldId: 'neoSessionToken',
            name: 'Kotak Neo',
            icon: '🏛️',
            helpText: 'Get your session token from the Neo trading platform after logging in.',
            tokenPlaceholder: 'Enter your Neo session token',
            loginUrl: 'https://neoapi.kotaksecurities.com'
        }
    };

    // Current auth state
    let currentBroker = null;
    let pendingRequest = null;

    /**
     * Create authentication modal HTML
     * @param {string} broker - 'breeze' or 'neo'
     * @returns {string} Modal HTML
     */
    function createAuthModal(broker) {
        const cfg = config[broker];
        if (!cfg) return '';

        return `
            <div class="modal" id="${cfg.modalId}" style="display: none;">
                <div class="modal-overlay" onclick="BrokerAuth.closeModal('${broker}')"></div>
                <div class="modal-content" style="max-width: 500px;">
                    <div class="modal-header">
                        <h3 class="modal-title">
                            ${cfg.icon} ${cfg.name} Authentication Required
                        </h3>
                        <button class="modal-close" onclick="BrokerAuth.closeModal('${broker}')">×</button>
                    </div>
                    <div class="modal-body">
                        <div id="${broker}AuthMessage" class="auth-message"></div>

                        <p style="margin-bottom: 15px;">
                            Your ${cfg.name} session has expired. Please enter your Session Token to continue.
                        </p>

                        <div class="form-group">
                            <label for="${cfg.tokenFieldId}" style="display: block; margin-bottom: 5px; font-weight: 500;">
                                Session Token:
                            </label>
                            <input type="text"
                                   id="${cfg.tokenFieldId}"
                                   class="form-control"
                                   placeholder="${cfg.tokenPlaceholder}"
                                   style="width: 100%; padding: 10px; border: 1px solid #e5e7eb; border-radius: 6px;"
                                   onkeypress="if(event.key==='Enter') BrokerAuth.updateSession('${broker}')">
                        </div>

                        <p class="help-text" style="font-size: 0.9em; color: #6b7280; margin-top: 10px;">
                            ℹ️ ${cfg.helpText}
                            ${cfg.loginUrl ? `<br><a href="${cfg.loginUrl}" target="_blank" style="color: #3b82f6; text-decoration: underline;">Click here to login and get your session token →</a>` : ''}
                        </p>

                        <div id="${broker}LoadingIndicator" style="display: none; text-align: center; margin-top: 15px;">
                            <div class="spinner"></div>
                            <span>Authenticating...</span>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-primary"
                                id="${broker}UpdateBtn"
                                onclick="BrokerAuth.updateSession('${broker}')">
                            🔐 Update Session
                        </button>
                        <button class="btn btn-secondary"
                                onclick="BrokerAuth.closeModal('${broker}')">
                            Cancel
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Initialize authentication modals and check for pending requests
     */
    function init() {
        // Check if modals already exist
        if (!document.getElementById(config.breeze.modalId)) {
            // Create container for modals
            const container = document.createElement('div');
            container.id = 'brokerAuthModals';
            container.innerHTML = createAuthModal('breeze') + createAuthModal('neo');
            document.body.appendChild(container);
        }

        console.log('[BrokerAuth] Initialized with Breeze and Neo authentication support');

        // Check for pending requests from previous auth flow
        checkAndRetryPendingRequest();
    }

    /**
     * Check sessionStorage for pending requests and retry after successful auth
     */
    function checkAndRetryPendingRequest() {
        const pendingRequestStr = sessionStorage.getItem('breeze_pending_request');
        if (!pendingRequestStr) return;

        try {
            const storedRequest = JSON.parse(pendingRequestStr);
            console.log('[BrokerAuth] Found pending request from previous session:', storedRequest);

            // Clear the stored request immediately to avoid infinite retries
            sessionStorage.removeItem('breeze_pending_request');

            // Verify the session is now valid before retrying
            fetch('/brokers/breeze/session-status/')
                .then(response => response.json())
                .then(status => {
                    if (status.valid) {
                        console.log('[BrokerAuth] Session now valid - retrying pending request');

                        // Show success notification
                        showNotification(
                            'Authentication Successful',
                            'Breeze session restored. Retrying your previous action...',
                            'success'
                        );

                        // Set the pending request and retry
                        pendingRequest = storedRequest;
                        currentBroker = 'breeze';

                        // Small delay to let the page settle
                        setTimeout(() => {
                            retryPendingRequest();
                        }, 1000);
                    } else {
                        console.log('[BrokerAuth] Session still invalid - not retrying');
                    }
                })
                .catch(err => {
                    console.error('[BrokerAuth] Error checking session status:', err);
                });

        } catch (e) {
            console.error('[BrokerAuth] Error parsing pending request:', e);
            sessionStorage.removeItem('breeze_pending_request');
        }
    }

    /**
     * Show authentication modal or redirect to auto-login page
     * @param {string} broker - 'breeze' or 'neo'
     * @param {Object} request - Optional pending request to retry after auth
     */
    function showAuthModal(broker, request = null) {
        const cfg = config[broker];
        if (!cfg) {
            console.error(`[BrokerAuth] Unknown broker: ${broker}`);
            return;
        }

        currentBroker = broker;
        pendingRequest = request;

        console.log(`[BrokerAuth] Authentication required for ${cfg.name}`);

        // For Breeze, check if auto-login is available and redirect to login page
        if (broker === 'breeze') {
            // Check session status and redirect to auto-login page
            checkAndRedirectToAutoLogin(broker);
            return;
        }

        // For other brokers (Neo), show the manual token entry modal
        showManualTokenModal(broker);
    }

    /**
     * Check Breeze session status and redirect to auto-login page
     * @param {string} broker - 'breeze'
     */
    async function checkAndRedirectToAutoLogin(broker) {
        try {
            const response = await fetch('/brokers/breeze/session-status/');
            const status = await response.json();

            console.log('[BrokerAuth] Session status:', status);

            if (!status.valid) {
                // Session is expired - redirect to login page with current URL as return
                const currentUrl = encodeURIComponent(window.location.pathname + window.location.search);
                const loginUrl = `/brokers/breeze/login/?next=${currentUrl}`;

                console.log(`[BrokerAuth] Session expired - redirecting to: ${loginUrl}`);

                // Show a brief notification before redirect
                showNotification(
                    'Session Expired',
                    'Redirecting to Breeze login page. Please complete auto-login to continue.',
                    'warning'
                );

                // Store pending request info in sessionStorage for retry after login
                if (pendingRequest) {
                    sessionStorage.setItem('breeze_pending_request', JSON.stringify(pendingRequest));
                }

                // Redirect after a brief delay to show the notification
                setTimeout(() => {
                    window.location.href = loginUrl;
                }, 1500);
            }
        } catch (error) {
            console.error('[BrokerAuth] Error checking session status:', error);
            // Fallback to manual token entry modal if API fails
            showManualTokenModal(broker);
        }
    }

    /**
     * Show notification to user
     * @param {string} title - Notification title
     * @param {string} message - Notification message
     * @param {string} type - 'info', 'warning', 'error', 'success'
     */
    function showNotification(title, message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `broker-auth-notification broker-auth-notification-${type}`;
        notification.innerHTML = `
            <div class="broker-auth-notification-content">
                <strong>${title}</strong>
                <p>${message}</p>
            </div>
        `;

        // Style the notification based on type
        const bgColors = {
            'warning': '#fef3cd',
            'error': '#f8d7da',
            'success': '#d4edda',
            'info': '#d1ecf1'
        };
        const borderColors = {
            'warning': '#ffc107',
            'error': '#dc3545',
            'success': '#28a745',
            'info': '#17a2b8'
        };

        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${bgColors[type] || bgColors.info};
            border: 1px solid ${borderColors[type] || borderColors.info};
            border-radius: 8px;
            padding: 16px 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 10000;
            max-width: 400px;
            animation: slideIn 0.3s ease-out;
        `;

        // Add animation keyframes
        if (!document.getElementById('broker-auth-styles')) {
            const style = document.createElement('style');
            style.id = 'broker-auth-styles';
            style.textContent = `
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(notification);

        // Remove after 5 seconds
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }

    /**
     * Show manual token entry modal (for Neo or fallback)
     * @param {string} broker - 'breeze' or 'neo'
     */
    function showManualTokenModal(broker) {
        const cfg = config[broker];
        if (!cfg) return;

        // Clear previous messages
        const messageDiv = document.getElementById(`${broker}AuthMessage`);
        if (messageDiv) {
            messageDiv.innerHTML = '';
        }

        // Reset input field
        const tokenInput = document.getElementById(cfg.tokenFieldId);
        if (tokenInput) {
            tokenInput.value = '';
            tokenInput.focus();
        }

        // Show modal
        const modal = document.getElementById(cfg.modalId);
        if (modal) {
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
        } else {
            // If modal doesn't exist, initialize and try again
            init();
            setTimeout(() => showManualTokenModal(broker), 100);
        }

        console.log(`[BrokerAuth] Showing ${cfg.name} manual token entry modal`);
    }

    /**
     * Close authentication modal
     * @param {string} broker - 'breeze' or 'neo'
     */
    function closeModal(broker) {
        const cfg = config[broker];
        if (!cfg) return;

        const modal = document.getElementById(cfg.modalId);
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }

        // Clear pending request if cancelled
        if (currentBroker === broker) {
            currentBroker = null;
            pendingRequest = null;
        }
    }

    /**
     * Update broker session
     * @param {string} broker - 'breeze' or 'neo'
     */
    async function updateSession(broker) {
        const cfg = config[broker];
        if (!cfg) return;

        const tokenInput = document.getElementById(cfg.tokenFieldId);
        const token = tokenInput ? tokenInput.value.trim() : '';
        const messageDiv = document.getElementById(`${broker}AuthMessage`);
        const updateBtn = document.getElementById(`${broker}UpdateBtn`);
        const loadingDiv = document.getElementById(`${broker}LoadingIndicator`);

        // Validate token
        if (!token) {
            showMessage(messageDiv, 'Please enter a session token', 'error');
            return;
        }

        // Show loading state
        if (updateBtn) {
            updateBtn.disabled = true;
            updateBtn.innerHTML = '⏳ Updating...';
        }
        if (loadingDiv) {
            loadingDiv.style.display = 'block';
        }

        try {
            // Get CSRF token
            const csrftoken = getCookie('csrftoken');

            // Make API call
            const response = await fetch(cfg.endpoint, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    session_token: token
                })
            });

            const result = await response.json();

            if (result.success) {
                showMessage(messageDiv, '✅ Session updated successfully!', 'success');

                // Store session info
                sessionStorage.setItem(`${broker}_authenticated`, 'true');
                sessionStorage.setItem(`${broker}_auth_time`, new Date().toISOString());

                // Close modal after brief delay
                setTimeout(() => {
                    closeModal(broker);

                    // Retry pending request if exists
                    if (pendingRequest && currentBroker === broker) {
                        retryPendingRequest();
                    }
                }, 1000);

            } else {
                showMessage(messageDiv,
                    result.error || `Failed to update ${cfg.name} session`,
                    'error'
                );
            }
        } catch (error) {
            console.error(`[BrokerAuth] Error updating ${broker} session:`, error);
            showMessage(messageDiv,
                `Network error: ${error.message}`,
                'error'
            );
        } finally {
            // Reset button state
            if (updateBtn) {
                updateBtn.disabled = false;
                updateBtn.innerHTML = '🔐 Update Session';
            }
            if (loadingDiv) {
                loadingDiv.style.display = 'none';
            }
        }
    }

    /**
     * Retry pending request after authentication
     */
    function retryPendingRequest() {
        if (!pendingRequest) return;

        const request = pendingRequest;
        pendingRequest = null;

        console.log('[BrokerAuth] Retrying pending request:', request);

        // Retry based on request type
        if (request.callback && typeof request.callback === 'function') {
            request.callback(request.params);
        } else if (request.type) {
            // Handle specific request types
            switch(request.type) {
                case 'futures':
                    if (window.FuturesAlgorithm) {
                        window.FuturesAlgorithm.run();
                    }
                    break;
                case 'strangle':
                    if (window.NiftyStrangle) {
                        window.NiftyStrangle.generate();
                    }
                    break;
                case 'verify':
                    if (window.TradeVerification) {
                        window.TradeVerification.verify();
                    }
                    break;
                default:
                    console.warn('[BrokerAuth] Unknown request type:', request.type);
            }
        }
    }

    /**
     * Check if broker is authenticated
     * @param {string} broker - 'breeze' or 'neo'
     * @returns {boolean} Authentication status
     */
    function isAuthenticated(broker) {
        const authStatus = sessionStorage.getItem(`${broker}_authenticated`);
        const authTime = sessionStorage.getItem(`${broker}_auth_time`);

        if (authStatus === 'true' && authTime) {
            // Check if session is less than 24 hours old
            const authDate = new Date(authTime);
            const now = new Date();
            const hoursDiff = (now - authDate) / (1000 * 60 * 60);

            return hoursDiff < 24;
        }

        return false;
    }

    /**
     * Clear authentication for a broker
     * @param {string} broker - 'breeze' or 'neo'
     */
    function clearAuth(broker) {
        sessionStorage.removeItem(`${broker}_authenticated`);
        sessionStorage.removeItem(`${broker}_auth_time`);
    }

    /**
     * Handle authentication error from API response
     * @param {Object} response - API response
     * @param {string} requestType - Type of request that failed
     * @returns {boolean} True if auth error was handled
     */
    function handleAuthError(response, requestType) {
        console.log('[BrokerAuth] handleAuthError called:', {
            requestType,
            auth_required: response.auth_required,
            authenticated: response.authenticated,
            broker: response.broker,
            hasMessage: !!response.message,
            hasError: !!response.error
        });

        // Check for both auth_required (backend format) and authenticated===false (legacy format)
        // Only treat as auth error if explicitly marked, not just missing the field
        if (response.auth_required === true || response.authenticated === false) {
            // Determine which broker based on error message or request type
            let broker = 'breeze'; // Default to Breeze

            if (response.broker) {
                broker = response.broker.toLowerCase();
            } else if (response.message || response.error) {
                const message = (response.message || response.error).toLowerCase();
                if (message.includes('neo') || message.includes('kotak')) {
                    broker = 'neo';
                }
            }

            console.log(`[BrokerAuth] Authentication required for ${broker} - showing modal`);

            // Show auth modal with pending request
            showAuthModal(broker, {
                type: requestType,
                timestamp: new Date().getTime()
            });

            return true;
        }

        console.log('[BrokerAuth] No authentication required - continuing normally');
        return false;
    }

    /**
     * Show message in modal
     * @param {HTMLElement} messageDiv - Message container
     * @param {string} message - Message text
     * @param {string} type - 'success' or 'error'
     */
    function showMessage(messageDiv, message, type) {
        if (!messageDiv) return;

        const className = type === 'success' ? 'success-message' : 'error-message';
        const icon = type === 'success' ? '✅' : '❌';

        messageDiv.innerHTML = `
            <div class="${className}" style="padding: 10px; margin-bottom: 15px; border-radius: 6px;">
                ${icon} ${message}
            </div>
        `;
    }

    /**
     * Get cookie value
     * @param {string} name - Cookie name
     * @returns {string} Cookie value
     */
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

    // Public API
    return {
        init,
        showAuthModal,
        showManualTokenModal,
        checkAndRedirectToAutoLogin,
        closeModal,
        updateSession,
        isAuthenticated,
        clearAuth,
        handleAuthError,
        retryPendingRequest,
        checkAndRetryPendingRequest,
        showNotification
    };
})();

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', BrokerAuth.init);
} else {
    BrokerAuth.init();
}

// Make available globally
window.BrokerAuth = BrokerAuth;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BrokerAuth;
}