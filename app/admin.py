import io
import csv
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, abort, Response
)
from flask_login import login_required, current_user
from app import db
from app.models import User, Test, Question, Option, Attempt, Answer, SuspiciousLog

admin_bp = Blueprint("admin", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# GUARD — All admin routes require the admin role
# ─────────────────────────────────────────────────────────────────────────────
def admin_required(f):
    """Decorator that ensures only admin users can access a route."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    total_tests      = Test.query.filter_by(created_by=current_user.id).count()
    published_tests  = Test.query.filter_by(created_by=current_user.id, is_published=True).count()
    total_candidates = User.query.filter_by(role="candidate").count()
    total_attempts   = Attempt.query.join(Test).filter(
                           Test.created_by == current_user.id
                       ).count()

    recent_attempts = (
        Attempt.query
        .join(Test).filter(Test.created_by == current_user.id)
        .order_by(Attempt.started_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        total_tests=total_tests,
        published_tests=published_tests,
        total_candidates=total_candidates,
        total_attempts=total_attempts,
        recent_attempts=recent_attempts,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST LIST
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests")
@login_required
@admin_required
def test_list():
    tests = (
        Test.query
        .filter_by(created_by=current_user.id)
        .order_by(Test.created_at.desc())
        .all()
    )
    return render_template("admin/test_list.html", tests=tests)


# ─────────────────────────────────────────────────────────────────────────────
# CREATE TEST
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/new", methods=["GET", "POST"])
@login_required
@admin_required
def create_test():
    if request.method == "POST":
        title            = request.form.get("title", "").strip()
        description      = request.form.get("description", "").strip()
        duration_minutes = request.form.get("duration_minutes", 60)
        negative_marking = request.form.get("negative_marking", 0.0)
        pass_marks       = request.form.get("pass_marks", 0.0)

        if not title:
            flash("Test title is required.", "danger")
            return render_template("admin/test_form.html", test=None)

        try:
            duration_minutes = int(duration_minutes)
            negative_marking = float(negative_marking)
            pass_marks       = float(pass_marks)
        except ValueError:
            flash("Invalid numeric values provided.", "danger")
            return render_template("admin/test_form.html", test=None)

        test = Test(
            title=title,
            description=description,
            duration_minutes=duration_minutes,
            negative_marking=negative_marking,
            pass_marks=pass_marks,
            created_by=current_user.id,
        )
        db.session.add(test)
        db.session.commit()
        flash(f'Test "{title}" created successfully.', "success")
        return redirect(url_for("admin.test_list"))

    return render_template("admin/test_form.html", test=None)


# ─────────────────────────────────────────────────────────────────────────────
# EDIT TEST
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/<int:test_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_test(test_id):
    test = Test.query.filter_by(id=test_id, created_by=current_user.id).first_or_404()

    if request.method == "POST":
        title            = request.form.get("title", "").strip()
        description      = request.form.get("description", "").strip()
        duration_minutes = request.form.get("duration_minutes", 60)
        negative_marking = request.form.get("negative_marking", 0.0)
        pass_marks       = request.form.get("pass_marks", 0.0)

        if not title:
            flash("Test title is required.", "danger")
            return render_template("admin/test_form.html", test=test)

        try:
            duration_minutes = int(duration_minutes)
            negative_marking = float(negative_marking)
            pass_marks       = float(pass_marks)
        except ValueError:
            flash("Invalid numeric values provided.", "danger")
            return render_template("admin/test_form.html", test=test)

        test.title            = title
        test.description      = description
        test.duration_minutes = duration_minutes
        test.negative_marking = negative_marking
        test.pass_marks       = pass_marks
        db.session.commit()

        flash("Test updated successfully.", "success")
        return redirect(url_for("admin.test_list"))

    return render_template("admin/test_form.html", test=test)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE TEST
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/<int:test_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_test(test_id):
    test = Test.query.filter_by(id=test_id, created_by=current_user.id).first_or_404()
    db.session.delete(test)
    db.session.commit()
    flash("Test deleted.", "info")
    return redirect(url_for("admin.test_list"))


# ─────────────────────────────────────────────────────────────────────────────
# PUBLISH / UNPUBLISH TEST
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/<int:test_id>/publish", methods=["POST"])
@login_required
@admin_required
def toggle_publish(test_id):
    test = Test.query.filter_by(id=test_id, created_by=current_user.id).first_or_404()

    if not test.is_published and test.question_count() == 0:
        flash("Cannot publish a test with no questions.", "warning")
        return redirect(url_for("admin.test_list"))

    test.is_published = not test.is_published
    db.session.commit()
    status = "published" if test.is_published else "unpublished"
    flash(f'Test "{test.title}" has been {status}.', "success")
    return redirect(url_for("admin.test_list"))


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION LIST (for a specific test)
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/<int:test_id>/questions")
@login_required
@admin_required
def question_list(test_id):
    test      = Test.query.filter_by(id=test_id, created_by=current_user.id).first_or_404()
    questions = test.questions.order_by(Question.order_index).all()
    return render_template("admin/question_form.html", test=test, questions=questions, editing=None)


# ─────────────────────────────────────────────────────────────────────────────
# ADD QUESTION
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/<int:test_id>/questions/add", methods=["POST"])
@login_required
@admin_required
def add_question(test_id):
    test = Test.query.filter_by(id=test_id, created_by=current_user.id).first_or_404()

    question_text  = request.form.get("question_text", "").strip()
    marks          = request.form.get("marks", 1)
    correct_index  = request.form.get("correct_option")   # "0", "1", "2", "3"
    option_texts   = request.form.getlist("option_text")  # list of 4 strings

    # ── Validation ─────────────────────────────────────────────────────────
    if not question_text:
        flash("Question text is required.", "danger")
        return redirect(url_for("admin.question_list", test_id=test_id))

    option_texts = [o.strip() for o in option_texts if o.strip()]
    if len(option_texts) < 2:
        flash("At least 2 options are required.", "danger")
        return redirect(url_for("admin.question_list", test_id=test_id))

    if correct_index is None or not correct_index.isdigit():
        flash("Please select the correct option.", "danger")
        return redirect(url_for("admin.question_list", test_id=test_id))

    correct_index = int(correct_index)
    if correct_index >= len(option_texts):
        flash("Invalid correct option selected.", "danger")
        return redirect(url_for("admin.question_list", test_id=test_id))

    try:
        marks = int(marks)
    except ValueError:
        marks = 1

    # ── Determine display order ─────────────────────────────────────────────
    last = test.questions.order_by(Question.order_index.desc()).first()
    order_index = (last.order_index + 1) if last else 0

    # ── Persist question + options ──────────────────────────────────────────
    question = Question(
        test_id=test_id,
        text=question_text,
        marks=marks,
        order_index=order_index,
    )
    db.session.add(question)
    db.session.flush()  # Get question.id before committing

    for idx, opt_text in enumerate(option_texts):
        option = Option(
            question_id=question.id,
            text=opt_text,
            is_correct=(idx == correct_index),
        )
        db.session.add(option)

    db.session.commit()
    flash("Question added successfully.", "success")
    return redirect(url_for("admin.question_list", test_id=test_id))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE QUESTION
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/<int:test_id>/questions/<int:question_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_question(test_id, question_id):
    test     = Test.query.filter_by(id=test_id, created_by=current_user.id).first_or_404()
    question = Question.query.filter_by(id=question_id, test_id=test.id).first_or_404()
    db.session.delete(question)
    db.session.commit()
    flash("Question deleted.", "info")
    return redirect(url_for("admin.question_list", test_id=test_id))


# ─────────────────────────────────────────────────────────────────────────────
# CSV IMPORT
# Expected CSV format (with header row):
#   question_text, option_a, option_b, option_c, option_d, correct_option, marks
#   correct_option must be one of: a, b, c, d
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/<int:test_id>/import-csv", methods=["POST"])
@login_required
@admin_required
def import_csv(test_id):
    test = Test.query.filter_by(id=test_id, created_by=current_user.id).first_or_404()
    file = request.files.get("csv_file")

    if not file or not file.filename.endswith(".csv"):
        flash("Please upload a valid .csv file.", "danger")
        return redirect(url_for("admin.question_list", test_id=test_id))

    stream  = io.StringIO(file.stream.read().decode("utf-8"))
    reader  = csv.DictReader(stream)

    required_columns = {"question_text", "option_a", "option_b", "option_c", "option_d",
                        "correct_option", "marks"}

    if not required_columns.issubset(set(reader.fieldnames or [])):
        flash(
            "CSV must have columns: question_text, option_a, option_b, "
            "option_c, option_d, correct_option, marks",
            "danger",
        )
        return redirect(url_for("admin.question_list", test_id=test_id))

    correct_map = {"a": 0, "b": 1, "c": 2, "d": 3}
    imported    = 0
    errors      = 0

    last = test.questions.order_by(Question.order_index.desc()).first()
    order_index = (last.order_index + 1) if last else 0

    for row in reader:
        q_text       = row.get("question_text", "").strip()
        correct_key  = row.get("correct_option", "").strip().lower()
        option_texts = [
            row.get("option_a", "").strip(),
            row.get("option_b", "").strip(),
            row.get("option_c", "").strip(),
            row.get("option_d", "").strip(),
        ]

        try:
            marks = int(row.get("marks", 1))
        except ValueError:
            marks = 1

        if not q_text or correct_key not in correct_map:
            errors += 1
            continue

        if any(o == "" for o in option_texts):
            errors += 1
            continue

        question = Question(
            test_id=test_id,
            text=q_text,
            marks=marks,
            order_index=order_index,
        )
        db.session.add(question)
        db.session.flush()

        correct_idx = correct_map[correct_key]
        for idx, opt_text in enumerate(option_texts):
            db.session.add(Option(
                question_id=question.id,
                text=opt_text,
                is_correct=(idx == correct_idx),
            ))

        order_index += 1
        imported    += 1

    db.session.commit()
    flash(f"CSV import complete: {imported} questions imported, {errors} rows skipped.", "success")
    return redirect(url_for("admin.question_list", test_id=test_id))


# ─────────────────────────────────────────────────────────────────────────────
# RESULTS — View all attempts for a test
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/<int:test_id>/results")
@login_required
@admin_required
def results(test_id):
    test     = Test.query.filter_by(id=test_id, created_by=current_user.id).first_or_404()
    attempts = (
        Attempt.query
        .filter_by(test_id=test_id, is_submitted=True)
        .order_by(Attempt.submitted_at.desc())
        .all()
    )
    return render_template("admin/results.html", test=test, attempts=attempts)


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT RESULTS as CSV
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/tests/<int:test_id>/results/export")
@login_required
@admin_required
def export_results(test_id):
    test     = Test.query.filter_by(id=test_id, created_by=current_user.id).first_or_404()
    attempts = (
        Attempt.query
        .filter_by(test_id=test_id, is_submitted=True)
        .order_by(Attempt.submitted_at.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Candidate Name", "Email", "Score", "Total Marks",
        "Pass Marks", "Result", "Time Taken (min)",
        "Auto Submitted", "Submitted At",
        "Tab Switches", "Fullscreen Exits", "Copy Attempts"
    ])

    for attempt in attempts:
        logs        = attempt.suspicious_logs
        tab_sw      = logs.filter_by(event_type="tab_switch").count()
        fs_exits    = logs.filter_by(event_type="fullscreen_exit").count()
        copy_att    = logs.filter_by(event_type="copy_attempt").count()
        total_marks = test.total_marks()
        result      = "PASS" if attempt.passed() else "FAIL"

        writer.writerow([
            attempt.candidate.name,
            attempt.candidate.email,
            attempt.score,
            total_marks,
            test.pass_marks,
            result,
            attempt.duration_taken(),
            "Yes" if attempt.auto_submitted else "No",
            attempt.submitted_at.strftime("%Y-%m-%d %H:%M") if attempt.submitted_at else "",
            tab_sw,
            fs_exits,
            copy_att,
        ])

    output.seek(0)
    filename = f"results_{test.title.replace(' ', '_')}_{datetime.utcnow().strftime('%Y%m%d')}.csv"

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# SUSPICIOUS LOGS for one attempt
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/attempts/<int:attempt_id>/logs")
@login_required
@admin_required
def attempt_logs(attempt_id):
    attempt = Attempt.query.get_or_404(attempt_id)
    # Ensure the test belongs to this admin
    test = Test.query.filter_by(id=attempt.test_id, created_by=current_user.id).first_or_404()
    logs = attempt.suspicious_logs.order_by(SuspiciousLog.timestamp.asc()).all()
    return render_template("admin/results.html", test=test, attempts=None,
                           single_attempt=attempt, logs=logs)