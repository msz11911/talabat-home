"""إعدادات سيرفر Talabat Home."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# المتغيرات الموجودة في البيئة (مثل Render/Fly) تأخذ الأولوية على ملف .env المحلي.
load_dotenv(BASE_DIR / ".env", override=False)

ROOT_DIR = BASE_DIR.parent
WEB_DIR = ROOT_DIR / "web"
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_default_db = DATA_DIR / "talabat.db"
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{_default_db}"


def _load_secret() -> str:
    """مفتاح توقيع الجلسات: من المتغير أو ملف محلي ثابت بين إعادة التشغيل."""
    env_secret = os.getenv("APP_SECRET", "").strip()
    if env_secret:
        return env_secret
    secret_file = DATA_DIR / "app_secret.txt"
    if secret_file.exists():
        saved = secret_file.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    generated = secrets.token_urlsafe(32)
    secret_file.write_text(generated, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    print(f"[talabat] تم توليد APP_SECRET وحفظه في: {secret_file}")
    return generated


APP_SECRET = _load_secret()
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(30 * 24 * 3600)))
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(2 * 1024 * 1024)))
MAX_IMAGE_SIDE = 320
MAX_ROWS_PER_ORDER = 300
PIN_MIN_LENGTH = 4
ROLE_NAMES = {"husband": "الزوج", "wife": "الزوجة"}
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

DEFAULT_GROUPS: list[tuple[str, str]] = [
    ("خضراوات", "🥬"),
    ("فواكه", "🍎"),
    ("بقالة", "🛒"),
    ("منظفات", "🧴"),
    ("أدوية", "💊"),
    ("دواجن", "🍗"),
    ("لحوم", "🥩"),
    ("أسماك", "🐟"),
]
