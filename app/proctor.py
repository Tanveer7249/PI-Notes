from flask import Blueprint, render_template, abort, jsonify
from flask_login import login_required, current_user
from app.models import Test, Attempt, SuspiciousLog, User

proctor_bp = Blueprint("proctor", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# GUARD — Only proctors can access these routes
# ─────────────────────────────────────────────────────────────────────────────
def proctor_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_proctor():
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD — Shows all currently active (non-submitted) attempts across all tests
# Proctors can see every live candidate, regardless of which admin created the test.
# ─────────────────────────────────────────────────────────────────────────────
@proctor_bp.route("/dashboard")
@login_required
@proctor_required
def dashboard():
    # Active attempts: started but not yet submitted
    active_attempts = (
        Attempt.query
        .filter_by(is_submitted=False)
        .order_by(Attempt.started_at.asc())
        .all()
    )

    # Recent violations (last 20) across all active attempts for the alert feed
    recent_logs = (
        SuspiciousLog.query
        .order_by(SuspiciousLog.timestamp.desc())
        .limit(20)
        .all()
    )

    # All published tests for the filter dropdown
    all_tests = Test.query.filter_by(is_published=True).all()

    return render_template(
        "proctor/dashboard.html",
        active_attempts=active_attempts,
        recent_logs=recent_logs,
        all_tests=all_tests,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MONITOR — Detailed view of one candidate's live attempt
# Shows webcam feed, screen share, and suspicious log history for that attempt.
# ─────────────────────────────────────────────────────────────────────────────
@proctor_bp.route("/monitor/<int:attempt_id>")
@login_required
@proctor_required
def monitor(attempt_id):
    attempt = Attempt.query.get_or_404(attempt_id)

    logs = (
        SuspiciousLog.query
        .filter_by(attempt_id=attempt_id)
        .order_by(SuspiciousLog.timestamp.desc())
        .all()
    )

    # Count violations by type for the summary panel
    violation_summary = {}
    for log in logs:
        violation_summary[log.event_type] = violation_summary.get(log.event_type, 0) + 1

    return render_template(
        "proctor/monitor.html",
        attempt=attempt,
        logs=logs,
        violation_summary=violation_summary,
    )


# ─────────────────────────────────────────────────────────────────────────────
# LIVE STATS API — Called by proctor.js via polling to refresh the dashboard
# Returns JSON with active candidate count and recent alerts.
# ─────────────────────────────────────────────────────────────────────────────
@proctor_bp.route("/api/live-stats")
@login_required
@proctor_required
def live_stats():
    active_count = Attempt.query.filter_by(is_submitted=False).count()

    recent_logs = (
        SuspiciousLog.query
        .order_by(SuspiciousLog.timestamp.desc())
        .limit(10)
        .all()
    )

    alerts = []
    for log in recent_logs:
        alerts.append({
            "candidate":  log.attempt.candidate.name,
            "event_type": log.event_type,
            "timestamp":  log.timestamp.strftime("%H:%M:%S"),
            "attempt_id": log.attempt_id,
        })

    return jsonify({
        "active_candidates": active_count,
        "alerts":            alerts,
    })


# ─────────────────────────────────────────────────────────────────────────────
# CANDIDATE LOGS API — Returns suspicious logs for one attempt as JSON
# Used by proctor.js to update the log panel inside monitor view in real time.
# ─────────────────────────────────────────────────────────────────────────────
@proctor_bp.route("/api/attempt/<int:attempt_id>/logs")
@login_required
@proctor_required
def attempt_logs_api(attempt_id):
    attempt = Attempt.query.get_or_404(attempt_id)

    logs = (
        SuspiciousLog.query
        .filter_by(attempt_id=attempt_id)
        .order_by(SuspiciousLog.timestamp.desc())
        .limit(50)
        .all()
    )

    data = []
    for log in logs:
        data.append({
            "event_type":   log.event_type,
            "timestamp":    log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "snapshot_url": log.snapshot_url,
        })

    return jsonify({
        "attempt_id":    attempt_id,
        "candidate":     attempt.candidate.name,
        "is_submitted":  attempt.is_submitted,
        "logs":          data,
    })