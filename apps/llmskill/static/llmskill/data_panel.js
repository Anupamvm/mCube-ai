/*
 * Shared "Get Data" panel renderer for the llmskill trade-verification flow.
 * Renders a purely-from-the-database data dump (no live API calls) - one
 * section per data source, showing which table it came from, when it was
 * last updated, and the raw stored rows.
 *
 * Used by both llmskill/verify_trade.html (open positions) and
 * trading/analysis_detail.html (pre-trade "View Full Analysis") so both
 * entry points render identical panels from the same
 * /llmskill/api/get-data/ response.
 *
 * Usage:
 *   LLMSkill.init({ symbol, expiryDate, positionId, buttonId, containerId });
 */
(function (window) {
    'use strict';

    function getCookie(name) {
        const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return v ? v.pop() : '';
    }

    function esc(s) {
        if (s == null) return '';
        return String(s).replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    }

    function formatVal(v) {
        if (Array.isArray(v) || (typeof v === 'object' && v !== null)) return JSON.stringify(v);
        return v;
    }

    function fmtTimestamp(iso) {
        if (!iso) return '';
        return String(iso).slice(0, 19).replace('T', ' ');
    }

    function renderRow(row) {
        const entries = Object.keys(row)
            .filter(k => row[k] !== null && row[k] !== '' && row[k] !== undefined)
            .map(k => `<div class="llmskill-kv">
                <span class="llmskill-kv-key">${esc(k)}</span>
                <span class="llmskill-kv-val">${esc(formatVal(row[k]))}</span>
            </div>`)
            .join('');
        return `<div class="llmskill-row">${entries}</div>`;
    }

    function renderSource(src) {
        const body = (src.rows && src.rows.length)
            ? src.rows.map(renderRow).join('')
            : `<div class="llmskill-empty">${esc(src.note || 'No rows found in this table for this symbol')}</div>`;

        return `<div class="llmskill-section">
            <div class="llmskill-section-title">
                <span>${esc(src.label)}</span>
                ${src.table ? `<span class="llmskill-table-tag">${esc(src.table)}</span>` : ''}
            </div>
            <div class="llmskill-source-meta">
                ${src.count} row(s)${src.last_updated ? ' · last updated ' + esc(fmtTimestamp(src.last_updated)) : ''}
            </div>
            ${body}
        </div>`;
    }

    function render(container, data) {
        const errors = (data.errors || []).map(e => `<div class="llmskill-error">${esc(e)}</div>`).join('');
        const sources = (data.sources || []).map(renderSource).join('');
        container.innerHTML = errors + sources;
    }

    function init(config) {
        const btn = document.getElementById(config.buttonId);
        const container = document.getElementById(config.containerId);
        if (!btn || !container) return;

        btn.addEventListener('click', function () {
            btn.disabled = true;
            const originalText = btn.textContent;
            btn.textContent = 'Loading…';
            container.innerHTML = '<div class="llmskill-empty">Reading stored data (no external API calls)…</div>';

            const body = new URLSearchParams({
                symbol: config.symbol,
                expiry_date: config.expiryDate,
            });
            if (config.positionId) body.append('position_id', config.positionId);

            fetch('/llmskill/api/get-data/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: body.toString(),
            })
                .then(r => r.json())
                .then(resp => {
                    btn.disabled = false;
                    btn.textContent = originalText;
                    if (!resp.success) {
                        container.innerHTML = `<div class="llmskill-error">${esc(resp.error || 'Failed to fetch data')}</div>`;
                        return;
                    }
                    render(container, resp.data);
                })
                .catch(err => {
                    btn.disabled = false;
                    btn.textContent = originalText;
                    container.innerHTML = `<div class="llmskill-error">${esc(err.message || err)}</div>`;
                });
        });
    }

    window.LLMSkill = { init: init };
})(window);
