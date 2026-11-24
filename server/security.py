"""تشفير رموز PIN وتوقيع جلسات الدخول."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Depends, Header, HTTPException, Request

from config import APP_SECRET, ROLE_NAMES, TOKEN_TTL_SECONDS

_PBKDF2_ROUNDS = 120_000


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_pin(pin: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ROUNDS
    ).hex()
    return f"{salt}${digest}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ROUNDS
        ).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False


def make_token(role: str) -> str:
    payload = {"r": role, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64e(hmac.new(APP_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def decode_token(token: str) -> str | None:
    try:
        body, signature = token.split(".", 1)
        expected = _b64e(
            hmac.new(APP_SECRET.encode(), body.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        role = payload.get("r")
        return role if role in ROLE_NAMES else None
    except Exception:
        return None


def role_from_request(
    request: Request, authorization: str | None = Header(default=None)
) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        role = decode_token(authorization[7:].strip())
        if role:
            return role
    raise HTTPException(status_code=401, detail="انتهت الجلسة، سجّل الدخول من جديد")


def require_husband(role: str = Depends(role_from_request)) -> str:
    if role != "husband":
        raise HTTPException(status_code=403, detail="هذا الإجراء مخصص للزوج فقط")
    return role


def require_wife(role: str = Depends(role_from_request)) -> str:
    if role != "wife":
        raise HTTPException(status_code=403, detail="هذا الإجراء مخصص للزوجة فقط")
    return role
