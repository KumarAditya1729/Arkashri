# pyre-ignore-all-errors
import base64
import logging
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization

from arkashri.services.canonical import canonical_json_bytes

logger = logging.getLogger("services.trust_anchor")

class ArkashriRootCA:
    """
    Simulates the Arkashri offline Master Root Key that signs tenant public keys.
    In production, this is an Air-Gapped HSM.
    """
    def __init__(self):
        # Generate a root key in memory for simulation
        self._root_key = ec.generate_private_key(ec.SECP256R1())
        self._public_key = self._root_key.public_key()

    def get_public_key_pem(self) -> str:
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

    def sign_tenant_key(self, tenant_id: str, tenant_pub_pem: str) -> str:
        """
        Signs the tenant public key establishing the chain of trust.
        """
        payload = {
            "tenant_id": tenant_id,
            "public_key": tenant_pub_pem,
            "issuer": "Arkashri_Root_CA_v1"
        }
        
        sig = self._root_key.sign(
            canonical_json_bytes(payload),
            ec.ECDSA(hashes.SHA256())
        )
        return base64.b64encode(sig).decode('utf-8')

trust_anchor = ArkashriRootCA()
