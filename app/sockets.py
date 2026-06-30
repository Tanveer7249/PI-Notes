from flask import request
from flask_login import current_user
from flask_socketio import join_room, leave_room, emit
from app import socketio, db
from app.models import Attempt, SuspiciousLog

# ─────────────────────────────────────────────────────────────────────────────
# ROOM NAMING CONVENTION
#
#   "proctor_room"          → All connected proctors join this single room.
#                             Used to broadcast global alerts to every proctor.
#
#   "attempt_{attempt_id}"  → Each candidate's live attempt has its own room.
#                             Proctors join this room when opening the monitor view.
#                             The candidate's webcam/screen frames are emitted here.
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# CANDIDATE — Join their exam room on socket connect
# exam.js calls this immediately after the exam page loads.
# ─────────────────────────────────────────────────────────────────────────────
@socketio.on("candidate_join")
def on_candidate_join(data):
    """
    Payload: { attempt_id: int }
    The candidate joins a room named after their attempt so proctors can
    subscribe to that specific feed.
    """
    attempt_id = data.get("attempt_id")
    if not attempt_id:
        return

    attempt = Attempt.query.get(attempt_id)
    if not attempt or attempt.is_submitted:
        return

    room = f"attempt_{attempt_id}"
    join_room(room)

    # Notify all proctors that a new candidate is live
    emit(
        "candidate_online",
        {
            "attempt_id":     attempt_id,
            "candidate_name": attempt.candidate.name,
            "test_title":     attempt.test.title,
        },
        to="proctor_room",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CANDIDATE — Leave exam room on disconnect or submission
# ─────────────────────────────────────────────────────────────────────────────
@socketio.on("candidate_leave")
def on_candidate_leave(data):
    """
    Payload: { attempt_id: int }
    """
    attempt_id = data.get("attempt_id")
    if not attempt_id:
        return

    room = f"attempt_{attempt_id}"
    leave_room(room)

    attempt = Attempt.query.get(attempt_id)
    name    = attempt.candidate.name if attempt else "Unknown"

    emit(
        "candidate_offline",
        {"attempt_id": attempt_id, "candidate_name": name},
        to="proctor_room",
    )


# ─────────────────────────────────────────────────────────────────────────────
# PROCTOR — Join the global proctor room on dashboard load
# proctor.js calls this on page load.
# ─────────────────────────────────────────────────────────────────────────────
@socketio.on("proctor_join")
def on_proctor_join():
    join_room("proctor_room")


# ─────────────────────────────────────────────────────────────────────────────
# PROCTOR — Subscribe to a specific candidate's feed (monitor page)
# ─────────────────────────────────────────────────────────────────────────────
@socketio.on("proctor_monitor")
def on_proctor_monitor(data):
    """
    Payload: { attempt_id: int }
    Proctor joins the specific attempt room to receive webcam/screen frames.
    """
    attempt_id = data.get("attempt_id")
    if attempt_id:
        join_room(f"attempt_{attempt_id}")


# ─────────────────────────────────────────────────────────────────────────────
# SUSPICIOUS ACTIVITY ALERT
# exam.js emits this whenever an anti-cheat rule is triggered.
# We save the log to DB and broadcast to all proctors.
# ─────────────────────────────────────────────────────────────────────────────
@socketio.on("suspicious_event")
def on_suspicious_event(data):
    """
    Payload: {
        attempt_id:   int,
        event_type:   str,   (tab_switch | fullscreen_exit | copy_attempt | etc.)
        snapshot_url: str    (optional base64 webcam frame)
    }
    """
    attempt_id   = data.get("attempt_id")
    event_type   = data.get("event_type", "unknown")
    snapshot_url = data.get("snapshot_url")

    if not attempt_id:
        return

    attempt = Attempt.query.get(attempt_id)
    if not attempt or attempt.is_submitted:
        return

    # Persist to DB
    log = SuspiciousLog(
        attempt_id=attempt_id,
        event_type=event_type,
        snapshot_url=snapshot_url,
    )
    db.session.add(log)
    db.session.commit()

    # Build alert payload for proctors
    alert_payload = {
        "attempt_id":     attempt_id,
        "candidate_name": attempt.candidate.name,
        "test_title":     attempt.test.title,
        "event_type":     event_type,
        "timestamp":      log.timestamp.strftime("%H:%M:%S"),
        "snapshot_url":   snapshot_url,
    }

    # Broadcast to all proctors in the global room
    emit("new_alert", alert_payload, to="proctor_room")

    # Also send to anyone monitoring this specific attempt
    emit("new_alert", alert_payload, to=f"attempt_{attempt_id}")


# ─────────────────────────────────────────────────────────────────────────────
# WEBCAM FRAME — Candidate streams webcam snapshots to their attempt room
# exam.js captures a frame from the webcam every N seconds and emits it here.
# Proctors monitoring that candidate receive it in real time.
# ─────────────────────────────────────────────────────────────────────────────
@socketio.on("webcam_frame")
def on_webcam_frame(data):
    """
    Payload: {
        attempt_id: int,
        frame:      str   (base64-encoded JPEG data URI)
    }
    """
    attempt_id = data.get("attempt_id")
    frame      = data.get("frame")

    if not attempt_id or not frame:
        return

    # Forward to the proctor monitoring this candidate (do not broadcast globally)
    emit(
        "webcam_update",
        {"attempt_id": attempt_id, "frame": frame},
        to=f"attempt_{attempt_id}",
        include_self=False,   # Don't echo back to the candidate
    )


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN SHARE FRAME — Candidate streams screen share frames
# Same pattern as webcam_frame but for screen content.
# ─────────────────────────────────────────────────────────────────────────────
@socketio.on("screen_frame")
def on_screen_frame(data):
    """
    Payload: {
        attempt_id: int,
        frame:      str   (base64-encoded JPEG data URI of screen capture)
    }
    """
    attempt_id = data.get("attempt_id")
    frame      = data.get("frame")

    if not attempt_id or not frame:
        return

    emit(
        "screen_update",
        {"attempt_id": attempt_id, "frame": frame},
        to=f"attempt_{attempt_id}",
        include_self=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PROCTOR FORCE SUBMIT — Proctor manually ends a candidate's exam
# ─────────────────────────────────────────────────────────────────────────────
@socketio.on("proctor_force_submit")
def on_force_submit(data):
    """
    Payload: { attempt_id: int }
    Emits a force_submit event directly to the candidate's attempt room,
    which exam.js listens for and triggers the submit flow.
    """
    attempt_id = data.get("attempt_id")
    if not attempt_id:
        return

    emit(
        "force_submit",
        {"reason": "Proctor has ended your examination."},
        to=f"attempt_{attempt_id}",
    )