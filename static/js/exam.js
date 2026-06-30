/**
 * exam.js
 * ───────────────────────────────────────────────────────────────────────────
 * Handles the entire candidate exam experience:
 *   1. Fullscreen enforcement
 *   2. Anti-cheat detection (tab switch, copy/paste, right-click, visibility)
 *   3. Webcam capture + SocketIO streaming
 *   4. Screen share capture + SocketIO streaming
 *   5. Countdown timer with auto-submit
 *   6. Auto-save answers via AJAX on every selection
 *   7. Manual submit with confirmation
 *   8. Proctor force-submit listener
 *
 * All constants are injected by the Jinja2 template via data attributes
 * on the #exam-root element.
 * ───────────────────────────────────────────────────────────────────────────
 */

// ── Read configuration injected by the server ────────────────────────────────
const examRoot      = document.getElementById("exam-root");
const ATTEMPT_ID    = parseInt(examRoot.dataset.attemptId);
const TEST_ID       = parseInt(examRoot.dataset.testId);
const REMAINING_SEC = parseInt(examRoot.dataset.remainingSecs);
const SAVE_URL      = examRoot.dataset.saveUrl;
const LOG_URL       = examRoot.dataset.logUrl;
const SUBMIT_URL    = examRoot.dataset.submitUrl;

// ── SocketIO connection ───────────────────────────────────────────────────────
const socket = io();

// ── State ─────────────────────────────────────────────────────────────────────
let timerInterval      = null;
let remainingSeconds   = REMAINING_SEC;
let webcamStream       = null;
let screenStream       = null;
let webcamFrameTimer   = null;
let screenFrameTimer   = null;
let isSubmitting       = false;   // Guard against double-submit

// ─────────────────────────────────────────────────────────────────────────────
// 1. SOCKET — Join exam room
// ─────────────────────────────────────────────────────────────────────────────
socket.emit("candidate_join", { attempt_id: ATTEMPT_ID });

// Listen for proctor force-submit
socket.on("force_submit", (data) => {
    showToast(data.reason || "Your exam has been ended by the proctor.", "error");
    setTimeout(() => submitExam(true), 2000);
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. FULLSCREEN — Request and enforce
// ─────────────────────────────────────────────────────────────────────────────
function requestFullscreen() {
    const el = document.documentElement;
    if (el.requestFullscreen)           el.requestFullscreen();
    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
    else if (el.mozRequestFullScreen)    el.mozRequestFullScreen();
}

function isFullscreen() {
    return !!(
        document.fullscreenElement ||
        document.webkitFullscreenElement ||
        document.mozFullScreenElement
    );
}

// Detect fullscreen exit
document.addEventListener("fullscreenchange",       handleFullscreenChange);
document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
document.addEventListener("mozfullscreenchange",    handleFullscreenChange);

function handleFullscreenChange() {
    if (!isFullscreen()) {
        logEvent("fullscreen_exit");
        showWarning("⚠️ You exited fullscreen! Please return to fullscreen mode.");
        // Re-request fullscreen after a short delay
        setTimeout(requestFullscreen, 1500);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. ANTI-CHEAT DETECTORS
// ─────────────────────────────────────────────────────────────────────────────

// ── Tab / window visibility change ───────────────────────────────────────────
document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
        logEvent("tab_switch");
        showWarning("⚠️ Tab switching detected and logged!");
    }
});

// ── Window blur (switching to another app) ────────────────────────────────────
window.addEventListener("blur", () => {
    logEvent("visibility_hidden");
});

// ── Disable right-click ───────────────────────────────────────────────────────
document.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    logEvent("right_click");
});

// ── Disable copy ─────────────────────────────────────────────────────────────
document.addEventListener("copy", (e) => {
    e.preventDefault();
    logEvent("copy_attempt");
});

// ── Disable cut ──────────────────────────────────────────────────────────────
document.addEventListener("cut", (e) => {
    e.preventDefault();
    logEvent("copy_attempt");
});

// ── Disable paste ─────────────────────────────────────────────────────────────
document.addEventListener("paste", (e) => {
    e.preventDefault();
    logEvent("paste_attempt");
});

// ── Disable text selection via keyboard shortcuts ─────────────────────────────
document.addEventListener("keydown", (e) => {
    // Block Ctrl+A (select all), Ctrl+C, Ctrl+V, Ctrl+X, Ctrl+U (view source)
    const blocked = ["a", "c", "v", "x", "u", "s", "p"];
    if ((e.ctrlKey || e.metaKey) && blocked.includes(e.key.toLowerCase())) {
        e.preventDefault();
    }
    // Block F12 (DevTools)
    if (e.key === "F12") e.preventDefault();
    // Block Escape (might exit fullscreen)
    if (e.key === "Escape") e.preventDefault();
});

// ── Disable text selection via CSS (also in custom.css for safety) ────────────
document.addEventListener("selectstart", (e) => {
    e.preventDefault();
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. WEBCAM — Initialize and stream frames to proctor
// ─────────────────────────────────────────────────────────────────────────────
async function initWebcam() {
    try {
        webcamStream = await navigator.mediaDevices.getUserMedia({
            video: { width: 320, height: 240, facingMode: "user" },
            audio: false,
        });

        const video = document.getElementById("webcam-preview");
        if (video) {
            video.srcObject = webcamStream;
            video.play();
        }

        // Stream a frame every 5 seconds to proctors
        webcamFrameTimer = setInterval(() => captureAndSendWebcamFrame(), 5000);

    } catch (err) {
        logEvent("camera_off");
        showWarning("⚠️ Webcam access denied or unavailable. This has been logged.");
    }
}

function captureAndSendWebcamFrame() {
    if (!webcamStream) return;

    const video  = document.getElementById("webcam-preview");
    const canvas = document.createElement("canvas");
    canvas.width  = 320;
    canvas.height = 240;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const frame = canvas.toDataURL("image/jpeg", 0.5);   // 50% quality to keep payload small

    socket.emit("webcam_frame", { attempt_id: ATTEMPT_ID, frame });
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. SCREEN SHARE — Initialize and stream frames
// ─────────────────────────────────────────────────────────────────────────────
async function initScreenShare() {
    try {
        screenStream = await navigator.mediaDevices.getDisplayMedia({
            video: { frameRate: 1 },   // Low frame rate — enough for proctoring
            audio: false,
        });

        const screenVideo = document.getElementById("screen-preview");
        if (screenVideo) {
            screenVideo.srcObject = screenStream;
            screenVideo.play();
        }

        // Stream a frame every 8 seconds
        screenFrameTimer = setInterval(() => captureAndSendScreenFrame(), 8000);

        // Detect if user stops screen share manually
        screenStream.getVideoTracks()[0].addEventListener("ended", () => {
            logEvent("screen_share_stopped");
            showWarning("⚠️ Screen sharing stopped. This has been logged.");
            clearInterval(screenFrameTimer);
        });

    } catch (err) {
        showWarning("⚠️ Screen sharing is required for this examination.");
    }
}

function captureAndSendScreenFrame() {
    if (!screenStream) return;

    const screenVideo = document.getElementById("screen-preview");
    const canvas      = document.createElement("canvas");
    canvas.width  = 640;
    canvas.height = 400;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(screenVideo, 0, 0, canvas.width, canvas.height);
    const frame = canvas.toDataURL("image/jpeg", 0.4);

    socket.emit("screen_frame", { attempt_id: ATTEMPT_ID, frame });
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. COUNTDOWN TIMER
// ─────────────────────────────────────────────────────────────────────────────
function startTimer() {
    const timerEl = document.getElementById("timer-display");

    timerInterval = setInterval(() => {
        if (remainingSeconds <= 0) {
            clearInterval(timerInterval);
            showToast("⏰ Time's up! Your exam is being submitted automatically.", "warning");
            submitExam(true);
            return;
        }

        remainingSeconds--;

        const hrs  = Math.floor(remainingSeconds / 3600);
        const mins = Math.floor((remainingSeconds % 3600) / 60);
        const secs = remainingSeconds % 60;

        const formatted = [
            hrs > 0 ? String(hrs).padStart(2, "0") + ":" : "",
            String(mins).padStart(2, "0"),
            ":",
            String(secs).padStart(2, "0"),
        ].join("");

        if (timerEl) timerEl.textContent = formatted;

        // Warn when 5 minutes remain
        if (remainingSeconds === 300) {
            showToast("⚠️ 5 minutes remaining!", "warning");
        }

        // Danger color when under 1 minute
        if (remainingSeconds <= 60 && timerEl) {
            timerEl.classList.add("text-red-500", "animate-pulse");
        }

    }, 1000);
}

// ─────────────────────────────────────────────────────────────────────────────
// 7. AUTO-SAVE ANSWER
// Called whenever the candidate clicks a radio button.
// ─────────────────────────────────────────────────────────────────────────────
function saveAnswer(questionId, optionId) {
    const indicator = document.getElementById(`save-status-${questionId}`);
    if (indicator) {
        indicator.textContent = "Saving…";
        indicator.className   = "text-xs text-yellow-500";
    }

    fetch(SAVE_URL, {
        method:  "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken":  getCsrfToken(),
        },
        body: JSON.stringify({
            question_id: questionId,
            option_id:   optionId,
        }),
    })
    .then((r) => r.json())
    .then((data) => {
        if (indicator) {
            if (data.success) {
                indicator.textContent = "✓ Saved";
                indicator.className   = "text-xs text-green-500";
            } else {
                indicator.textContent = "Save failed";
                indicator.className   = "text-xs text-red-500";
            }
        }
        // Update question palette dot
        updatePalette(questionId, true);
    })
    .catch(() => {
        if (indicator) {
            indicator.textContent = "Error saving";
            indicator.className   = "text-xs text-red-500";
        }
    });
}

// Attach change listeners to all radio buttons
document.querySelectorAll("input[type='radio'][name^='question_']").forEach((radio) => {
    radio.addEventListener("change", () => {
        const questionId = parseInt(radio.dataset.questionId);
        const optionId   = parseInt(radio.value);
        saveAnswer(questionId, optionId);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// 8. QUESTION PALETTE — Visual indicator of answered/unanswered questions
// ─────────────────────────────────────────────────────────────────────────────
function updatePalette(questionId, answered) {
    const dot = document.getElementById(`palette-dot-${questionId}`);
    if (!dot) return;
    if (answered) {
        dot.classList.remove("bg-gray-300");
        dot.classList.add("bg-green-500");
    } else {
        dot.classList.remove("bg-green-500");
        dot.classList.add("bg-gray-300");
    }
}

// Scroll to a question when palette dot is clicked
function scrollToQuestion(questionId) {
    const el = document.getElementById(`question-${questionId}`);
    if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.remove("question-flash");
        // Force reflow so the animation can re-trigger on repeated clicks
        void el.offsetWidth;
        el.classList.add("question-flash");
        setTimeout(() => el.classList.remove("question-flash"), 1200);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 9. SUBMIT EXAM
// ─────────────────────────────────────────────────────────────────────────────
function submitExam(auto = false) {
    if (isSubmitting) return;
    isSubmitting = true;

    // Stop all streams and timers
    clearInterval(timerInterval);
    clearInterval(webcamFrameTimer);
    clearInterval(screenFrameTimer);

    if (webcamStream) webcamStream.getTracks().forEach((t) => t.stop());
    if (screenStream) screenStream.getTracks().forEach((t) => t.stop());

    socket.emit("candidate_leave", { attempt_id: ATTEMPT_ID });

    fetch(SUBMIT_URL, {
        method:  "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken":  getCsrfToken(),
        },
        body: JSON.stringify({ auto }),
    })
    .then((r) => r.json())
    .then((data) => {
        if (data.success) {
            // Exit fullscreen before redirecting
            if (document.exitFullscreen) document.exitFullscreen();
            window.location.href = data.redirect;
        } else {
            showToast("Submission failed. Please try again.", "error");
            isSubmitting = false;
        }
    })
    .catch(() => {
        showToast("Network error during submission. Retrying…", "error");
        setTimeout(() => {
            isSubmitting = false;
            submitExam(auto);
        }, 3000);
    });
}

// Manual submit button
const submitBtn = document.getElementById("submit-exam-btn");
if (submitBtn) {
    submitBtn.addEventListener("click", () => {
        if (confirm("Are you sure you want to submit your exam? This action cannot be undone.")) {
            submitExam(false);
        }
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// 10. LOG SUSPICIOUS EVENT — POST to server + emit via socket
// ─────────────────────────────────────────────────────────────────────────────
function logEvent(eventType, snapshotUrl = null) {
    // Capture a webcam snapshot when a violation occurs (if webcam is active)
    if (!snapshotUrl && webcamStream) {
        snapshotUrl = captureWebcamSnapshot();
    }

    // Via socket (real-time alert to proctor)
    socket.emit("suspicious_event", {
        attempt_id:   ATTEMPT_ID,
        event_type:   eventType,
        snapshot_url: snapshotUrl,
    });

    // Via HTTP (persist to DB in case socket drops)
    fetch(LOG_URL, {
        method:  "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken":  getCsrfToken(),
        },
        body: JSON.stringify({
            event_type:   eventType,
            snapshot_url: snapshotUrl,
        }),
    }).catch(() => {});  // Silent fail — socket already handled it
}

function captureWebcamSnapshot() {
    try {
        const video  = document.getElementById("webcam-preview");
        const canvas = document.createElement("canvas");
        canvas.width  = 160;
        canvas.height = 120;
        canvas.getContext("2d").drawImage(video, 0, 0, 160, 120);
        return canvas.toDataURL("image/jpeg", 0.4);
    } catch {
        return null;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 11. UI HELPERS
// ─────────────────────────────────────────────────────────────────────────────
function showWarning(message) {
    const banner = document.getElementById("warning-banner");
    if (!banner) return;
    banner.textContent = message;
    banner.classList.remove("hidden");
    setTimeout(() => banner.classList.add("hidden"), 5000);
}

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
    toast.className = `text-white text-sm px-4 py-3 rounded shadow-lg mb-2 ${colorMap[type] || colorMap.info}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => toast.remove(), 5000);
}

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
}

// ─────────────────────────────────────────────────────────────────────────────
// 12. INITIALISE ON PAGE LOAD
// ─────────────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
    // Enter fullscreen immediately
    requestFullscreen();

    // Start countdown timer
    startTimer();

    // Initialize media streams
    await initWebcam();
    await initScreenShare();

    // Mark already-answered questions in the palette (from saved_answers injected by server)
    document.querySelectorAll("input[type='radio'][name^='question_']:checked").forEach((radio) => {
        const questionId = parseInt(radio.dataset.questionId);
        updatePalette(questionId, true);
    });
});

// Prevent navigation away from exam (back button, refresh)
window.addEventListener("beforeunload", (e) => {
    if (!isSubmitting) {
        e.preventDefault();
        e.returnValue = "Are you sure you want to leave? Your exam progress may be lost.";
    }
});