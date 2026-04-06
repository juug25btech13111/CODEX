import os
import secrets
from dotenv import load_dotenv
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    """Base configuration shared by all environments."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # Session Security
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=15)  # Idle timeout
    SESSION_ABSOLUTE_TIMEOUT = 12 * 60 * 60  # 12 hours in seconds
    
    # Database (fallback to SQLite if DATABASE_URL not set)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'sentiment.sqlite')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Connection pooling (for PostgreSQL; SQLite ignores these)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,       # Verify connections before use
        'pool_size': 20,             # Base pool for 1000+ users
        'max_overflow': 40,          # Burst capacity
        'pool_recycle': 1800,        # Recycle stale connections every 30 min
        'pool_timeout': 10,          # Wait max 10s for a connection
    }
    
    # File upload handling
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max
    ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}
    
    # Session Cookie Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_NAME = 'neurosent_session'
    
    # Mail settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@neurosent.com')
    
    # Rate Limiting
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '200 per day;50 per hour')
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_STRATEGY = 'fixed-window'
    
    # Account lockout
    MAX_FAILED_LOGINS = 5
    LOCKOUT_DURATION_MINUTES = 15
    
    # OpenRouter API (Primary Sentiment Engine)
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
    OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'google/gemini-2.0-flash-001')
    OPENROUTER_TIMEOUT = int(os.environ.get('OPENROUTER_TIMEOUT', '10'))
    OPENROUTER_BATCH_SIZE = int(os.environ.get('OPENROUTER_BATCH_SIZE', '15'))


class DevelopmentConfig(Config):
    """Local development settings."""
    DEBUG = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False
    # SQLite doesn't support pool_size; override to empty
    SQLALCHEMY_ENGINE_OPTIONS = {}


class ProductionConfig(Config):
    """Production deployment settings."""
    DEBUG = False
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = True
    # In production, SECRET_KEY must be set via env var
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
