/**
 * Trading Triggers Application
 * Main application file that initializes and coordinates all modules
 */

const TradingApp = (function() {
    'use strict';

    // Application state
    let isInitialized = false;

    /**
     * Initialize the application
     */
    function init() {
        if (isInitialized) {
            console.log('Trading app already initialized');
            return;
        }

        console.log('Initializing Trading Application...');

        // Migrate existing window variables to state
        if (window.TradingState) {
            TradingState.migrateWindowVariables();
        }

        // Initialize sidebar navigation
        initSidebar();

        // Initialize tab handling
        initTabs();

        // Setup event listeners
        setupEventListeners();

        // Initialize feature modules
        initFeatures();

        // Load initial data
        loadInitialData();

        isInitialized = true;
        console.log('Trading Application initialized successfully');
    }

    /**
     * Initialize sidebar navigation
     */
    function initSidebar() {
        // Handle sidebar navigation clicks
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', function(e) {
                e.preventDefault();

                // Update active state
                document.querySelectorAll('.nav-item').forEach(nav => {
                    nav.classList.remove('active');
                });
                this.classList.add('active');

                // Switch tab content
                const targetTab = this.getAttribute('href').substring(1);
                switchTab(targetTab);

                // Update URL hash
                window.location.hash = targetTab;

                // Track active tab in state
                if (window.TradingState) {
                    TradingState.setActiveTab(targetTab);
                }
            });
        });

        // Handle sidebar toggle
        const toggleButton = document.querySelector('.sidebar-toggle');
        if (toggleButton) {
            toggleButton.addEventListener('click', function() {
                const sidebar = document.querySelector('.trading-sidebar');
                sidebar.classList.toggle('collapsed');

                // Save preference
                localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
            });
        }

        // Restore sidebar state
        const sidebarCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        if (sidebarCollapsed) {
            document.querySelector('.trading-sidebar')?.classList.add('collapsed');
        }

        // Handle mobile menu toggle
        const mobileToggle = document.querySelector('.mobile-menu-toggle');
        if (mobileToggle) {
            mobileToggle.addEventListener('click', function() {
                const sidebar = document.querySelector('.trading-sidebar');
                sidebar.classList.toggle('mobile-open');
            });
        }
    }

    /**
     * Initialize tab handling
     */
    function initTabs() {
        // Handle initial hash
        const initialHash = window.location.hash.substring(1) || 'futures';
        switchTab(initialHash);

        // Handle browser back/forward
        window.addEventListener('hashchange', function() {
            const tab = window.location.hash.substring(1) || 'futures';
            switchTab(tab);
        });
    }

    /**
     * Switch to a specific tab
     * @param {string} tabId - Tab identifier
     */
    function switchTab(tabId) {
        console.log('Switching to tab:', tabId);

        // Hide all tab contents
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });

        // Show selected tab content
        const selectedContent = document.getElementById(`${tabId}-content`);
        if (selectedContent) {
            selectedContent.classList.add('active');
        }

        // Update nav items
        document.querySelectorAll('.nav-item').forEach(nav => {
            const href = nav.getAttribute('href');
            nav.classList.toggle('active', href === `#${tabId}`);
        });

        // Update state
        if (window.TradingState) {
            TradingState.setActiveTab(tabId);
        }

        // Trigger tab-specific initialization if needed
        initTabContent(tabId);
    }

    /**
     * Initialize tab-specific content
     * @param {string} tabId - Tab identifier
     */
    function initTabContent(tabId) {
        switch(tabId) {
            case 'futures':
                if (window.FuturesAlgorithm) {
                    FuturesAlgorithm.init();
                }
                break;
            case 'strangle':
                if (window.NiftyStrangle) {
                    NiftyStrangle.init();
                }
                break;
            case 'verify':
                if (window.TradeVerification) {
                    TradeVerification.init();
                }
                break;
        }
    }

    /**
     * Setup global event listeners
     */
    function setupEventListeners() {
        // Handle escape key to close modals
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                closeAllModals();
            }
        });

        // Handle state changes
        if (window.TradingState) {
            TradingState.subscribe(handleStateChange);
        }

        // Handle window resize for responsive adjustments
        let resizeTimeout;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(handleResize, 250);
        });

        // Handle form submissions
        document.addEventListener('submit', function(e) {
            if (e.target.classList.contains('ajax-form')) {
                e.preventDefault();
                handleAjaxForm(e.target);
            }
        });
    }

    /**
     * Handle state changes
     * @param {CustomEvent} event - State change event
     */
    function handleStateChange(event) {
        const { key, value } = event.detail;
        console.log('State changed:', key, value);

        // Update UI based on state changes
        switch(key) {
            case 'isLoading.futures':
            case 'isLoading.strangle':
            case 'isLoading.verify':
                updateLoadingState(key.split('.')[1], value);
                break;
        }
    }

    /**
     * Update loading state in UI
     * @param {string} feature - Feature name
     * @param {boolean} isLoading - Loading state
     */
    function updateLoadingState(feature, isLoading) {
        const button = document.getElementById(`${feature}Button`);
        const spinner = document.getElementById(`${feature}Loading`);

        if (button) {
            button.disabled = isLoading;
            if (isLoading) {
                button.dataset.originalText = button.textContent;
                button.innerHTML = '<span class="spinner"></span> Processing...';
            } else if (button.dataset.originalText) {
                button.textContent = button.dataset.originalText;
            }
        }

        if (spinner) {
            spinner.style.display = isLoading ? 'block' : 'none';
        }
    }

    /**
     * Initialize feature modules
     */
    function initFeatures() {
        // Features will be initialized when their tabs are accessed
        console.log('Feature modules ready for initialization');
    }

    /**
     * Load initial data
     */
    async function loadInitialData() {
        try {
            // Don't load margins on page init - they will be loaded when needed
            // This prevents unnecessary API calls that might trigger auth modals

            // Load any other initial data
            console.log('Initial data loaded');
        } catch (error) {
            console.error('Error loading initial data:', error);
        }
    }

    /**
     * Load margin data
     */
    async function loadMargins() {
        try {
            const response = await ApiClient.get(ApiClient.endpoints.getMargins);
            if (response && response.success) {
                TradingState?.cache.setMargins(response.data);
            }
        } catch (error) {
            console.error('Error loading margins:', error);
        }
    }

    /**
     * Handle responsive adjustments
     */
    function handleResize() {
        const isMobile = window.innerWidth < 768;
        const sidebar = document.querySelector('.trading-sidebar');

        if (sidebar) {
            if (isMobile) {
                sidebar.classList.remove('collapsed');
                sidebar.classList.remove('mobile-open');
            }
        }
    }

    /**
     * Close all open modals
     */
    function closeAllModals() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.style.display = 'none';
        });
        document.body.style.overflow = '';
    }

    /**
     * Handle AJAX form submission
     * @param {HTMLFormElement} form - Form element
     */
    async function handleAjaxForm(form) {
        const formData = new FormData(form);
        const data = Object.fromEntries(formData);

        try {
            const response = await ApiClient.post(form.action, data);

            if (response.success) {
                UIBuilders.showNotification({
                    type: 'success',
                    message: response.message || 'Operation successful',
                    icon: '✅'
                });

                // Reset form if needed
                if (form.dataset.resetOnSuccess === 'true') {
                    form.reset();
                }
            } else {
                throw new Error(response.error || 'Operation failed');
            }
        } catch (error) {
            UIBuilders.showNotification({
                type: 'error',
                message: error.message,
                icon: '❌'
            });
        }
    }

    /**
     * Global function mappings for backward compatibility
     */
    function setupGlobalFunctions() {
        // Map old global functions to new module functions
        window.getCookie = ApiClient.getCookie;
        window.formatIndianNumber = TradingUtils.formatIndianNumber;
        window.showError = TradingUtils.showError;
        window.showSuccess = TradingUtils.showSuccess;

        // Position sizing functions
        window.fetchPositionSizing = PositionSizing.fetchPositionSizing;
        window.updatePositionSize = PositionSizing.updatePositionSize;
        window.updatePnLTable = PositionSizing.updatePnLTable;
        window.updateAveragingStrategy = PositionSizing.updateAveragingStrategy;
        window.toggleAveraging = PositionSizing.toggleAveraging;
        window.adjustLots = PositionSizing.adjustLots;
    }

    // Public API
    const api = {
        init,
        switchTab,
        loadMargins,
        closeAllModals
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            setupGlobalFunctions();
            init();
        });
    } else {
        setupGlobalFunctions();
        init();
    }

    return api;
})();

// Make available globally
window.TradingApp = TradingApp;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TradingApp;
}