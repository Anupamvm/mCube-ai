/**
 * Shared "Deep Portfolio Analysis" component.
 * Used by both consolidated.html (family-wide, memberIds=null) and
 * member_detail.html (single member, memberIds=[id]).
 *
 * Requires Chart.js to already be loaded on the page, and the DOM
 * skeleton from investments/_portfolio_analysis.html to be present.
 */
(function (global) {
    'use strict';

    const API = '/investments/api';

    const TYPE_LABELS = {
        MUTUAL_FUND: 'Mutual Fund', EQUITY: 'Equity', FD: 'Fixed Deposit', RD: 'Recurring Deposit',
        SGB: 'Sovereign Gold Bond', BOND: 'Bond', PPF: 'PPF', EPF: 'EPF / PF', NPS: 'NPS',
        REAL_ESTATE: 'Real Estate', PHYSICAL_GOLD: 'Physical Gold', CRYPTO: 'Crypto',
        CASH: 'Cash', SAVINGS: 'Savings', OTHER: 'Other',
    };

    // dataviz skill's validated categorical palette (light mode) — fixed hue order, never cycled.
    const PALETTE = ['#2a78d6', '#1baf7a', '#eda100', '#008300', '#4a3aa7', '#e34948', '#e87ba4', '#eb6834'];
    const OTHER_COLOR = '#94a3b8';
    const MAX_SLICES = 8; // 7 named + "Other"

    // Standard AMFI/SEBI fund categorisation, used for the manual category picker.
    const AMFI_CATEGORIES = {
        'Equity': [
            'Large Cap Fund', 'Large & Mid Cap Fund', 'Mid Cap Fund', 'Small Cap Fund',
            'Multi Cap Fund', 'Flexi Cap Fund', 'Focused Fund', 'Value Fund', 'Contra Fund',
            'Dividend Yield Fund', 'Sectoral / Thematic Fund', 'ELSS (Tax Saving)', 'Index Fund / ETF',
        ],
        'Hybrid': [
            'Aggressive Hybrid Fund', 'Conservative Hybrid Fund', 'Balanced Advantage Fund',
            'Multi Asset Allocation Fund', 'Equity Savings Fund', 'Arbitrage Fund',
        ],
        'Debt': [
            'Overnight Fund', 'Liquid Fund', 'Ultra Short Duration Fund', 'Low Duration Fund',
            'Money Market Fund', 'Short Duration Fund', 'Medium Duration Fund',
            'Medium to Long Duration Fund', 'Long Duration Fund', 'Dynamic Bond Fund',
            'Corporate Bond Fund', 'Credit Risk Fund', 'Banking and PSU Fund', 'Gilt Fund', 'Floater Fund',
        ],
        'Other': ['Fund of Funds', 'Solution Oriented Fund', 'Other / Custom'],
    };

    function fmt(n) { n = parseFloat(n) || 0; return '₹' + Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 0 }); }
    function pct(n) { return (parseFloat(n) || 0).toFixed(2) + '%'; }
    function signed(n) { return parseFloat(n) >= 0 ? '+' : ''; }
    function gainClass(n) { return parseFloat(n) >= 0 ? 'gain-pos' : 'gain-neg'; }
    function escapeHtml(str) {
        return String(str == null ? '' : str).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }
    function uniqueSorted(arr) { return [...new Set(arr.filter(v => v))].sort(); }

    function paToast(msg, type) {
        const container = el('pa-toasts');
        if (!container) { if (typeof toast === 'function') toast(msg, type); return; }
        const d = document.createElement('div');
        d.className = `alert alert-${type === 'error' ? 'danger' : 'success'} shadow mb-2 py-2 px-3`;
        d.style.cssText = 'font-size:.85rem;min-width:220px';
        d.textContent = msg;
        container.appendChild(d);
        setTimeout(() => d.remove(), 5000);
    }

    function mcapBucket(cr) {
        if (cr === null || cr === undefined) return '';
        if (cr > 20000) return 'Large Cap';
        if (cr >= 5000) return 'Mid Cap';
        return 'Small Cap';
    }

    function el(id) { return document.getElementById(id); }

    function PortfolioAnalysis(opts) {
        this.memberIds = opts.memberIds || null; // null = all of the user's members
        this.showMemberFilter = !!opts.showMemberFilter;
        this.csrfToken = opts.csrfToken || '';
        this.allProducts = [];
        this.colorMaps = {}; // dimension -> { key: color }
        this.charts = {};    // canvas id -> Chart.js instance
        this.state = {
            search: '', members: new Set(), types: new Set(), categories: new Set(),
            amcs: new Set(), sectors: new Set(), mcaps: new Set(),
            pnl: 'all', hideZero: false, sort: 'current_desc', group: 'none',
        };
        this.showInactive = false;
    }

    PortfolioAnalysis.prototype._memberIdsCsv = function () {
        return this.memberIds && this.memberIds.length ? this.memberIds.join(',') : '';
    };

    PortfolioAnalysis.prototype._productsUrl = function () {
        const params = new URLSearchParams();
        params.set('is_active', this.showInactive ? 'false' : 'true');
        if (this.memberIds && this.memberIds.length === 1) params.set('member_id', this.memberIds[0]);
        return `${API}/products/?${params.toString()}`;
    };

    PortfolioAnalysis.prototype._analyticsUrl = function (path) {
        const csv = this._memberIdsCsv();
        return csv ? `${API}/analytics/${path}/?member_ids=${csv}` : `${API}/analytics/${path}/`;
    };

    PortfolioAnalysis.prototype.init = async function () {
        this._wireStaticControls();
        if (this.showMemberFilter) {
            await this._loadMembers();
        } else {
            const grp = el('pa-group-member');
            if (grp) grp.style.display = 'none';
        }
        await this._loadProducts();
        this._buildColorMaps();
        this._buildFilterChips();
        this.applyFilters();
        this._loadMemberScopedAnalytics();
    };

    PortfolioAnalysis.prototype._wireStaticControls = function () {
        const search = el('pa-search');
        if (search) search.addEventListener('input', e => { this.state.search = e.target.value; this.applyFilters(); });
        const sort = el('pa-sort');
        if (sort) sort.addEventListener('change', e => { this.state.sort = e.target.value; this.applyFilters(); });
        const group = el('pa-group');
        if (group) group.addEventListener('change', e => { this.state.group = e.target.value; this.applyFilters(); });
        const hideZero = el('pa-hide-zero');
        if (hideZero) hideZero.addEventListener('change', e => { this.state.hideZero = e.target.checked; this.applyFilters(); });
        const reset = el('pa-reset-filters');
        if (reset) reset.addEventListener('click', e => { e.preventDefault(); this.resetFilters(); });
        const showInactive = el('pa-show-inactive');
        if (showInactive) showInactive.addEventListener('change', async e => {
            this.showInactive = e.target.checked;
            await this.refresh();
        });
        document.querySelectorAll('#pa-pnl .btn').forEach(btn => {
            btn.addEventListener('click', () => this.setPnl(btn.dataset.pnl));
        });
        const syncCats = el('pa-sync-categories');
        if (syncCats) syncCats.addEventListener('click', e => { e.preventDefault(); this.syncCategories(); });
        this._initCategoryModal();
        this._initLegacyPurchaseModal();
        this._wireSortableHeaders();
    };

    // ── Add legacy purchase date (fills the XIRR cashflow gap) ──────────────
    PortfolioAnalysis.prototype._initLegacyPurchaseModal = function () {
        const modalEl = el('paLegacyPurchaseModal');
        if (!modalEl || typeof bootstrap === 'undefined') return;
        this._legacyPurchaseModal = new bootstrap.Modal(modalEl);

        const saveBtn = el('pa-legacy-save');
        if (saveBtn && !saveBtn.dataset.wired) {
            saveBtn.dataset.wired = '1';
            saveBtn.addEventListener('click', () => this._saveLegacyPurchase());
        }
    };

    PortfolioAnalysis.prototype.openLegacyPurchaseModal = async function (productId, fundName) {
        if (!this._legacyPurchaseModal) return;
        this._legacyPurchaseProductId = productId;
        el('pa-legacy-fund-name').textContent = fundName;
        el('pa-legacy-gap-amount').textContent = '…';
        el('pa-legacy-earliest-date').textContent = '…';
        el('pa-legacy-date').value = '';
        el('pa-legacy-amount').value = '';
        el('pa-legacy-error').style.display = 'none';
        this._legacyPurchaseModal.show();

        try {
            const r = await fetch(`${API}/products/${productId}/cashflow-gap/`);
            const d = await r.json();
            el('pa-legacy-gap-amount').textContent = fmt(d.gap_amount);
            el('pa-legacy-earliest-date').textContent = d.earliest_known_date || 'today';
            el('pa-legacy-amount').value = d.gap_amount;
            if (d.earliest_known_date) el('pa-legacy-date').max = d.earliest_known_date;
        } catch (e) {
            el('pa-legacy-gap-amount').textContent = 'the missing portion';
        }
    };

    PortfolioAnalysis.prototype._saveLegacyPurchase = async function () {
        const errEl = el('pa-legacy-error');
        const date = el('pa-legacy-date').value;
        const amount = el('pa-legacy-amount').value;
        if (!date || !amount || parseFloat(amount) <= 0) {
            errEl.textContent = 'Please enter a valid date and amount.';
            errEl.style.display = '';
            return;
        }
        try {
            const r = await fetch(`${API}/products/${this._legacyPurchaseProductId}/legacy-purchase/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                body: JSON.stringify({ date, amount }),
            });
            const d = await r.json();
            if (!r.ok) { errEl.textContent = d.error || 'Save failed.'; errEl.style.display = ''; return; }
            this._legacyPurchaseModal.hide();
            paToast(d.xirr_pct !== null ? `Saved — XIRR is now ${d.xirr_pct}%.` : 'Saved, but XIRR still needs more history.', 'success');
            this._loadReturnsBreakdown(
                document.querySelector('#pa-returns-group-toggle button.active')?.dataset.group || 'fund',
                'pa-chart-returns', 'pa-returns-chart-box', 'pa-returns-tbody',
            );
        } catch (e) {
            errEl.textContent = 'Network error.'; errEl.style.display = '';
        }
    };

    PortfolioAnalysis.prototype._wireSortableHeaders = function () {
        const table = el('pa-holdings-table');
        if (!table) return;
        const headers = Array.from(table.querySelectorAll('.pa-sortable'));
        const defaultDir = {
            name: 'asc', member: 'asc', category: 'asc',
            invested: 'desc', current: 'desc', gain: 'desc', gain_pct: 'desc', xirr: 'desc',
        };
        headers.forEach(th => {
            th.addEventListener('click', () => {
                const key = th.dataset.sort;
                const match = /^(.+)_(asc|desc)$/.exec(this.state.sort || '');
                const curKey = match ? match[1] : null;
                const curDir = match ? match[2] : null;
                const dir = (curKey === key) ? (curDir === 'asc' ? 'desc' : 'asc') : (defaultDir[key] || 'desc');
                this.state.sort = `${key}_${dir}`;
                headers.forEach(h => {
                    h.classList.remove('sort-active');
                    h.querySelector('.sort-arrow').textContent = '';
                });
                th.classList.add('sort-active');
                th.querySelector('.sort-arrow').textContent = dir === 'asc' ? '▲' : '▼';
                this.applyFilters();
            });
        });
    };

    // ── Sync missing categories from MFAPI ──────────────────────────────────
    PortfolioAnalysis.prototype.syncCategories = async function () {
        const link = el('pa-sync-categories');
        const original = link ? link.textContent : '';
        if (link) { link.textContent = '⏳ Syncing…'; link.classList.add('disabled'); }
        try {
            const body = {};
            if (this.memberIds && this.memberIds.length === 1) body.member_id = this.memberIds[0];
            const r = await fetch(`${API}/analytics/sync-categories/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                body: JSON.stringify(body),
            });
            const d = await r.json();
            if (!r.ok) { paToast(d.error || 'Category sync failed.', 'error'); return; }
            if (d.status === 'sync_complete') {
                paToast(d.updated ? `Updated categories for ${d.updated} fund(s).` : 'All held funds already have a category.', 'success');
                await this.refresh();
            } else {
                paToast('Category sync started — refresh in a moment to see updates.', 'success');
                setTimeout(() => this.refresh(), 4000);
            }
        } catch (e) {
            paToast('Network error while syncing categories.', 'error');
        } finally {
            if (link) { link.textContent = original; link.classList.remove('disabled'); }
        }
    };

    // ── Manual category picker ──────────────────────────────────────────────
    PortfolioAnalysis.prototype._initCategoryModal = function () {
        const modalEl = el('paCategoryModal');
        if (!modalEl || typeof bootstrap === 'undefined') return;
        this._categoryModal = new bootstrap.Modal(modalEl);

        const select = el('pa-cat-select');
        if (select && !select.dataset.built) {
            select.dataset.built = '1';
            select.innerHTML = Object.keys(AMFI_CATEGORIES).map(group =>
                `<optgroup label="${escapeHtml(group)}">` +
                AMFI_CATEGORIES[group].map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('') +
                `</optgroup>`
            ).join('');
            select.addEventListener('change', () => {
                const custom = el('pa-cat-custom');
                if (!custom) return;
                custom.style.display = select.value === 'Other / Custom' ? '' : 'none';
            });
        }

        const saveBtn = el('pa-cat-save');
        if (saveBtn && !saveBtn.dataset.wired) {
            saveBtn.dataset.wired = '1';
            saveBtn.addEventListener('click', () => this._saveCategory());
        }
    };

    PortfolioAnalysis.prototype.openCategoryModal = function (productId) {
        const p = this.allProducts.find(x => x.id === productId);
        if (!p || !this._categoryModal) return;
        this._editingCategoryProductId = productId;
        el('pa-cat-fund-name').textContent = p.name;
        const select = el('pa-cat-select');
        const custom = el('pa-cat-custom');
        const currentCategory = p.mf_category || '';
        const knownValues = Object.values(AMFI_CATEGORIES).flat();
        if (currentCategory && knownValues.includes(currentCategory)) {
            select.value = currentCategory;
            custom.style.display = 'none';
            custom.value = '';
        } else {
            select.value = 'Other / Custom';
            custom.style.display = '';
            custom.value = currentCategory;
        }
        el('pa-cat-error').style.display = 'none';
        this._categoryModal.show();
    };

    PortfolioAnalysis.prototype._saveCategory = async function () {
        const errEl = el('pa-cat-error');
        const select = el('pa-cat-select');
        const custom = el('pa-cat-custom');
        const category = (select.value === 'Other / Custom' ? custom.value : select.value).trim();
        if (!category) { errEl.textContent = 'Please choose or enter a category.'; errEl.style.display = ''; return; }

        try {
            const r = await fetch(`${API}/products/${this._editingCategoryProductId}/set-category/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                body: JSON.stringify({ category }),
            });
            const d = await r.json();
            if (!r.ok) { errEl.textContent = d.error || 'Save failed.'; errEl.style.display = ''; return; }
            this._categoryModal.hide();
            paToast('Category updated.', 'success');
            await this.refresh();
        } catch (e) {
            errEl.textContent = 'Network error.'; errEl.style.display = '';
        }
    };

    // Re-fetch holdings and re-render everything driven by them. Call this after
    // any external action that changes the underlying data (e.g. deleting an account).
    PortfolioAnalysis.prototype.refresh = async function () {
        await this._loadProducts();
        this._buildColorMaps();
        this._buildFilterChips();
        this.applyFilters();
    };

    PortfolioAnalysis.prototype.setPnl = function (v) {
        this.state.pnl = v;
        document.querySelectorAll('#pa-pnl .btn').forEach(b => b.classList.toggle('active', b.dataset.pnl === v));
        this.applyFilters();
    };

    PortfolioAnalysis.prototype.resetFilters = function () {
        this.state.search = ''; this.state.members.clear(); this.state.types.clear();
        this.state.categories.clear(); this.state.amcs.clear(); this.state.sectors.clear(); this.state.mcaps.clear();
        this.state.pnl = 'all'; this.state.hideZero = false;
        const search = el('pa-search'); if (search) search.value = '';
        const hideZero = el('pa-hide-zero'); if (hideZero) hideZero.checked = false;
        document.querySelectorAll('#pa-pnl .btn').forEach(b => b.classList.toggle('active', b.dataset.pnl === 'all'));
        this._renderChipGroupsUI();
        this.applyFilters();
    };

    PortfolioAnalysis.prototype._loadMembers = async function () {
        try {
            const r = await fetch(`${API}/family-members/`);
            this.members = await r.json();
        } catch (e) { this.members = []; }
    };

    PortfolioAnalysis.prototype._loadProducts = async function () {
        try {
            const r = await fetch(this._productsUrl());
            const products = await r.json();
            this.allProducts = products.map(p => {
                const category = p.mf_category || TYPE_LABELS[p.product_type] || p.product_type;
                return {
                    ...p,
                    _inv: parseFloat(p.invested_value) || 0,
                    _cur: parseFloat(p.current_value) || 0,
                    _gain: parseFloat(p.gain_loss) || 0,
                    _gainPct: parseFloat(p.gain_loss_pct) || 0,
                    _xirr: p.xirr === null || p.xirr === undefined ? null : parseFloat(p.xirr),
                    _category: category,
                    _mcapBucket: mcapBucket(p.equity_market_cap_cr),
                };
            });
        } catch (e) {
            this.allProducts = [];
        }
    };

    // ── Stable color assignment (identity, not rank — computed once from the
    //    full unfiltered set so a chip toggle never repaints survivors) ─────
    PortfolioAnalysis.prototype._buildColorMaps = function () {
        const dims = {
            category: p => p._category,
            member_name: p => p.member_name,
            product_type: p => TYPE_LABELS[p.product_type] || p.product_type,
            equity_sector: p => p.equity_sector,
            mf_amc: p => p.mf_amc,
            _mcapBucket: p => p._mcapBucket,
        };
        this.colorMaps = {};
        Object.keys(dims).forEach(dim => {
            const totals = {};
            this.allProducts.forEach(p => {
                const key = dims[dim](p);
                if (!key) return;
                totals[key] = (totals[key] || 0) + p._cur;
            });
            const ordered = Object.keys(totals).sort((a, b) => totals[b] - totals[a]);
            const map = {};
            ordered.forEach((key, i) => { map[key] = i < PALETTE.length ? PALETTE[i] : OTHER_COLOR; });
            this.colorMaps[dim] = map;
        });
    };

    PortfolioAnalysis.prototype._colorFor = function (dim, key) {
        return (this.colorMaps[dim] && this.colorMaps[dim][key]) || OTHER_COLOR;
    };

    // ── Filter chips ─────────────────────────────────────────────────────────
    PortfolioAnalysis.prototype._buildFilterChips = function () {
        if (this.showMemberFilter) {
            const memberCounts = {};
            this.allProducts.forEach(p => { memberCounts[p.member_name] = (memberCounts[p.member_name] || 0) + 1; });
            this._filterValues_members = uniqueSorted(this.allProducts.map(p => p.member_name)).map(v => ({ v, n: memberCounts[v] }));
        }
        const typeCounts = {};
        this.allProducts.forEach(p => { typeCounts[p.product_type] = (typeCounts[p.product_type] || 0) + 1; });
        this._filterValues_types = uniqueSorted(this.allProducts.map(p => p.product_type)).map(v => ({ v, n: typeCounts[v], label: TYPE_LABELS[v] || v }));

        const catCounts = {};
        this.allProducts.forEach(p => { if (p.mf_category) catCounts[p.mf_category] = (catCounts[p.mf_category] || 0) + 1; });
        this._filterValues_categories = uniqueSorted(this.allProducts.filter(p => p.mf_category).map(p => p.mf_category)).map(v => ({ v, n: catCounts[v] }));

        const amcCounts = {};
        this.allProducts.forEach(p => { if (p.mf_amc) amcCounts[p.mf_amc] = (amcCounts[p.mf_amc] || 0) + 1; });
        this._filterValues_amcs = uniqueSorted(this.allProducts.filter(p => p.mf_amc).map(p => p.mf_amc)).map(v => ({ v, n: amcCounts[v] }));

        const sectorCounts = {};
        this.allProducts.forEach(p => { if (p.equity_sector) sectorCounts[p.equity_sector] = (sectorCounts[p.equity_sector] || 0) + 1; });
        this._filterValues_sectors = uniqueSorted(this.allProducts.filter(p => p.equity_sector).map(p => p.equity_sector)).map(v => ({ v, n: sectorCounts[v] }));

        const mcapCounts = {};
        this.allProducts.forEach(p => { if (p._mcapBucket) mcapCounts[p._mcapBucket] = (mcapCounts[p._mcapBucket] || 0) + 1; });
        this._filterValues_mcaps = ['Large Cap', 'Mid Cap', 'Small Cap'].filter(v => mcapCounts[v]).map(v => ({ v, n: mcapCounts[v] }));

        this._renderChipGroupsUI();
    };

    PortfolioAnalysis.prototype._renderChipGroup = function (containerId, values, stateSet, labelFn) {
        const container = el(containerId);
        if (!container) return;
        const wrap = container.closest('.pa-filter-group');
        if (!values.length) { if (wrap) wrap.style.display = 'none'; return; }
        if (wrap) wrap.style.display = '';
        container.innerHTML = values.map(({ v, n }) => {
            const active = stateSet.has(v) ? 'active' : '';
            const label = labelFn ? labelFn(v) : escapeHtml(v);
            return `<button type="button" class="filter-chip ${active}" data-key="${escapeHtml(v)}">${label}<span class="chip-count">${n}</span></button>`;
        }).join('');
        container.querySelectorAll('.filter-chip').forEach(btn => {
            btn.addEventListener('click', () => {
                const key = btn.dataset.key;
                if (stateSet.has(key)) stateSet.delete(key); else stateSet.add(key);
                btn.classList.toggle('active');
                this.applyFilters();
            });
        });
    };

    PortfolioAnalysis.prototype._renderChipGroupsUI = function () {
        if (this.showMemberFilter) {
            this._renderChipGroup('pa-chips-member', this._filterValues_members || [], this.state.members);
        }
        this._renderChipGroup('pa-chips-type', this._filterValues_types || [], this.state.types, v => (TYPE_LABELS[v] || v));
        this._renderChipGroup('pa-chips-category', this._filterValues_categories || [], this.state.categories);
        this._renderChipGroup('pa-chips-amc', this._filterValues_amcs || [], this.state.amcs);
        this._renderChipGroup('pa-chips-sector', this._filterValues_sectors || [], this.state.sectors);
        this._renderChipGroup('pa-chips-mcap', this._filterValues_mcaps || [], this.state.mcaps);
    };

    // ── Filtering + summary + charts + table ─────────────────────────────────
    PortfolioAnalysis.prototype._filtered = function () {
        let list = this.allProducts;
        const s = this.state;
        if (s.hideZero) list = list.filter(p => p._cur !== 0 || p._inv !== 0);
        if (s.members.size) list = list.filter(p => s.members.has(p.member_name));
        if (s.types.size) list = list.filter(p => s.types.has(p.product_type));
        if (s.categories.size) list = list.filter(p => s.categories.has(p.mf_category));
        if (s.amcs.size) list = list.filter(p => s.amcs.has(p.mf_amc));
        if (s.sectors.size) list = list.filter(p => s.sectors.has(p.equity_sector));
        if (s.mcaps.size) list = list.filter(p => s.mcaps.has(p._mcapBucket));
        if (s.pnl === 'profit') list = list.filter(p => p._gain > 0);
        if (s.pnl === 'loss') list = list.filter(p => p._gain < 0);
        if (s.search) {
            const q = s.search.toLowerCase();
            list = list.filter(p =>
                (p.name || '').toLowerCase().includes(q) ||
                (p.isin || '').toLowerCase().includes(q) ||
                (p.mf_amc || '').toLowerCase().includes(q) ||
                (p._category || '').toLowerCase().includes(q));
        }
        return list;
    };

    PortfolioAnalysis.prototype.applyFilters = function () {
        const list = this._filtered();
        this._renderSummary(list);
        this._renderCharts(list);
        this._renderTable(list);
    };

    PortfolioAnalysis.prototype._renderSummary = function (list) {
        const inv = list.reduce((s, p) => s + p._inv, 0);
        const cur = list.reduce((s, p) => s + p._cur, 0);
        const gain = cur - inv;
        const gainPct = inv ? (gain / inv * 100) : 0;
        const xirrRows = list.filter(p => p._xirr !== null && p._cur);
        const xirrDenom = xirrRows.reduce((s, p) => s + p._cur, 0);
        const weightedXirr = xirrDenom ? xirrRows.reduce((s, p) => s + p._xirr * p._cur, 0) / xirrDenom : null;

        const set = (id, text, cls) => { const e = el(id); if (e) { e.textContent = text; if (cls) e.className = 'value ' + cls; } };
        set('pa-m-inv', fmt(inv));
        set('pa-m-cur', fmt(cur));
        set('pa-m-gain', signed(gain) + fmt(gain) + ' (' + pct(gainPct) + ')', gainClass(gain));
        set('pa-m-xirr', weightedXirr === null ? '—' : signed(weightedXirr) + (weightedXirr * 100).toFixed(2) + '%', weightedXirr === null ? '' : gainClass(weightedXirr));

        const gainCard = el('pa-m-gain-card');
        if (gainCard) gainCard.style.borderLeftColor = gain >= 0 ? 'var(--success)' : 'var(--danger)';

        const badge = el('pa-badge');
        if (badge) {
            if (!this.allProducts.length) {
                badge.textContent = '';
            } else if (this.showMemberFilter) {
                const memberCount = new Set(list.map(p => p.member_name)).size;
                badge.textContent = `Showing ${list.length} of ${this.allProducts.length} holdings across ${memberCount} member${memberCount === 1 ? '' : 's'}`;
            } else {
                badge.textContent = `Showing ${list.length} of ${this.allProducts.length} holdings`;
            }
        }
    };

    // ── Charts ────────────────────────────────────────────────────────────────
    PortfolioAnalysis.prototype._bucketByDim = function (list, dimKeyFn, colorDim) {
        const totals = {};
        list.forEach(p => {
            const key = dimKeyFn(p);
            if (!key) return;
            totals[key] = (totals[key] || 0) + p._cur;
        });
        let entries = Object.entries(totals).sort((a, b) => b[1] - a[1]);
        if (entries.length > MAX_SLICES) {
            const head = entries.slice(0, MAX_SLICES - 1);
            const tailValue = entries.slice(MAX_SLICES - 1).reduce((s, [, v]) => s + v, 0);
            entries = head.concat([['Other', tailValue]]);
        }
        return {
            labels: entries.map(([k]) => k),
            values: entries.map(([, v]) => v),
            colors: entries.map(([k]) => k === 'Other' ? OTHER_COLOR : this._colorFor(colorDim, k)),
        };
    };

    PortfolioAnalysis.prototype._renderDonut = function (canvasId, data, legendId) {
        const canvas = el(canvasId);
        if (!canvas) return;
        if (this.charts[canvasId]) this.charts[canvasId].destroy();
        if (!data.labels.length) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const legend = el(legendId); if (legend) legend.innerHTML = '<p class="text-muted small mb-0">No data.</p>';
            return;
        }
        this.charts[canvasId] = new Chart(canvas, {
            type: 'doughnut',
            data: { labels: data.labels, datasets: [{ data: data.values, backgroundColor: data.colors, borderColor: 'var(--surface-1, #fff)', borderWidth: 2 }] },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.label}: ${fmt(c.parsed)}` } } },
            },
        });
        const legend = el(legendId);
        if (legend) {
            const total = data.values.reduce((a, b) => a + b, 0) || 1;
            legend.innerHTML = data.labels.map((label, i) => {
                const share = (data.values[i] / total * 100).toFixed(1);
                return `<div class="d-flex align-items-center gap-2 small mb-1">
                    <span style="width:10px;height:10px;border-radius:50%;background:${data.colors[i]};display:inline-block;flex-shrink:0"></span>
                    <span class="text-truncate" style="max-width:140px" title="${escapeHtml(label)}">${escapeHtml(label)}</span>
                    <span class="text-muted ms-auto text-end">${share}%<br><span style="font-size:.85em">${fmt(data.values[i])}</span></span>
                </div>`;
            }).join('');
        }
    };

    PortfolioAnalysis.prototype._renderBar = function (canvasId, data) {
        const canvas = el(canvasId);
        if (!canvas) return;
        if (this.charts[canvasId]) this.charts[canvasId].destroy();
        if (!data.labels.length) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        }
        this.charts[canvasId] = new Chart(canvas, {
            type: 'bar',
            data: { labels: data.labels, datasets: [{ data: data.values, backgroundColor: data.colors, borderRadius: 4, maxBarThickness: 36 }] },
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmt(c.parsed.x) } } },
                scales: { x: { ticks: { callback: (v) => fmt(v) } } },
            },
        });
    };

    PortfolioAnalysis.prototype._renderCharts = function (list) {
        this._renderDonut('pa-chart-category', this._bucketByDim(list, p => p._category, 'category'), 'pa-legend-category');
        if (this.showMemberFilter) {
            this._renderDonut('pa-chart-member', this._bucketByDim(list, p => p.member_name, 'member_name'), 'pa-legend-member');
        }
        this._renderDonut('pa-chart-assetclass', this._bucketByDim(list, p => TYPE_LABELS[p.product_type] || p.product_type, 'product_type'), 'pa-legend-assetclass');
        this._renderDonut('pa-chart-sector', this._bucketByDim(list.filter(p => p.product_type === 'EQUITY'), p => p.equity_sector, 'equity_sector'), 'pa-legend-sector');
        this._renderBar('pa-chart-mcap', this._bucketByDim(list.filter(p => p.product_type === 'EQUITY'), p => p._mcapBucket, '_mcapBucket'));
        this._renderBar('pa-chart-amc', this._bucketByDim(list.filter(p => p.mf_amc), p => p.mf_amc, 'mf_amc'));
    };

    // ── Holdings table ──────────────────────────────────────────────────────
    PortfolioAnalysis.prototype._rowHtml = function (p, indent) {
        const cls = gainClass(p._gain);
        const catColor = this._colorFor('category', p._category);
        const subParts = [p.account_name, p.equity_sector].filter(Boolean).map(escapeHtml);
        const isMf = p.product_type === 'MUTUAL_FUND';
        const catCell = isMf
            ? `<span class="badge-type" style="background:${catColor}22;color:${catColor};cursor:pointer" title="Click to set category" onclick="event.stopPropagation();window.__paInstance.openCategoryModal(${p.id})">${escapeHtml(p._category)} ✏️</span>`
            : `<span class="badge-type" style="background:${catColor}22;color:${catColor}">${escapeHtml(p._category)}</span>`;
        return `<tr onclick="window.location.href='/investments/account/${p.investment_account}/'" style="cursor:pointer">
            <td class="ps-3" style="${indent ? 'padding-left:2rem' : ''}">
                <div class="fw-medium text-truncate" style="max-width:240px" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</div>
                <div class="text-muted" style="font-size:.72rem">${subParts.join(' · ')}</div>
            </td>
            ${this.showMemberFilter ? `<td><span class="text-muted small">${escapeHtml(p.member_name || '')}</span></td>` : ''}
            <td>${catCell}</td>
            <td class="text-end">${fmt(p._inv)}</td>
            <td class="text-end">${fmt(p._cur)}</td>
            <td class="text-end ${cls}">${signed(p._gain)}${fmt(p._gain)}</td>
            <td class="text-end ${cls}">${p._inv ? (p._gain >= 0 ? '+' : '') + p._gainPct.toFixed(2) + '%' : '—'}</td>
            <td class="text-end pe-3">${p._xirr === null ? '—' : pct(p._xirr * 100)}</td>
        </tr>`;
    };

    PortfolioAnalysis.prototype._renderTable = function (list) {
        const tbody = el('pa-holdings-body');
        if (!tbody) return;

        const summaryEl = el('pa-holdings-summary');
        if (summaryEl) {
            const inv = list.reduce((s, p) => s + p._inv, 0);
            const cur = list.reduce((s, p) => s + p._cur, 0);
            const gain = cur - inv;
            summaryEl.innerHTML = this.allProducts.length
                ? `Showing <strong>${list.length}</strong> of <strong>${this.allProducts.length}</strong> · Invested ${fmt(inv)} · Current ${fmt(cur)} · <span class="${gainClass(gain)}">${signed(gain)}${fmt(gain)}</span>`
                : '';
        }

        const colspan = this.showMemberFilter ? 8 : 7;
        if (!this.allProducts.length) {
            tbody.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted py-3">No holdings found.</td></tr>`;
            return;
        }
        if (!list.length) {
            tbody.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted py-3">No holdings match these filters.</td></tr>`;
            return;
        }

        const xirrCmp = (dir) => (a, b) => {
            if (a._xirr === null && b._xirr === null) return 0;
            if (a._xirr === null) return 1;   // nulls always last, either direction
            if (b._xirr === null) return -1;
            return dir === 'asc' ? a._xirr - b._xirr : b._xirr - a._xirr;
        };
        const cmp = {
            current_desc: (a, b) => b._cur - a._cur, current_asc: (a, b) => a._cur - b._cur,
            gain_pct_desc: (a, b) => b._gainPct - a._gainPct, gain_pct_asc: (a, b) => a._gainPct - b._gainPct,
            gain_desc: (a, b) => b._gain - a._gain, gain_asc: (a, b) => a._gain - b._gain,
            invested_desc: (a, b) => b._inv - a._inv, invested_asc: (a, b) => a._inv - b._inv,
            name_asc: (a, b) => (a.name || '').localeCompare(b.name || ''),
            name_desc: (a, b) => (b.name || '').localeCompare(a.name || ''),
            member_asc: (a, b) => (a.member_name || '').localeCompare(b.member_name || ''),
            member_desc: (a, b) => (b.member_name || '').localeCompare(a.member_name || ''),
            category_asc: (a, b) => (a._category || '').localeCompare(b._category || ''),
            category_desc: (a, b) => (b._category || '').localeCompare(a._category || ''),
            xirr_asc: xirrCmp('asc'), xirr_desc: xirrCmp('desc'),
        }[this.state.sort] || ((a, b) => b._cur - a._cur);
        const sorted = list.slice().sort(cmp);

        if (this.state.group === 'none') {
            tbody.innerHTML = sorted.map(p => this._rowHtml(p, false)).join('');
            return;
        }

        const groupKeyFn = {
            product_type: p => TYPE_LABELS[p.product_type] || p.product_type,
            category: p => p._category,
            mf_amc: p => p.mf_amc || 'Uncategorised',
            member_name: p => p.member_name,
            equity_sector: p => p.equity_sector || 'Uncategorised',
        }[this.state.group] || (p => p._category);

        const groups = {};
        sorted.forEach(p => { const key = groupKeyFn(p); (groups[key] = groups[key] || []).push(p); });
        const grandTotal = sorted.reduce((s, p) => s + p._cur, 0) || 1;
        const groupKeys = Object.keys(groups).sort((a, b) => groups[b].reduce((s, p) => s + p._cur, 0) - groups[a].reduce((s, p) => s + p._cur, 0));

        tbody.innerHTML = groupKeys.map(key => {
            const items = groups[key];
            const inv = items.reduce((s, p) => s + p._inv, 0);
            const cur = items.reduce((s, p) => s + p._cur, 0);
            const gain = cur - inv;
            const gainPct = inv ? (gain / inv * 100) : 0;
            const share = (cur / grandTotal * 100).toFixed(1);
            const groupRow = `<tr class="group-row">
                <td class="ps-3 fw-bold" colspan="${this.showMemberFilter ? 3 : 2}">${escapeHtml(key)} <span class="text-muted fw-normal">(${items.length} · ${share}% of shown)</span></td>
                <td class="text-end fw-bold">${fmt(inv)}</td>
                <td class="text-end fw-bold">${fmt(cur)}</td>
                <td class="text-end fw-bold ${gainClass(gain)}">${signed(gain)}${fmt(gain)}</td>
                <td class="text-end fw-bold ${gainClass(gain)}">${inv ? (gain >= 0 ? '+' : '') + gainPct.toFixed(2) + '%' : '—'}</td>
                <td class="pe-3"></td>
            </tr>`;
            return groupRow + items.map(p => this._rowHtml(p, true)).join('');
        }).join('');
    };

    // ── Member-scoped analytics (risk / tenor / trend / concentration) ──────
    PortfolioAnalysis.prototype._loadMemberScopedAnalytics = async function () {
        await Promise.all([
            this._loadRiskSummary(),
            this._loadTenorLadder(),
            this._loadTrend(),
            this._loadOverlap(),
            this._loadReturnsBreakdown('fund', 'pa-chart-returns', 'pa-returns-chart-box', 'pa-returns-tbody'),
            this._loadReturnsBreakdown('category', 'pa-chart-returns-category', 'pa-returns-category-chart-box', null),
        ]);
        const toggle = el('pa-returns-group-toggle');
        if (toggle && !toggle.dataset.wired) {
            toggle.dataset.wired = '1';
            toggle.querySelectorAll('button').forEach(btn => {
                btn.addEventListener('click', () => {
                    toggle.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this._loadReturnsBreakdown(btn.dataset.group, 'pa-chart-returns', 'pa-returns-chart-box', 'pa-returns-tbody');
                });
            });
        }
    };

    // groupBy: 'fund'|'amc'|'sector'|'asset_class'. tbodyId may be null for a
    // chart-only view (e.g. the fixed sector chart, which doesn't need its
    // own table alongside the main toggle-driven one).
    PortfolioAnalysis.prototype._loadReturnsBreakdown = async function (groupBy, canvasId, boxId, tbodyId) {
        const box = el(boxId);
        const tbody = tbodyId ? el(tbodyId) : null;
        try {
            const base = this._analyticsUrl('returns-breakdown');
            const url = base + (base.includes('?') ? '&' : '?') + `group_by=${groupBy}`;
            const r = await fetch(url);
            if (!r.ok) throw new Error();
            const d = await r.json();
            const groups = d.groups || [];

            // Chart: only groups with a real (annualised) XIRR — mixing that
            // with plain gain/loss % on one axis would misleadingly compare
            // different kinds of return.
            const withXirr = groups.filter(g => g.xirr_pct !== null).slice(0, 12);
            const canvas = el(canvasId);
            if (this.charts[canvasId]) this.charts[canvasId].destroy();
            if (canvas && withXirr.length) {
                this.charts[canvasId] = new Chart(canvas, {
                    type: 'bar',
                    data: {
                        labels: withXirr.map(g => g.label.length > 28 ? g.label.slice(0, 27) + '…' : g.label),
                        datasets: [{
                            data: withXirr.map(g => g.xirr_pct),
                            backgroundColor: withXirr.map(g => g.xirr_pct >= 0 ? '#1baf7a' : '#e34948'),
                            borderRadius: 4,
                        }],
                    },
                    options: {
                        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: { callbacks: { label: (c) => `XIRR: ${c.parsed.x.toFixed(2)}%` } },
                        },
                        scales: { x: { ticks: { callback: (v) => v + '%' } } },
                    },
                });
            } else if (canvas) {
                const ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
            if (box) {
                let note = box.querySelector('.pa-no-xirr-note');
                if (!withXirr.length) {
                    if (!note) {
                        note = document.createElement('p');
                        note.className = 'pa-no-xirr-note text-muted small text-center mb-0 mt-5';
                        note.textContent = 'None of these groups have dated transaction history yet — see gain/loss % in the table below.';
                        box.appendChild(note);
                    }
                } else if (note) {
                    note.remove();
                }
            }

            if (tbody) {
                tbody.innerHTML = groups.map(g => `
                    <tr>
                        <td class="text-truncate" style="max-width:260px" title="${escapeHtml(g.label)}">${escapeHtml(g.label)}</td>
                        <td class="text-end">${fmt(g.invested_value)}</td>
                        <td class="text-end">${fmt(g.current_value)}</td>
                        <td class="text-end ${gainClass(g.gain_loss)}">${signed(g.gain_loss)}${fmt(g.gain_loss)} (${signed(g.gain_loss_pct)}${g.gain_loss_pct.toFixed(2)}%)</td>
                        <td class="text-end ${g.xirr_pct !== null ? gainClass(g.xirr_pct) : 'text-muted'}">${
                            g.xirr_pct !== null
                                ? signed(g.xirr_pct) + g.xirr_pct.toFixed(2) + '%'
                                : (g.product_id
                                    ? `— <a href="#" class="small" onclick="event.preventDefault();window.__paInstance.openLegacyPurchaseModal(${g.product_id},'${escapeHtml(g.label).replace(/'/g, "\\'")}')">📅 add date</a>`
                                    : '—')
                        }</td>
                        <td class="text-end text-muted">${g.holdings_count}</td>
                    </tr>`).join('');
            }
        } catch (e) {
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted small py-3">Returns breakdown unavailable.</td></tr>';
        }
    };

    PortfolioAnalysis.prototype._loadRiskSummary = async function () {
        const panel = el('pa-risk-panel');
        if (!panel) return;
        try {
            const r = await fetch(this._analyticsUrl('risk-summary'));
            if (!r.ok) throw new Error();
            const d = await r.json();
            const set = (id, v, isPct) => { const e = el(id); if (e) e.textContent = v === null || v === undefined ? '—' : (isPct ? pct(v * 100) : v.toFixed(2)); };
            set('pa-risk-sharpe', d.weighted_sharpe);
            set('pa-risk-sortino', d.weighted_sortino);
            set('pa-risk-stddev', d.weighted_std_dev, true);
            set('pa-risk-maxdd', d.weighted_max_drawdown, true);
            set('pa-risk-beta', d.weighted_beta);
            set('pa-risk-alpha', d.weighted_alpha, true);
            const setRet = (id, v) => { const e = el(id); if (e) e.textContent = (v === null || v === undefined) ? '—' : pct(v); };
            const rets = d.weighted_returns || {};
            setRet('pa-risk-ret-1m', rets['1M']);
            setRet('pa-risk-ret-3m', rets['3M']);
            setRet('pa-risk-ret-6m', rets['6M']);
            setRet('pa-risk-ret-1y', rets['1Y']);
            setRet('pa-risk-ret-3y', rets['3Y']);
            setRet('pa-risk-ret-5y', rets['5Y']);
            const cov = el('pa-risk-coverage');
            if (cov) {
                cov.textContent = d.coverage_pct !== undefined
                    ? `Based on ${d.coverage_pct.toFixed(0)}% of mutual fund value (funds with ≥30 days NAV history)`
                    : '';
            }
        } catch (e) {
            panel.querySelectorAll('.pa-risk-tile .value').forEach(v => v.textContent = '—');
            const cov = el('pa-risk-coverage'); if (cov) cov.textContent = 'Risk metrics unavailable.';
        }
    };

    PortfolioAnalysis.prototype._loadTenorLadder = async function () {
        try {
            const r = await fetch(this._analyticsUrl('tenor-ladder'));
            if (!r.ok) throw new Error();
            const d = await r.json();
            const buckets = d.buckets || {};
            const labels = ['<1Y', '1-3Y', '3-5Y', '5Y+'];
            this._renderBar('pa-chart-tenor', {
                labels, values: labels.map(l => buckets[l] || 0),
                colors: labels.map((_, i) => PALETTE[i]),
            });
            const avg = el('pa-tenor-avg');
            if (avg) avg.textContent = d.weighted_avg_tenor_years ? `${d.weighted_avg_tenor_years.toFixed(1)} yrs weighted avg. tenor` : 'No maturity data available';
            const cov = el('pa-tenor-coverage');
            if (cov) {
                const known = (d.total_debt_value || 0) > 0 ? Math.round((d.covered_value / d.total_debt_value) * 100) : 0;
                cov.textContent = d.total_debt_value ? `${known}% of debt holdings have maturity data (${d.holdings_missing_maturity} missing)` : 'No debt holdings (FD/RD/Bond/SGB) found.';
            }
        } catch (e) { /* leave empty state */ }
    };

    PortfolioAnalysis.prototype._loadTrend = async function () {
        try {
            const r = await fetch(this._analyticsUrl('trend'));
            if (!r.ok) throw new Error();
            const d = await r.json();
            const series = d.series || [];
            const canvas = el('pa-chart-trend');
            const empty = el('pa-trend-empty');
            if (series.length < 2) {
                if (this.charts['pa-chart-trend']) this.charts['pa-chart-trend'].destroy();
                if (canvas) canvas.style.display = 'none';
                if (empty) empty.style.display = '';
                return;
            }
            if (canvas) canvas.style.display = '';
            if (empty) empty.style.display = 'none';
            if (this.charts['pa-chart-trend']) this.charts['pa-chart-trend'].destroy();
            this.charts['pa-chart-trend'] = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: series.map(s => s.date),
                    datasets: [
                        { label: 'Invested', data: series.map(s => s.invested), borderColor: PALETTE[0], backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.15 },
                        { label: 'Current', data: series.map(s => s.current), borderColor: PALETTE[1], backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.15 },
                    ],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: true, position: 'bottom' }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y)}` } } },
                    scales: { y: { ticks: { callback: (v) => fmt(v) } } },
                },
            });
        } catch (e) { /* leave empty state */ }
    };

    PortfolioAnalysis.prototype._loadOverlap = async function () {
        const box = el('pa-concentration');
        if (!box) return;
        try {
            const csv = this._memberIdsCsv();
            const r = await fetch(`${API}/analytics/overlap/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                body: JSON.stringify(csv ? { member_ids: csv.split(',').map(Number) } : {}),
            });
            const d = await r.json();
            if (d.error) { box.innerHTML = `<p class="text-muted small mb-0">${escapeHtml(d.error)}</p>`; return; }

            const warnings = (d.warnings || []).map(w => `<div class="alert alert-warning py-2 px-3 small mb-2">⚠️ ${escapeHtml(w)}</div>`).join('');
            const stats = `<div class="d-flex flex-wrap gap-3 small text-muted">
                <span>Weighted expense ratio: <strong class="text-dark">${(d.weighted_expense_ratio || 0).toFixed(2)}%</strong></span>
                <span>Estimated annual cost: <strong class="text-dark">${fmt(d.estimated_annual_cost)}</strong></span>
            </div>`;
            box.innerHTML = (warnings || '<p class="text-muted small mb-2">No concentration warnings — portfolio looks well diversified.</p>') + stats;
        } catch (e) {
            box.innerHTML = '<p class="text-muted small mb-0">Could not load concentration analysis.</p>';
        }
    };

    global.PortfolioAnalysis = {
        init: function (opts) {
            const instance = new PortfolioAnalysis(opts);
            global.__paInstance = instance; // used by inline onclick handlers in _rowHtml
            instance.init();
            return instance;
        },
    };
})(window);
