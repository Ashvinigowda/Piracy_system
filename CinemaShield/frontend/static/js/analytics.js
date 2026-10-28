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

    if (!res.ok) {
      throw new Error(`Analytics request failed: ${res.status}`);
    }

    const data = await res.json();

    // Overview cards
    setText("total-events", data.total_events ?? 0);
    setText("unique-ips", data.unique_ip_count ?? 0);

    // Threat level
    const threats = data.threats || {};
    const riskLevel = threats.risk_level || "low";
    const riskScore = Number(threats.risk_score) || 0;

    const levelEl = document.getElementById("risk-level");

    if (levelEl) {
      levelEl.textContent = riskLevel.toUpperCase();
      levelEl.className = "ai-card-value risk-" + riskLevel;
    }

    // Threat meter
    const fill = document.getElementById("threat-fill");

    if (fill) {
      fill.style.width = Math.min(100, Math.max(0, riskScore)) + "%";
      fill.className = "threat-fill threat-" + riskLevel;
    }

    setText("threat-score", riskScore + " / 100");

    // Mesh status
    const mesh = data.mesh_status || {};
    const nodes = mesh.nodes || {};

    if (mesh.nodes) {
      const totalNodes = Object.keys(nodes).length;
      const onlineNodes = Object.values(nodes).filter(
        (node) => String(node?.status || "").toUpperCase() === "ONLINE"
      ).length;

      setText("total-mesh-nodes", `${onlineNodes} / ${totalNodes} Nodes Online`);
      renderMeshTopology(nodes);
    }

    // Anomalies
    const anomalyList = document.getElementById("anomaly-list");

    if (anomalyList) {
      const anomalies = threats.anomalies || [];

      if (anomalies.length === 0) {
        anomalyList.innerHTML =
          '<p class="empty-state">No anomalies detected — zero-trust distribution verified</p>';
      } else {
        anomalyList.innerHTML = anomalies
          .map(
            (a) => `
              <div class="anomaly-item anomaly-${escapeHTML(a.severity || "unknown")}">
                <div class="anomaly-header">
                  <span class="anomaly-badge">${escapeHTML(
                    String(a.severity || "unknown").toUpperCase()
                  )}</span>
                  <span class="anomaly-type">${escapeHTML(
                    String(a.type || "Unknown").replace(/_/g, " ")
                  )}</span>
                </div>
                <p class="anomaly-msg">${escapeHTML(a.message || "")}</p>
                <p class="anomaly-rec">${escapeHTML(a.recommendation || "")}</p>
              </div>
            `
          )
          .join("");
      }
    }

    // Authentication statistics
    const auth = data.auth_stats || {};
    const rate = Number(auth.success_rate) || 0;

    setText("auth-success", auth.success ?? 0);
    setText("auth-failed", auth.failed ?? 0);
    setText("auth-total", auth.total ?? 0);

    const ringFill = document.getElementById("ring-fill");

    if (ringFill) {
      ringFill.setAttribute(
        "stroke-dasharray",
        `${Math.min(100, Math.max(0, rate))}, 100`
      );
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

/* ── Mesh Topology Renderer ─────────────────────── */
function renderMeshTopology(nodes) {
  const grid = document.getElementById("analytics-mesh-grid");

  if (!grid) return;

  const entries = Object.entries(nodes || {});

  if (entries.length === 0) {
    grid.innerHTML = '<p class="empty-state">No mesh nodes available.</p>';
    return;
  }

  grid.innerHTML = entries
    .map(([key, n]) => {
      const node = n || {};

      const nodeId = node.node_id || key;
      const nodeName =
        node.name ||
        `AI Enmesh Node ${String(nodeId).replace("ENM-", "")}`;

      const port = node.port ?? "";
      const status = String(node.status || "UNKNOWN").toUpperCase();
      const isOnline = status === "ONLINE";

      const shardCount = Number(node.shard_count ?? 0);
      const totalBytes =
        node.total_bytes != null ? Number(node.total_bytes) : null;

      const storage =
        totalBytes !== null && Number.isFinite(totalBytes)
          ? `${(totalBytes / (1024 * 1024)).toFixed(2)} MB`
          : "Unavailable";

      const latency =
        node.latency_ms != null && Number.isFinite(Number(node.latency_ms))
          ? `${Number(node.latency_ms)} ms`
          : "Unavailable";

      const statusClass = isOnline ? "badge-active" : "badge-inactive";

      return `
        <div class="mesh-node-card">
          <div class="mesh-node-header">
            <span class="mesh-node-icon" aria-hidden="true">▦</span>

            <div class="mesh-node-title">
              <strong>${escapeHTML(nodeName)}</strong>
              <span class="mesh-node-region">
                ${escapeHTML(nodeId)}${port !== "" ? ` · Port ${escapeHTML(port)}` : ""}
              </span>
            </div>
          </div>

          <div class="mesh-node-stats">
            <div class="mesh-stat">
              <span class="mesh-stat-lbl">Latency</span>
              <span class="mesh-stat-val">${latency}</span>
            </div>

            <div class="mesh-stat">
              <span class="mesh-stat-lbl">Encrypted Storage</span>
              <span class="mesh-stat-val">
                <strong>${Number.isFinite(shardCount) ? shardCount : 0}</strong>
                shards (${storage})
              </span>
            </div>

            <div class="mesh-stat">
              <span class="mesh-stat-lbl">State</span>
              <span class="${statusClass}">${escapeHTML(status)}</span>
            </div>
          </div>
        </div>
      `;
    })
    .join("");
}

/* ── Timeline Bar Chart ─────────────────────────── */
function buildTimeline(hourly) {
  const chart = document.getElementById("timeline-chart");
  const labels = document.getElementById("timeline-labels");

  if (!chart || !labels) return;

  const values = Object.values(hourly).map(Number);
  const max = Math.max(...values, 1);

  chart.innerHTML = "";
  labels.innerHTML = "";

  for (let h = 0; h < 24; h++) {
    const val = Number(hourly[String(h)] || 0);
    const pct = (val / max) * 100;

    const bar = document.createElement("div");
    bar.className = "tl-bar";
    bar.style.height = Math.max(pct, 2) + "%";
    bar.title = `${h}:00 — ${val} event(s)`;

    if (val > 0) {
      bar.classList.add("tl-bar-active");
    }

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

/* ── Event Breakdown ────────────────────────────── */
function buildEventBreakdown(counts) {
  const container = document.getElementById("event-breakdown");

  if (!container) return;

  const entries = Object.entries(counts);

  if (entries.length === 0) {
    container.innerHTML = '<p class="empty-state">No events recorded yet</p>';
    return;
  }

  const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);

  container.innerHTML = entries
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([action, count]) => {
      const pct = total > 0 ? ((Number(count) / total) * 100).toFixed(1) : 0;
      const cls = getEventClass(action);

      return `
        <div class="event-row">
          <span class="event-name ${cls}">${escapeHTML(action)}</span>

          <div class="event-bar-track">
            <div class="event-bar-fill ${cls}" style="width: ${pct}%"></div>
          </div>

          <span class="event-count">${Number(count) || 0}</span>
        </div>
      `;
    })
    .join("");
}

/* ── Event Classification ──────────────────────── */
function getEventClass(action) {
  const value = String(action).toUpperCase();

  if (
    value.includes("FAIL") ||
    value.includes("EXPIRED") ||
    value.includes("DENIED")
  ) {
    return "ev-danger";
  }

  if (
    value.includes("AUTH") ||
    value.includes("PLAYBACK") ||
    value.includes("KDM")
  ) {
    return "ev-warn";
  }

  if (
    value.includes("AI") ||
    value.includes("FORENSIC") ||
    value.includes("MERKLE")
  ) {
    return "ev-ai";
  }

  return "ev-info";
}

/* ── Forensic Fingerprint ───────────────────────── */
async function generateFingerprint() {
  const theatre =
    document.getElementById("fp-theatre").value.trim() || "THEATRE_001";

  const token =
    document.getElementById("fp-token").value.trim() || "demo-session";

  try {
    const res = await fetch("/api/ai/fingerprint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        theatre_id: theatre,
        token: token,
      }),
    });

    if (!res.ok) {
      throw new Error(`Fingerprint request failed: ${res.status}`);
    }

    const fp = await res.json();

    setText("fp-hash", fp.fingerprint || "Unavailable");
    setText("fp-short", fp.fingerprint_short || "Unavailable");
    setText("fp-trace", fp.traceable ? "Yes" : "No");

    setText(
      "fp-time",
      fp.generated_at ? new Date(fp.generated_at).toLocaleString() : "Unavailable"
    );

    const result = document.getElementById("fingerprint-result");

    if (result) {
      result.style.display = "block";
    }
  } catch (err) {
    console.error("Fingerprint error:", err);
  }
}

/* ── Helpers ────────────────────────────────────── */
function setText(id, val) {
  const el = document.getElementById(id);

  if (el) {
    el.textContent = val ?? "";
  }
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };

    return entities[char];
  });
}
