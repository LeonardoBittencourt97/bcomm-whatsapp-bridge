"""
Decrypt WhatsApp audio files (.enc) using mediaKey.
WhatsApp encrypts media with AES-256-CBC. This module handles decryption.
"""
import hashlib
import hmac
import logging
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)

# WhatsApp media types
MEDIA_TYPE_AUDIO = b"WhatsApp Audio Keys\x01"


def decrypt_whatsapp_audio(encrypted_data: bytes, media_key: bytes) -> bytes:
    """
    Decrypt WhatsApp audio file (.enc format).

    WhatsApp audio encryption:
    1. Derive AES key from mediaKey using PBKDF2-HMAC-SHA1
    2. File starts with 10-byte IV
    3. Rest is AES-256-CBC encrypted data

    Args:
        encrypted_data: Raw encrypted .enc file bytes
        media_key: The mediaKey from the webhook (raw bytes)

    Returns:
        Decrypted audio bytes (OGG Opus)
    """
    if len(encrypted_data) < 10:
        raise ValueError("Encrypted data too short")

    # Derive AES key using PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=32,
        salt=MEDIA_TYPE_AUDIO,
        iterations=16,
    )
    aes_key = kdf.derive(media_key)

    # Extract IV (first 10 bytes) + zero-pad to 16 bytes
    iv = encrypted_data[:10] + b"\x00" * 6

    # Decrypt
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_data[10:]) + decryptor.finalize()

    # Remove PKCS7 padding
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16:
        decrypted = decrypted[:-pad_len]

    return decrypted


def media_key_from_dict(mk_dict: dict) -> bytes:
    """
    Convert mediaKey dict (from webhook) to raw bytes.
    WhatsApp sends mediaKey as dict with numeric keys representing byte values.

    Args:
        mk_dict: Dict like {0: 1, 1: 24, 2: 39, ...}

    Returns:
        Raw bytes
    """
    return bytes(mk_dict.values())
