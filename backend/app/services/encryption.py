"""Fernet-based symmetric encryption for cookies/credentials at rest."""

from cryptography.fernet import Fernet

from app.config import get_settings


def _cipher() -> Fernet:
    settings = get_settings()
    return Fernet(settings.master_encryption_key.encode())


def encrypt_bytes(plaintext: bytes) -> bytes:
    return _cipher().encrypt(plaintext)


def decrypt_bytes(ciphertext: bytes) -> bytes:
    return _cipher().decrypt(ciphertext)


def encrypt_str(plaintext: str) -> bytes:
    return encrypt_bytes(plaintext.encode("utf-8"))


def decrypt_str(ciphertext: bytes) -> str:
    return decrypt_bytes(ciphertext).decode("utf-8")
