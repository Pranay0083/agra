import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "768"))
PRICE_IN = float(os.environ.get("GEMINI_PRICE_INPUT_PER_M", "0.30"))
PRICE_OUT = float(os.environ.get("GEMINI_PRICE_OUTPUT_PER_M", "2.50"))

_raw_supabase = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
if _raw_supabase.endswith("/rest/v1"):
    _raw_supabase = _raw_supabase[: -len("/rest/v1")]
SUPABASE_URL = _raw_supabase
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", "")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

MAX_VALIDATION_ATTEMPTS = int(os.environ.get("MAX_VALIDATION_ATTEMPTS", "3"))
