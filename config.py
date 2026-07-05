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
    # Replace postgres:// with postgresql:// for SQLAlchemy compatibility
    _db_url = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    if _db_url and _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Suppress overhead warning

    # ── Flask-WTF CSRF ────────────────────────────────────────────────────────
    WTF_CSRF_ENABLED = False

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
    DEBUG = False
    # Use environment secret key if set, otherwise use fallback
    SECRET_KEY = os.environ.get("SECRET_KEY", "pitestsecretkey2024abcdef")
    SESSION_COOKIE_SECURE = True  # Render enforces HTTPS, so cookie must be Secure
    SESSION_COOKIE_SAMESITE = "Lax"  # Secure default that modern browsers accept
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_NAME = "pitest_session"
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_SSL_STRICT = False

# ── Config selector ───────────────────────────────────────────────────────────
# Set FLASK_ENV=production in Render environment variables.
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}

def get_config():
    env = os.environ.get("FLASK_ENV", "development")
    return config_map.get(env, DevelopmentConfig)