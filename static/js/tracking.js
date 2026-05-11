/* tracking.js — client-side half of the custom user tracker.
 *
 *   - Reports time-on-page via sendBeacon when the tab is hidden / closed.
 *   - Sends event pings when the visitor selects a country, switches a
 *     metric tab, or clicks a chart-tab on the data page.
 *
 * Server-side page-view logging happens in tracking.py before this script
 * even runs, so tracking still works with JS disabled (just no duration
 * or event data).
 */
(function () {
    var meta = document.querySelector('meta[name="x-pageview-id"]');
    var pageviewId = meta ? parseInt(meta.content, 10) : null;
    var startTs = (window.performance && performance.now) ? performance.now() : Date.now();
    var sent = false;

    function sendDuration() {
        if (sent || !pageviewId) return;
        sent = true;
        var now = (window.performance && performance.now) ? performance.now() : Date.now();
        var duration = Math.round(now - startTs);
        var body = JSON.stringify({
            pageview_id: pageviewId,
            duration_ms: duration
        });
        try {
            if (navigator.sendBeacon) {
                navigator.sendBeacon(
                    '/track/duration',
                    new Blob([body], { type: 'application/json' })
                );
            } else {
                fetch('/track/duration', {
                    method: 'POST',
                    body: body,
                    headers: { 'Content-Type': 'application/json' },
                    keepalive: true
                });
            }
        } catch (e) { /* swallow — tracking must never break the page */ }
    }

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') sendDuration();
    });
    window.addEventListener('pagehide', sendDuration);

    function sendEvent(type, value) {
        try {
            fetch('/track/event', {
                method: 'POST',
                body: JSON.stringify({
                    type: type,
                    value: value || '',
                    path: window.location.pathname
                }),
                headers: { 'Content-Type': 'application/json' },
                keepalive: true
            });
        } catch (e) { /* swallow */ }
    }

    function bindEventListeners() {
        var sel = document.getElementById('country-select');
        if (sel) {
            sel.addEventListener('change', function () {
                if (sel.value) {
                    var label = sel.options[sel.selectedIndex].text;
                    sendEvent('country_select', label);
                }
            });
        }

        document.querySelectorAll('.chart-tab').forEach(function (btn) {
            btn.addEventListener('click', function () {
                sendEvent(
                    'chart_tab',
                    btn.dataset.metric || (btn.textContent || '').trim()
                );
            });
        });

        document.querySelectorAll('.metric-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                sendEvent(
                    'metric_toggle',
                    btn.dataset.field || (btn.textContent || '').trim()
                );
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindEventListeners);
    } else {
        bindEventListeners();
    }
})();
