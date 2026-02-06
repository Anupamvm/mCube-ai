/**
 * Breeze Authentication Handler
 *
 * Centralized JavaScript utilities for handling Breeze authentication errors
 * across all AJAX calls in the application.
 *
 * Usage:
 *   // Option 1: Use the wrapper function for fetch
 *   const data = await breezeFetch('/trading/api/get-positions/?broker=breeze');
 *
 *   // Option 2: Check response manually
 *   const response = await fetch('/api/endpoint');
 *   const data = await response.json();
 *   if (handleBreezeAuthError(data)) return; // Returns true if auth error handled
 *
 *   // Option 3: Show login prompt in a container
 *   showBreezeLoginPrompt(containerElement, 'Breeze session expired');
 */

/**
 * Check if response indicates Breeze auth is required and handle it.
 *
 * @param {Object} data - JSON response data
 * @param {Object} options - Options for handling
 * @param {boolean} options.redirect - If true, redirect to login page (default: false)
 * @param {HTMLElement} options.container - Container to show login prompt in
 * @param {string} options.broker - Broker name for display ('Breeze' or 'Neo')
 * @returns {boolean} - True if auth error was detected and handled
 */
function handleBreezeAuthError(data, options = {}) {
    if (!data || !data.auth_required) {
        return false;
    }

    const {
        redirect = false,
        container = null,
        broker = 'Breeze'
    } = options;

    console.warn(`${broker} authentication required:`, data.error);

    if (redirect) {
        // Redirect to login page
        window.location.href = data.login_url || '/brokers/breeze/login/';
        return true;
    }

    if (container) {
        // Show login prompt in container
        showBreezeLoginPrompt(container, data.error, data.login_url, broker);
        return true;
    }

    // Default: Show alert and return true
    if (confirm(`${broker} session expired. Would you like to re-authenticate now?`)) {
        window.location.href = data.login_url || '/brokers/breeze/login/';
    }

    return true;
}

/**
 * Show a login prompt in the specified container.
 *
 * @param {HTMLElement|string} container - Container element or selector
 * @param {string} message - Error message to display
 * @param {string} loginUrl - URL to redirect for login
 * @param {string} broker - Broker name for display
 */
function showBreezeLoginPrompt(container, message, loginUrl, broker = 'Breeze') {
    const el = typeof container === 'string' ? document.querySelector(container) : container;

    if (!el) {
        console.error('Container not found for login prompt');
        return;
    }

    // Add current page as next parameter
    const nextUrl = encodeURIComponent(window.location.pathname + window.location.search);
    const fullLoginUrl = loginUrl ? `${loginUrl}?next=${nextUrl}` : `/brokers/breeze/login/?next=${nextUrl}`;

    el.innerHTML = `
        <div class="breeze-auth-prompt" style="text-align: center; padding: 2rem; background: #fef3cd; border-radius: 8px; margin: 1rem 0;">
            <div style="font-size: 2.5rem; margin-bottom: 1rem;">🔐</div>
            <h3 style="margin: 0 0 0.5rem 0; color: #856404;">${broker} Session Expired</h3>
            <p style="margin: 0 0 1.5rem 0; color: #856404;">${message || 'Please re-authenticate to continue.'}</p>
            <a href="${fullLoginUrl}" class="btn" style="
                display: inline-block;
                padding: 0.75rem 1.5rem;
                background: #2563eb;
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-weight: 600;
                transition: background 0.2s;
            " onmouseover="this.style.background='#1d4ed8'" onmouseout="this.style.background='#2563eb'">
                Login to ${broker}
            </a>
        </div>
    `;
}

/**
 * Wrapper for fetch that automatically handles Breeze auth errors.
 *
 * @param {string} url - URL to fetch
 * @param {Object} options - Fetch options
 * @param {Object} authOptions - Auth handling options (passed to handleBreezeAuthError)
 * @returns {Promise<Object>} - JSON response data
 * @throws {Error} - If request fails or auth error not handled
 */
async function breezeFetch(url, options = {}, authOptions = {}) {
    try {
        const response = await fetch(url, options);
        const data = await response.json();

        if (data.auth_required) {
            const handled = handleBreezeAuthError(data, authOptions);
            if (handled) {
                // Throw special error so caller knows auth was required
                const error = new Error(data.error || 'Authentication required');
                error.authRequired = true;
                error.loginUrl = data.login_url;
                throw error;
            }
        }

        return data;
    } catch (error) {
        if (error.authRequired) {
            throw error;
        }
        console.error('Fetch error:', error);
        throw error;
    }
}

/**
 * Check Breeze session status.
 *
 * @returns {Promise<Object>} - Session status {valid, message, auto_login_available, login_url}
 */
async function checkBreezeSession() {
    try {
        const response = await fetch('/brokers/api/breeze-session-status/');
        return await response.json();
    } catch (error) {
        console.error('Error checking Breeze session:', error);
        return {
            valid: false,
            message: 'Could not check session status',
            auto_login_available: false,
            login_url: '/brokers/breeze/login/'
        };
    }
}

/**
 * Initialize Breeze auth handling for all forms with data-breeze-auth attribute.
 *
 * Usage in HTML:
 *   <form data-breeze-auth data-error-container="#error-div">
 *     ...
 *   </form>
 */
function initBreezeAuthForms() {
    document.querySelectorAll('form[data-breeze-auth]').forEach(form => {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            const errorContainer = form.dataset.errorContainer ?
                document.querySelector(form.dataset.errorContainer) : null;

            try {
                const formData = new FormData(form);
                const response = await fetch(form.action, {
                    method: form.method || 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                const data = await response.json();

                if (handleBreezeAuthError(data, { container: errorContainer })) {
                    return;
                }

                // Handle success/error normally
                if (data.success) {
                    if (form.dataset.successRedirect) {
                        window.location.href = form.dataset.successRedirect;
                    } else if (form.dataset.successCallback) {
                        window[form.dataset.successCallback](data);
                    }
                } else {
                    if (errorContainer) {
                        errorContainer.innerHTML = `<div class="error-message">${data.error}</div>`;
                    } else {
                        alert(data.error || 'An error occurred');
                    }
                }
            } catch (error) {
                console.error('Form submission error:', error);
                if (errorContainer) {
                    errorContainer.innerHTML = `<div class="error-message">${error.message}</div>`;
                }
            }
        });
    });
}

// Auto-initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBreezeAuthForms);
} else {
    initBreezeAuthForms();
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        handleBreezeAuthError,
        showBreezeLoginPrompt,
        breezeFetch,
        checkBreezeSession,
        initBreezeAuthForms
    };
}
