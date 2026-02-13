(function() {
    'use strict';
    const CELERY_CONFIG = window.CELERY_CONFIG || {};

    // =========================================================================
    // Algorithm / Notification Logic (from inline script blocks)
    // =========================================================================

    var previousNotificationLevel = CELERY_CONFIG.previousNotificationLevel || '';

    function handleNotificationChange(select) {
        if (select.value === 'AUTONOMOUS' && previousNotificationLevel !== 'AUTONOMOUS') {
            document.getElementById('autonomous-warning-modal').style.display = 'flex';
        } else {
            select.form.submit();
        }
    }

    function confirmAutonomous() {
        document.getElementById('autonomous-warning-modal').style.display = 'none';
        document.getElementById('notification-form').submit();
    }

    function cancelAutonomous() {
        document.getElementById('autonomous-warning-modal').style.display = 'none';
        // Reset to previous value
        var select = document.querySelector('select[name="notification_level"]');
        select.value = previousNotificationLevel;
    }

    var ALGO_TASK_DATA = CELERY_CONFIG.algoTaskData || {};
    var previousFuturesState = CELERY_CONFIG.previousFuturesState || false;
    var previousOptionsStrategy = CELERY_CONFIG.previousOptionsStrategy || '';
    var _algoModalOnConfirm = null;

    function handleFuturesToggle(checkbox) {
        var enabling = checkbox.checked;
        var title = enabling ? 'Enable Futures Algorithm?' : 'Disable Futures Algorithm?';
        var body = buildAlgoTaskList('futures', enabling);
        var btnText = enabling ? 'Enable & Start Tasks' : 'Disable & Stop Tasks';
        var btnColor = enabling ? '#48bb78' : '#e53e3e';

        showAlgoModal(title, body, btnText, btnColor, function() {
            checkbox.form.querySelector('[name="manage_tasks"]').value = '1';
            checkbox.form.submit();
        });
    }

    function handleOptionsChange(select) {
        var oldVal = previousOptionsStrategy;
        var newVal = select.value;
        var wasEnabled = oldVal !== 'NONE';
        var willEnable = newVal !== 'NONE';

        if (wasEnabled === willEnable) {
            // Just changing strategy type, no task changes needed
            select.form.submit();
            return;
        }

        var enabling = willEnable;
        var title = enabling ? 'Enable Options Algorithm?' : 'Disable Options Algorithm?';
        var body = buildAlgoTaskList('options', enabling);
        var btnText = enabling ? 'Enable & Start Tasks' : 'Disable & Stop Tasks';
        var btnColor = enabling ? '#48bb78' : '#e53e3e';

        showAlgoModal(title, body, btnText, btnColor, function() {
            select.form.querySelector('[name="manage_tasks"]').value = '1';
            select.form.submit();
        });
    }

    function buildAlgoTaskList(algoKey, enabling) {
        var data = ALGO_TASK_DATA[algoKey];
        if (!data) return '';
        var html = '';

        function taskListHtml(tasks, label) {
            if (!tasks || tasks.length === 0) return '';
            var items = tasks.map(function(t) {
                var icon = enabling ? '&#x2705;' : '&#x274C;';
                return '<li style="margin: 4px 0;">' + icon + ' <strong>' + t.name + '</strong> <span style="color:#a0aec0;">(' + t.schedule + ')</span></li>';
            }).join('');
            return '<div style="margin-bottom: 10px;"><strong style="color:#2d3748;">' + label + '</strong><ul style="list-style:none; padding-left:5px; margin:5px 0;">' + items + '</ul></div>';
        }

        if (enabling) {
            html += taskListHtml(data.own, 'Strategy Tasks');
            html += taskListHtml(data.shared, 'Shared Tasks');
            html += taskListHtml(data.monitoring, 'Monitoring Tasks');
            html += '<p style="font-size:12px; color:#718096; margin-top:10px;">These tasks will be <strong>enabled</strong> and Celery Beat will be restarted.</p>';
        } else {
            // Check if other algo has active own tasks
            var otherActive = false;
            for (var key in ALGO_TASK_DATA) {
                if (key === algoKey) continue;
                var otherOwn = ALGO_TASK_DATA[key].own;
                if (otherOwn && otherOwn.some(function(t) { return t.enabled; })) {
                    otherActive = true;
                    break;
                }
            }
            html += taskListHtml(data.own, 'Tasks to Disable');
            if (otherActive) {
                html += '<div style="margin-bottom:10px;"><strong style="color:#2d3748;">Shared & Monitoring Tasks</strong>';
                html += '<p style="color:#718096; font-size:13px; margin:5px 0;">Kept active (other algorithm is running)</p></div>';
            } else {
                html += taskListHtml(data.shared, 'Shared Tasks to Disable');
                html += taskListHtml(data.monitoring, 'Monitoring Tasks to Disable');
            }
            html += '<p style="font-size:12px; color:#718096; margin-top:10px;">These tasks will be <strong>disabled</strong> and Celery Beat will be restarted.</p>';
        }
        return html;
    }

    function showAlgoModal(title, body, btnText, btnColor, onConfirm) {
        document.getElementById('algo-modal-title').innerHTML = title;
        document.getElementById('algo-modal-body').innerHTML = body;
        var confirmBtn = document.getElementById('algo-modal-confirm-btn');
        confirmBtn.innerHTML = btnText;
        confirmBtn.style.background = btnColor;
        _algoModalOnConfirm = onConfirm;
        confirmBtn.onclick = function() {
            document.getElementById('algo-task-modal').style.display = 'none';
            if (_algoModalOnConfirm) _algoModalOnConfirm();
        };
        document.getElementById('algo-task-modal').style.display = 'flex';
    }

    function cancelAlgoAction() {
        document.getElementById('algo-task-modal').style.display = 'none';
        // Revert futures checkbox
        var futuresCheckbox = document.querySelector('#futures-toggle-form input[type="checkbox"]');
        if (futuresCheckbox) futuresCheckbox.checked = previousFuturesState;
        // Revert options select
        var optionsSelect = document.querySelector('#options-strategy-form select[name="options_strategy"]');
        if (optionsSelect) optionsSelect.value = previousOptionsStrategy;
    }

    // =========================================================================
    // Toggle Task (Dynamic / DB Tasks)
    // =========================================================================

    function toggleTask(taskId, button, action) {
        var taskRow = button.closest('.task-row') || document.getElementById('dynamic-task-' + taskId);

        // Visual feedback on the toggle switch
        button.style.opacity = '0.5';
        button.style.pointerEvents = 'none';

        fetch(CELERY_CONFIG.urls.toggleCeleryTask.replace('0', taskId), {
            method: 'POST',
            headers: {
                'X-CSRFToken': CELERY_CONFIG.csrfToken,
                'Content-Type': 'application/json',
            },
        })
        .then(response => response.json())
        .then(data => {
            button.style.opacity = '';
            button.style.pointerEvents = '';

            if (data.success) {
                // Update toggle switch visual state
                if (data.is_enabled) {
                    button.classList.add('active');
                    button.setAttribute('onclick', "toggleTask('" + taskId + "', this, 'stop')");
                    button.title = 'Click to deactivate';
                } else {
                    button.classList.remove('active');
                    button.setAttribute('onclick', "toggleTask('" + taskId + "', this, 'start')");
                    button.title = 'Click to activate';
                }
                updateStats(data.is_enabled ? 1 : -1);
                showSuccessToast(data.is_enabled ? 'Task Activated' : 'Task Deactivated', data.message || 'Dynamic task toggled successfully', data);
            } else {
                showErrorToast('Toggle Failed', data.error || 'Failed to toggle task');
            }
        })
        .catch(error => {
            button.style.opacity = '';
            button.style.pointerEvents = '';
            showErrorToast('Connection Error', error.toString());
        });
    }

    function updateStats(delta) {
        // Update status bar active count
        var countEl = document.getElementById('statusbar-active-count');
        if (countEl) {
            var text = countEl.textContent;
            var match = text.match(/(\d+)\/(\d+)/);
            if (match) {
                var current = parseInt(match[1]) + delta;
                var total = parseInt(match[2]);
                countEl.textContent = current + '/' + total + ' active';
            }
        }
        // Update timeline summary
        var activeCountEl = document.getElementById('active-task-count');
        if (activeCountEl) {
            var val = parseInt(activeCountEl.textContent) + delta;
            activeCountEl.textContent = val;
        }
    }

    // =========================================================================
    // Toggle Static Task
    // =========================================================================

    function toggleStaticTask(taskKey, taskPath, button, action) {
        // New DOM: button is a .toggle-switch div inside .task-row
        var taskRow = button.closest('.task-row');

        // Visual feedback
        button.style.opacity = '0.5';
        button.style.pointerEvents = 'none';

        var formData = new FormData();
        formData.append('task_key', taskKey);
        formData.append('task_path', taskPath);

        fetch(CELERY_CONFIG.urls.toggleStaticTask, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CELERY_CONFIG.csrfToken,
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            button.style.opacity = '';
            button.style.pointerEvents = '';

            if (data.success) {
                // Update toggle switch visual state
                if (data.is_enabled) {
                    button.classList.add('active');
                    button.setAttribute('onclick', "toggleStaticTask('" + taskKey + "', '" + taskPath + "', this, 'stop')");
                    button.title = 'Click to deactivate';
                } else {
                    button.classList.remove('active');
                    button.setAttribute('onclick', "toggleStaticTask('" + taskKey + "', '" + taskPath + "', this, 'start')");
                    button.title = 'Click to activate';
                }

                updateStats(data.is_enabled ? 1 : -1);

                // Show improved status toast
                var displayName = taskKey.replace(/-/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
                showSuccessToast(
                    data.is_enabled ? 'Task Activated' : 'Task Deactivated',
                    displayName,
                    data
                );
            } else {
                showErrorToast('Toggle Failed', data.error || 'Failed to toggle task');
            }
        })
        .catch(error => {
            button.style.opacity = '';
            button.style.pointerEvents = '';
            showErrorToast('Connection Error', error.toString());
        });
    }

    // =========================================================================
    // Run Task Now Function
    // =========================================================================

    function runTaskNow(taskKey, button) {
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = '\u23F3 Running...';
        button.classList.add('running');

        fetch(CELERY_CONFIG.urls.runTaskNow, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CELERY_CONFIG.csrfToken,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ task_key: taskKey })
        })
        .then(response => response.json())
        .then(data => {
            button.classList.remove('running');

            if (data.success) {
                button.textContent = '\u2713 Queued!';
                button.style.background = '#48bb78';

                // Show success toast
                showRunToast(taskKey, data, false);

                // Reset button after delay
                setTimeout(() => {
                    button.disabled = false;
                    button.textContent = originalText;
                    button.style.background = '';
                }, 3000);
            } else {
                button.textContent = '\u2717 Failed';
                button.style.background = '#e53e3e';
                showRunToast(taskKey, data, true);

                setTimeout(() => {
                    button.disabled = false;
                    button.textContent = originalText;
                    button.style.background = '';
                }, 3000);
            }
        })
        .catch(error => {
            button.classList.remove('running');
            button.textContent = '\u2717 Error';
            button.style.background = '#e53e3e';
            showRunToast(taskKey, { error: error.toString() }, true);

            setTimeout(() => {
                button.disabled = false;
                button.textContent = originalText;
                button.style.background = '';
            }, 3000);
        });
    }

    function showRunToast(taskKey, data, isError) {
        if (isError) {
            showErrorToast('Task Failed', data.error || 'Failed to queue task');
        } else {
            var displayName = taskKey.replace(/-/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
            showSuccessToast('Task Queued', displayName + ' has been sent to the worker', data);
        }
    }

    // =========================================================================
    // Improved Toast Notifications
    // =========================================================================

    function showSuccessToast(titleText, message, data) {
        var toast = document.getElementById('statusToast');
        var header = document.getElementById('toastHeader');
        var title = document.getElementById('toastTitle');
        var body = document.getElementById('toastBody');

        header.className = 'status-toast-header success';
        title.textContent = titleText;

        var celery = (data && data.celery) || {};
        var beatOk = data && (data.beat_restarted || celery.beat_restarted || celery.beat_status === 'restarted');
        var workerOk = celery.worker_status === 'running' || celery.worker_started;

        var html = '<div class="toast-success-content">';
        html += '<div class="toast-main-message">';
        html += '<span class="toast-check-icon">&#10003;</span>';
        html += '<span>' + escapeHtml(message) + '</span>';
        html += '</div>';

        // Show celery status summary if available
        if (data && (celery.success !== undefined || data.beat_restarted !== undefined)) {
            html += '<div class="toast-details">';
            if (workerOk) {
                html += '<span class="toast-detail-item success">Worker Running</span>';
            }
            if (beatOk) {
                html += '<span class="toast-detail-item success">Schedule Updated</span>';
            }
            if (celery.worker_status === 'failed') {
                html += '<span class="toast-detail-item error">Worker Failed</span>';
            }
            if (celery.beat_status === 'failed') {
                html += '<span class="toast-detail-item error">Beat Failed</span>';
            }
            var activeCount = data.active_tasks ? data.active_tasks.total_active : null;
            if (activeCount !== null) {
                html += '<span class="toast-detail-item">' + activeCount + ' tasks active</span>';
            }
            html += '</div>';
        }

        html += '</div>';
        body.innerHTML = html;

        toast.classList.add('show');
        // Auto-dismiss after 4 seconds
        clearTimeout(window._toastTimer);
        window._toastTimer = setTimeout(function() {
            toast.classList.remove('show');
        }, 4000);
    }

    function showErrorToast(titleText, message) {
        var toast = document.getElementById('statusToast');
        var header = document.getElementById('toastHeader');
        var title = document.getElementById('toastTitle');
        var body = document.getElementById('toastBody');

        header.className = 'status-toast-header error';
        title.textContent = titleText;

        body.innerHTML = '<div class="toast-error-content">' +
            '<span class="toast-error-icon">&#10007;</span>' +
            '<span>' + escapeHtml(message) + '</span>' +
            '</div>';

        toast.classList.add('show');
        // Error toasts stay until manually closed
    }

    // Legacy wrapper for backward compatibility
    function showStatusToast(taskKey, data, isError) {
        if (isError) {
            showErrorToast('Error', (data && data.error) || (data && data.message) || 'Unknown error');
        } else {
            var displayName = taskKey.replace(/-/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
            var msg = (data && data.message) || displayName;
            showSuccessToast(
                data.is_enabled !== undefined ? (data.is_enabled ? 'Task Activated' : 'Task Deactivated') : 'Success',
                msg,
                data
            );
        }
    }

    function hideStatusToast() {
        var toast = document.getElementById('statusToast');
        toast.classList.remove('show');
        clearTimeout(window._toastTimer);
    }

    // =========================================================================
    // Task Logs Modal Functions
    // =========================================================================

    // Global state for logs
    let currentLogs = [];
    let currentLogMode = 'all'; // 'all' or 'task'
    let currentTaskName = '';

    function showTaskLogs(taskKey, taskPath) {
        const modal = document.getElementById('logsModal');
        const title = document.getElementById('logsModalTitle');
        const body = document.getElementById('logsModalBody');
        const filters = document.getElementById('logsFilters');
        const statusBar = document.getElementById('logsStatusBar');

        // Set mode and task
        currentLogMode = 'task';
        currentTaskName = taskKey;

        // Set title
        title.textContent = `Logs: ${taskKey}`;

        // Show filters, hide status bar for task logs
        filters.style.display = 'flex';
        statusBar.style.display = 'none';

        // Reset filters
        document.getElementById('filterStatus').value = 'all';
        document.getElementById('filterSource').value = 'all';
        document.getElementById('filterLevel').value = 'all';
        document.getElementById('filterCategory').value = 'all';

        // Show loading
        body.innerHTML = '<div class="logs-loading">Loading logs...</div>';

        // Show modal
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Fetch logs
        const limit = document.getElementById('filterLimit').value;
        fetch(`${CELERY_CONFIG.urls.getTaskLogs}?task_name=${encodeURIComponent(taskKey)}&limit=${limit}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    currentLogs = data.logs;
                    if (data.logs.length > 0) {
                        body.innerHTML = renderFlatLogs(data.logs);
                    } else {
                        body.innerHTML = `
                            <div class="logs-empty">
                                <p style="font-size: 48px; margin-bottom: 16px;">\uD83D\uDCCB</p>
                                <p>No logs found for <strong>${taskKey}</strong></p>
                                <p style="font-size: 13px; margin-top: 8px;">Logs will appear here once the task runs.</p>
                                <p style="font-size: 12px; margin-top: 16px; color: #a0aec0;">
                                    Task path: ${taskPath || 'N/A'}
                                </p>
                            </div>
                        `;
                    }
                } else {
                    body.innerHTML = `
                        <div class="logs-empty">
                            <p>Error loading logs: ${data.error || 'Unknown error'}</p>
                        </div>
                    `;
                }
            })
            .catch(error => {
                body.innerHTML = `
                    <div class="logs-empty">
                        <p>Error loading logs: ${error}</p>
                    </div>
                `;
            });
    }

    const CATEGORY_META = {
        'data': { label: 'Market Data', color: '#3182ce' },
        'strategies': { label: 'Strategy', color: '#805ad5' },
        'transactions': { label: 'Transaction', color: '#d69e2e' },
        'monitoring': { label: 'Monitoring', color: '#dd6b20' },
        'risk': { label: 'Risk', color: '#e53e3e' },
        'reports': { label: 'Analytics', color: '#38a169' },
    };

    const STATUS_META = {
        'success': { icon: '\u2705', label: 'Success', bg: '#38a169' },
        'error':   { icon: '\u274C', label: 'Failed',  bg: '#e53e3e' },
        'received':{ icon: '\uD83D\uDCE5', label: 'Received', bg: '#667eea' },
        'scheduled':{ icon: '\uD83D\uDCC5', label: 'Scheduled', bg: '#ed8936' },
        'starting': { icon: '\uD83D\uDE80', label: 'Started', bg: '#3182ce' },
        'info':    { icon: '\u2139\uFE0F', label: '',        bg: '' },
    };

    function makeCategoryBadge(cat) {
        if (!cat || !CATEGORY_META[cat]) return '';
        const cm = CATEGORY_META[cat];
        return `<span style="background:${cm.color};color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;">${cm.label}</span>`;
    }

    function makeStatusBadge(status) {
        const sm = STATUS_META[status];
        if (!sm || !sm.bg) return '';
        return `<span style="background:${sm.bg};color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;">${sm.label}</span>`;
    }

    function renderLogs(logs) {
        if (!logs || logs.length === 0) {
            return '<div class="logs-empty"><p>No logs to display</p></div>';
        }

        // Group logs by task_id; ungrouped entries (no task_id) go as standalone
        const groups = [];       // ordered list of { id, displayName, category, status, logs[], firstTs, lastTs }
        const groupMap = {};     // task_id -> group
        const standalone = [];   // logs without task_id

        for (const log of logs) {
            const tid = log.task_id || '';
            if (tid) {
                if (!groupMap[tid]) {
                    const grp = {
                        id: tid,
                        displayName: log.task_display_name || '',
                        category: log.category || '',
                        source: log.source || '',
                        status: log.status || 'info',
                        firstTs: log.timestamp || '',
                        lastTs: log.timestamp || '',
                        logs: [],
                    };
                    groupMap[tid] = grp;
                    groups.push(grp);
                }
                const grp = groupMap[tid];
                grp.logs.push(log);
                if (log.timestamp) grp.lastTs = log.timestamp;
                if (!grp.displayName && log.task_display_name) grp.displayName = log.task_display_name;
                if (!grp.category && log.category) grp.category = log.category;
                // Promote status: success/error > starting > received > info
                const rank = { error: 5, success: 4, starting: 3, received: 2, scheduled: 1, info: 0 };
                if ((rank[log.status] || 0) > (rank[grp.status] || 0)) grp.status = log.status;
            } else {
                standalone.push(log);
            }
        }

        // Merge into a single timeline sorted by first timestamp (most recent first)
        // Each item is either { type:'group', ...group } or { type:'standalone', log }
        let timeline = [];
        for (const g of groups) timeline.push({ type: 'group', ts: g.firstTs, data: g });
        for (const s of standalone) timeline.push({ type: 'standalone', ts: s.timestamp || '', data: s });
        timeline.sort((a, b) => (b.ts || '').localeCompare(a.ts || ''));

        let html = '';
        for (const item of timeline) {
            if (item.type === 'group') {
                html += renderTaskGroup(item.data);
            } else {
                html += renderStandaloneLine(item.data);
            }
        }
        return html;
    }

    function renderTaskGroup(grp) {
        const sm = STATUS_META[grp.status] || STATUS_META['info'];
        const borderColor = sm.bg || '#4a5568';
        const displayName = grp.displayName || 'Unknown Task';
        const detailCount = grp.logs.length;

        // Compute duration if we have first and last timestamps
        let duration = '';
        if (grp.firstTs && grp.lastTs && grp.firstTs !== grp.lastTs) {
            const d1 = new Date(grp.firstTs.replace(',','.'));
            const d2 = new Date(grp.lastTs.replace(',','.'));
            const diffMs = d2 - d1;
            if (diffMs > 0) {
                const secs = Math.round(diffMs / 1000);
                duration = secs >= 60 ? `${Math.floor(secs/60)}m ${secs%60}s` : `${secs}s`;
            }
        }

        // Check if any sub-log has an error-level entry
        const hasError = grp.logs.some(l => l.level === 'error');
        const statusForCss = grp.status === 'error' || hasError ? 'error' : grp.status;

        // Build inner detail lines
        let detailHtml = '';
        for (const log of grp.logs) {
            const levelIcon = (STATUS_META[log.status] || STATUS_META['info']).icon;
            detailHtml += `
                <div class="log-group-detail-line" style="padding:4px 12px;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;display:flex;gap:8px;align-items:flex-start;">
                    <span style="color:#a0aec0;white-space:nowrap;min-width:140px;">${log.timestamp || ''}</span>
                    <span>${levelIcon}</span>
                    <span style="color:#cbd5e0;flex:1;word-break:break-word;">${escapeHtml(log.message || '')}</span>
                </div>`;
        }

        const cat = grp.category;
        const dataAttrs = `data-status="${grp.status}" data-source="${grp.source}" data-level="" data-category="${cat}"`;

        return `
            <div class="log-entry log-group-card" ${dataAttrs}
                 style="border-left:3px solid ${borderColor};margin-bottom:6px;border-radius:6px;background:rgba(26,32,44,0.6);">
                <div class="log-group-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'; this.querySelector('.expand-arrow').textContent = this.nextElementSibling.style.display === 'none' ? '\u25B6' : '\u25BC';"
                     style="padding:10px 14px;cursor:pointer;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                    <span class="expand-arrow" style="color:#a0aec0;font-size:10px;width:12px;">\u25B6</span>
                    <span style="font-weight:600;color:#e2e8f0;font-size:14px;">${sm.icon} ${escapeHtml(displayName)}</span>
                    ${makeStatusBadge(grp.status)}
                    ${makeCategoryBadge(cat)}
                    ${hasError && grp.status !== 'error' ? '<span style="background:#e53e3e;color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;">Has Errors</span>' : ''}
                    <span style="color:#a0aec0;font-size:12px;margin-left:auto;">${grp.firstTs}${duration ? ` &middot; ${duration}` : ''} &middot; ${detailCount} logs</span>
                </div>
                <div class="log-group-details" style="display:none;border-top:1px solid rgba(255,255,255,0.1);max-height:400px;overflow-y:auto;">
                    ${detailHtml}
                </div>
            </div>`;
    }

    function renderStandaloneLine(log) {
        const sm = STATUS_META[log.status] || STATUS_META['info'];
        let statusClass = log.status || log.level || 'info';
        if (['received','scheduled','starting'].includes(statusClass)) statusClass = 'info';

        const sourceBadge = log.source
            ? `<span style="background:${log.source === 'worker' ? '#667eea' : '#ed8936'};color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;">${log.source.toUpperCase()}</span>`
            : '';

        return `
            <div class="log-entry log-${statusClass}" data-status="${log.status || ''}" data-source="${log.source || ''}" data-level="${log.level || ''}" data-category="${log.category || ''}">
                <div class="log-header">
                    <span class="log-time">${log.timestamp || ''}</span>
                    <span class="log-level ${statusClass}">
                        ${sm.icon} ${log.level ? log.level.toUpperCase() : ''}
                        ${log.process ? `/ ${log.process}` : ''}
                    </span>
                    ${sourceBadge}${makeCategoryBadge(log.category)}${makeStatusBadge(log.status)}
                </div>
                <div class="log-message">${escapeHtml(log.message || '')}</div>
            </div>`;
    }

    // Keep original flat render for individual task logs (non-"all" mode)
    function renderFlatLogs(logs) {
        if (!logs || logs.length === 0) {
            return '<div class="logs-empty"><p>No logs to display</p></div>';
        }
        let html = '';
        for (const log of logs) {
            const sm = STATUS_META[log.status] || STATUS_META['info'];
            let statusClass = log.status || log.level || 'info';
            if (['received','scheduled','starting'].includes(statusClass)) statusClass = 'info';
            html += `
                <div class="log-entry log-${statusClass}" data-status="${log.status || ''}" data-source="${log.source || ''}" data-level="${log.level || ''}" data-category="${log.category || ''}">
                    <div class="log-header">
                        <span class="log-time">${log.timestamp || ''}</span>
                        <span class="log-level ${statusClass}">
                            ${sm.icon} ${log.level ? log.level.toUpperCase() : ''}
                            ${log.process ? `/ ${log.process}` : ''}
                        </span>
                    </div>
                    <div class="log-message">${escapeHtml(log.message || '')}</div>
                </div>`;
        }
        return html;
    }

    function applyLogFilters() {
        const statusFilter = document.getElementById('filterStatus').value;
        const sourceFilter = document.getElementById('filterSource').value;
        const levelFilter = document.getElementById('filterLevel').value;
        const categoryFilter = document.getElementById('filterCategory').value;

        const entries = document.querySelectorAll('#logsModalBody .log-entry');
        let visibleCount = 0;

        entries.forEach(entry => {
            const status = entry.dataset.status || '';
            const source = entry.dataset.source || '';
            const level = entry.dataset.level || '';
            const category = entry.dataset.category || '';

            let show = true;

            // Handle special status filters
            if (statusFilter === 'completed') {
                // Show only success or error (completed tasks)
                if (status !== 'success' && status !== 'error') show = false;
            } else if (statusFilter === 'active') {
                // Show only received/starting (tasks in progress)
                if (status !== 'received' && status !== 'starting' && status !== 'info') show = false;
            } else if (statusFilter !== 'all' && status !== statusFilter) {
                show = false;
            }

            if (sourceFilter !== 'all' && source && source !== sourceFilter) show = false;
            if (levelFilter !== 'all' && level && level !== levelFilter) show = false;
            if (categoryFilter !== 'all' && category !== categoryFilter) show = false;

            entry.style.display = show ? 'block' : 'none';
            if (show) visibleCount++;
        });

        // Show message if no results
        const body = document.getElementById('logsModalBody');
        const existingMsg = body.querySelector('.filter-no-results');
        if (existingMsg) existingMsg.remove();

        if (visibleCount === 0 && entries.length > 0) {
            const msg = document.createElement('div');
            msg.className = 'filter-no-results logs-empty';
            msg.innerHTML = '<p>No logs match the current filters</p>';
            body.prepend(msg);
        }
    }

    function reloadLogs() {
        if (currentLogMode === 'task') {
            showTaskLogs(currentTaskName, '');
            return;
        }
        // Refresh data only -- keep current filter selections
        const body = document.getElementById('logsModalBody');
        const statusBar = document.getElementById('logsStatusBar');
        const limit = document.getElementById('filterLimit').value;

        body.innerHTML = '<div class="logs-loading">Refreshing logs...</div>';

        fetch(`${CELERY_CONFIG.urls.getAllCeleryLogs}?limit=${limit}`)
            .then(response => response.json())
            .then(data => {
                currentLogs = data.logs || [];
                statusBar.innerHTML = `
                    <div class="logs-status-bar">
                        <div class="status-item">
                            <strong>Worker:</strong>
                            ${data.status?.worker_running ? '<span style="color: #38a169;">\u2705 Running</span>' : '<span style="color: #e53e3e;">\u274C Not Running</span>'}
                        </div>
                        <div class="status-item">
                            <strong>Beat:</strong>
                            ${data.status?.beat_running ? '<span style="color: #38a169;">\u2705 Running</span>' : '<span style="color: #e53e3e;">\u274C Not Running</span>'}
                        </div>
                        <div class="status-item">
                            <strong>Log Entries:</strong> ${data.count || 0}
                        </div>
                    </div>
                `;
                if (data.success && data.logs.length > 0) {
                    body.innerHTML = renderLogs(data.logs);
                    applyLogFilters();
                } else {
                    body.innerHTML = '<div class="logs-empty"><p>No celery logs found.</p></div>';
                }
            })
            .catch(error => {
                body.innerHTML = `<div class="logs-empty"><p>Error refreshing logs: ${error}</p></div>`;
            });
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function showAllCeleryLogs() {
        const modal = document.getElementById('logsModal');
        const title = document.getElementById('logsModalTitle');
        const body = document.getElementById('logsModalBody');
        const filters = document.getElementById('logsFilters');
        const statusBar = document.getElementById('logsStatusBar');

        // Set mode
        currentLogMode = 'all';
        currentTaskName = '';

        // Set title
        title.textContent = 'All Celery Logs';

        // Show filters and set defaults
        filters.style.display = 'flex';
        statusBar.style.display = 'block';

        // Reset filter to default (completed = success + failed)
        document.getElementById('filterStatus').value = 'completed';
        document.getElementById('filterCategory').value = 'all';

        // Show loading
        body.innerHTML = '<div class="logs-loading">Loading celery logs...</div>';

        // Show modal
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Fetch all logs with limit from filter
        const limit = document.getElementById('filterLimit').value;
        fetch(`${CELERY_CONFIG.urls.getAllCeleryLogs}?limit=${limit}`)
            .then(response => response.json())
            .then(data => {
                currentLogs = data.logs || [];

                // Update status bar
                statusBar.innerHTML = `
                    <div class="logs-status-bar">
                        <div class="status-item">
                            <strong>Worker:</strong>
                            ${data.status?.worker_running ? '<span style="color: #38a169;">\u2705 Running</span>' : '<span style="color: #e53e3e;">\u274C Not Running</span>'}
                        </div>
                        <div class="status-item">
                            <strong>Beat:</strong>
                            ${data.status?.beat_running ? '<span style="color: #38a169;">\u2705 Running</span>' : '<span style="color: #e53e3e;">\u274C Not Running</span>'}
                        </div>
                        <div class="status-item">
                            <strong>Log Entries:</strong> ${data.count || 0}
                        </div>
                    </div>
                `;

                if (data.success && data.logs.length > 0) {
                    body.innerHTML = renderLogs(data.logs);
                    // Apply default filter (completed) after rendering
                    applyLogFilters();
                } else if (data.success && data.logs.length === 0) {
                    body.innerHTML = `
                        <div class="logs-empty">
                            <p style="font-size: 48px; margin-bottom: 16px;">\uD83D\uDCCB</p>
                            <p>No celery logs found.</p>
                            <p style="font-size: 13px; margin-top: 8px;">Make sure Celery worker and beat are running.</p>
                        </div>
                    `;
                } else {
                    body.innerHTML = `
                        <div class="logs-empty">
                            <p>Error loading logs: ${data.error || 'Unknown error'}</p>
                        </div>
                    `;
                }
            })
            .catch(error => {
                body.innerHTML = `
                    <div class="logs-empty">
                        <p>Error loading logs: ${error}</p>
                    </div>
                `;
            });
    }

    function closeLogsModal(event) {
        if (event && event.target !== event.currentTarget) return;

        const modal = document.getElementById('logsModal');
        const filters = document.getElementById('logsFilters');
        const statusBar = document.getElementById('logsStatusBar');

        modal.classList.remove('active');
        filters.style.display = 'none';
        statusBar.style.display = 'none';
        document.body.style.overflow = '';

        // Reset state
        currentLogs = [];
        currentLogMode = 'all';
        currentTaskName = '';
    }

    // Close modal on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeLogsModal();
            closeConfigModal();
        }
    });

    // Auto-refresh disabled -- use the Refresh button instead
    // setTimeout(function() {
    //     location.reload();
    // }, 120000);

    // =========================================================================
    // Task Configuration Modal Functions
    // =========================================================================

    let currentConfigTaskKey = '';

    function showTaskConfig(taskKey, displayName) {
        const modal = document.getElementById('configModal');
        const title = document.getElementById('configModalTitle');
        const body = document.getElementById('configModalBody');

        currentConfigTaskKey = taskKey;
        title.textContent = `Configure: ${displayName || taskKey}`;
        body.innerHTML = '<div class="logs-loading">Loading configuration...</div>';

        // Show modal
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Fetch configuration
        fetch(`${CELERY_CONFIG.urls.getTaskConfig}?task_key=${encodeURIComponent(taskKey)}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    body.innerHTML = renderConfigForm(data);
                } else {
                    body.innerHTML = `
                        <div class="logs-empty">
                            <p>Error loading configuration: ${data.error || 'Unknown error'}</p>
                        </div>
                    `;
                }
            })
            .catch(error => {
                body.innerHTML = `
                    <div class="logs-empty">
                        <p>Error loading configuration: ${error}</p>
                    </div>
                `;
            });
    }

    // Store current config data for form rendering
    let currentConfigData = null;

    function renderConfigForm(data) {
        const { task_key, display_name, description, schedule_type, category, fields, values, use_custom_schedule } = data;

        // Schedule type badge
        const scheduleTypeLabel = {
            'crontab': 'Fixed Time',
            'interval': 'Interval',
            'recurring': 'Recurring Window'
        }[schedule_type] || schedule_type;

        const scheduleTypeColor = {
            'crontab': '#3182ce',
            'interval': '#38a169',
            'recurring': '#805ad5'
        }[schedule_type] || '#718096';

        const scheduleTypeIcon = {
            'crontab': '\uD83D\uDD50',
            'interval': '\uD83D\uDD04',
            'recurring': '\uD83D\uDCC5'
        }[schedule_type] || '\u2699\uFE0F';

        currentConfigData = data;

        let html = `
            <div class="config-info">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                    <strong style="font-size: 16px;">${display_name || task_key}</strong>
                    <span style="background: ${scheduleTypeColor}; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                        ${scheduleTypeIcon} ${scheduleTypeLabel}
                    </span>
                </div>
                <p style="color: #4a5568; font-size: 13px; margin: 0;">${description || 'Configure schedule and timing for this task.'}</p>
                ${use_custom_schedule ? '<p style="color: #805ad5; font-size: 12px; margin-top: 8px;"><strong>\u2713</strong> Using custom schedule</p>' : '<p style="color: #718096; font-size: 12px; margin-top: 8px;">Using default schedule (modify to customize)</p>'}
            </div>
            <form class="config-form" id="taskConfigForm">
                <input type="hidden" name="task_key" value="${escapeHtml(task_key)}">
        `;

        // Render based on schedule type
        if (schedule_type === 'crontab') {
            html += `
                <div class="config-section">
                    <h4>\uD83D\uDD50 Run Time (IST)</h4>
                    <p style="font-size: 12px; color: #718096; margin-bottom: 12px;">Set the exact time when this task should run each day.</p>
                    <div class="config-row">
                        <div class="config-field">
                            <label for="schedule_hour">Hour</label>
                            <input type="number" id="schedule_hour" name="schedule_hour" value="${values.schedule_hour || 9}" min="0" max="23" required>
                            <span class="field-help">0-23 (24-hour format)</span>
                        </div>
                        <div class="config-field">
                            <label for="schedule_minute">Minute</label>
                            <input type="number" id="schedule_minute" name="schedule_minute" value="${values.schedule_minute || 0}" min="0" max="59" required>
                            <span class="field-help">0-59</span>
                        </div>
                    </div>
                </div>
            `;
        } else if (schedule_type === 'interval') {
            html += `
                <div class="config-section">
                    <h4>\uD83D\uDD04 Repeat Interval</h4>
                    <p style="font-size: 12px; color: #718096; margin-bottom: 12px;">Set how often this task should repeat.</p>
                    <div class="config-field">
                        <label for="interval_seconds">Interval</label>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <input type="number" id="interval_seconds" name="interval_seconds" value="${values.interval_seconds || 60}" min="1" max="86400" required style="width: 120px;">
                            <span class="field-unit">seconds</span>
                        </div>
                        <span class="field-help">Common: 10s=monitoring, 60s=checks, 300s=polling</span>
                    </div>
                </div>
            `;
        } else if (schedule_type === 'recurring') {
            html += `
                <div class="config-section">
                    <h4>\uD83D\uDCC5 Recurring Window</h4>
                    <p style="font-size: 12px; color: #718096; margin-bottom: 12px;">Task runs repeatedly within a time window each day.</p>

                    <div style="margin-bottom: 16px;">
                        <label style="font-weight: 600; color: #2d3748; font-size: 13px; display: block; margin-bottom: 8px;">Start Time</label>
                        <div class="config-row">
                            <div class="config-field">
                                <label for="recurring_start_hour">Hour</label>
                                <input type="number" id="recurring_start_hour" name="recurring_start_hour" value="${values.recurring_start_hour || 9}" min="0" max="23" required>
                            </div>
                            <div class="config-field">
                                <label for="recurring_start_minute">Minute</label>
                                <input type="number" id="recurring_start_minute" name="recurring_start_minute" value="${values.recurring_start_minute || 0}" min="0" max="59" required>
                            </div>
                        </div>
                    </div>

                    <div style="margin-bottom: 16px;">
                        <label style="font-weight: 600; color: #2d3748; font-size: 13px; display: block; margin-bottom: 8px;">End Time</label>
                        <div class="config-row">
                            <div class="config-field">
                                <label for="recurring_end_hour">Hour</label>
                                <input type="number" id="recurring_end_hour" name="recurring_end_hour" value="${values.recurring_end_hour || 15}" min="0" max="23" required>
                            </div>
                            <div class="config-field">
                                <label for="recurring_end_minute">Minute</label>
                                <input type="number" id="recurring_end_minute" name="recurring_end_minute" value="${values.recurring_end_minute || 30}" min="0" max="59" required>
                            </div>
                        </div>
                    </div>

                    <div class="config-field">
                        <label for="recurring_interval_minutes">Repeat Every</label>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <input type="number" id="recurring_interval_minutes" name="recurring_interval_minutes" value="${values.recurring_interval_minutes || 5}" min="1" max="60" required style="width: 100px;">
                            <span class="field-unit">minutes</span>
                        </div>
                        <span class="field-help">How often to run within the window</span>
                    </div>
                </div>
            `;
        }

        // Always render days of week
        const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        const selectedDays = values.days_of_week || [0, 1, 2, 3, 4];

        html += `
            <div class="config-section">
                <h4>\uD83D\uDCC6 Days of Week</h4>
                <p style="font-size: 12px; color: #718096; margin-bottom: 12px;">Select which days this task should run.</p>
                <div class="days-selector">
        `;

        for (let i = 0; i < 7; i++) {
            const isChecked = selectedDays.includes(i);
            const isWeekend = i >= 5;
            html += `
                <label class="day-checkbox ${isWeekend ? 'weekend' : ''} ${isChecked ? 'active' : ''}">
                    <input type="checkbox" name="days_of_week[]" value="${i}" ${isChecked ? 'checked' : ''} onchange="this.parentElement.classList.toggle('active', this.checked)">
                    <span>${dayNames[i]}</span>
                </label>
            `;
        }

        html += `
                </div>
                <div style="margin-top: 8px;">
                    <button type="button" class="btn btn-sm btn-secondary" onclick="selectAllDays()" style="font-size: 11px; padding: 4px 8px;">Select All</button>
                    <button type="button" class="btn btn-sm btn-secondary" onclick="selectWeekdays()" style="font-size: 11px; padding: 4px 8px; margin-left: 4px;">Weekdays Only</button>
                </div>
            </div>
        `;

        // Render task-specific parameters if available
        const taskParamFields = data.task_param_fields || [];
        const taskParamsValues = data.task_params_values || {};

        if (taskParamFields.length > 0) {
            html += `
                <div class="config-section">
                    <h4>\u2699\uFE0F Task Parameters</h4>
                    <p style="font-size: 12px; color: #718096; margin-bottom: 12px;">Configure task-specific execution parameters.</p>
                    <div class="config-row" style="flex-wrap: wrap; gap: 16px;">
            `;

            for (const field of taskParamFields) {
                const value = taskParamsValues[field.name] !== undefined ? taskParamsValues[field.name] : field.default;
                const minAttr = field.min !== undefined ? `min="${field.min}"` : '';
                const maxAttr = field.max !== undefined ? `max="${field.max}"` : '';

                html += `
                    <div class="config-field" style="min-width: 180px;">
                        <label for="${field.name}">${escapeHtml(field.label)}</label>
                        <input type="number"
                               id="${field.name}"
                               name="${field.name}"
                               value="${value}"
                               ${minAttr} ${maxAttr}
                               required
                               style="width: 100%;">
                        ${field.help ? `<span class="field-help">${escapeHtml(field.help)}</span>` : ''}
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        html += `
            </form>
            <div class="config-warning">
                <p><strong>\u26A0\uFE0F Note:</strong> Saving changes will restart Celery Beat to apply the new schedule. Active tasks may be briefly interrupted.</p>
            </div>
        `;

        return html;
    }

    function selectAllDays() {
        document.querySelectorAll('.days-selector input[type="checkbox"]').forEach(cb => {
            cb.checked = true;
            cb.parentElement.classList.add('active');
        });
    }

    function selectWeekdays() {
        document.querySelectorAll('.days-selector input[type="checkbox"]').forEach((cb, i) => {
            const isWeekday = i < 5;
            cb.checked = isWeekday;
            cb.parentElement.classList.toggle('active', isWeekday);
        });
    }

    function renderField(field, values) {
        const value = values[field.name] !== undefined ? values[field.name] : field.default;
        const min = field.min !== undefined ? `min="${field.min}"` : '';
        const max = field.max !== undefined ? `max="${field.max}"` : '';
        const unit = field.unit ? `<span class="field-unit">${field.unit}</span>` : '';

        return `
            <div class="config-field">
                <label for="${field.name}">${field.label}</label>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <input type="number"
                           id="${field.name}"
                           name="${field.name}"
                           value="${value}"
                           ${min} ${max}
                           required>
                    ${unit}
                </div>
                ${field.help ? `<span class="field-help">${field.help}</span>` : ''}
            </div>
        `;
    }

    function renderDaysField(field, values) {
        const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        const dayValues = values[field.name] || field.default || [0, 1, 2, 3, 4];

        let html = `
            <div class="config-section">
                <h4>${field.label}</h4>
                <div class="days-selector">
        `;

        for (let i = 0; i < 7; i++) {
            const isChecked = dayValues.includes(i) ? 'checked' : '';
            const isWeekend = i >= 5 ? 'weekend' : '';
            html += `
                <label class="day-checkbox ${isWeekend} ${isChecked ? 'active' : ''}">
                    <input type="checkbox"
                           name="${field.name}[]"
                           value="${i}"
                           ${isChecked}
                           onchange="this.parentElement.classList.toggle('active', this.checked)">
                    <span>${dayNames[i]}</span>
                </label>
            `;
        }

        html += `
                </div>
                ${field.help ? `<span class="field-help">${field.help}</span>` : ''}
            </div>
        `;

        return html;
    }

    function closeConfigModal(event) {
        if (event && event.target !== event.currentTarget) return;

        const modal = document.getElementById('configModal');
        modal.classList.remove('active');
        document.body.style.overflow = '';
        currentConfigTaskKey = '';
    }

    function saveTaskConfig() {
        const form = document.getElementById('taskConfigForm');
        if (!form) {
            showStatusToast(currentConfigTaskKey, {error: 'No configuration form found'}, true);
            return;
        }

        const saveBtn = document.getElementById('saveConfigBtn');
        saveBtn.classList.add('loading');
        saveBtn.textContent = 'Saving...';

        const formData = new FormData(form);

        fetch(CELERY_CONFIG.urls.saveTaskConfig, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CELERY_CONFIG.csrfToken,
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            saveBtn.classList.remove('loading');
            saveBtn.textContent = 'Save & Apply';

            if (data.success) {
                closeConfigModal();
                showStatusToast(currentConfigTaskKey, {
                    is_enabled: true,
                    celery: data.celery || {},
                    active_tasks: {},
                    message: data.message
                }, false);

                // Reload page after a brief delay to show updated schedule
                setTimeout(() => {
                    location.reload();
                }, 2000);
            } else {
                showStatusToast(currentConfigTaskKey, {error: data.error || 'Failed to save configuration'}, true);
            }
        })
        .catch(error => {
            saveBtn.classList.remove('loading');
            saveBtn.textContent = 'Save & Apply';
            showStatusToast(currentConfigTaskKey, {error: error.toString()}, true);
        });
    }

    function resetTaskConfig() {
        if (!currentConfigTaskKey) {
            showStatusToast('', {error: 'No task selected'}, true);
            return;
        }

        const resetBtn = document.getElementById('resetConfigBtn');
        resetBtn.classList.add('loading');
        resetBtn.textContent = 'Loading preview...';

        // GET preview first
        fetch(`${CELERY_CONFIG.urls.resetTaskConfig}?task_key=${encodeURIComponent(currentConfigTaskKey)}`)
            .then(r => r.json())
            .then(preview => {
                resetBtn.classList.remove('loading');
                resetBtn.textContent = 'Reset to Defaults';

                if (!preview.success) {
                    showStatusToast(currentConfigTaskKey, {error: preview.error}, true);
                    return;
                }

                if (preview.changed_tasks.length === 0) {
                    alert('This task is already using default schedule. Nothing to reset.');
                    return;
                }

                const t = preview.changed_tasks[0];
                let msg = `Reset "${t.display_name}" to defaults?\n\n`;
                msg += `Current:  ${t.current_summary}\n`;
                msg += `Default:  ${t.default_summary}`;
                if (t.current_params) {
                    msg += `\n\nCustom params will also be reset.`;
                }

                if (!confirm(msg)) return;

                // POST to execute
                _executeReset({ task_key: currentConfigTaskKey });
            })
            .catch(error => {
                resetBtn.classList.remove('loading');
                resetBtn.textContent = 'Reset to Defaults';
                showStatusToast(currentConfigTaskKey, {error: error.toString()}, true);
            });
    }

    function resetAllTaskConfigs() {
        // GET preview first
        fetch(`${CELERY_CONFIG.urls.resetTaskConfig}?reset_all=true`)
            .then(r => r.json())
            .then(preview => {
                if (!preview.success) {
                    showStatusToast('all', {error: preview.error}, true);
                    return;
                }

                const tasks = preview.changed_tasks;

                if (tasks.length === 0) {
                    alert('All tasks are already using default schedules. Nothing to reset.');
                    return;
                }

                // Build a detailed confirmation message
                let msg = `${tasks.length} task(s) have custom schedules:\n\n`;
                tasks.forEach(t => {
                    msg += `${t.display_name}\n`;
                    msg += `  Current: ${t.current_summary}\n`;
                    msg += `  Default: ${t.default_summary}\n\n`;
                });
                msg += 'Reset all to defaults? Celery Beat will restart.';

                if (!confirm(msg)) return;

                _executeReset({ reset_all: true });
            })
            .catch(error => {
                showStatusToast('all', {error: error.toString()}, true);
            });
    }

    function _executeReset(payload) {
        fetch(CELERY_CONFIG.urls.resetTaskConfig, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CELERY_CONFIG.csrfToken,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                closeConfigModal();
                showStatusToast(payload.task_key || 'all', {
                    is_enabled: true,
                    celery: data.celery || {},
                    active_tasks: {},
                    message: data.message
                }, false);
                setTimeout(() => location.reload(), 2000);
            } else {
                showStatusToast(payload.task_key || 'all', {error: data.error || 'Failed to reset'}, true);
            }
        })
        .catch(error => {
            showStatusToast(payload.task_key || 'all', {error: error.toString()}, true);
        });
    }

    // =========================================================================
    // 24-HOUR TIMELINE VISUALIZATION
    // =========================================================================

    // Create global tooltip element
    let globalTooltip = null;

    function createGlobalTooltip() {
        if (globalTooltip) return;
        globalTooltip = document.createElement('div');
        globalTooltip.className = 'task-tooltip';
        globalTooltip.id = 'global-task-tooltip';
        document.body.appendChild(globalTooltip);
    }

    function showTooltip(marker, event) {
        if (!globalTooltip) createGlobalTooltip();

        const content = marker.dataset.tooltipContent;
        if (!content) return;

        globalTooltip.innerHTML = content;
        globalTooltip.classList.add('visible');

        // Position tooltip above the marker
        const rect = marker.getBoundingClientRect();
        const tooltipRect = globalTooltip.getBoundingClientRect();

        let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
        let top = rect.top - tooltipRect.height - 15;

        // Keep tooltip within viewport
        if (left < 10) left = 10;
        if (left + tooltipRect.width > window.innerWidth - 10) {
            left = window.innerWidth - tooltipRect.width - 10;
        }
        if (top < 10) {
            // Show below marker if not enough space above
            top = rect.bottom + 15;
        }

        globalTooltip.style.left = `${left}px`;
        globalTooltip.style.top = `${top}px`;
    }

    function hideTooltip() {
        if (globalTooltip) {
            globalTooltip.classList.remove('visible');
        }
    }

    const CATEGORY_COLORS = {
        'data': '#3182ce',
        'strategies': '#805ad5',
        'monitoring': '#dd6b20',
        'risk': '#e53e3e',
        'reports': '#38a169'
    };

    // Task schedule data from server (serialized as JSON in the template bridge)
    const taskSchedule = CELERY_CONFIG.taskSchedule || [];

    function parseScheduleTime(schedule, scheduleType) {
        // Parse time from schedule string
        // Formats: "08:30", "crontab(hour=8, minute=30)", "Every 10s", "09:00-15:30 (every 5m)"

        if (scheduleType === 'interval') {
            return null; // Interval tasks run continuously, no specific time
        }

        // Try HH:MM format
        const timeMatch = schedule.match(/^(\d{1,2}):(\d{2})/);
        if (timeMatch) {
            return { hour: parseInt(timeMatch[1]), minute: parseInt(timeMatch[2]) };
        }

        // Try crontab format
        const crontabMatch = schedule.match(/hour=(\d+).*minute=(\d+)/);
        if (crontabMatch) {
            return { hour: parseInt(crontabMatch[1]), minute: parseInt(crontabMatch[2]) };
        }

        // Try recurring format
        const recurringMatch = schedule.match(/^(\d{1,2}):(\d{2})-/);
        if (recurringMatch) {
            return { hour: parseInt(recurringMatch[1]), minute: parseInt(recurringMatch[2]), recurring: true };
        }

        return null;
    }

    function initTimeline() {
        const container = document.getElementById('timeline-hours');
        if (!container) return;

        // Create global tooltip
        createGlobalTooltip();

        // Generate hour columns
        for (let h = 0; h < 24; h++) {
            const hourStr = String(h).padStart(2, '0');
            const div = document.createElement('div');
            div.className = 'hour-column';
            div.dataset.hour = hourStr;

            // Add phase class
            if (h >= 7 && h < 9) {
                div.classList.add('pre-market');
            } else if (h >= 9 && h < 16) {
                div.classList.add('trading-hours');
            } else if (h >= 16 && h < 18) {
                div.classList.add('post-market');
            }

            div.innerHTML = `<div class="hour-label">${hourStr}:00</div>`;
            container.appendChild(div);
        }

        const hourColumns = container.querySelectorAll('.hour-column');
        let nextTaskTime = null;
        const now = new Date();
        const currentMinutes = now.getHours() * 60 + now.getMinutes();

        // Group tasks by hour for stacking
        const tasksByHour = {};

        taskSchedule.forEach(task => {
            // Use direct hour/minute values from server when available,
            // fall back to parsing schedule string
            let time = null;
            if (task.scheduleHour !== null && task.scheduleHour !== undefined) {
                time = { hour: task.scheduleHour, minute: task.scheduleMinute || 0 };
            } else {
                time = parseScheduleTime(task.schedule, task.scheduleType);
            }
            if (!time) return;

            const hourKey = time.hour;
            if (!tasksByHour[hourKey]) {
                tasksByHour[hourKey] = [];
            }
            tasksByHour[hourKey].push({ ...task, time });
        });

        // Add task markers to timeline
        Object.keys(tasksByHour).forEach(hourKey => {
            const hour = parseInt(hourKey);
            const hourColumn = hourColumns[hour];
            if (!hourColumn) return;

            const tasks = tasksByHour[hourKey];
            const verticalSpacing = 160 / (tasks.length + 1);

            tasks.forEach((task, index) => {
                const marker = document.createElement('div');
                marker.className = 'task-marker';

                // Position based on minute and stack index - spread horizontally within hour
                const minuteOffset = (task.time.minute / 60) * 80 + 10; // 10-90% range
                const topPosition = 20 + (index * 35); // Stack vertically with 35px spacing

                marker.style.left = `${minuteOffset}%`;
                marker.style.top = `${topPosition}px`;

                const dot = document.createElement('div');
                dot.className = `task-dot ${task.isActive ? 'active' : ''}`;
                dot.style.background = task.isActive ? task.color : '#a0aec0';

                // Calculate next execution time
                const taskHour = task.time.hour;
                const taskMinute = task.time.minute;
                const taskTime = `${String(taskHour).padStart(2, '0')}:${String(taskMinute).padStart(2, '0')}`;

                let nextExecDisplay = '';
                if (task.isActive) {
                    const todayTask = new Date();
                    todayTask.setHours(taskHour, taskMinute, 0, 0);
                    if (todayTask > now) {
                        const diffMs = todayTask - now;
                        const diffMins = Math.round(diffMs / 60000);
                        if (diffMins < 60) {
                            nextExecDisplay = `<div class="tooltip-next">\u23F1 Runs in <strong>${diffMins} min</strong></div>`;
                        } else {
                            const hours = Math.floor(diffMins / 60);
                            const mins = diffMins % 60;
                            nextExecDisplay = `<div class="tooltip-next">\u23F1 Runs in <strong>${hours}h ${mins}m</strong></div>`;
                        }
                    } else {
                        nextExecDisplay = `<div class="tooltip-next">\u23F1 Next run <strong>tomorrow ${taskTime}</strong></div>`;
                    }
                }

                // Last execution info
                let lastExecDisplay = '';
                if (task.lastExecution) {
                    const statusIcon = task.lastExecution.success ? '\u2705' : '\u274C';
                    const statusClass = task.lastExecution.success ? 'success' : 'failed';
                    const duration = task.lastExecution.durationMs
                        ? ` (${task.lastExecution.durationMs}ms)`
                        : '';
                    lastExecDisplay = `
                        <div class="tooltip-last-exec ${statusClass}">
                            <div class="exec-header">${statusIcon} Last run: ${task.lastExecution.timestampDisplay}${duration}</div>
                            ${task.lastExecution.message ? `<div class="exec-message">${task.lastExecution.message}</div>` : ''}
                        </div>
                    `;
                } else {
                    lastExecDisplay = `<div class="tooltip-last-exec none">No execution history</div>`;
                }

                const tooltipContent = `
                    <div class="tooltip-header">
                        <div class="tooltip-title">${task.name}</div>
                        <div class="tooltip-category" style="background: ${task.color}20; color: ${task.color};">${task.categoryName || task.category}</div>
                    </div>
                    ${task.description ? `<div class="tooltip-desc">${task.description}</div>` : ''}
                    <div class="tooltip-schedule">
                        <span class="schedule-time">\uD83D\uDD50 ${taskTime}</span>
                        <span class="tooltip-status ${task.isActive ? 'active' : 'inactive'}">
                            ${task.isActive ? '\u25CF Active' : '\u25CB Inactive'}
                        </span>
                    </div>
                    ${nextExecDisplay}
                    ${lastExecDisplay}
                `;

                // Store tooltip content as data attribute
                marker.dataset.tooltipContent = tooltipContent;

                // Add hover event listeners
                marker.addEventListener('mouseenter', function(e) {
                    showTooltip(this, e);
                });
                marker.addEventListener('mouseleave', hideTooltip);

                marker.appendChild(dot);
                hourColumn.appendChild(marker);

                // Track next task
                const taskMinutes = task.time.hour * 60 + task.time.minute;
                if (task.isActive && taskMinutes > currentMinutes) {
                    if (!nextTaskTime || taskMinutes < nextTaskTime.minutes) {
                        nextTaskTime = {
                            minutes: taskMinutes,
                            display: `${String(task.time.hour).padStart(2, '0')}:${String(task.time.minute).padStart(2, '0')}`
                        };
                    }
                }
            });
        });

        // Update next task display
        const nextTaskEl = document.getElementById('next-task-time');
        if (nextTaskEl && nextTaskTime) {
            nextTaskEl.textContent = nextTaskTime.display;
        }

        // Show current time indicator
        updateNowLine();
        setInterval(updateNowLine, 60000); // Update every minute
    }

    function updateNowLine() {
        const now = new Date();
        const hour = now.getHours();
        const minute = now.getMinutes();

        const container = document.getElementById('timeline-hours');
        const nowLine = document.getElementById('now-line');
        if (!container || !nowLine) return;

        // Calculate position
        const hourWidth = container.offsetWidth / 24;
        const position = (hour * hourWidth) + (minute / 60 * hourWidth);

        nowLine.style.left = `${position}px`;
        nowLine.style.display = 'block';
    }

    // Initialize timeline when page loads
    document.addEventListener('DOMContentLoaded', initTimeline);

    // ========================================
    // RECENT EXECUTIONS
    // ========================================

    function loadRecentExecutions() {
        fetch(CELERY_CONFIG.urls.apiRecentExecutions)
            .then(r => r.json())
            .then(data => {
                if (!data.success) return;
                renderExecutions(data.executions);
            })
            .catch(err => console.error('Failed to load recent executions:', err));
    }

    function renderExecutions(executions) {
        const container = document.getElementById('recent-executions-list');
        const countEl = document.getElementById('exec-count');

        if (!executions || executions.length === 0) {
            container.innerHTML = '<div class="exec-empty">No task executions recorded today</div>';
            countEl.textContent = '';
            return;
        }

        countEl.textContent = `(${executions.length} today)`;

        let html = '';
        for (const exec of executions) {
            const statusIcon = exec.status === 'success' ? '&#10004;'
                : exec.status === 'failed' ? '&#10008;'
                : '&#9881;';
            const statusClass = exec.status;

            const startDate = new Date(exec.start_time);
            const endDate = new Date(exec.end_time);
            const startStr = startDate.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
            const endStr = endDate.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

            let durationStr = '';
            if (exec.execution_time_ms !== null && exec.execution_time_ms !== undefined) {
                const secs = (exec.execution_time_ms / 1000).toFixed(1);
                durationStr = `${secs}s`;
            } else if (exec.status !== 'running') {
                const diffMs = endDate - startDate;
                const secs = (diffMs / 1000).toFixed(1);
                durationStr = `~${secs}s`;
            }

            const badgeLabel = exec.status === 'success' ? 'Success'
                : exec.status === 'failed' ? 'Failed'
                : 'Running';

            // Steps HTML
            let stepsHtml = '';
            for (const step of exec.steps) {
                const stepTime = new Date(step.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
                const levelClass = (step.level === 'warning' || step.level === 'error' || step.level === 'critical') ? ` level-${step.level}` : '';

                stepsHtml += `<div class="execution-step">
                    <span class="step-time">${stepTime}</span>
                    <span class="step-action${levelClass}">${step.action}</span>
                    <span class="step-message">${escapeHtml(step.message)}</span>
                </div>`;

                if (step.context_data && Object.keys(step.context_data).length > 0) {
                    const ctxStr = Object.entries(step.context_data)
                        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
                        .join(', ');
                    stepsHtml += `<div class="exec-context-data">${escapeHtml(ctxStr)}</div>`;
                }
            }

            let errorHtml = '';
            if (exec.error_details) {
                errorHtml = `<div class="exec-error-box">${escapeHtml(exec.error_details)}</div>`;
            }

            html += `<div class="execution-card status-${statusClass}" data-taskid="${exec.task_id}">
                <div class="execution-header" onclick="toggleExecution(this)">
                    <span class="exec-status-icon">${statusIcon}</span>
                    <span class="exec-name" title="${escapeHtml(exec.display_name)}">${escapeHtml(exec.display_name)}</span>
                    <span class="exec-time">${startStr} &rarr; ${endStr}</span>
                    <span class="exec-duration">${durationStr}</span>
                    <span class="exec-badge ${statusClass}">${badgeLabel}</span>
                    <span class="exec-chevron">&#9654;</span>
                </div>
                <div class="execution-details">
                    <div class="exec-metrics">
                        <span>Steps: ${exec.steps.length}</span>
                        ${exec.warnings_count > 0 ? `<span style="color:#d69e2e">Warnings: ${exec.warnings_count}</span>` : ''}
                        ${exec.errors_count > 0 ? `<span style="color:#e53e3e">Errors: ${exec.errors_count}</span>` : ''}
                        ${durationStr ? `<span>Duration: ${durationStr}</span>` : ''}
                    </div>
                    <div class="execution-steps">${stepsHtml}</div>
                    ${errorHtml}
                </div>
            </div>`;
        }

        container.innerHTML = html;
    }

    function toggleRecentExecutions() {
        document.getElementById('recent-executions-section').classList.toggle('expanded');
    }

    function toggleExecution(headerEl) {
        const card = headerEl.closest('.execution-card');
        card.classList.toggle('expanded');
    }

    // Load on page ready + auto-refresh every 30s
    document.addEventListener('DOMContentLoaded', function() {
        loadRecentExecutions();
        setInterval(loadRecentExecutions, 30000);
    });

    // =========================================================================
    // KEBAB DROPDOWN MENU
    // =========================================================================

    function toggleKebab(btn) {
        var dropdown = btn.nextElementSibling;
        var wasOpen = dropdown.classList.contains('show');

        // Close all open kebab dropdowns first
        document.querySelectorAll('.kebab-dropdown.show').forEach(function(d) {
            d.classList.remove('show');
        });

        if (!wasOpen) {
            dropdown.classList.add('show');
            // Close on outside click
            setTimeout(function() {
                document.addEventListener('click', function closeKebab(e) {
                    if (!btn.contains(e.target) && !dropdown.contains(e.target)) {
                        dropdown.classList.remove('show');
                        document.removeEventListener('click', closeKebab);
                    }
                });
            }, 0);
        }
    }

    // =========================================================================
    // SLIDE-IN LOGS PANEL
    // =========================================================================

    var _panelCurrentMode = null; // 'task' or 'all'
    var _panelCurrentTaskKey = null;
    var _panelCurrentTaskPath = null;
    var _panelAutoRefreshInterval = null;
    var _panelAllLogs = [];

    function openLogsPanel(mode, taskKey, taskPath) {
        var panel = document.getElementById('logsPanel');
        var title = document.getElementById('logsPanelTitle');
        var body = document.getElementById('logsPanelBody');
        var filtersEl = document.getElementById('logsPanelFilters');

        _panelCurrentMode = mode;
        _panelCurrentTaskKey = taskKey;
        _panelCurrentTaskPath = taskPath;

        if (mode === 'all') {
            title.textContent = 'All Celery Logs';
            filtersEl.style.display = 'flex';
        } else {
            title.textContent = (taskKey || '').replace(/-/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); }) + ' Logs';
            filtersEl.style.display = 'flex';
        }

        body.innerHTML = '<div class="logs-loading">Loading logs...</div>';
        panel.classList.add('open');
        document.body.style.marginRight = '42%';

        reloadPanelLogs();
    }

    function closeLogsPanel() {
        var panel = document.getElementById('logsPanel');
        panel.classList.remove('open');
        document.body.style.marginRight = '';

        if (_panelAutoRefreshInterval) {
            clearInterval(_panelAutoRefreshInterval);
            _panelAutoRefreshInterval = null;
        }
        _panelCurrentMode = null;
        _panelCurrentTaskKey = null;
    }

    function switchLogTab(tab, btn) {
        // Update tab buttons
        document.querySelectorAll('.logs-panel-tabs button').forEach(function(b) {
            b.classList.remove('active');
        });
        btn.classList.add('active');

        var body = document.getElementById('logsPanelBody');

        if (tab === 'activity') {
            // Load recent activity/executions
            body.innerHTML = '<div class="logs-loading">Loading activity...</div>';
            fetch(CELERY_CONFIG.urls.apiRecentExecutions)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.success || !data.executions || data.executions.length === 0) {
                        body.innerHTML = '<div class="logs-loading">No recent activity</div>';
                        return;
                    }
                    var html = '';
                    data.executions.forEach(function(exec) {
                        var statusIcon = exec.status === 'success' ? '&#10004;' : exec.status === 'failed' ? '&#10008;' : '&#9881;';
                        var statusClass = exec.status === 'success' ? 'color:#48bb78' : exec.status === 'failed' ? 'color:#e53e3e' : 'color:#d69e2e';
                        var time = new Date(exec.start_time).toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit', hour12: false});
                        html += '<div style="padding:8px 20px; border-bottom:1px solid #edf2f7; font-size:13px;">';
                        html += '<span style="' + statusClass + '">' + statusIcon + '</span> ';
                        html += '<strong>' + escapeHtml(exec.display_name) + '</strong> ';
                        html += '<span style="color:#a0aec0;">' + time + '</span>';
                        if (exec.execution_time_ms) {
                            html += ' <span style="color:#718096;">(' + (exec.execution_time_ms / 1000).toFixed(1) + 's)</span>';
                        }
                        html += '</div>';
                    });
                    body.innerHTML = html;
                })
                .catch(function() {
                    body.innerHTML = '<div class="logs-loading">Failed to load activity</div>';
                });
        } else {
            // Reload logs
            reloadPanelLogs();
        }
    }

    function reloadPanelLogs() {
        var body = document.getElementById('logsPanelBody');
        var limit = document.getElementById('panelFilterLimit').value || '100';

        var url;
        if (_panelCurrentMode === 'all') {
            url = CELERY_CONFIG.urls.getAllCeleryLogs + '?limit=' + limit;
        } else if (_panelCurrentTaskKey) {
            url = CELERY_CONFIG.urls.getTaskLogs + '?task_name=' + encodeURIComponent(_panelCurrentTaskKey) + '&limit=' + limit;
        } else {
            body.innerHTML = '<div class="logs-loading">No task selected</div>';
            return;
        }

        body.innerHTML = '<div class="logs-loading">Loading logs...</div>';

        fetch(url)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (_panelCurrentMode === 'all') {
                    _panelAllLogs = data.logs || [];
                    applyPanelLogFilters();
                } else {
                    _panelAllLogs = data.logs || [];
                    applyPanelLogFilters();
                }
                var countEl = document.getElementById('logsPanelCount');
                if (countEl) countEl.textContent = (_panelAllLogs.length) + ' logs';
            })
            .catch(function(err) {
                body.innerHTML = '<div class="logs-loading">Failed to load logs: ' + err.message + '</div>';
            });
    }

    function applyPanelLogFilters() {
        var statusFilter = document.getElementById('panelFilterStatus').value;
        var sourceFilter = document.getElementById('panelFilterSource').value;
        var levelFilter = document.getElementById('panelFilterLevel').value;
        var categoryFilter = document.getElementById('panelFilterCategory').value;

        var filtered = _panelAllLogs.filter(function(log) {
            // Status filter
            if (statusFilter === 'active') {
                if (log.status !== 'running' && log.status !== 'received' && log.status !== 'started') return false;
            } else if (statusFilter === 'completed') {
                if (log.status === 'running' || log.status === 'received' || log.status === 'started') return false;
            } else if (statusFilter === 'success') {
                if (log.status !== 'success' && log.level !== 'info') return false;
            } else if (statusFilter === 'error') {
                if (log.status !== 'failed' && log.level !== 'error' && log.level !== 'critical') return false;
            }

            // Source filter
            if (sourceFilter !== 'all') {
                var src = (log.source || '').toLowerCase();
                if (sourceFilter === 'worker' && src !== 'worker') return false;
                if (sourceFilter === 'beat' && src !== 'beat') return false;
            }

            // Level filter
            if (levelFilter !== 'all') {
                if ((log.level || '').toLowerCase() !== levelFilter) return false;
            }

            // Category filter
            if (categoryFilter !== 'all') {
                if ((log.category || '').toLowerCase() !== categoryFilter) return false;
            }

            return true;
        });

        renderPanelLogs(filtered);
    }

    function renderPanelLogs(logs) {
        var body = document.getElementById('logsPanelBody');
        var countEl = document.getElementById('logsPanelCount');

        if (!logs || logs.length === 0) {
            body.innerHTML = '<div class="logs-loading">No logs match filters</div>';
            if (countEl) countEl.textContent = '0 logs';
            return;
        }
        if (countEl) countEl.textContent = logs.length + ' logs';

        var html = '';
        logs.forEach(function(log) {
            var levelClass = '';
            var level = (log.level || 'info').toLowerCase();
            if (level === 'error' || level === 'critical') levelClass = ' style="border-left:3px solid #e53e3e;"';
            else if (level === 'warning') levelClass = ' style="border-left:3px solid #d69e2e;"';
            else levelClass = ' style="border-left:3px solid #48bb78;"';

            var time = '';
            if (log.timestamp) {
                try {
                    time = new Date(log.timestamp).toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit', second:'2-digit', hour12: false});
                } catch(e) { time = log.timestamp; }
            }

            var taskName = log.task_name || log.background_task || '';
            taskName = taskName.replace(/-/g, ' ').replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });

            html += '<div class="panel-log-entry"' + levelClass + '>';
            html += '<div style="display:flex; justify-content:space-between; margin-bottom:2px;">';
            html += '<strong style="font-size:12px;">' + escapeHtml(taskName) + '</strong>';
            html += '<span style="color:#a0aec0; font-size:11px;">' + time + '</span>';
            html += '</div>';
            if (log.message) {
                html += '<div style="font-size:12px; color:#4a5568;">' + escapeHtml(log.message.substring(0, 200)) + '</div>';
            }
            if (log.category) {
                html += '<span class="category-pill" style="font-size:10px; background:#edf2f7; padding:1px 6px; border-radius:10px; color:#718096;">' + escapeHtml(log.category) + '</span>';
            }
            html += '</div>';
        });

        body.innerHTML = html;
    }

    function toggleAutoRefreshLogs() {
        var checkbox = document.getElementById('autoRefreshLogs');
        if (checkbox.checked) {
            _panelAutoRefreshInterval = setInterval(reloadPanelLogs, 10000);
        } else {
            if (_panelAutoRefreshInterval) {
                clearInterval(_panelAutoRefreshInterval);
                _panelAutoRefreshInterval = null;
            }
        }
    }

    // =========================================================================
    // TIMELINE ZOOM TOGGLE
    // =========================================================================

    function setTimelineZoom(mode) {
        var container = document.getElementById('timeline-hours');
        var tradingBtn = document.getElementById('zoom-trading');
        var fullBtn = document.getElementById('zoom-full');
        if (!container) return;

        if (mode === 'trading') {
            container.classList.add('trading-hours-only');
            if (tradingBtn) tradingBtn.classList.add('active');
            if (fullBtn) fullBtn.classList.remove('active');
            container.scrollLeft = 0;
        } else {
            container.classList.remove('trading-hours-only');
            if (tradingBtn) tradingBtn.classList.remove('active');
            if (fullBtn) fullBtn.classList.add('active');
            // Scroll to 8 AM area
            var hourWidth = container.scrollWidth / 24;
            container.scrollLeft = hourWidth * 8;
        }
    }

    // =========================================================================
    // TASK PRESETS
    // =========================================================================

    function applyPreset(presetName) {
        if (!confirm('Apply preset "' + presetName + '"? This will toggle tasks accordingly.')) return;

        // Built-in presets
        var presets = {
            'full-trading': null, // Server-side
            'futures-only': null,
            'options-only': null,
            'data-monitoring': null,
            'all-off': null,
        };

        fetch(CELERY_CONFIG.urls.controlCategoryTasks, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': CELERY_CONFIG.csrfToken,
            },
            body: 'action=preset&preset_name=' + encodeURIComponent(presetName),
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                showStatusToast('preset', {message: 'Preset "' + presetName + '" applied successfully'});
                setTimeout(function() { location.reload(); }, 1500);
            } else {
                showStatusToast('preset', {message: data.error || 'Failed to apply preset'}, true);
            }
        })
        .catch(function(err) {
            showStatusToast('preset', {message: 'Error: ' + err.message}, true);
        });
    }

    function saveCurrentPreset() {
        var name = prompt('Enter preset name:');
        if (!name) return;

        fetch(CELERY_CONFIG.urls.controlCategoryTasks, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': CELERY_CONFIG.csrfToken,
            },
            body: 'action=save_preset&preset_name=' + encodeURIComponent(name),
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                showStatusToast('preset', {message: 'Preset "' + name + '" saved'});
            } else {
                showStatusToast('preset', {message: data.error || 'Failed to save preset'}, true);
            }
        })
        .catch(function(err) {
            showStatusToast('preset', {message: 'Error: ' + err.message}, true);
        });
    }

    // =========================================================================
    // STATUS BAR UPDATES
    // =========================================================================

    function updateStatusBarCounts(enabledDelta) {
        var countEl = document.getElementById('statusbar-active-count');
        if (!countEl) return;
        var current = parseInt(countEl.textContent) || 0;
        var newCount = current + enabledDelta;
        countEl.textContent = newCount + '/' + CELERY_CONFIG.totalCount + ' active';
    }

    // =========================================================================
    // Expose functions needed by HTML onclick attributes
    // =========================================================================
    window.toggleTask = toggleTask;
    window.toggleStaticTask = toggleStaticTask;
    window.runTaskNow = runTaskNow;
    window.showTaskLogs = showTaskLogs;
    window.showAllCeleryLogs = showAllCeleryLogs;
    window.closeLogsModal = closeLogsModal;
    window.showTaskConfig = showTaskConfig;
    window.closeConfigModal = closeConfigModal;
    window.saveTaskConfig = saveTaskConfig;
    window.resetTaskConfig = resetTaskConfig;
    window.resetAllTaskConfigs = resetAllTaskConfigs;
    window.selectAllDays = selectAllDays;
    window.selectWeekdays = selectWeekdays;
    window.handleNotificationChange = handleNotificationChange;
    window.confirmAutonomous = confirmAutonomous;
    window.cancelAutonomous = cancelAutonomous;
    window.handleFuturesToggle = handleFuturesToggle;
    window.handleOptionsChange = handleOptionsChange;
    window.toggleRecentExecutions = toggleRecentExecutions;
    window.toggleExecution = toggleExecution;
    window.hideStatusToast = hideStatusToast;
    window.applyLogFilters = applyLogFilters;
    window.reloadLogs = reloadLogs;

    window.cancelAlgoAction = cancelAlgoAction;

    // New Phase 2-5 functions
    window.toggleKebab = toggleKebab;
    window.openLogsPanel = openLogsPanel;
    window.closeLogsPanel = closeLogsPanel;
    window.switchLogTab = switchLogTab;
    window.applyPanelLogFilters = applyPanelLogFilters;
    window.reloadPanelLogs = reloadPanelLogs;
    window.toggleAutoRefreshLogs = toggleAutoRefreshLogs;
    window.setTimelineZoom = setTimelineZoom;
    window.applyPreset = applyPreset;
    window.saveCurrentPreset = saveCurrentPreset;
    window.saveCurrentAsPreset = saveCurrentPreset; // alias for template
    window.updateStatusBarCounts = updateStatusBarCounts;
})();
