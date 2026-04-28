from __future__ import annotations

import base64
import hashlib
from typing import Final

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


ENC_PREFIX: Final[str] = "enc::"


def _derive_key(raw: str) -> bytes:
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    plugin_cfg = getattr(settings, "PLUGINS_CONFIG", {}).get("main", {})
    secret = plugin_cfg.get("secret_key")
    if not secret:
        raise RuntimeError("Set PLUGINS_CONFIG['main']['secret_key'] for encryption")
    return Fernet(_derive_key(secret))


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(ENC_PREFIX))


def encrypt_value(value: str | None) -> str:
    if not value:
        return ""
    if is_encrypted(value):
        return value
    token = _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{ENC_PREFIX}{token}"


def decrypt_value(value: str | None) -> str:
    if not value:
        return ""
    if not is_encrypted(value):
        return value
    token = value[len(ENC_PREFIX) :]
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Credential decrypt failed: invalid token or secret key") from exc
