/* =============================================
   AI ENMESH - Main Application Controller
   Wires telemetry, graph, tooltip, and panel
   ============================================= */

document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('meshCanvas');
    const tooltip = document.getElementById('nodeTooltip');
    const tooltipNodeId = document.getElementById('tooltipNodeId');
    const tooltipStatusBadge = document.getElementById('tooltipStatusBadge');
    const tooltipStatus = document.getElementById('tooltipStatus');
    const tooltipHealth = document.getElementById('tooltipHealth');
    const tooltipLatency = document.getElementById('tooltipLatency');
    const tooltipShards = document.getElementById('tooltipShards');
    const tooltipMovies = document.getElementById('tooltipMovies');
    const tooltipFooter = document.getElementById('tooltipFooter');

    const statTotalNodes = document.getElementById('statTotalNodes');
    const statOnline = document.getElementById('statOnline');
    const statOffline = document.getElementById('statOffline');
    const statShards = document.getElementById('statShards');
    const statMovies = document.getElementById('statMovies');
    const statNetwork = document.getElementById('statNetwork');
    const panelIndicator = document.getElementById('panelIndicator');
    const nodeList = document.getElementById('nodeList');
    const topBarTime = document.getElementById('topBarTime');

    // Initialize graph
    MeshGraph.init(canvas, onNodeHover, onNodeSelect);

    // Clock
    function updateClock() {
        const now = new Date();
        topBarTime.textContent = now.toLocaleTimeString('en-US', { hour12: false });
    }
    updateClock();
    setInterval(updateClock, 1000);

    // Telemetry updates
    Telemetry.onUpdate(data => {
        MeshGraph.updateData(data);
        updatePanel(data);
        updateNodeList(data);
    });
    Telemetry.startPolling(3000);

    // === Tooltip ===
    function onNodeHover(node, cx, cy) {
        if (!node || node.type === 'center') {
            tooltip.classList.remove('visible');
            return;
        }

        const data = node.data || {};
        tooltipNodeId.textContent = node.id;

        const status = node.status || 'OFFLINE';
        tooltipStatusBadge.textContent = status;
        tooltipStatusBadge.className = 'tooltip-status-badge ' +
            (status === 'ONLINE' ? 'online' : status === 'BACKUP' ? 'backup' : 'offline');

        tooltipStatus.textContent = status;
        tooltipStatus.style.color = status === 'ONLINE' ? '#22c55e' : status === 'BACKUP' ? '#eab308' : '#ef4444';

        tooltipHealth.textContent = data.health || 'Unknown';
        tooltipHealth.style.color = data.health === 'HEALTHY' ? '#22c55e' : data.health === 'DEGRADED' ? '#eab308' : '#ef4444';

        const lat = data.latency_ms;
        tooltipLatency.textContent = lat >= 0 ? `${lat} ms` : '—';

        tooltipShards.textContent = data.shard_count || 0;
        tooltipMovies.textContent = data.movie_count || 0;

        if (data.is_backup_for && data.is_backup_for.length > 0) {
            tooltipFooter.textContent = `Backup for: ${data.is_backup_for.join(', ')}`;
            tooltipFooter.style.display = 'block';
        } else {
            tooltipFooter.style.display = 'none';
        }

        // Position tooltip
        const graphRect = document.getElementById('graphContainer').getBoundingClientRect();
        let tx = cx - graphRect.left + 16;
        let ty = cy - graphRect.top - 20;
        if (tx + 220 > graphRect.width) tx = cx - graphRect.left - 230;
        if (ty + 200 > graphRect.height) ty = graphRect.height - 210;
        if (ty < 10) ty = 10;

        tooltip.style.left = tx + 'px';
        tooltip.style.top = ty + 'px';
        tooltip.classList.add('visible');
    }

    function onNodeSelect(node) {
        // Update node list selection
        document.querySelectorAll('.node-list-item').forEach(el => {
            el.classList.toggle('selected', el.dataset.nodeId === (node ? node.id : ''));
        });
    }

    // === Status Panel ===
    function updatePanel(data) {
        if (!data || !data.summary) return;
        const s = data.summary;
        statTotalNodes.textContent = s.total_nodes || 0;
        statOnline.textContent = s.online || 0;
        statOffline.textContent = s.offline || 0;
        statShards.textContent = s.total_shards || 0;
        statMovies.textContent = s.total_movies || 0;

        const ns = s.network_status || 'Unknown';
        statNetwork.textContent = ns;
        statNetwork.className = 'stat-value network-status ' + ns.toLowerCase();

        panelIndicator.className = 'panel-indicator' +
            (ns === 'Operational' ? '' : ns === 'Degraded' ? ' degraded' : ' critical');
    }

    function updateNodeList(data) {
        if (!data || !data.nodes) return;
        const selected = MeshGraph.getSelectedNode();
        const ids = Object.keys(data.nodes).sort();

        nodeList.innerHTML = ids.map(nid => {
            const n = data.nodes[nid];
            let dotClass = 'online';
            if (n.is_backup_for && n.is_backup_for.length > 0) dotClass = 'backup';
            else if (n.status === 'OFFLINE') dotClass = 'offline';
            else if (n.status !== 'ONLINE') dotClass = 'offline';
            const isSelected = selected && selected.id === nid;
            const latStr = n.latency_ms >= 0 ? `${n.latency_ms}ms` : '—';
            return `<div class="node-list-item${isSelected ? ' selected' : ''}" data-node-id="${nid}">
                <span class="node-dot ${dotClass}"></span>
                <span class="node-list-id">${nid}</span>
                <span class="node-list-latency">${latStr}</span>
            </div>`;
        }).join('');

        // Bind click on list items
        nodeList.querySelectorAll('.node-list-item').forEach(el => {
            el.addEventListener('click', () => {
                const node = MeshGraph.getNodeById(el.dataset.nodeId);
                if (node) MeshGraph.setSelectedNode(node);
            });
        });
    }
});
