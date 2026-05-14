from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.cache import cache
from django.http import HttpRequest

from ..logging import logger
from ..models import CredentialRevealAudit, DeviceCredential


def _plugin_cfg() -> dict[str, Any]:
    return getattr(settings, "PLUGINS_CONFIG", {}).get("main", {})


def validate_security_settings() -> None:
    secret_key = str(_plugin_cfg().get("secret_key") or "").strip()
    if not secret_key:
        raise ImproperlyConfigured(
            "PLUGINS_CONFIG['main']['secret_key'] must be set for credential encryption."
        )
    if len(secret_key) < 16:
        logger.warning("config-weaver secret_key is short (<16 chars); use a long random value.")
    if secret_key.lower() in {"changeme", "replace-me", "replace-with-a-long-random-plugin-secret"}:
        logger.warning("config-weaver secret_key looks like a placeholder. Replace it in production.")


def _int_cfg(key: str, default: int) -> int:
    raw = _plugin_cfg().get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _extract_client_ip(request: HttpRequest) -> str:
    xff = str(request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR") or "").strip()


@dataclass(frozen=True)
class RevealAttemptState:
    blocked: bool
    remaining_attempts: int
    wait_seconds: int


class CredentialRevealService:
    @classmethod
    def max_attempts(cls) -> int:
        return _int_cfg("credential_reveal_max_attempts", 5)

    @classmethod
    def window_seconds(cls) -> int:
        return _int_cfg("credential_reveal_window_seconds", 300)

    @classmethod
    def _failure_key(cls, user_id: int | None, credential_id: int) -> str:
        return f"cw:cred-reveal:fail:{user_id or 'anon'}:{credential_id}"

    @classmethod
    def attempt_state(cls, user_id: int | None, credential_id: int) -> RevealAttemptState:
        key = cls._failure_key(user_id, credential_id)
        failed = int(cache.get(key) or 0)
        max_attempts = cls.max_attempts()
        blocked = failed >= max_attempts
        remaining = max(max_attempts - failed, 0)
        return RevealAttemptState(
            blocked=blocked,
            remaining_attempts=remaining,
            wait_seconds=cls.window_seconds() if blocked else 0,
        )

    @classmethod
    def record_failure(cls, user_id: int | None, credential_id: int) -> None:
        key = cls._failure_key(user_id, credential_id)
        timeout = cls.window_seconds()
        if cache.add(key, 1, timeout=timeout):
            return
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=timeout)

    @classmethod
    def reset_failures(cls, user_id: int | None, credential_id: int) -> None:
        cache.delete(cls._failure_key(user_id, credential_id))

    @classmethod
    def audit(
        cls,
        *,
        request: HttpRequest,
        credential: DeviceCredential,
        status: str,
        reason: str = "",
    ) -> None:
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        user_agent = str(request.META.get("HTTP_USER_AGENT") or "").strip()[:255]
        CredentialRevealAudit.objects.create(
            credential=credential,
            requested_by=user,
            status=status,
            reason=reason[:128],
            source_ip=_extract_client_ip(request) or None,
            user_agent=user_agent,
        )
