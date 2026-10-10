from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.security import create_access_token, decode_token, hash_password, verify_password


def test_hash_and_verify_password():
    hashed = hash_password("password123")
    assert hashed != "password123"
    assert verify_password("password123", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    token = create_access_token(42, "u@example.com", "admin")
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    assert payload["email"] == "u@example.com"


def test_expired_token_raises():
    token = create_access_token(1, "u@example.com", "user", expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_token_signed_with_other_secret_raises():
    forged = jwt.encode(
        {"sub": "1", "role": "admin", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "attacker-secret-attacker-secret-32b",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(forged)
