"""إعداد بيئة الاختبار قبل استيراد التطبيق."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

TMP_DIR = Path(tempfile.mkdtemp(prefix="talabat-tests-"))
os.environ["DATA_DIR"] = str(TMP_DIR)
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DIR / 'test.db'}"
os.environ["APP_SECRET"] = "unit-test-secret-not-for-production"
os.environ["HUSBAND_PIN"] = "1111"
os.environ["WIFE_PIN"] = "2222"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client
