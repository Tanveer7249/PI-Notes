/**
 * proctor.js
 * ───────────────────────────────────────────────────────────────────────────
 * Handles the proctor-side real-time experience:
 *   1. SocketIO connection — joins proctor_room on load
 *   2. Live alert feed — renders new_alert events as they arrive
 *   3. Candidate online/offline status updates
 *   4. Webcam + screen frame rendering inside monitor.html
 *   5. Polling fallback for live stats (in case socket drops)
 *   6. Proctor force-submit action
 * ───────────────────────────────────────────────────────────────────────────
 */

// ── SocketIO connection ───────────────────────────────────────────────────────
const socket = io();

// ── Page detection (are we on dashboard or monitor page?) ────────────────────
const isDashboard = !!document.getElementById("proctor-dashboard");
const isMonitor   = !!document.getElementById("proctor-monitor");

// ─────────────────────────────────────────────────────────────────────────────
// 1. JOIN PROCTOR ROOM
// Every proctor page joins the global proctor_room for broadcast alerts.
// ─────────────────────────────────────────────────────────────────────────────
socket.on("connect", () => {
    socket.emit("proctor_join");

    // If on the monitor page, also subscribe to the specific candidate's room
    if (isMonitor) {
        const monitorRoot = document.getElementById("proctor-monitor");
        const attemptId   = monitorRoot ? parseInt(monitorRoot.dataset.attemptId) : null;
        if (attemptId) {
            socket.emit("proctor_monitor", { attempt_id: attemptId });
        }
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. LIVE ALERT FEED — new_alert event from server
// ─────────────────────────────────────────────────────────────────────────────
socket.on("new_alert", (data) => {
    /*
     * data = {
     *   attempt_id, candidate_name, test_title,
     *   event_type, timestamp, snapshot_url
     * }
     */
    if (isDashboard) {
        prependAlertRow(data);
        flashAlertBadge();
        bumpViolationCounter(data.attempt_id);
    }

    if (isMonitor) {
        prependMonitorLog(data);
        updateViolationSummary(data.event_type);
    }

    // Show toast on both pages
    showToast(
        `${data.candidate_name}: ${formatEventType(data.event_type)}`,
        "warning"
    );
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. CANDIDATE ONLINE — A new candidate started their exam
// ─────────────────────────────────────────────────────────────────────────────
socket.on("candidate_online", (data) => {
    /*
     * data = { attempt_id, candidate_name, test_title }
     */
    if (!isDashboard) return;

    showToast(`🟢 ${data.candidate_name} joined "${data.test_title}"`, "success");
    incrementActiveBadge(1);

    // Add a new row to the live candidates table if it doesn't exist
    addCandidateRow(data);
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. CANDIDATE OFFLINE — A candidate submitted or disconnected
// ─────────────────────────────────────────────────────────────────────────────
socket.on("candidate_offline", (data) => {
    if (!isDashboard) return;

    showToast(`🔴 ${data.candidate_name} left the exam.`, "info");
    incrementActiveBadge(-1);
    markCandidateOffline(data.attempt_id);
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. WEBCAM FRAME — Render incoming webcam frame on monitor page
// ─────────────────────────────────────────────────────────────────────────────
socket.on("webcam_update", (data) => {
    if (!isMonitor) return;
    const img = document.getElementById("live-webcam");
    if (img && data.frame) {
        img.src = data.frame;
        img.classList.remove("hidden");
        document.getElementById("webcam-placeholder")?.classList.add("hidden");
        updateLastSeen("webcam");
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// 6. SCREEN FRAME — Render incoming screen share frame on monitor page
// ─────────────────────────────────────────────────────────────────────────────
socket.on("screen_update", (data) => {
    if (!isMonitor) return;
    const img = document.getElementById("live-screen");
    if (img && data.frame) {
        img.src = data.frame;
        img.classList.remove("hidden");
        document.getElementById("screen-placeholder")?.classList.add("hidden");
        updateLastSeen("screen");
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// 7. DASHBOARD HELPERS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Prepend a new alert row to the alert feed table on the dashboard.
 */
function prependAlertRow(data) {
    const tbody = document.getElementById("alert-feed-body");
    if (!tbody) return;

    const row = document.createElement("tr");
    row.className  = "bg-yellow-50 border-b border-yellow-200 animate-pulse-once";
    row.id         = `alert-row-${Date.now()}`;
    row.innerHTML  = `
        <td class="px-4 py-2 text-sm font-medium text-gray-800">${escapeHtml(data.candidate_name)}</td>
        <td class="px-4 py-2 text-sm text-gray-600">${escapeHtml(data.test_title)}</td>
        <td class="px-4 py-2">
            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${eventBadgeClass(data.event_type)}">
                ${escapeHtml(formatEventType(data.event_type))}
            </span>
        </td>
        <td class="px-4 py-2 text-xs text-gray-500">${escapeHtml(data.timestamp)}</td>
        <td class="px-4 py-2">
            <a href="/proctor/monitor/${data.attempt_id}"
               class="text-xs text-indigo-600 hover:text-indigo-800 font-medium">
                Monitor →
            </a>
        </td>
    `;

    // Keep the feed to 30 rows maximum
    tbody.insertBefore(row, tbody.firstChild);
    const rows = tbody.querySelectorAll("tr");
    if (rows.length > 30) rows[rows.length - 1].remove();
}

/**
 * Flash the alert count badge in the nav.
 */
function flashAlertBadge() {
    const badge = document.getElementById("alert-count-badge");
    if (!badge) return;
    const current = parseInt(badge.textContent) || 0;
    badge.textContent = current + 1;
    badge.classList.remove("hidden");
    badge.classList.add("animate-bounce");
    setTimeout(() => badge.classList.remove("animate-bounce"), 1000);
}

/**
 * Increment or decrement the live active candidate count badge.
 */
function incrementActiveBadge(delta) {
    const el = document.getElementById("active-candidate-count");
    if (!el) return;
    const current = parseInt(el.textContent) || 0;
    el.textContent = Math.max(0, current + delta);
}

/**
 * Bump per-candidate violation counter in the candidates table.
 */
function bumpViolationCounter(attemptId) {
    const cell = document.getElementById(`violations-${attemptId}`);
    if (!cell) return;
    const current = parseInt(cell.textContent) || 0;
    cell.textContent = current + 1;
    cell.classList.add("text-red-600", "font-bold");
}

/**
 * Add a new candidate row to the live table (if they just joined).
 */
function addCandidateRow(data) {
    const tbody = document.getElementById("candidates-table-body");
    if (!tbody) return;

    // Don't add duplicates
    if (document.getElementById(`candidate-row-${data.attempt_id}`)) return;

    const row = document.createElement("tr");
    row.id        = `candidate-row-${data.attempt_id}`;
    row.className = "border-b border-gray-100 hover:bg-gray-50";
    row.innerHTML = `
        <td class="px-4 py-3 text-sm font-medium text-gray-800">${escapeHtml(data.candidate_name)}</td>
        <td class="px-4 py-3 text-sm text-gray-600">${escapeHtml(data.test_title)}</td>
        <td class="px-4 py-3">
            <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                🟢 Live
            </span>
        </td>
        <td class="px-4 py-3 text-sm text-gray-500" id="violations-${data.attempt_id}">0</td>
        <td class="px-4 py-3">
            <a href="/proctor/monitor/${data.attempt_id}"
               class="text-xs font-medium text-indigo-600 hover:text-indigo-800">
                Monitor →
            </a>
        </td>
    `;
    tbody.insertBefore(row, tbody.firstChild);
}

/**
 * Mark a candidate row as offline when they submit/disconnect.
 */
function markCandidateOffline(attemptId) {
    const row = document.getElementById(`candidate-row-${attemptId}`);
    if (!row) return;
    const statusCell = row.querySelector("span");
    if (statusCell) {
        statusCell.textContent  = "🔴 Offline";
        statusCell.className    = "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800";
    }
    row.classList.add("opacity-50");
}

// ─────────────────────────────────────────────────────────────────────────────
// 8. MONITOR PAGE HELPERS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Prepend a log row inside the monitor page's violation log panel.
 */
function prependMonitorLog(data) {
    const container = document.getElementById("monitor-log-feed");
    if (!container) return;

    const item = document.createElement("div");
    item.className = `flex items-start gap-3 p-3 rounded-lg border mb-2 ${eventCardClass(data.event_type)}`;
    item.innerHTML = `
        <div class="flex-1">
            <p class="text-sm font-medium text-gray-800">${escapeHtml(formatEventType(data.event_type))}</p>
            <p class="text-xs text-gray-500 mt-0.5">${escapeHtml(data.timestamp)}</p>
        </div>
        ${data.snapshot_url
            ? `<img src="${data.snapshot_url}" alt="Snapshot"
                    class="w-16 h-12 object-cover rounded border border-gray-300 cursor-pointer"
                    onclick="openSnapshot('${data.snapshot_url}')" />`
            : ""}
    `;
    container.insertBefore(item, container.firstChild);
}

/**
 * Update the violation summary counters on the monitor sidebar.
 */
function updateViolationSummary(eventType) {
    const el = document.getElementById(`summary-${eventType}`);
    if (!el) return;
    const current = parseInt(el.textContent) || 0;
    el.textContent = current + 1;
    el.parentElement?.classList.add("bg-red-50");
}

/**
 * Track the last time a frame was received and show it in the UI.
 */
function updateLastSeen(type) {
    const el = document.getElementById(`last-seen-${type}`);
    if (el) el.textContent = new Date().toLocaleTimeString();
}

/**
 * Open a snapshot image in a lightbox overlay.
 */
function openSnapshot(src) {
    const overlay = document.getElementById("snapshot-overlay");
    const img     = document.getElementById("snapshot-full");
    if (overlay && img) {
        img.src = src;
        overlay.classList.remove("hidden");
    }
}

// Close snapshot lightbox
document.getElementById("snapshot-overlay")?.addEventListener("click", () => {
    document.getElementById("snapshot-overlay")?.classList.add("hidden");
});

// ─────────────────────────────────────────────────────────────────────────────
// 9. FORCE SUBMIT — Proctor ends a candidate's exam manually
// ─────────────────────────────────────────────────────────────────────────────
const forceSubmitBtn = document.getElementById("force-submit-btn");
if (forceSubmitBtn) {
    forceSubmitBtn.addEventListener("click", () => {
        const attemptId = parseInt(forceSubmitBtn.dataset.attemptId);
        if (!attemptId) return;
        if (!confirm("Are you sure you want to force-submit this candidate's exam?")) return;

        socket.emit("proctor_force_submit", { attempt_id: attemptId });
        showToast("Force submit signal sent to candidate.", "warning");
        forceSubmitBtn.disabled    = true;
        forceSubmitBtn.textContent = "Signal Sent";
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// 10. POLLING FALLBACK — Refresh active count every 30s via HTTP
// In case WebSocket connection drops, the dashboard stays roughly up to date.
// ─────────────────────────────────────────────────────────────────────────────
if (isDashboard) {
    setInterval(() => {
        fetch("/proctor/api/live-stats")
            .then((r) => r.json())
            .then((data) => {
                const el = document.getElementById("active-candidate-count");
                if (el) el.textContent = data.active_candidates;
            })
            .catch(() => {});   // Silent fail — socket is primary
    }, 30000);
}

// ─────────────────────────────────────────────────────────────────────────────
// 11. UTILITY FUNCTIONS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Human-readable label for each event_type code.
 */
function formatEventType(type) {
    const labels = {
        tab_switch:           "Tab Switch",
        fullscreen_exit:      "Fullscreen Exit",
        copy_attempt:         "Copy Attempt",
        paste_attempt:        "Paste Attempt",
        right_click:          "Right Click",
        camera_off:           "Camera Disabled",
        screen_share_stopped: "Screen Share Stopped",
        auto_submitted:       "Auto Submitted",
        visibility_hidden:    "Window Unfocused",
    };
    return labels[type] || type;
}

/**
 * Tailwind badge classes for each event severity.
 */
function eventBadgeClass(type) {
    const high   = ["tab_switch", "fullscreen_exit", "screen_share_stopped", "auto_submitted"];
    const medium = ["copy_attempt", "paste_attempt", "camera_off"];
    if (high.includes(type))   return "bg-red-100 text-red-800";
    if (medium.includes(type)) return "bg-yellow-100 text-yellow-800";
    return "bg-gray-100 text-gray-700";
}

/**
 * Tailwind card classes for monitor log items.
 */
function eventCardClass(type) {
    const high   = ["tab_switch", "fullscreen_exit", "screen_share_stopped", "auto_submitted"];
    const medium = ["copy_attempt", "paste_attempt", "camera_off"];
    if (high.includes(type))   return "bg-red-50 border-red-200";
    if (medium.includes(type)) return "bg-yellow-50 border-yellow-200";
    return "bg-gray-50 border-gray-200";
}

/**
 * Escape HTML to prevent XSS when inserting server data into innerHTML.
 */
function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

/**
 * Show a toast notification.
 */
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const colorMap = {
        info:    "bg-blue-600",
        success: "bg-green-600",
        warning: "bg-yellow-500",
        error:   "bg-red-600",
    };

    const toast = document.createElement("div");
    toast.className = `text-white text-sm px-4 py-3 rounded shadow-lg mb-2 transition-opacity ${colorMap[type] || colorMap.info}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 400);
    }, 5000);
}