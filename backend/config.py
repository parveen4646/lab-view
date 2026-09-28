import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"

    # Anthropic / Claude
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_EXTRACTION_MODEL = os.getenv("CLAUDE_EXTRACTION_MODEL", "claude-haiku-4-5-20251001")
    CLAUDE_QA_MODEL = os.getenv("CLAUDE_QA_MODEL", "claude-sonnet-5")

    # File upload
    UPLOAD_FOLDER = "uploads"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    ALLOWED_EXTENSIONS = {"pdf"}

    # CORS
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")

    # Database — SQLite by default; set DATABASE_URL to a postgres:// URI in prod
    _base_dir = os.path.dirname(os.path.abspath(__file__))
    _default_db = f"sqlite:///{os.path.join(_base_dir, 'vitals.db')}"
    DATABASE_URL = os.getenv("DATABASE_URL") or _default_db

    # JWT — defaults to SECRET_KEY if not set
    JWT_SECRET = os.getenv("JWT_SECRET") or SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
