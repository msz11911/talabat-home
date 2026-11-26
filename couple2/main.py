"""Vercel entrypoint for Talabat Home.

The real FastAPI application lives in server/app.py.  We prepend that folder to
sys.path because the server modules use flat imports (``from config import ...``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent / "server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

from app import app  # noqa: E402  (server/app.py)

__all__ = ["app"]
