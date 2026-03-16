import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', f'sqlite:///{os.path.join(basedir, "instance", "skyght.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # Session settings
    SESSION_COOKIE_SECURE = True  # HTTPS via Apache proxy
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_PATH = '/rest'

    # Application root for URL generation behind proxy
    APPLICATION_ROOT = '/rest'

    # File uploads
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB max upload

    # Mail settings (Flask-Mail)
    MAIL_SERVER = 'mail.jetoko.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'noreply@aroaero.com'
    MAIL_PASSWORD = '{,81,WntIaB'
    MAIL_DEFAULT_SENDER = 'noreply@aroaero.com'

    # SMTP settings (alternative naming)
    SMTP_SERVER = 'mail.jetoko.com'
    SMTP_PORT = 587
    SMTP_USE_TLS = True
    SMTP_USERNAME = 'noreply@aroaero.com'
    SMTP_PASSWORD = '{,81,WntIaB'
    FROM_EMAIL = 'noreply@aroaero.com'
