from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, abort, jsonify
)
from flask_login import login_required, current_user
from app import db
from app.models import Test, Question, Option, Attempt, Answer, SuspiciousLog

candidate_bp = Blueprint("candidate", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# GUARD — Only candidates can access these routes
# ─────────────────────────────────────────────────────────────────────────────
def candidate_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_candidate():
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD — List all published tests available to the candidate
# ─────────────────────────────────────────────────────────────────────────────
@candidate_bp.route("/dashboard")
@login_required
@candidate_required
def dashboard():
    published_tests = Test.query.filter_by(is_published=True).order_by(Test.created_at.desc()).all()

    # Determine which tests this candidate has already attempted
    attempted_test_ids = {
        a.test_id for a in Attempt.query.filter_by(user_id=current_user.id).all()
    }

    return render_template(
        "candidate/dashboard.html",
        tests=published_tests,
        attempted_ids=attempted_test_ids,
    )


# ─────────────────────────────────────────────────────────────────────────────
# LOBBY — Pre-exam setup: webcam + screen share permissions
# Candidate lands here before the actual exam starts.
# ─────────────────────────────────────────────────────────────────────────────
@candidate_bp.route("/tests/<int:test_id>/lobby")
@login_required
@candidate_required
def lobby(test_id):
    test = Test.query.filter_by(id=test_id, is_published=True).first_or_404()

    # Prevent re-attempting a submitted test
    existing = Attempt.query.filter_by(
        test_id=test_id, user_id=current_user.id, is_submitted=True
    ).first()
    if existing:
        flash("You have already submitted this test. You cannot retake it.", "warning")
        return redirect(url_for("candidate.dashboard"))

    return render_template("candidate/lobby.html", test=test)


# ─────────────────────────────────────────────────────────────────────────────
# START EXAM — Creates the Attempt record and redirects to exam page
# Called when candidate clicks "Start Exam" from the lobby.
# ─────────────────────────────────────────────────────────────────────────────
@candidate_bp.route("/tests/<int:test_id>/start", methods=["POST"])
@login_required
@candidate_required
def start_exam(test_id):
    test = Test.query.filter_by(id=test_id, is_published=True).first_or_404()

    # Check for existing submitted attempt
    submitted = Attempt.query.filter_by(
        test_id=test_id, user_id=current_user.id, is_submitted=True
    ).first()
    if submitted:
        flash("You have already completed this test.", "warning")
        return redirect(url_for("candidate.dashboard"))

    # Resume an in-progress attempt instead of creating a duplicate
    attempt = Attempt.query.filter_by(
        test_id=test_id, user_id=current_user.id, is_submitted=False
    ).first()

    if not attempt:
        attempt = Attempt(test_id=test_id, user_id=current_user.id)
        db.session.add(attempt)
        db.session.commit()

    return redirect(url_for("candidate.exam", test_id=test_id))


# ─────────────────────────────────────────────────────────────────────────────
# EXAM PAGE — The main fullscreen MCQ interface
# ─────────────────────────────────────────────────────────────────────────────
@candidate_bp.route("/tests/<int:test_id>/exam")
@login_required
@candidate_required
def exam(test_id):
    test = Test.query.filter_by(id=test_id, is_published=True).first_or_404()

    attempt = Attempt.query.filter_by(
        test_id=test_id, user_id=current_user.id, is_submitted=False
    ).first()

    if not attempt:
        flash("No active attempt found. Please start the test from the lobby.", "warning")
        return redirect(url_for("candidate.lobby", test_id=test_id))

    questions = test.questions.order_by(Question.order_index).all()

    # Build a map of already-saved answers {question_id: selected_option_id}
    saved_answers = {
        a.question_id: a.selected_option_id
        for a in attempt.answers.all()
    }

    # Calculate elapsed seconds so JS can set the timer correctly
    elapsed_seconds = int((datetime.utcnow() - attempt.started_at).total_seconds())
    total_seconds   = test.duration_minutes * 60
    remaining_secs  = max(0, total_seconds - elapsed_seconds)

    return render_template(
        "candidate/exam.html",
        test=test,
        attempt=attempt,
        questions=questions,
        saved_answers=saved_answers,
        remaining_secs=remaining_secs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-SAVE ANSWER — Called via AJAX every time a candidate selects an option
# Returns JSON so exam.js can confirm save without a page reload.
# ─────────────────────────────────────────────────────────────────────────────
@candidate_bp.route("/attempts/<int:attempt_id>/save-answer", methods=["POST"])
@login_required
@candidate_required
def save_answer(attempt_id):
    attempt = Attempt.query.filter_by(
        id=attempt_id, user_id=current_user.id, is_submitted=False
    ).first()

    if not attempt:
        return jsonify({"success": False, "error": "Invalid or already submitted attempt."}), 400

    data        = request.get_json()
    question_id = data.get("question_id")
    option_id   = data.get("option_id")   # Can be None (deselect/skip)

    if not question_id:
        return jsonify({"success": False, "error": "question_id is required."}), 400

    # Verify question belongs to this test
    question = Question.query.filter_by(id=question_id, test_id=attempt.test_id).first()
    if not question:
        return jsonify({"success": False, "error": "Question not found."}), 404

    # Verify the option belongs to this question (if provided)
    if option_id:
        option = Option.query.filter_by(id=option_id, question_id=question_id).first()
        if not option:
            return jsonify({"success": False, "error": "Option not found."}), 404

    # Upsert: update existing answer or create new one
    answer = Answer.query.filter_by(
        attempt_id=attempt_id, question_id=question_id
    ).first()

    if answer:
        answer.selected_option_id = option_id
    else:
        answer = Answer(
            attempt_id=attempt_id,
            question_id=question_id,
            selected_option_id=option_id,
        )
        db.session.add(answer)

    db.session.commit()
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
# LOG SUSPICIOUS ACTIVITY — Called via AJAX from exam.js anti-cheat listeners
# ─────────────────────────────────────────────────────────────────────────────
@candidate_bp.route("/attempts/<int:attempt_id>/log-event", methods=["POST"])
@login_required
@candidate_required
def log_event(attempt_id):
    attempt = Attempt.query.filter_by(
        id=attempt_id, user_id=current_user.id
    ).first()

    if not attempt:
        return jsonify({"success": False}), 400

    data         = request.get_json()
    event_type   = data.get("event_type", "unknown")
    snapshot_url = data.get("snapshot_url", None)   # Optional base64 webcam image

    allowed_events = {
        "tab_switch", "fullscreen_exit", "copy_attempt",
        "paste_attempt", "right_click", "camera_off",
        "screen_share_stopped", "auto_submitted", "visibility_hidden"
    }

    if event_type not in allowed_events:
        return jsonify({"success": False, "error": "Unknown event type."}), 400

    log = SuspiciousLog(
        attempt_id=attempt_id,
        event_type=event_type,
        snapshot_url=snapshot_url,
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
# SUBMIT EXAM — Calculates score with negative marking and marks attempt done
# Called both manually (candidate clicks Submit) and automatically (timer/violations)
# ─────────────────────────────────────────────────────────────────────────────
@candidate_bp.route("/attempts/<int:attempt_id>/submit", methods=["POST"])
@login_required
@candidate_required
def submit_exam(attempt_id):
    attempt = Attempt.query.filter_by(
        id=attempt_id, user_id=current_user.id, is_submitted=False
    ).first()

    if not attempt:
        return jsonify({"success": False, "error": "Attempt not found or already submitted."}), 400

    data          = request.get_json(silent=True) or {}
    auto_flag     = data.get("auto", False)   # True if triggered by timer or anti-cheat
    test          = attempt.test
    questions     = test.questions.all()
    negative_rate = test.negative_marking     # e.g. 0.25 means 25% of question marks deducted

    total_score = 0.0

    for question in questions:
        answer = Answer.query.filter_by(
            attempt_id=attempt_id, question_id=question.id
        ).first()

        correct_option = question.correct_option()

        if answer and answer.selected_option_id:
            if answer.selected_option_id == correct_option.id:
                # Correct answer — full marks
                answer.is_correct = True
                total_score      += question.marks
            else:
                # Wrong answer — apply negative marking if enabled
                answer.is_correct = False
                total_score      -= question.marks * negative_rate
        else:
            # Skipped question — no marks, no penalty
            if answer:
                answer.is_correct = None

    # Ensure score never goes below zero
    total_score = max(0.0, round(total_score, 2))

    attempt.score          = total_score
    attempt.is_submitted   = True
    attempt.auto_submitted = auto_flag
    attempt.submitted_at   = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "success":  True,
        "score":    total_score,
        "total":    test.total_marks(),
        "passed":   attempt.passed(),
        "redirect": url_for("candidate.result", attempt_id=attempt_id),
    })


# ─────────────────────────────────────────────────────────────────────────────
# RESULT PAGE — Shown after submission
# ─────────────────────────────────────────────────────────────────────────────
@candidate_bp.route("/attempts/<int:attempt_id>/result")
@login_required
@candidate_required
def result(attempt_id):
    attempt = Attempt.query.filter_by(
        id=attempt_id, user_id=current_user.id, is_submitted=True
    ).first_or_404()

    test      = attempt.test
    answers   = attempt.answers.all()
    questions = test.questions.order_by(Question.order_index).all()

    # Build a lookup: question_id → Answer
    answer_map = {a.question_id: a for a in answers}

    return render_template(
        "candidate/dashboard.html",
        show_result=True,
        attempt=attempt,
        test=test,
        questions=questions,
        answer_map=answer_map,
    )