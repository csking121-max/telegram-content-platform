"""
Tests for HMAC validation and webhook signature verification.
"""
import hashlib
import hmac

import pytest

from backend.security.hmac_validation import validate_hmac


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_hmac():
    secret = "my-secret"
    body = b'{"action":"test"}'
    sig = _sign(secret, body)
    assert validate_hmac(secret, body, sig) is True


def test_invalid_hmac():
    secret = "my-secret"
    body = b'{"action":"test"}'
    assert validate_hmac(secret, body, "invalid-signature") is False


def test_wrong_secret():
    body = b'{"data":"hello"}'
    sig = _sign("correct-secret", body)
    assert validate_hmac("wrong-secret", body, sig) is False


def test_tampered_body():
    secret = "my-secret"
    original = b'{"amount":100}'
    sig = _sign(secret, original)
    tampered = b'{"amount":9999}'
    assert validate_hmac(secret, tampered, sig) is False


def test_empty_body():
    secret = "s"
    body = b""
    sig = _sign(secret, body)
    assert validate_hmac(secret, body, sig) is True


def test_empty_signature():
    assert validate_hmac("secret", b"body", "") is False