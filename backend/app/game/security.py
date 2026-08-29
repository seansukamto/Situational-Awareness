from __future__ import annotations

import hashlib
import hmac
import secrets


def hash_staff_pin(pin: str, *, salt: bytes | None = None) -> tuple[bytes, bytes]:
    resolved_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        pin.encode("utf-8"),
        salt=resolved_salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return resolved_salt, digest


def verify_staff_pin(pin: str, salt: bytes, expected_digest: bytes) -> bool:
    _, actual_digest = hash_staff_pin(pin, salt=salt)
    return hmac.compare_digest(actual_digest, expected_digest)
