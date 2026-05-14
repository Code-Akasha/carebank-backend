"""
Encryption/decryption utilities for sensitive fields in models.

Uses Fernet (symmetric encryption from cryptography library) for field-level encryption.
The encryption key is derived from a master key stored in configuration.
"""

import logging
from typing import Optional
from cryptography.fernet import Fernet
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EncryptionManager:
    """Manages field-level encryption for sensitive data like API tokens."""

    def __init__(self):
        settings = get_settings()
        # Derive encryption key from a master secret (typically from env or settings)
        # For now, use jwt_secret as the base (in production, use a dedicated encryption key)
        master_key = settings.jwt_secret.encode("utf-8")
        # Fernet requires a 32-byte base64-encoded key; derive it from master_key
        import base64
        import hashlib

        derived_key = base64.urlsafe_b64encode(hashlib.sha256(master_key).digest())
        self.cipher_suite = Fernet(derived_key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string and return base64-encoded ciphertext."""
        if not plaintext:
            return plaintext
        ciphertext = self.cipher_suite.encrypt(plaintext.encode("utf-8"))
        return ciphertext.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext string and return plaintext."""
        if not ciphertext:
            return ciphertext
        try:
            plaintext = self.cipher_suite.decrypt(ciphertext.encode("utf-8"))
            return plaintext.decode("utf-8")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Failed to decrypt value: {str(e)}")

    @staticmethod
    def mask_sensitive_value(value: str, show_chars: int = 4) -> str:
        """
        Mask a sensitive value for display (e.g., "abc...xyz").
        Shows first and last N characters; hides the middle.
        """
        if not value or len(value) <= show_chars * 2:
            return "*" * len(value)
        return f"{value[:show_chars]}...{value[-show_chars:]}"


# Global instance
_encryption_manager: Optional[EncryptionManager] = None


def get_encryption_manager() -> EncryptionManager:
    """Get the singleton EncryptionManager instance."""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager
