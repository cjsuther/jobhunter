"""Encryption roundtrip."""

from app.services.encryption import decrypt_str, encrypt_str


def test_roundtrip():
    secret = "linkedin_session_cookie=abc123; expires=…"
    ciphertext = encrypt_str(secret)
    assert ciphertext != secret.encode()
    assert decrypt_str(ciphertext) == secret
