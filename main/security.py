from __future__ import annotations

import re


SENSITIVE_PATTERNS = (
    # Cisco style
    re.compile(r"(username\s+\S+\s+password\s+\d\s+)(\S+)", flags=re.IGNORECASE),
    re.compile(r"(username\s+\S+\s+secret\s+\d\s+)(\S+)", flags=re.IGNORECASE),
    re.compile(r"(enable\s+secret\s+\d\s+)(\S+)", flags=re.IGNORECASE),
    re.compile(r"(snmp-server\s+community\s+)(\S+)", flags=re.IGNORECASE),
    # D-Link / generic
    re.compile(r"(password\s+)(\S+)", flags=re.IGNORECASE),
    re.compile(r"(secret\s+)(\S+)", flags=re.IGNORECASE),
)


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1<REDACTED>", redacted)
    return redacted
