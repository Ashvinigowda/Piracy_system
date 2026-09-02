// ═══════════════════════════════════════════
// CinemaShield 2.0 — Producer Studio Ingest Logic
// ═══════════════════════════════════════════

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const fileInfo = document.getElementById("file-info");
const fileName = document.getElementById("file-name");
const fileSize = document.getElementById("file-size");
const clearBtn = document.getElementById("clear-file");
const uploadBtn = document.getElementById("upload-btn");

const pipelineSec = document.getElementById("pipeline-section");
const progressBar = document.getElementById("progress-bar");
const statusText = document.getElementById("pipeline-status");

const successSec = document.getElementById("success-section");
const keyDisplay = document.getElementById("key-display");
const merkleDisplay = document.getElementById("merkle-root-display");
const copyKeyBtn = document.getElementById("copy-key-btn");
const copyMerkleBtn = document.getElementById("copy-merkle-btn");

const resShards = document.getElementById("res-shards");
const resTheatre = document.getElementById("res-theatre");
const resFingerprint = document.getElementById("res-fingerprint");
const meshNodesGrid = document.getElementById("mesh-nodes-grid");

const uploadProgress = document.getElementById("upload-progress");
const uploadBar = document.getElementById("upload-bar");
const uploadPercent = document.getElementById("upload-percent");
const theatreIdSelect = document.getElementById("theatre-id");
const uploadAnotherBtn = document.getElementById("upload-another-btn");

let selectedFile = null;

// ── File Selection ──────────────────────

dropzone.addEventListener("click", () => fileInput.click());

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("drag-over");
});

dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));

dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag-over");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});

clearBtn.addEventListener("click", clearFile);

function setFile(file) {
  const ext = file.name.split(".").pop().toLowerCase();
  if (!["mp4", "mkv", "avi", "mov"].includes(ext)) {
    alert("Invalid format. Use MP4, MKV, AVI, or MOV.");
    return;
  }
  selectedFile = file;
  fileName.textContent = file.name;
  fileSize.textContent = formatSize(file.size);
  fileInfo.classList.remove("hidden");
  uploadBtn.classList.remove("hidden");
}

function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  fileInfo.classList.add("hidden");
  uploadBtn.classList.add("hidden");
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

// ── Upload & Start Pipeline ─────────────

uploadBtn.addEventListener("click", () => {
  if (!selectedFile) return;

  uploadBtn.disabled = true;
  uploadBtn.textContent = "Uploading to Ingest Buffer…";
  uploadProgress.classList.remove("hidden");

  const form = new FormData();
  form.append("file", selectedFile);
  form.append("theatre_id", theatreIdSelect.value.trim() || "THEATRE_001");

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      uploadBar.style.width = pct + "%";
      uploadPercent.textContent = `Uploading ${pct}%`;
    }
  };

  xhr.onload = () => {
    const data = JSON.parse(xhr.responseText);
    if (xhr.status !== 200) {
      alert(data.error || "Upload failed");
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Secure, Shard & Disperse";
      uploadProgress.classList.add("hidden");
      return;
    }
    uploadPercent.textContent = "Ingest buffer ready!";
    document.getElementById("upload-section").classList.add("hidden");
    pipelineSec.classList.remove("hidden");
    runPipeline(data.movie_id, theatreIdSelect.value);
  };

  xhr.onerror = () => {
    alert("Upload error. Check connection.");
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Secure, Shard & Disperse";
    uploadProgress.classList.add("hidden");
  };

  xhr.send(form);
});

// ── Pipeline Stepper via SSE ────────────

function runPipeline(movieId, targetTheatre) {
  const steps = document.querySelectorAll(".stepper .step");
  const source = new EventSource(`/api/process/${movieId}`);

  source.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    progressBar.style.width = msg.progress + "%";
    statusText.textContent = msg.message;

    const stepMap = {
      cleanup: 0,
      sharding: 1,
      sharding_done: 1,
      encrypting: 2,
      encrypting_done: 2,
      mesh_dispersion: 3,
      mesh_done: 3,
      manifest: 4,
      manifest_done: 4,
      ai_analysis: 5,
      ai_done: 5,
      done: 6,
    };

    const idx = stepMap[msg.step];
    if (idx !== undefined) {
      steps.forEach((s, i) => {
        s.classList.remove("active");
        if (i < idx) s.classList.add("done");
      });
      if (steps[idx]) steps[idx].classList.add("active");
    }

    if (msg.step === "done") {
      source.close();
      steps.forEach((s) => {
        s.classList.remove("active");
        s.classList.add("done");
      });
      renderSuccess(msg, targetTheatre);
      loadHistory();
    }

    if (msg.step === "error") {
      source.close();
      statusText.textContent = "❌ " + msg.message;
      statusText.style.color = "#ff4e6a";
    }
  };

  source.onerror = () => {
    source.close();
    statusText.textContent = "❌ Connection to pipeline lost";
    statusText.style.color = "#ff4e6a";
  };
}

// ── Render Multi-Cloud Mesh & Success Screen ──

function renderSuccess(msg, targetTheatre) {
  successSec.classList.remove("hidden");
  keyDisplay.textContent = msg.key || "AES-256-GCM Ephemeral Master KEK";
  merkleDisplay.textContent = msg.merkle_root || "Merkle Root generated";
  resShards.textContent = msg.shards || 0;
  resTheatre.textContent = targetTheatre;

  // Render Mesh Nodes
  if (msg.mesh && msg.mesh.nodes) {
    meshNodesGrid.innerHTML = Object.values(msg.mesh.nodes).map(node => `
      <div class="mesh-node-card">
        <div class="mesh-node-header">
          <span class="mesh-node-icon">${node.icon}</span>
          <div class="mesh-node-title">
            <strong>${node.name}</strong>
            <span class="mesh-node-region">${node.region}</span>
          </div>
        </div>
        <div class="mesh-node-stats">
          <div class="mesh-stat">
            <span class="mesh-stat-lbl">Latency:</span>
            <span class="mesh-stat-val" style="color: var(--success);">${node.latency_ms}ms</span>
          </div>
          <div class="mesh-stat">
            <span class="mesh-stat-lbl">Shards Stored:</span>
            <span class="mesh-stat-val"><strong>${node.shard_count}</strong> shards</span>
          </div>
          <div class="mesh-stat">
            <span class="mesh-stat-lbl">Status:</span>
            <span class="badge-active">ONLINE</span>
          </div>
        </div>
      </div>
    `).join("");
  }
}

// ── Copy Handlers ───────────────────────

if (copyKeyBtn) {
  copyKeyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(keyDisplay.textContent).then(() => {
      copyKeyBtn.textContent = "Copied! ✅";
      setTimeout(() => copyKeyBtn.textContent = "Copy", 2000);
    });
  });
}

if (copyMerkleBtn) {
  copyMerkleBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(merkleDisplay.textContent).then(() => {
      copyMerkleBtn.textContent = "Copied! ✅";
      setTimeout(() => copyMerkleBtn.textContent = "Copy", 2000);
    });
  });
}

// ── Reset & Distribute Another ──────────

if (uploadAnotherBtn) {
  uploadAnotherBtn.addEventListener("click", () => {
    successSec.classList.add("hidden");
    pipelineSec.classList.add("hidden");
    uploadProgress.classList.add("hidden");
    uploadBar.style.width = "0%";
    progressBar.style.width = "0%";
    const uploadSec = document.getElementById("upload-section");
    uploadSec.classList.remove("hidden");
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Secure, Shard & Disperse";
    clearFile();
    document.querySelectorAll(".stepper .step").forEach((s) => {
      s.classList.remove("active", "done");
    });
  });
}

// ── History Loader ──────────────────────

async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    const list = document.getElementById("history-list");
    if (!data.length) {
      list.innerHTML = `<p class="text-muted">No distribution history recorded yet.</p>`;
      return;
    }
    list.innerHTML = data.map(h => `
      <div class="history-item" style="display: flex; justify-content: space-between; align-items: center; padding: 0.8rem; border-bottom: 1px solid var(--border);">
        <div>
          <strong style="color: var(--text);">🎬 ${h.name}</strong>
          <span class="text-muted"> &bull; ${h.shards} shards &bull; ${h.theatre_id}</span>
          <div style="font-size: 0.75rem; color: #60a5fa; font-family: monospace; margin-top: 0.2rem;">
            Merkle: ${h.merkle_root ? h.merkle_root.slice(0, 24) + '...' : 'N/A'}
          </div>
        </div>
        <button class="btn btn-sm btn-outline" onclick="navigator.clipboard.writeText('${h.key}')" title="Copy Master KEK">Copy KEK</button>
      </div>
    `).join("");
  } catch (err) {
    console.error("Failed loading history", err);
  }
}

loadHistory();
