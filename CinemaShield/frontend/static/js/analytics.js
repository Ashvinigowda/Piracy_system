/* ═══════════════════════════════════════════
   CinemaShield 2.0 — AI Analytics & Mesh JS
   ═══════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", loadAll);

function loadAll() {
  loadAnalyticsSummary();
}

/* ── Summary + Threats + Mesh ──────────────────── */
async function loadAnalyticsSummary() {
  try {
    const res = await fetch("/api/ai/analytics-summary");
    const data = await res.json();

    // Overview cards
    setText("total-events", data.total_events);
    setText("unique-ips", data.unique_ip_count);

    // Threat level
    const threats = data.threats || {};
    const riskLevel = threats.risk_level || "low";
    const riskScore = threats.risk_score || 0;
    const levelEl = document.getElementById("risk-level");
    if (levelEl) {
      levelEl.textContent = riskLevel.toUpperCase();
      levelEl.className = "ai-card-value risk-" + riskLevel;
    }

    // Threat meter
    const fill = document.getElementById("threat-fill");
    if (fill) {
      fill.style.width = riskScore + "%";
      fill.className = "threat-fill threat-" + riskLevel;
    }
    setText("threat-score", riskScore + " / 100");

    // Mesh status
    const mesh = data.mesh_status || {};
    if (mesh.nodes) {
      setText("total-mesh-nodes", `${Object.keys(mesh.nodes).length} Nodes Active`);
      renderMeshTopology(mesh.nodes);
    }

    // Anomalies
    const anomalyList = document.getElementById("anomaly-list");
    if (anomalyList) {
      const anomalies = threats.anomalies || [];
      if (anomalies.length === 0) {
        anomalyList.innerHTML =
          '<p class="empty-state">✅ No anomalies detected — zero-trust distribution verified</p>';
      } else {
        anomalyList.innerHTML = anomalies
          .map(
            (a) => `
          <div class="anomaly-item anomaly-${a.severity}">
            <div class="anomaly-header">
              <span class="anomaly-badge">${a.severity.toUpperCase()}</span>
              <span class="anomaly-type">${a.type.replace(/_/g, " ")}</span>
            </div>
            <p class="anomaly-msg">${a.message}</p>
            <p class="anomaly-rec">💡 ${a.recommendation}</p>
          </div>
        `,
          )
          .join("");
      }
    }

    // Auth stats ring
    const auth = data.auth_stats || {};
    const rate = auth.success_rate || 0;
    setText("auth-success", auth.success || 0);
    setText("auth-failed", auth.failed || 0);
    setText("auth-total", auth.total || 0);
    const ringFill = document.getElementById("ring-fill");
    if (ringFill) {
      ringFill.setAttribute("stroke-dasharray", `${rate}, 100`);
    }
    setText("ring-text", rate + "%");

    // Timeline chart
    buildTimeline(data.hourly_distribution || {});

    // Event breakdown
    buildEventBreakdown(data.action_counts || {});
  } catch (err) {
    console.error("Analytics load error:", err);
  }
}

/* ── Mesh Topology Renderer ─────────────── */
function renderMeshTopology(nodes) {
  const grid = document.getElementById("analytics-mesh-grid");
  if (!grid) return;

  grid.innerHTML = Object.values(nodes).map(n => `
    <div class="mesh-node-card">
      <div class="mesh-node-header">
        <span class="mesh-node-icon">${n.icon}</span>
        <div class="mesh-node-title">
          <strong>${n.name}</strong>
          <span class="mesh-node-region">${n.region} &bull; ${n.provider}</span>
        </div>
      </div>
      <div class="mesh-node-stats">
        <div class="mesh-stat">
          <span class="mesh-stat-lbl">Latency:</span>
          <span class="mesh-stat-val" style="color: var(--success);">${n.latency_ms}ms</span>
        </div>
        <div class="mesh-stat">
          <span class="mesh-stat-lbl">Encrypted Storage:</span>
          <span class="mesh-stat-val"><strong>${n.shard_count}</strong> shards (${n.storage_used_mb} MB)</span>
        </div>
        <div class="mesh-stat">
          <span class="mesh-stat-lbl">State:</span>
          <span class="badge-active">ONLINE</span>
        </div>
      </div>
    </div>
  `).join("");
}

/* ── Timeline Bar Chart ─────────────────── */
function buildTimeline(hourly) {
  const chart = document.getElementById("timeline-chart");
  const labels = document.getElementById("timeline-labels");
  if (!chart || !labels) return;

  const values = Object.values(hourly).map(Number);
  const max = Math.max(...values, 1);

  chart.innerHTML = "";
  labels.innerHTML = "";

  for (let h = 0; h < 24; h++) {
    const val = hourly[String(h)] || 0;
    const pct = (val / max) * 100;

    const bar = document.createElement("div");
    bar.className = "tl-bar";
    bar.style.height = Math.max(pct, 2) + "%";
    bar.title = `${h}:00 — ${val} event(s)`;
    if (val > 0) bar.classList.add("tl-bar-active");
    chart.appendChild(bar);

    if (h % 3 === 0) {
      const lbl = document.createElement("span");
      lbl.className = "tl-label";
      lbl.textContent = String(h).padStart(2, "0");
      lbl.style.left = (h / 24) * 100 + "%";
      labels.appendChild(lbl);
    }
  }
}

/* ── Event Breakdown ────────────────────── */
function buildEventBreakdown(counts) {
  const container = document.getElementById("event-breakdown");
  if (!container) return;

  const entries = Object.entries(counts);
  if (entries.length === 0) {
    container.innerHTML = '<p class="empty-state">No events recorded yet</p>';
    return;
  }

  const total = entries.reduce((s, [, v]) => s + v, 0);

  container.innerHTML = entries
    .sort((a, b) => b[1] - a[1])
    .map(([action, count]) => {
      const pct = ((count / total) * 100).toFixed(1);
      const cls = getEventClass(action);
      return `
        <div class="event-row">
          <span class="event-name ${cls}">${action}</span>
          <div class="event-bar-track">
            <div class="event-bar-fill ${cls}" style="width: ${pct}%"></div>
          </div>
          <span class="event-count">${count}</span>
        </div>`;
    })
    .join("");
}

function getEventClass(action) {
  if (action.includes("FAIL") || action.includes("EXPIRED") || action.includes("DENIED")) return "ev-danger";
  if (action.includes("AUTH") || action.includes("PLAYBACK") || action.includes("KDM")) return "ev-warn";
  if (action.includes("AI") || action.includes("FORENSIC") || action.includes("MERKLE")) return "ev-ai";
  return "ev-info";
}

/* ── Forensic Fingerprint ───────────────── */
async function generateFingerprint() {
  const theatre = document.getElementById("fp-theatre").value.trim() || "THEATRE_001";
  const token = document.getElementById("fp-token").value.trim() || "demo-session";

  try {
    const res = await fetch("/api/ai/fingerprint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theatre_id: theatre, token: token }),
    });
    const fp = await res.json();

    document.getElementById("fp-hash").textContent = fp.fingerprint;
    document.getElementById("fp-short").textContent = fp.fingerprint_short;
    document.getElementById("fp-trace").textContent = fp.traceable ? "✅ Yes" : "❌ No";
    document.getElementById("fp-time").textContent = new Date(fp.generated_at).toLocaleString();
    document.getElementById("fingerprint-result").style.display = "block";
  } catch (err) {
    console.error("Fingerprint error:", err);
  }
}

/* ── Helpers ─────────────────────────────── */
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

