import os
from dotenv import load_dotenv

# Load environment variables from .env file (ignored in production where env vars are set directly)
load_dotenv()


class Config:
    """
    Base configuration shared across all environments.
    All sensitive values are read from environment variables — never hardcoded.
    """

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")

    # ── Database ──────────────────────────────────────────────────────────────
    # Supabase provides a standard PostgreSQL connection string.
    # Format: postgresql://user:password@host:port/dbname
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Suppress overhead warning

    # ── Flask-WTF CSRF ────────────────────────────────────────────────────────
    WTF_CSRF_ENABLED = True

    # ── Flask-SocketIO ────────────────────────────────────────────────────────
    # gevent is used as the async mode — fully supports Python 3.13, unlike eventlet
    SOCKETIO_ASYNC_MODE = "gevent"

    # ── Session ───────────────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True   # JS cannot read session cookie
    SESSION_COOKIE_SAMESITE = "Lax" # Protect against CSRF via cross-origin

    # ── File Upload (CSV import) ───────────────────────────────────────────────
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB max upload size


class DevelopmentConfig(Config):
    """
    Development environment.
    Debug mode on, uses local SQLite fallback if DATABASE_URL is not set.
    """
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # HTTP is fine locally


class ProductionConfig(Config):
    """
    Production environment (Render + Supabase).
    Debug off, secure cookies enforced.
    """
    DEBUG = False
    SESSION_COOKIE_SECURE = True   # HTTPS only — enforced on Render


# ── Config selector ───────────────────────────────────────────────────────────
# Set FLASK_ENV=production in Render environment variables.
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}

def get_config():
    env = os.environ.get("FLASK_ENV", "development")
    return config_map.get(env, DevelopmentConfig)