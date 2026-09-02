/* =============================================
   AI ENMESH - Canvas Network Graph Engine
   Animated mesh topology with particles
   ============================================= */

const MeshGraph = (() => {
    let canvas, ctx, W, H, dpr;
    let nodes = [];
    let edges = [];
    let particles = [];
    let centerNode = null;
    let hoveredNode = null;
    let selectedNode = null;
    let animId = null;
    let _onHover = null, _onSelect = null;

    // Camera / Pan state
    let camX = 0, camY = 0, camScale = 1;
    let isDragging = false, dragStartX = 0, dragStartY = 0, camStartX = 0, camStartY = 0;

    const NODE_RADIUS = 22;
    const CENTER_RADIUS = 32;
    const PARTICLE_SPEED = 0.6;
    const MAX_PARTICLES_PER_EDGE = 5;

    const COLORS = {
        ONLINE:  { fill: '#22c55e', glow: 'rgba(34,197,94,0.35)',  ring: 'rgba(34,197,94,0.6)' },
        BACKUP:  { fill: '#eab308', glow: 'rgba(234,179,8,0.35)',  ring: 'rgba(234,179,8,0.6)' },
        OFFLINE: { fill: '#ef4444', glow: 'rgba(239,68,68,0.35)',  ring: 'rgba(239,68,68,0.6)' },
        CENTER:  { fill: '#00f0ff', glow: 'rgba(0,240,255,0.3)',   ring: 'rgba(0,240,255,0.5)' }
    };

    function init(canvasEl, onHoverCb, onSelectCb) {
        canvas = canvasEl;
        ctx = canvas.getContext('2d');
        _onHover = onHoverCb;
        _onSelect = onSelectCb;
        resize();
        _buildDefaultLayout();
        _bindEvents();
        _startLoop();
    }

    function resize() {
        const rect = canvas.parentElement.getBoundingClientRect();
        dpr = window.devicePixelRatio || 1;
        W = rect.width;
        H = rect.height;
        canvas.width = W * dpr;
        canvas.height = H * dpr;
        canvas.style.width = W + 'px';
        canvas.style.height = H + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        if (centerNode) {
            centerNode.x = W / 2;
            centerNode.y = H / 2;
            _repositionOuterNodes();
        }
    }

    function _buildDefaultLayout() {
        const cx = W / 2, cy = H / 2;
        centerNode = {
            id: 'ENMESH', type: 'center',
            x: cx, y: cy, targetX: cx, targetY: cy,
            radius: CENTER_RADIUS, status: 'CENTER',
            data: null
        };

        const nodeIds = ['ENM-01','ENM-02','ENM-03','ENM-04','ENM-05'];
        const orbitRadius = Math.min(W, H) * 0.3;
        const startAngle = -Math.PI / 2;

        nodes = [centerNode];
        edges = [];

        nodeIds.forEach((id, i) => {
            const angle = startAngle + (2 * Math.PI * i) / nodeIds.length;
            const x = cx + Math.cos(angle) * orbitRadius;
            const y = cy + Math.sin(angle) * orbitRadius;
            const node = {
                id, type: 'cloud',
                x, y, targetX: x, targetY: y,
                radius: NODE_RADIUS, status: 'OFFLINE',
                data: null
            };
            nodes.push(node);
            edges.push({ from: centerNode, to: node, status: 'OFFLINE', particles: [] });
        });
    }

    function _repositionOuterNodes() {
        const cx = centerNode.x, cy = centerNode.y;
        const orbitRadius = Math.min(W, H) * 0.3;
        const startAngle = -Math.PI / 2;
        const outerNodes = nodes.filter(n => n.type === 'cloud');
        outerNodes.forEach((node, i) => {
            const angle = startAngle + (2 * Math.PI * i) / outerNodes.length;
            node.targetX = cx + Math.cos(angle) * orbitRadius;
            node.targetY = cy + Math.sin(angle) * orbitRadius;
        });
    }

    function updateData(telemetryData) {
        if (!telemetryData || !telemetryData.nodes) return;

        const nodeMap = telemetryData.nodes;
        nodes.forEach(node => {
            if (node.type === 'center') return;
            const data = nodeMap[node.id];
            if (data) {
                node.data = data;
                if (data.is_backup_for && data.is_backup_for.length > 0) {
                    node.status = 'BACKUP';
                } else {
                    node.status = data.status || 'OFFLINE';
                }
            }
        });

        edges.forEach(edge => {
            if (edge.to.status === 'ONLINE') {
                edge.status = 'ONLINE';
            } else if (edge.to.status === 'BACKUP') {
                edge.status = 'BACKUP';
            } else {
                edge.status = 'OFFLINE';
            }
        });
    }

    // === RENDERING ===

    function _draw() {
        ctx.clearRect(0, 0, W, H);
        ctx.save();
        ctx.translate(camX, camY);
        ctx.scale(camScale, camScale);

        _drawGrid();
        _drawEdges();
        _drawParticles();
        _drawNodes();

        ctx.restore();
    }

    function _drawGrid() {
        const step = 60;
        ctx.strokeStyle = 'rgba(255,255,255,0.015)';
        ctx.lineWidth = 1;
        const x0 = -camX / camScale, y0 = -camY / camScale;
        const x1 = x0 + W / camScale, y1 = y0 + H / camScale;
        for (let x = Math.floor(x0 / step) * step; x < x1; x += step) {
            ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y1); ctx.stroke();
        }
        for (let y = Math.floor(y0 / step) * step; y < y1; y += step) {
            ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
        }
    }

    function _drawEdges() {
        edges.forEach(edge => {
            const { from, to, status } = edge;
            const isSelected = selectedNode && (selectedNode === to || selectedNode === from);
            const isHovered = hoveredNode && (hoveredNode === to || hoveredNode === from);

            ctx.beginPath();
            ctx.moveTo(from.x, from.y);
            ctx.lineTo(to.x, to.y);

            if (status === 'OFFLINE') {
                ctx.strokeStyle = 'rgba(239,68,68,0.15)';
                ctx.lineWidth = 1;
                ctx.setLineDash([6, 8]);
            } else if (status === 'BACKUP') {
                ctx.strokeStyle = isSelected || isHovered ? 'rgba(234,179,8,0.6)' : 'rgba(234,179,8,0.25)';
                ctx.lineWidth = isSelected ? 2 : 1.5;
                ctx.setLineDash([]);
            } else {
                ctx.strokeStyle = isSelected || isHovered ? 'rgba(0,240,255,0.5)' : 'rgba(0,240,255,0.12)';
                ctx.lineWidth = isSelected ? 2 : 1;
                ctx.setLineDash([]);
            }
            ctx.stroke();
            ctx.setLineDash([]);
        });
    }

    function _drawParticles() {
        edges.forEach(edge => {
            if (edge.status === 'OFFLINE') return;

            // Spawn particles
            if (edge.particles.length < MAX_PARTICLES_PER_EDGE && Math.random() < 0.02) {
                edge.particles.push({ t: 0, speed: PARTICLE_SPEED + Math.random() * 0.3 });
            }

            const { from, to } = edge;
            const color = edge.status === 'BACKUP' ? 'rgba(234,179,8,0.8)' : 'rgba(0,240,255,0.7)';

            edge.particles = edge.particles.filter(p => {
                p.t += p.speed * 0.01;
                if (p.t > 1) return false;

                const px = from.x + (to.x - from.x) * p.t;
                const py = from.y + (to.y - from.y) * p.t;

                ctx.beginPath();
                ctx.arc(px, py, 2, 0, Math.PI * 2);
                ctx.fillStyle = color;
                ctx.fill();

                // Trail
                const trailT = p.t - 0.03;
                if (trailT > 0) {
                    const tx = from.x + (to.x - from.x) * trailT;
                    const ty = from.y + (to.y - from.y) * trailT;
                    ctx.beginPath();
                    ctx.arc(tx, ty, 1.2, 0, Math.PI * 2);
                    ctx.fillStyle = edge.status === 'BACKUP' ? 'rgba(234,179,8,0.3)' : 'rgba(0,240,255,0.3)';
                    ctx.fill();
                }
                return true;
            });
        });
    }

    function _drawNodes() {
        nodes.forEach(node => {
            // Smooth movement
            node.x += (node.targetX - node.x) * 0.08;
            node.y += (node.targetY - node.y) * 0.08;

            const isHov = hoveredNode === node;
            const isSel = selectedNode === node;
            const r = node.radius;
            const colors = node.type === 'center' ? COLORS.CENTER : (COLORS[node.status] || COLORS.OFFLINE);

            // Outer glow
            const glowR = r + (isHov || isSel ? 18 : 10);
            const grad = ctx.createRadialGradient(node.x, node.y, r * 0.5, node.x, node.y, glowR);
            grad.addColorStop(0, colors.glow);
            grad.addColorStop(1, 'transparent');
            ctx.beginPath();
            ctx.arc(node.x, node.y, glowR, 0, Math.PI * 2);
            ctx.fillStyle = grad;
            ctx.fill();

            // Ring
            ctx.beginPath();
            ctx.arc(node.x, node.y, r + 3, 0, Math.PI * 2);
            ctx.strokeStyle = isHov || isSel ? colors.ring : 'rgba(255,255,255,0.08)';
            ctx.lineWidth = isHov || isSel ? 2 : 1;
            ctx.stroke();

            // Core circle
            const coreGrad = ctx.createRadialGradient(node.x - r * 0.2, node.y - r * 0.2, 0, node.x, node.y, r);
            coreGrad.addColorStop(0, 'rgba(30,41,59,0.9)');
            coreGrad.addColorStop(1, 'rgba(15,23,42,0.95)');
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
            ctx.fillStyle = coreGrad;
            ctx.fill();
            ctx.strokeStyle = colors.ring;
            ctx.lineWidth = 1.5;
            ctx.stroke();

            // Inner status dot
            const dotR = node.type === 'center' ? 6 : 4.5;
            ctx.beginPath();
            ctx.arc(node.x, node.y, dotR, 0, Math.PI * 2);
            ctx.fillStyle = colors.fill;
            ctx.fill();

            // Pulsing ring for center
            if (node.type === 'center') {
                const pulsePhase = (Date.now() % 3000) / 3000;
                const pulseR = r + 5 + pulsePhase * 20;
                const pulseAlpha = 0.3 * (1 - pulsePhase);
                ctx.beginPath();
                ctx.arc(node.x, node.y, pulseR, 0, Math.PI * 2);
                ctx.strokeStyle = `rgba(0,240,255,${pulseAlpha})`;
                ctx.lineWidth = 1;
                ctx.stroke();
            }

            // Label
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.font = `600 ${node.type === 'center' ? 13 : 11}px 'JetBrains Mono', monospace`;
            ctx.fillStyle = isHov || isSel ? '#fff' : 'rgba(226,232,240,0.7)';
            ctx.fillText(node.id, node.x, node.y + r + 10);
        });
    }

    // === ANIMATION LOOP ===

    function _startLoop() {
        function loop() {
            _draw();
            animId = requestAnimationFrame(loop);
        }
        loop();
    }

    // === EVENTS ===

    function _bindEvents() {
        canvas.addEventListener('mousemove', _onMouseMove);
        canvas.addEventListener('mousedown', _onMouseDown);
        canvas.addEventListener('mouseup', _onMouseUp);
        canvas.addEventListener('mouseleave', _onMouseLeave);
        canvas.addEventListener('wheel', _onWheel, { passive: false });
        canvas.addEventListener('click', _onClick);
        window.addEventListener('resize', () => { resize(); });
    }

    function _screenToWorld(sx, sy) {
        return { x: (sx - camX) / camScale, y: (sy - camY) / camScale };
    }

    function _hitTest(sx, sy) {
        const { x, y } = _screenToWorld(sx, sy);
        for (let i = nodes.length - 1; i >= 0; i--) {
            const n = nodes[i];
            const dx = x - n.x, dy = y - n.y;
            if (dx * dx + dy * dy <= (n.radius + 8) * (n.radius + 8)) return n;
        }
        return null;
    }

    function _onMouseMove(e) {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;

        if (isDragging) {
            camX = camStartX + (e.clientX - dragStartX);
            camY = camStartY + (e.clientY - dragStartY);
            return;
        }

        const hit = _hitTest(mx, my);
        if (hit !== hoveredNode) {
            hoveredNode = hit;
            canvas.style.cursor = hit ? 'pointer' : 'grab';
            if (_onHover) _onHover(hit, e.clientX, e.clientY);
        } else if (hit && _onHover) {
            _onHover(hit, e.clientX, e.clientY);
        }
    }

    function _onMouseDown(e) {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        const hit = _hitTest(mx, my);
        if (!hit) {
            isDragging = true;
            dragStartX = e.clientX; dragStartY = e.clientY;
            camStartX = camX; camStartY = camY;
            canvas.style.cursor = 'grabbing';
        }
    }

    function _onMouseUp() {
        isDragging = false;
        canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
    }

    function _onMouseLeave() {
        isDragging = false;
        hoveredNode = null;
        canvas.style.cursor = 'grab';
        if (_onHover) _onHover(null, 0, 0);
    }

    function _onWheel(e) {
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        const delta = e.deltaY > 0 ? 0.92 : 1.08;
        const newScale = Math.max(0.4, Math.min(3, camScale * delta));
        const wx = (mx - camX) / camScale;
        const wy = (my - camY) / camScale;
        camScale = newScale;
        camX = mx - wx * camScale;
        camY = my - wy * camScale;
    }

    function _onClick(e) {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        const hit = _hitTest(mx, my);
        selectedNode = (hit === selectedNode) ? null : hit;
        if (_onSelect) _onSelect(selectedNode);
    }

    function getSelectedNode() { return selectedNode; }
    function setSelectedNode(node) {
        selectedNode = node;
        if (_onSelect) _onSelect(selectedNode);
    }
    function getNodeById(id) { return nodes.find(n => n.id === id) || null; }

    return { init, resize, updateData, getSelectedNode, setSelectedNode, getNodeById };
})();
