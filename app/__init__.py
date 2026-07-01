from flask import Flask, app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO

from config import get_config

# ── Extension instances (created here, initialized in create_app) ─────────────
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()
socketio = SocketIO()


def create_app():
    """
    Flask application factory.
    Creates and configures the app, registers all extensions and blueprints.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="../static",
    )

    # ── Load config ───────────────────────────────────────────────────────────
    app.config.from_object(get_config())
    # Trust Render's proxy so Flask sees HTTPS correctly
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=2, x_host=2, x_prefix=2)
    

    # ── Initialize extensions ─────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    # SocketIO must be initialized with the app and async mode
    socketio.init_app(
        app,
        async_mode=app.config["SOCKETIO_ASYNC_MODE"],
        cors_allowed_origins="*",   # Tighten this to your domain in production
    )

    # ── Flask-Login configuration ─────────────────────────────────────────────
    login_manager.login_view = "auth.login"          # Redirect here if @login_required fails
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"

    # ── User loader (required by Flask-Login) ─────────────────────────────────
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ── Register blueprints ───────────────────────────────────────────────────
    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.candidate import candidate_bp
    from app.proctor import proctor_bp

    app.register_blueprint(auth_bp)               # /login, /logout, /register
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(candidate_bp, url_prefix="/candidate")
    app.register_blueprint(proctor_bp, url_prefix="/proctor")

    # ── Register SocketIO event handlers ─────────────────────────────────────
    from app import sockets  # noqa: F401 — importing registers the @socketio.on handlers

    # ── Shell context (flask shell convenience) ────────────────────────────────
    @app.shell_context_processor
    def make_shell_context():
        from app.models import User, Test, Question, Option, Attempt, Answer, SuspiciousLog
        return {
            "db": db,
            "User": User,
            "Test": Test,
            "Question": Question,
            "Option": Option,
            "Attempt": Attempt,
            "Answer": Answer,
            "SuspiciousLog": SuspiciousLog,
        }

    return app