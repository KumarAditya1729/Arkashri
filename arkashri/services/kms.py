# pyre-ignore-all-errors
from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidSignature

from arkashri.config import get_settings

logger = logging.getLogger("services.kms")

class BaseKeyProvider(ABC):
    """Abstract base class for Cryptographic Key Providers"""
    
    @abstractmethod
    def get_key(self, key_id: str) -> bytes:
        """Retrieve the raw key bytes for the given identifier"""
        pass

class EnvKeyProvider(BaseKeyProvider):
    """Legacy/Default provider using environment variables"""
    
    def __init__(self):
        self.settings = get_settings()
        
    def get_key(self, key_id: str) -> bytes:
        # Map key_id to settings attributes
        if key_id == "seal_v1":
            val = self.settings.seal_key_v1
        else:
            raise ValueError(f"Unknown key identifier: {key_id}")
            
        if not val:
            raise RuntimeError(f"Key {key_id} is not configured in the environment.")
            
        try:
            return base64.b64decode(val)
        except Exception as e:
            raise RuntimeError(f"Key {key_id} is not valid base64.") from e

class AWSKMSProvider(BaseKeyProvider):
    """
    AWS KMS Integration Provider.
    In production, this would use boto3.kms.decrypt().
    """
    
    def __init__(self, region: str):
        self.region = region
        # self.client = boto3.client("kms", region_name=region)
        
    def get_key(self, key_id: str) -> bytes:
        # In a real implementation:
        # response = self.client.decrypt(KeyId=key_id, CiphertextBlob=...)
        # return response['Plaintext']
        logger.warning(f"AWS KMS Key Retrieval triggered for {key_id} (Skeleton Mode)")
        raise NotImplementedError("AWS KMS provider requires production boto3 configuration.")

class AsymmetricKeyProvider(BaseKeyProvider):
    """
    Manages per-tenant ECDSA keys (secp256k1 or P-256) for trustless asymmetric verification.
    """
    def __init__(self):
        # tenant_id -> private_key
        self._keys: Dict[str, ec.EllipticCurvePrivateKey] = {}

    def get_key(self, key_id: str) -> bytes:
        raise NotImplementedError("Use get_tenant_keypair")

    def get_tenant_keypair(self, tenant_id: str) -> Tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
        if tenant_id not in self._keys:
            # ⚠️  PRODUCTION WARNING: This generates an ephemeral in-memory ECDSA keypair.
            # Keys are LOST on every server restart and DIFFER across workers.
            # This breaks:
            #   - verify_audit_seal (InvalidSignature after restart)
            #   - multi-worker deployments (Kubernetes, Railway replicas)
            # REQUIRED for production: back this with AWS KMS asymmetric keys or HashiCorp Vault.
            # Until then, single-worker only.
            import os
            if os.getenv("APP_ENV", "dev").lower() in {"production", "prod"}:
                raise RuntimeError(
                    "FATAL: Ephemeral in-memory ECDSA keys cannot be used in production. "
                    "Configure AWS KMS asymmetric keys or HashiCorp Vault and set KMS_PROVIDER=aws. "
                    "Keys are lost on restart and diverge across workers, making seal verification impossible."
                )
            logger.warning(
                "[C-3 AUDIT RISK] Generating ephemeral ECDSA keypair for tenant '%s'. "
                "This key will be lost on restart. Acceptable for local dev only.",
                tenant_id,
            )
            priv_key = ec.generate_private_key(ec.SECP256R1())
            self._keys[tenant_id] = priv_key
            pub_key = priv_key.public_key()
            
            # Root CA Sign and Transparency Log
            from arkashri.services.trust_anchor import trust_anchor
            pub_pem = pub_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')
            
            root_signature = trust_anchor.sign_tenant_key(tenant_id, pub_pem)
            logger.info("[Transparency Log] Generated KeyLifecycleEvent (CREATED) for %s", tenant_id)
        
        priv_key = self._keys[tenant_id]
        return priv_key, priv_key.public_key()

class KeyVaultService:
    """
    Primary orchestrator for Enterprise Key Management.
    Supports provider rotation, DEK generation for crypto-shredding, and asymmetric keys.
    """
    
    _instance: Optional[KeyVaultService] = None
    
    def __init__(self):
        self.settings = get_settings()
        self.provider = self._initialize_provider()
        self.asymmetric_provider = AsymmetricKeyProvider()
        self._cache: Dict[str, bytes] = {}

    def _initialize_provider(self) -> BaseKeyProvider:
        # Determine provider from config
        # Defaulting to EnvKeyProvider for current simulation
        provider_type = getattr(self.settings, "kms_provider", "env").lower()
        
        if provider_type == "aws":
            return AWSKMSProvider(region=self.settings.aws_region)
        return EnvKeyProvider()

    def get_active_key(self, key_id: str = "seal_v1") -> bytes:
        """
        Retrieves the key, with caching and audit logging.
        This forms the basis of the ISO 27001 'Key Access Trail'.
        """
        if key_id not in self._cache:
            logger.info(f"Key Access: Initializing {key_id} from {type(self.provider).__name__}")
            self._cache[key_id] = self.provider.get_key(key_id)
        
        return self._cache[key_id]

    def get_tenant_signing_key(self, tenant_id: str) -> ec.EllipticCurvePrivateKey:
        """Retrieves the ECDSA private key for signing audit logs for a tenant."""
        priv, _ = self.asymmetric_provider.get_tenant_keypair(tenant_id)
        return priv

    def get_tenant_public_key_pem(self, tenant_id: str) -> str:
        """Retrieves the public key in PEM format for external auditor verification."""
        _, pub = self.asymmetric_provider.get_tenant_keypair(tenant_id)
        pem = pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode('utf-8')

    def generate_dek(self) -> bytes:
        """Creates a new Data Encryption Key (DEK) for crypto-shredding."""
        import os
        return os.urandom(32)

    def decrypt_dek(self, encrypted_dek: bytes, is_shredded: bool = False) -> bytes:
        """
        Decrypts a DEK using the Active Master Key and AES-256-GCM.
        Expected format: 12-byte IV + ciphertext + 16-byte tag.
        """
        if is_shredded:
            logger.error("DEK decryption blocked: Record is formally SHREDDED.")
            raise PermissionError("DATA_SHREDDED")
            
        if len(encrypted_dek) < 28: # 12 IV + 16 Tag
            logger.error("Malformed encrypted DEK provided (too short)")
            raise ValueError("Malformed encrypted DEK")

        master_key = self.get_active_key()
        aesgcm = AESGCM(master_key)
        
        iv = encrypted_dek[:12]
        ciphertext = encrypted_dek[12:]
        
        try:
            return aesgcm.decrypt(iv, ciphertext, None)
        except Exception as e:
            logger.error("DEK decryption failed: possible key mismatch or tampering", error=str(e))
            raise RuntimeError("DEK decryption failed") from e

    def encrypt_dek(self, raw_dek: bytes) -> bytes:
        """
        Encrypts a DEK using the Active Master Key and AES-256-GCM.
        Returns: 12-byte IV + ciphertext + 16-byte tag.
        """
        import os
        master_key = self.get_active_key()
        aesgcm = AESGCM(master_key)
        
        iv = os.urandom(12)
        ciphertext = aesgcm.encrypt(iv, raw_dek, None)
        
        return iv + ciphertext

    @classmethod
    def get_instance(cls) -> KeyVaultService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

# Global access point
kms_service = KeyVaultService.get_instance()
