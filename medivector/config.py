import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "medivector-chat-app" / "dist"
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536  # text-embedding-3-small default
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
RISK_MODEL = "gpt-4o-mini-2024-07-18"
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
TOP_K = int(os.getenv("TOP_K", "5"))
REFERENCE_CANDIDATE_LIMIT = int(os.getenv("REFERENCE_CANDIDATE_LIMIT", "20"))
MAX_REFERENCE_DISTANCE = float(os.getenv("MAX_REFERENCE_DISTANCE", "0.65"))
REFERENCE_DISTANCE_MARGIN = float(os.getenv("REFERENCE_DISTANCE_MARGIN", "0.12"))
MIN_REFERENCE_COUNT = int(os.getenv("MIN_REFERENCE_COUNT", "2"))
MAX_EVIDENCE_DISTANCE = float(os.getenv("MAX_EVIDENCE_DISTANCE", str(MAX_REFERENCE_DISTANCE)))
MEMORY_MESSAGES = int(os.getenv("MEMORY_MESSAGES", "10"))
MAX_EMBEDDING_CHARS = int(os.getenv("MAX_EMBEDDING_CHARS", "6000"))
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "health-education-files")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "medivector")
PG_PASSWORD = os.getenv("PG_PASSWORD", "medivector")
PG_DATABASE = os.getenv("PG_DATABASE", "medivector")
QUERY_EXPANSION_MODEL = "gpt-4o-mini-2024-07-18"
