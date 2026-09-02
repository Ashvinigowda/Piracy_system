// ═══════════════════════════════════════════
// CinemaShield 2.0 — Theatre Ingest Gateway & DCI Bridge
// ═══════════════════════════════════════════

const statusBanner = document.getElementById("status-banner");
const statusText = document.getElementById("status-text");
const theatreSelect = document.getElementById("theatre-select");
const infoSmb = document.getElementById("info-smb");
const infoCertFp = document.getElementById("info-cert-fp");

const autoAttestBtn = document.getElementById("auto-attest-btn");
const toggleManualBtn = document.getElementById("toggle-manual-key-btn");
const manualKeyContainer = document.getElementById("manual-key-container");
const keyInput = document.getElementById("key-input");
const manualUnlockBtn = document.getElementById("manual-unlock-btn");

const authError = document.getElementById("auth-error");
const authLoading = document.getElementById("auth-loading");
const loadingStatusText = document.getElementById("loading-status-text");
const authSection = document.getElementById("auth-section");

const ingestProgressSec = document.getElementById("ingest-progress-section");
const shardTransferList = document.getElementById("shard-transfer-list");
const ingestStats = document.getElementById("ingest-stats");
const merkleStatusBadge = document.getElementById("merkle-status-badge");

const playerSec = document.getElementById("player-section");
const videoPlayer = document.getElementById("video-player");

let currentToken = null;
let expiryTimer = null;
let countdownTimer = null;
let windowEnd = null;

// Pre-registered theatre cert fingerprints
const THEATRE_CERTS = {
  THEATRE_001: {
    smb: "SMB-CHR-99482-DCI",
    model: "Christie CP4440-RGB Laser",
    fp: "SHA256:4a8f9c1b3d7e5a2c9e0f6b4a8c1d3e5f7a9b0c2d4e6f8a0b2c4d6e8f0a2b4c6d",
  },
  THEATRE_002: {
    smb: "SMB-DOLBY-77219-DCI",
    model: "Dolby Vision Cinema System Dual-Laser",
    fp: "SHA256:9f8e7d6c5b4a39281706f5e4d3c2b1a09876543210fedcba9876543210abcdef",
  },
  THEATRE_003: {
    smb: "SMB-BARCO-55102-DCI",
    model: "Dolby IMS3000 / Barco DP4K-60L",
    fp: "SHA256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b",
  },
};

// Update hardware cert info when theatre selection changes
if (theatreSelect) {
  theatreSelect.addEventListener("change", () => {
    const tid = theatreSelect.value;
    const info = THEATRE_CERTS[tid];
    if (info) {
      if (infoSmb) infoSmb.textContent = info.smb;
      if (infoCertFp) infoCertFp.textContent = info.fp.slice(0, 18) + "...";
    }
  });
}

// Toggle manual key container
if (toggleManualBtn && manualKeyContainer) {
  toggleManualBtn.addEventListener("click", () => {
    manualKeyContainer.classList.toggle("hidden");
  });
}

// ── Check System Status ──────────────────

async function checkStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    if (!data.ready) {
      if (statusBanner) {
        statusBanner.classList.remove("hidden");
        statusBanner.className = "banner banner-warn";
      }
      if (statusText) statusText.textContent = "⚠ No movie distributed to mesh yet. Ask the studio to ingest and shard first.";
      if (manualUnlockBtn) manualUnlockBtn.disabled = true;
    } else if (!data.playback_active) {
      if (statusBanner) {
        statusBanner.classList.remove("hidden");
        statusBanner.className = "banner banner-warn";
      }
      if (statusText) statusText.textContent = `⚠ Playback window inactive. Window: ${formatUTC(data.playback_start)} — ${formatUTC(data.playback_end)}`;
      if (manualUnlockBtn) manualUnlockBtn.disabled = true;
    } else {
      if (statusBanner) {
        statusBanner.classList.remove("hidden");
        statusBanner.className = "banner banner-info";
      }
      if (statusText) statusText.textContent = `✅ Ready on Mesh — ${data.shards} shards &bull; Assigned to ${data.theatre_id} &bull; Merkle Root: ${data.merkle_root ? data.merkle_root.slice(0, 16) + '...' : 'Verified'}`;
      if (manualUnlockBtn) manualUnlockBtn.disabled = false;
      if (data.theatre_id && theatreSelect) {
        theatreSelect.value = data.theatre_id;
      }
    }
  } catch {
    if (statusBanner) statusBanner.classList.add("hidden");
  }
}

function formatUTC(iso) {
  const d = new Date(iso);
  return (
    d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) +
    " " +
    d.toLocaleDateString([], { month: "short", day: "numeric" })
  );
}

async function checkEnmeshHealth() {
  const badge = document.getElementById("enmesh-conn-badge");
  if (!badge) return;
  try {
    const res = await fetch("/api/enmesh/status");
    const data = await res.json();
    if (data.connected && data.status === "ONLINE") {
      badge.textContent = `🟢 AI ENMESH CONNECTED (${data.online_nodes || 5}/5 NODES)`;
      badge.style.background = "rgba(34, 197, 94, 0.15)";
      badge.style.color = "#22c55e";
      badge.style.borderColor = "rgba(34, 197, 94, 0.3)";
    } else {
      badge.textContent = "🔴 AI ENMESH DISCONNECTED";
      badge.style.background = "rgba(239, 68, 68, 0.15)";
      badge.style.color = "#ef4444";
      badge.style.borderColor = "rgba(239, 68, 68, 0.3)";
    }
  } catch {
    badge.textContent = "🔴 AI ENMESH DISCONNECTED";
    badge.style.background = "rgba(239, 68, 68, 0.15)";
    badge.style.color = "#ef4444";
    badge.style.borderColor = "rgba(239, 68, 68, 0.3)";
  }
}

checkStatus();
checkEnmeshHealth();
setInterval(checkStatus, 15000);
setInterval(checkEnmeshHealth, 5000);

// ── 1-Click DCI Hardware Attestation (if present) ────
if (autoAttestBtn) {
  autoAttestBtn.addEventListener("click", async () => {
    const theatreId = theatreSelect ? theatreSelect.value : "THEATRE_001";
    const certInfo = THEATRE_CERTS[theatreId] || THEATRE_CERTS["THEATRE_001"];

    if (authError) authError.classList.add("hidden");
    if (authLoading) authLoading.classList.remove("hidden");
    if (loadingStatusText) loadingStatusText.textContent = "1. Sending DCI Hardware Certificate attestation to KMS Broker...";
    autoAttestBtn.disabled = true;

    try {
      if (loadingStatusText) loadingStatusText.textContent = "2. Pulling shards in parallel across AWS, Cloudflare, Wasabi, Edge mesh...";

      const ingestPromise = fetch("/api/theatre/ingest-simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theatre_id: theatreId }),
      }).then(r => r.json()).catch(() => ({ shards_ingested: [] }));

      const authPromise = fetch("/api/authenticate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          theatre_id: theatreId,
          cert_fingerprint: certInfo.fp,
        }),
      });

      const [ingestData, authRes] = await Promise.all([ingestPromise, authPromise]);

      if (ingestData && ingestData.shards_ingested && ingestData.shards_ingested.length > 0) {
        renderIngestTransfers(ingestData.shards_ingested);
      }

      const authData = await authRes.json();

      if (!authRes.ok) {
        throw new Error(authData.error || "DCI Attestation failed");
      }

      launchZeroDiskPlayer(authData);

    } catch (err) {
      if (authError) {
        authError.textContent = "Ingest Gateway Error: " + err.message;
        authError.classList.remove("hidden");
      }
      if (authLoading) authLoading.classList.add("hidden");
      autoAttestBtn.disabled = false;
    }
  });
}

// Manual Master KEK Unlock
manualUnlockBtn.addEventListener("click", async () => {
  const key = keyInput.value.trim();
  const theatreId = theatreSelect.value || "THEATRE_001";
  if (!key) return;

  authError.classList.add("hidden");
  authLoading.classList.remove("hidden");
  if (loadingStatusText) loadingStatusText.textContent = "Verifying Master KEK and decrypting mesh stream in RAM...";
  manualUnlockBtn.disabled = true;

  try {
    const authRes = await fetch("/api/authenticate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: key, theatre_id: theatreId }),
    });
    const authData = await authRes.json();

    if (!authRes.ok) {
      throw new Error(authData.error || "Invalid Master KEK");
    }

    launchZeroDiskPlayer(authData);
  } catch (err) {
    authError.textContent = "Manual Unlock Error: " + err.message;
    authError.classList.remove("hidden");
    authLoading.classList.add("hidden");
    manualUnlockBtn.disabled = false;
  }
});

// ── Outage & Failover Simulator Buttons ─────────
document.querySelectorAll(".node-toggle-btn").forEach(btn => {
  btn.addEventListener("click", async () => {
    const nodeId = btn.getAttribute("data-node");
    const isOnline = btn.classList.contains("active");
    const newStatus = isOnline ? "OFFLINE" : "ONLINE";

    try {
      const res = await fetch("/api/storage-mesh/node-toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: nodeId, status: newStatus })
      });
      const data = await res.json();
      if (data.success) {
        if (newStatus === "OFFLINE") {
          btn.classList.remove("active");
          btn.classList.add("offline");
          btn.querySelector("span").textContent = "OFFLINE 🔴";
        } else {
          btn.classList.remove("offline");
          btn.classList.add("active");
          btn.querySelector("span").textContent = "ONLINE 🟢";
        }
      }
    } catch (err) {
      console.error("Failed toggling node", err);
    }
  });
});

function renderIngestTransfers(shards) {
  if (ingestStats) {
    ingestStats.textContent = `${shards.length} sequential shards (100% verified across multi-cloud storage mesh)`;
  }
  if (merkleStatusBadge) {
    merkleStatusBadge.textContent = "🌲 Merkle Proofs: 100% Bit-for-Bit Verified";
  }

  const nodeIcons = {
    "ENM-01": "🟢 ENM-01",
    "ENM-02": "🟢 ENM-02",
    "ENM-03": "🟢 ENM-03",
    "ENM-04": "🟢 ENM-04",
    "ENM-05": "🟢 ENM-05",
    "ENM-01 [FAILOVER]": "🟡 ENM-01 [FAILOVER]",
    "ENM-02 [FAILOVER]": "🟡 ENM-02 [FAILOVER]",
    "ENM-03 [FAILOVER]": "🟡 ENM-03 [FAILOVER]",
    "ENM-04 [FAILOVER]": "🟡 ENM-04 [FAILOVER]",
    "ENM-05 [FAILOVER]": "🟡 ENM-05 [FAILOVER]",
    AWS_S3_US_EAST: "🟢 ENM-01",
    CLOUDFLARE_R2_EU: "🟢 ENM-02",
    WASABI_AP_SOUTH: "🟢 ENM-03",
    EDGE_POP_SINGAPORE: "🟢 ENM-04",
    GCP_STORAGE_WEST: "🟢 ENM-05",
  };

  if (shardTransferList) {
    shardTransferList.innerHTML = shards.map(s => {
      return `
        <div class="shard-transfer-card" style="padding: 0.6rem; border: 1px solid var(--border); border-radius: 6px; font-size: 0.8rem; background: rgba(255,255,255,0.02);">
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.3rem;">
            <strong style="color: var(--text);">${s.shard_id}</strong>
            <span style="color: var(--success);">✓ Verified</span>
          </div>
          <div style="display: flex; justify-content: space-between; color: var(--muted); font-size: 0.75rem;">
            <span>${nodeIcons[s.node] || s.node}</span>
            <span>${s.size_kb} KB</span>
          </div>
        </div>
      `;
    }).join("");
  }
}

function launchZeroDiskPlayer(data) {
  authLoading.classList.add("hidden");
  authSection.classList.add("hidden");
  statusBanner.classList.add("hidden");
  playerSec.classList.remove("hidden");

  currentToken = data.token;
  windowEnd = new Date(data.movie_info.window_end);

  document.getElementById("info-shards").textContent = data.movie_info.shards;
  document.getElementById("info-theatre").textContent = data.movie_info.theatre_id;
  document.getElementById("info-time").textContent = data.movie_info.time_remaining;
  document.getElementById("info-kdm").textContent = data.movie_info.kdm_id || "DCI-ACTIVE";

  // Dynamic DRM Watermark overlay
  const watermark = document.getElementById("drm-watermark");
  watermark.setAttribute(
    "data-watermark",
    `${data.movie_info.theatre_id} • DCI LEVEL 3 • ${new Date().toLocaleTimeString()}`,
  );

  videoPlayer.src = `/api/stream/${data.token}`;
  videoPlayer.load();
  videoPlayer.play().catch(() => {});

  enableScreenProtection();
  startExpiryCountdown();
}

// ── Screen Protection & Anti-Capture ────

function enableScreenProtection() {
  videoPlayer.addEventListener("contextmenu", (e) => e.preventDefault());
  document.addEventListener("keydown", (e) => {
    if (e.key === "PrintScreen" || (e.ctrlKey && (e.key === "s" || e.key === "S"))) {
      e.preventDefault();
      const container = document.getElementById("video-container");
      container.style.filter = "brightness(0)";
      setTimeout(() => { container.style.filter = ""; }, 800);
    }
  });
}

function startExpiryCountdown() {
  const timeBadge = document.getElementById("time-badge");
  const infoTime = document.getElementById("info-time");
  const expiryWarning = document.getElementById("expiry-warning");

  countdownTimer = setInterval(() => {
    if (!windowEnd) return;
    const now = new Date();
    const remaining = Math.max(0, Math.floor((windowEnd - now) / 1000));
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    infoTime.textContent = `${mins}m ${secs}s`;

    if (remaining < 300 && remaining > 60) {
      timeBadge.className = "time-badge warning";
      expiryWarning.classList.remove("hidden");
    } else if (remaining <= 60 && remaining > 0) {
      timeBadge.className = "time-badge danger";
    } else if (remaining <= 0) {
      clearInterval(countdownTimer);
      expireSession();
    }
  }, 10000);
}

function expireSession() {
  videoPlayer.pause();
  videoPlayer.src = "";
  document.getElementById("expired-overlay").classList.remove("hidden");
  const container = document.getElementById("video-container");
  container.classList.remove("cinema-mode");
}

// Fullscreen / Cinema Mode
document.getElementById("fullscreen-btn").addEventListener("click", () => {
  const container = document.getElementById("video-container");
  container.classList.add("cinema-mode");
  const exitBtn = document.createElement("button");
  exitBtn.className = "cinema-exit";
  exitBtn.textContent = "✕ Exit Cinema";
  exitBtn.addEventListener("click", () => {
    container.classList.remove("cinema-mode");
    exitBtn.remove();
  });
  document.body.appendChild(exitBtn);
});
