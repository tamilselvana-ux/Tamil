import base64
import hashlib
from django.conf import settings
from cryptography.fernet import Fernet


def get_fernet_cipher():
    """
    Returns a Fernet cipher instance using GOOGLE_OAUTH_ENCRYPTION_KEY from settings,
    or falls back to a deterministic 32-byte key derived from SECRET_KEY.
    """
    custom_key = getattr(settings, 'GOOGLE_OAUTH_ENCRYPTION_KEY', None)
    if custom_key and isinstance(custom_key, str) and custom_key.strip():
        key_bytes = custom_key.strip().encode()
        try:
            return Fernet(key_bytes)
        except Exception:
            pass

    # Derive deterministic 32-byte urlsafe base64 key from Django SECRET_KEY
    derived_hash = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    urlsafe_key = base64.urlsafe_b64encode(derived_hash)
    return Fernet(urlsafe_key)


def encrypt_secret(plain_text: str) -> str:
    """Encrypts a plaintext string and returns a base64 encoded ciphertext string."""
    if not plain_text:
        return ''
    cipher = get_fernet_cipher()
    encrypted_bytes = cipher.encrypt(plain_text.encode('utf-8'))
    return encrypted_bytes.decode('utf-8')


def decrypt_secret(cipher_text: str) -> str:
    """Decrypts a base64 ciphertext string back to plaintext."""
    if not cipher_text:
        return ''
    cipher = get_fernet_cipher()
    decrypted_bytes = cipher.decrypt(cipher_text.encode('utf-8'))
    return decrypted_bytes.decode('utf-8')
