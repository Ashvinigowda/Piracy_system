/* ═══════════════════════════════════════════
   AI ENMESH — Telemetry Module
   Fetches live data from the backend API
   ═══════════════════════════════════════════ */

const Telemetry = (() => {
    const API_BASE = window.location.origin;
    let _listeners = [];
    let _pollTimer = null;
    let _lastData = null;

    async function fetchTelemetry() {
        try {
            const resp = await fetch(`${API_BASE}/api/mesh/telemetry`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            _lastData = data;
            _listeners.forEach(fn => fn(data));
            return data;
        } catch (err) {
            console.warn('Telemetry fetch failed:', err.message);
            return _lastData;
        }
    }

    function onUpdate(callback) {
        _listeners.push(callback);
    }

    function startPolling(intervalMs = 3000) {
        fetchTelemetry();
        _pollTimer = setInterval(fetchTelemetry, intervalMs);
    }

    function stopPolling() {
        if (_pollTimer) clearInterval(_pollTimer);
    }

    function getLastData() {
        return _lastData;
    }

    async function toggleNode(nodeId, status) {
        try {
            const resp = await fetch(`${API_BASE}/api/mesh/toggle/${nodeId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status })
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            setTimeout(fetchTelemetry, 300);
            return await resp.json();
        } catch (err) {
            console.error('Toggle failed:', err);
            return null;
        }
    }

    return { fetchTelemetry, onUpdate, startPolling, stopPolling, getLastData, toggleNode };
})();
