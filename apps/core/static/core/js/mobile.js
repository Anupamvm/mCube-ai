/**
 * mobile.js — mCube Mobile Enhancement Layer
 *
 * Responsibilities:
 *  1. Bottom navigation bar (inject + active state)
 *  2. Slide-out drawer with full nav tree
 *  3. Analytics filter collapse toggle
 *  4. Table row expand/collapse for secondary columns
 *  5. Tooltip disable on touch devices
 *  6. Resize / orientation guard
 *
 * Guards: every DOM mutation is behind window.innerWidth < 768.
 * Zero impact on desktop (≥768px).
 */
(function () {
    'use strict';

    var MOBILE_BP = 768;   // px — below this = mobile
    var isTouch = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);

    /* ------------------------------------------------------------------
       NAV TREE DATA
       Built from the existing navbar structure. Kept in JS so we don't
       need a second HTML template.
    ------------------------------------------------------------------ */
    var navSections = [
        {
            label: 'Trade',
            links: [
                { icon: '🎯', text: 'Execute Trade', href: '/trading/triggers/', cls: 'highlight' },
                { icon: '📋', text: 'Open Positions', href: '/trading/view-trades/' },
                { icon: '⏳', text: 'Pending Approvals', href: '/trading/suggestions/pending/' },
                { icon: '📜', text: 'Trade History', href: '/trading/trade-history/' },
                { icon: '📈', text: 'Performance', href: '/trading/performance/' },
                { icon: '🗂️', text: 'System Positions', href: '/positions/system/' },
            ]
        },
        {
            label: 'Market',
            links: [
                { icon: '📈', text: 'NIFTY Quote', href: '/brokers/nifty-quote/' },
                { icon: '📊', text: 'Option Chain', href: '/brokers/option-chain/' },
                { icon: '📰', text: 'Market News', href: '/trading/news/' },
            ]
        },
        {
            label: 'Historical Analysis',
            links: [
                { icon: '📊', text: 'Performance Overview', href: '/analytics/historical-analysis/' },
                { icon: '💵', text: 'P&L Summary', href: '/analytics/historical-analysis/#pnlSummarySection' },
                { icon: '🎯', text: 'Symbol Performance', href: '/analytics/historical-analysis/#symbolsSection' },
                { icon: '💰', text: 'Tax Calculator', href: '/analytics/historical-analysis/#taxSection' },
                { icon: '📤', text: 'Upload Trade Data', href: '/brokers/csv-upload/' },
            ]
        },
        {
            label: 'Trading Insights',
            links: [
                { icon: '🧠', text: 'Smart Intelligence', href: '/analytics/insights/' },
                { icon: '💡', text: 'Parameter Suggestions', href: '/analytics/insights/suggestions/' },
                { icon: '🔮', text: 'Hindsight Tracker', href: '/analytics/hindsight/' },
                { icon: '⚙️', text: 'Learning Engine', href: '/analytics/learning/' },
            ]
        },
        {
            label: 'Settings',
            links: [
                { icon: '⚙', text: 'System Configuration', href: '/system/config/' },
                { icon: '📚', text: 'Docs', href: '/docs/' },
                { icon: '🚪', text: 'Logout', href: '/accounts/logout/' },
            ]
        }
    ];

    /* ------------------------------------------------------------------
       BOTTOM NAV CONFIG
    ------------------------------------------------------------------ */
    var bottomNavItems = [
        { icon: '🏠', label: 'Home', href: '/', match: /^\/$/ },
        { icon: '💼', label: 'Trade', href: '/trading/triggers/', match: /^\/trading/ },
        { icon: '📋', label: 'Pos', href: '/positions/system/', match: /^\/positions/ },
        { icon: '📊', label: 'Analytics', href: '/analytics/', match: /^\/analytics/ },
        { icon: '☰', label: 'More', href: '#', action: 'openDrawer' }
    ];

    /* ------------------------------------------------------------------
       UTILITIES
    ------------------------------------------------------------------ */
    function isMobile() {
        return window.innerWidth < MOBILE_BP;
    }

    function el(tag, attrs, children) {
        var node = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                if (k === 'class') node.className = attrs[k];
                else if (k === 'text') node.textContent = attrs[k];
                else node.setAttribute(k, attrs[k]);
            });
        }
        if (children) {
            children.forEach(function (c) {
                if (c) node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
            });
        }
        return node;
    }

    /* ------------------------------------------------------------------
       1. BOTTOM NAVIGATION BAR
    ------------------------------------------------------------------ */
    function buildBottomNav() {
        if (!isMobile()) return;
        if (document.querySelector('.mc-bottom-nav')) return; // already exists

        var nav = el('nav', { class: 'mc-bottom-nav', role: 'navigation', 'aria-label': 'Mobile navigation' });
        var path = window.location.pathname;

        bottomNavItems.forEach(function (item) {
            var isActive = item.match && item.match.test(path);
            var btn = el('button', {
                class: 'mc-bottom-nav-item' + (isActive ? ' active' : ''),
                type: 'button',
                'aria-label': item.label
            }, [
                el('span', { class: 'mc-bottom-nav-icon', 'aria-hidden': 'true' }, [item.icon]),
                el('span', { class: 'mc-bottom-nav-label' }, [item.label])
            ]);

            if (item.action === 'openDrawer') {
                btn.addEventListener('click', function (e) {
                    e.preventDefault();
                    openDrawer();
                });
            } else {
                btn.addEventListener('click', function () {
                    window.location.href = item.href;
                });
            }

            nav.appendChild(btn);
        });

        document.body.appendChild(nav);
    }

    /* ------------------------------------------------------------------
       2. SLIDE-OUT DRAWER
    ------------------------------------------------------------------ */
    var drawerEl = null;
    var backdropEl = null;

    function buildDrawer() {
        if (document.querySelector('.mc-nav-drawer')) return;

        // Backdrop
        backdropEl = el('div', { class: 'mc-drawer-backdrop' });
        backdropEl.addEventListener('click', closeDrawer);
        document.body.appendChild(backdropEl);

        // Drawer shell
        drawerEl = el('div', {
            class: 'mc-nav-drawer',
            role: 'dialog',
            'aria-modal': 'true',
            'aria-label': 'Navigation menu'
        });

        // Header
        var header = el('div', { class: 'mc-drawer-header' }, [
            el('h2', { class: 'mc-drawer-title' }, ['mCube']),
            (function () {
                var closeBtn = el('button', {
                    class: 'mc-drawer-close',
                    type: 'button',
                    'aria-label': 'Close menu'
                }, ['×']);
                closeBtn.addEventListener('click', closeDrawer);
                return closeBtn;
            })()
        ]);
        drawerEl.appendChild(header);

        // Nav content
        var navEl = el('nav', { class: 'mc-drawer-nav' });

        navSections.forEach(function (section) {
            navEl.appendChild(el('div', { class: 'mc-drawer-section-label' }, [section.label]));
            section.links.forEach(function (link) {
                var a = el('a', {
                    class: 'mc-drawer-link' + (link.cls ? ' ' + link.cls : ''),
                    href: link.href
                }, [
                    el('span', { 'aria-hidden': 'true' }, [link.icon]),
                    el('span', {}, [link.text])
                ]);
                navEl.appendChild(a);
            });
            navEl.appendChild(el('div', { class: 'mc-drawer-divider' }));
        });

        drawerEl.appendChild(navEl);
        document.body.appendChild(drawerEl);

        // Keyboard: Esc closes
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && drawerEl && drawerEl.classList.contains('open')) {
                closeDrawer();
            }
        });
    }

    function openDrawer() {
        if (!drawerEl) buildDrawer();
        drawerEl.classList.add('open');
        backdropEl.classList.add('open');
        document.body.style.overflow = 'hidden';
        // Focus management
        var firstLink = drawerEl.querySelector('a, button');
        if (firstLink) firstLink.focus();
    }

    function closeDrawer() {
        if (!drawerEl) return;
        drawerEl.classList.remove('open');
        backdropEl.classList.remove('open');
        document.body.style.overflow = '';
    }

    /* ------------------------------------------------------------------
       3. ANALYTICS FILTER TOGGLE
    ------------------------------------------------------------------ */
    function initAnalyticsFilterToggle() {
        if (!isMobile()) return;
        var filtersRow = document.getElementById('analytics-filters');
        if (!filtersRow) return;
        if (document.querySelector('.mc-filter-toggle')) return;

        var toggle = el('button', {
            class: 'mc-filter-toggle',
            type: 'button'
        }, [
            el('span', {}, ['Filters']),
            el('span', { class: 'mc-filter-arrow' }, ['▼'])
        ]);

        var isOpen = false;
        filtersRow.classList.add('mc-filters-hidden');

        toggle.addEventListener('click', function () {
            isOpen = !isOpen;
            toggle.classList.toggle('open', isOpen);
            filtersRow.classList.toggle('mc-filters-hidden', !isOpen);
        });

        filtersRow.parentNode.insertBefore(toggle, filtersRow);
    }

    /* ------------------------------------------------------------------
       4. TABLE ROW EXPAND / COLLAPSE
         Adds "Show more / Show less" to .mobile-cards rows when secondary
         columns (td.mc-secondary) are present.
    ------------------------------------------------------------------ */
    function initTableExpanders() {
        if (!isMobile()) return;
        var tables = document.querySelectorAll('table.mobile-cards');

        tables.forEach(function (table) {
            var rows = table.querySelectorAll('tbody tr');
            rows.forEach(function (row) {
                var secondary = row.querySelectorAll('td.mc-secondary');
                if (secondary.length === 0) return;

                var toggleBtn = el('button', {
                    class: 'mc-row-toggle',
                    type: 'button',
                    'aria-expanded': 'false'
                }, ['Show more ▾']);

                toggleBtn.addEventListener('click', function () {
                    var expanded = row.classList.toggle('mc-expanded');
                    toggleBtn.textContent = expanded ? 'Show less ▴' : 'Show more ▾';
                    toggleBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
                });

                // Append as a fake td to keep table structure valid
                var wrapTd = el('td', { class: 'mc-toggle-cell', colspan: '99' });
                wrapTd.appendChild(toggleBtn);
                // Remove colspan from the card rendering context
                row.appendChild(wrapTd);
                // Style the td to not show a label prefix
                wrapTd.style.cssText = 'display:block; padding: 0 !important; border:none !important;';
                wrapTd.setAttribute('data-label', '');
            });
        });
    }

    /* ------------------------------------------------------------------
       5. TOOLTIP DISABLE ON TOUCH DEVICES
    ------------------------------------------------------------------ */
    function disableTouchTooltips() {
        if (!isTouch) return;
        // Wait for Bootstrap to initialize, then destroy hover tooltips
        var attempts = 0;
        var interval = setInterval(function () {
            attempts++;
            if (attempts > 10) { clearInterval(interval); return; }
            if (typeof window.bootstrap === 'undefined') return;
            clearInterval(interval);
            document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
                var instance = window.bootstrap.Tooltip.getInstance(el);
                if (instance) instance.dispose();
                // Rebind as click-only popovers are skipped for simplicity
                el.removeAttribute('data-bs-toggle');
                el.removeAttribute('data-bs-original-title');
                el.removeAttribute('title');
            });
        }, 200);
    }

    /* ------------------------------------------------------------------
       6. RESIZE / ORIENTATION GUARD
    ------------------------------------------------------------------ */
    var resizeTimer;
    function onResize() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            if (isMobile()) {
                buildBottomNav();
            } else {
                // Remove bottom nav if viewport grows beyond mobile
                var nav = document.querySelector('.mc-bottom-nav');
                if (nav) nav.remove();
                document.body.style.paddingBottom = '';
                closeDrawer();
            }
        }, 200);
    }

    /* ------------------------------------------------------------------
       INIT
    ------------------------------------------------------------------ */
    function init() {
        if (isMobile()) {
            buildBottomNav();
            disableTouchTooltips();
        }

        initAnalyticsFilterToggle();
        initTableExpanders();

        window.addEventListener('resize', onResize);
        window.addEventListener('orientationchange', onResize);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
