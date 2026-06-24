import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def _get_key() -> bytes:
    key_str = getattr(settings, 'INVESTMENTS_ENCRYPTION_KEY', '') or settings.SECRET_KEY
    # Derive 32-byte key from the key string via SHA-256
    import hashlib
    return hashlib.sha256(key_str.encode()).digest()


def encrypt_bytes(data: bytes) -> bytes:
    """AES-256-GCM encrypt. Returns nonce + ciphertext."""
    key = _get_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt AES-256-GCM data (nonce + ciphertext)."""
    key = _get_key()
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)
