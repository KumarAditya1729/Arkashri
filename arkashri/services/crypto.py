# pyre-ignore-all-errors
import base64
import json
import os
import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from arkashri.config import get_settings

logger = structlog.get_logger("services.crypto")
settings = get_settings()

def get_aesgcm() -> AESGCM:
    key_b64 = settings.erp_config_encryption_key
    if not key_b64:
        logger.warning(
            "erp_encryption_key_missing",
            event="using_insecure_fallback_key",
            message="ERP_CONFIG_ENCRYPTION_KEY is not set. Falling back to dev constant."
        )
        key_b64 = base64.b64encode(b"arkashri_dev_erp_key_32bytes!!!!").decode()
    
    try:
        key = base64.b64decode(key_b64)
    except Exception:
        raise ValueError("ERP_CONFIG_ENCRYPTION_KEY must be a valid base64 encoded string.")
        
    if len(key) != 32:
        raise ValueError("ERP_CONFIG_ENCRYPTION_KEY must be exactly 32 bytes for AES-256-GCM.")
        
    return AESGCM(key)


def get_field_aesgcm() -> AESGCM:
    key_b64 = settings.field_data_encryption_key or settings.erp_config_encryption_key
    if not key_b64:
        logger.warning(
            "field_encryption_key_missing",
            event="using_insecure_fallback_key",
            message="FIELD_DATA_ENCRYPTION_KEY is not set. Falling back to dev constant."
        )
        key_b64 = base64.b64encode(b"arkashri_dev_field_key_32bytes!!").decode()

    try:
        key = base64.b64decode(key_b64)
    except Exception:
        raise ValueError("FIELD_DATA_ENCRYPTION_KEY must be a valid base64 encoded string.")

    if len(key) != 32:
        raise ValueError("FIELD_DATA_ENCRYPTION_KEY must be exactly 32 bytes for AES-256-GCM.")

    return AESGCM(key)

def encrypt_dict(data: dict) -> str:
    """
    Serialize a dictionary to JSON and encrypt it using AES-256-GCM.
    Returns a base64 encoded string combining the 12-byte nonce and ciphertext.
    """
    if not data:
        return ""
    
    aesgcm = get_aesgcm()
    plaintext = json.dumps(data).encode("utf-8")
    
    # Generate standard 96-bit (12-byte) nonce
    nonce = os.urandom(12)
    
    # Encrypt and authenticate
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    
    # Package into a single base64 string
    return base64.b64encode(nonce + ciphertext).decode("utf-8")

def decrypt_dict(encrypted_payload: str) -> dict:
    """
    Decrypt a base64 encoded AES-256-GCM payload back into a dictionary.
    """
    if not encrypted_payload:
        return {}
        
    try:
        raw = base64.b64decode(encrypted_payload)
        nonce, ciphertext = raw[:12], raw[12:]
        
        aesgcm = get_aesgcm()
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode("utf-8"))
        
    except Exception as e:
        logger.error(
            "erp_decryption_failed",
            error=str(e)
        )
        return {}


def encrypt_sensitive_value(value: str | None, *, tenant_id: str, field_name: str) -> dict:
    if value in (None, ""):
        return {"ciphertext": "", "last4": None, "field_name": field_name, "key_version": "field_v1"}

    plaintext = str(value).strip().upper().encode("utf-8")
    aad = f"{tenant_id}:{field_name}".encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = get_field_aesgcm().encrypt(nonce, plaintext, aad)
    normalized = plaintext.decode("utf-8")
    return {
        "ciphertext": base64.b64encode(nonce + ciphertext).decode("utf-8"),
        "last4": normalized[-4:],
        "field_name": field_name,
        "key_version": "field_v1",
    }


def decrypt_sensitive_value(encrypted_payload: dict, *, tenant_id: str, field_name: str) -> str:
    ciphertext = encrypted_payload.get("ciphertext")
    if not ciphertext:
        return ""
    raw = base64.b64decode(ciphertext)
    nonce, encrypted = raw[:12], raw[12:]
    aad = f"{tenant_id}:{field_name}".encode("utf-8")
    plaintext = get_field_aesgcm().decrypt(nonce, encrypted, aad)
    return plaintext.decode("utf-8")
