
const $ = (id) => document.getElementById(id);

const statusBanner = $("status-banner");
const statusText = $("status-text");
const theatreSelect = $("theatre-select");
const autoAttestBtn = $("auto-attest-btn");
const authError = $("auth-error");
const authLoading = $("auth-loading");
const loadingStatusText = $("loading-status-text");
const authSection = $("auth-section");
const shardTransferList = $("shard-transfer-list");
const ingestStats = $("ingest-stats");
const merkleStatusBadge = $("merkle-status-badge");
const playerSec = $("player-section");
const videoPlayer = $("video-player");

let currentToken = null;
let countdownTimer = null;
let windowEnd = null;
let sessionExpired = false;

const THEATRE_CERTS = {
  THEATRE_001: {
    fp: "SHA256:4a8f9c1b3d7e5a2c9e0f6b4a8c1d3e5f7a9b0c2d4e6f8a0b2c4d6e8f0a2b4c6d"
  },
  THEATRE_002: {
    fp: "SHA256:9f8e7d6c5b4a39281706f5e4d3c2b1a09876543210fedcba9876543210abcdef"
  },
  THEATRE_003: {
    fp: "SHA256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b"
  }
};

function showError(message) {
  if (!authError) return;
  authError.textContent = message;
  authError.classList.remove("hidden");
}

async function readJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

async function checkStatus() {
  try {
    const response = await fetch("/api/status");
    const data = await response.json();

    if (!statusBanner || !statusText) return;

    statusBanner.classList.remove("hidden");

    if (!data.ready) {
      statusBanner.className = "banner banner-warn";
      statusText.textContent = "No movie is distributed yet. Upload and process a movie first.";
      if (autoAttestBtn) autoAttestBtn.disabled = true;
    } else if (!data.playback_active) {
      statusBanner.className = "banner banner-warn";
      statusText.textContent = "The playback window is inactive. Process a new test video.";
      if (autoAttestBtn) autoAttestBtn.disabled = true;
    } else {
      statusBanner.className = "banner banner-info";
      statusText.textContent =
        `Ready on mesh — ${data.shards} shards; theatre ${data.theatre_id}.`;
      if (autoAttestBtn) autoAttestBtn.disabled = false;
    }
  } catch {
    if (statusBanner) statusBanner.classList.add("hidden");
  }
}

async function checkEnmeshHealth() {
  const badge = $("enmesh-conn-badge");
  if (!badge) return;

  try {
    const response = await fetch("/api/enmesh/status");
    const data = await response.json();
    badge.textContent =
      data.connected && data.status === "ONLINE"
        ? `AI ENMESH CONNECTED (${data.online_nodes || 5}/5 NODES)`
        : "AI ENMESH DISCONNECTED";
  } catch {
    badge.textContent = "AI ENMESH DISCONNECTED";
  }
}

async function authenticateTheatre() {
  if (!theatreSelect || !autoAttestBtn) return;

  const theatreId = theatreSelect.value;
  const cert = THEATRE_CERTS[theatreId];

  if (!cert) {
    showError("No registered certificate is configured for this theatre.");
    return;
  }

  if (authError) authError.classList.add("hidden");
  if (authLoading) authLoading.classList.remove("hidden");
  autoAttestBtn.disabled = true;

  try {
    if (loadingStatusText) {
      loadingStatusText.textContent = "Requesting KMS attestation and preparing playback...";
    }

    const response = await fetch("/api/authenticate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        theatre_id: theatreId,
        cert_fingerprint: cert.fp
      })
    });

    const data = await readJson(response);

    if (!data.success || !data.token || !data.movie_info) {
      throw new Error("The server returned an incomplete playback response.");
    }

    // Optional visual ingest simulation. Authentication is handled separately.
    try {
      const ingestResponse = await fetch("/api/theatre/ingest-simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theatre_id: theatreId })
      });

      if (ingestResponse.ok) {
        const ingestData = await ingestResponse.json();
        renderIngestTransfers(ingestData.shards_ingested || []);
      }
    } catch {
      // Playback authentication already succeeded; do not expose internal details.
    }

    launchPlayer(data);
  } catch (error) {
    showError(error.message || "KMS authentication failed.");
    if (authLoading) authLoading.classList.add("hidden");
    autoAttestBtn.disabled = false;
  }
}

if (autoAttestBtn) {
  autoAttestBtn.addEventListener("click", authenticateTheatre);
}

document.querySelectorAll(".node-toggle-btn").forEach((button) => {
  button.addEventListener("click", async () => {
    const nodeId = button.getAttribute("data-node");
    const currentlyOnline = button.classList.contains("active");
    const newStatus = currentlyOnline ? "OFFLINE" : "ONLINE";

    button.disabled = true;

    try {
      const response = await fetch("/api/storage-mesh/node-toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: nodeId, status: newStatus })
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error("The storage node status could not be changed.");
      }

      button.classList.toggle("active", newStatus === "ONLINE");
      button.classList.toggle("offline", newStatus === "OFFLINE");
      const label = button.querySelector("span");
      if (label) label.textContent = newStatus;
    } catch (error) {
      showError(error.message);
    } finally {
      button.disabled = false;
    }
  });
});

function renderIngestTransfers(shards) {
  if (ingestStats) {
    ingestStats.textContent = `${shards.length} shards reported by the ingest simulation.`;
  }

  if (merkleStatusBadge) {
    const verified = shards.length > 0 &&
      shards.every((shard) =>
        shard.status === "VERIFIED" &&
        shard.sha256_match === true &&
        shard.merkle_proof_valid === true
      );

    merkleStatusBadge.textContent = verified
      ? "Merkle proofs verified"
      : "Ingest simulation completed; inspect verification results";
  }

  if (!shardTransferList) return;
  shardTransferList.replaceChildren();

  for (const shard of shards) {
    const card = document.createElement("div");
    card.className = "shard-transfer-card";

    const title = document.createElement("strong");
    title.textContent = shard.shard_id || "Unknown shard";

    const details = document.createElement("span");
    details.textContent =
      `${shard.node || "Unknown node"} · ${shard.size_kb ?? "?"} KB · ${shard.status || "UNKNOWN"}`;

    card.append(title, details);
    shardTransferList.appendChild(card);
  }
}

function launchPlayer(data) {
  if (authLoading) authLoading.classList.add("hidden");
  if (authSection) authSection.classList.add("hidden");
  if (statusBanner) statusBanner.classList.add("hidden");
  if (playerSec) playerSec.classList.remove("hidden");

  currentToken = data.token;
  sessionExpired = false;
  windowEnd = new Date(data.movie_info.window_end);

  $("info-shards").textContent = data.movie_info.shards;
  $("info-theatre").textContent = data.movie_info.theatre_id;
  $("info-time").textContent = data.movie_info.time_remaining;
  $("info-kdm").textContent = data.movie_info.kdm_id || "KDM-ACTIVE";

  const watermark = $("drm-watermark");
  if (watermark) {
    watermark.setAttribute(
      "data-watermark",
      `${data.movie_info.theatre_id} · ${new Date().toLocaleTimeString()}`
    );
  }

  videoPlayer.src = `/api/stream/${encodeURIComponent(currentToken)}`;
  videoPlayer.load();
  videoPlayer.play().catch(() => {});

  videoPlayer.addEventListener("contextmenu", (event) => event.preventDefault());

  if (countdownTimer) clearInterval(countdownTimer);
  countdownTimer = setInterval(checkPlaybackExpiry, 1000);

  addLogoutButton();
}

async function checkPlaybackExpiry() {
  if (!windowEnd || sessionExpired) return;

  const remaining = Math.max(0, Math.floor((windowEnd - new Date()) / 1000));
  const infoTime = $("info-time");
  if (infoTime) {
    infoTime.textContent = `${Math.floor(remaining / 60)}m ${remaining % 60}s`;
  }

  if (remaining <= 0) {
    await endPlayback("Playback window expired.");
  }
}

function addLogoutButton() {
  if ($("logout-session-btn")) return;

  const button = document.createElement("button");
  button.id = "logout-session-btn";
  button.type = "button";
  button.className = "btn btn-secondary";
  button.textContent = "End Playback Session";
  button.addEventListener("click", () => endPlayback("Playback session ended."));
  playerSec.appendChild(button);
}

async function endPlayback(message) {
  if (sessionExpired) return;
  sessionExpired = true;

  if (countdownTimer) clearInterval(countdownTimer);

  videoPlayer.pause();
  videoPlayer.removeAttribute("src");
  videoPlayer.load();

  if (currentToken) {
    try {
      await fetch(`/api/stream/${encodeURIComponent(currentToken)}`, {
        method: "DELETE"
      });
    } catch {
      // Local player is still stopped if the server is unreachable.
    }
  }

  currentToken = null;
  windowEnd = null;

  const overlay = $("expired-overlay");
  if (overlay) {
    overlay.classList.remove("hidden");
    overlay.textContent = message;
  } else {
    showError(message);
  }
}

const fullscreenButton = $("fullscreen-btn");
if (fullscreenButton) {
  fullscreenButton.addEventListener("click", () => {
    const container = $("video-container") || playerSec;
    if (!container) return;

    if (container.requestFullscreen) {
      container.requestFullscreen().catch(() => {});
    }
  });
}

checkStatus();
checkEnmeshHealth();
setInterval(checkStatus, 15000);
setInterval(checkEnmeshHealth, 5000);
