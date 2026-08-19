"""
Decrypt WhatsApp audio files (.enc) using mediaKey.
Based on the actual Baileys (@whiskeysockets/baileys) implementation.

Key derivation: HKDF-SHA256 to 112 bytes
- IV: first 16 bytes of expanded key
- Cipher key: bytes 16-48
- MAC key: bytes 48-80

The encrypted file has a 10-byte MAC suffix that must be removed before decryption.
"""
import base64
import hashlib
import logging

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

logger = logging.getLogger(__name__)


def decrypt_whatsapp_audio(encrypted_data: bytes, media_key_bytes: bytes) -> bytes:
    """
    Decrypt WhatsApp audio file using the exact Baileys algorithm.

    Args:
        encrypted_data: Raw encrypted .enc file bytes from WhatsApp CDN
        media_key_bytes: Raw 32-byte mediaKey

    Returns:
        Decrypted audio bytes (OGG Opus)
    """
    logger.info(f"Decrypting: {len(encrypted_data)} bytes, media_key: {len(media_key_bytes)} bytes")

    # Derive 112 bytes using HKDF-SHA256 with info="WhatsApp Audio Keys"
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=112,
        salt=None,
        info=b"WhatsApp Audio Keys",
    )
    expanded = hkdf.derive(media_key_bytes)

    # Extract keys from expanded buffer
    iv = expanded[:16]          # IV from HKDF, NOT from file
    cipher_key = expanded[16:48]  # AES-256-CBC key
    # mac_key = expanded[48:80]  # Not needed for decryption

    # Remove 10-byte MAC suffix from end of encrypted file
    enc_data = encrypted_data[:-10]

    # Verify alignment
    if len(enc_data) % 16 != 0:
        logger.warning(f"Encrypted data not aligned: {len(enc_data)} % 16 = {len(enc_data) % 16}")

    # Decrypt with AES-256-CBC
    cipher = Cipher(algorithms.AES(cipher_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(enc_data) + decryptor.finalize()

    # Remove PKCS7 padding
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16 and all(b == pad_len for b in decrypted[-pad_len:]):
        decrypted = decrypted[:-pad_len]

    logger.info(f"Decrypted: {len(decrypted)} bytes, magic: {decrypted[:4]}")
    return decrypted
