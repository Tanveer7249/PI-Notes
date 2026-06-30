from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db, bcrypt
from app.models import User

auth_bp = Blueprint("auth", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# ROOT — redirect to login or appropriate dashboard
# ─────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)
    return redirect(url_for("auth.login"))


# ─────────────────────────────────────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    # Already logged-in users have no reason to register again
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role     = request.form.get("role", "candidate")

        # ── Validation ────────────────────────────────────────────────────────
        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("auth/register.html")

        if role not in ("admin", "candidate", "proctor"):
            flash("Invalid role selected.", "danger")
            return render_template("auth/register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "danger")
            return render_template("auth/register.html")

        # ── Create user ───────────────────────────────────────────────────────
        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        user = User(name=name, email=email, password_hash=hashed_pw, role=role)
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("auth/login.html")

        user = User.query.filter_by(email=email).first()

        if not user or not bcrypt.check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html")

        # Remember session across browser restarts
        login_user(user, remember=True)
        flash(f"Welcome back, {user.name}!", "success")

        # Honor the "next" parameter (Flask-Login sets it on @login_required redirect)
        next_page = request.args.get("next")
        if next_page:
            return redirect(next_page)

        return _redirect_by_role(user)

    return render_template("auth/login.html")


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — Role-based redirect after login
# ─────────────────────────────────────────────────────────────────────────────
def _redirect_by_role(user):
    if user.is_admin():
        return redirect(url_for("admin.dashboard"))
    elif user.is_proctor():
        return redirect(url_for("proctor.dashboard"))
    else:
        return redirect(url_for("candidate.dashboard"))