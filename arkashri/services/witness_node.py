# pyre-ignore-all-errors
import logging
from typing import Dict, List, Optional
import datetime
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
import base64

from arkashri.services.canonical import canonical_json_bytes
from arkashri.services.consistency import consistency_engine

logger = logging.getLogger("witness_node")

class IndependentWitnessNode:
    """
    Simulates a completely external verification node (e.g., hosted by an independent auditor).
    Maintains its own ledger, strictly verifies Arkashri, and gossips with other witnesses.
    """
    
    def __init__(self, witness_id: str, timezone_offset: int = 0):
        self.witness_id = witness_id
        self._private_key = ec.generate_private_key(ec.SECP256R1())
        self._public_key = self._private_key.public_key()
        
        # Isolated Ledger
        self._highest_sth: Optional[Dict] = None
        self._sth_history: List[Dict] = []
        
    def get_identity(self) -> str:
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

    def receive_sth_for_signature(self, sth: Dict, consistency_proof: List[bytes]) -> Optional[str]:
        """
        Adversarial evaluation of Arkashri's STH broadcast.
        1. Timestamps must go strictly forward.
        2. Tree size must continuously grow or stay equal.
        3. RFC 6962 Consistency Proof must mathematically check out.
        """
        new_size = sth.get("tree_size")
        new_ts = sth.get("timestamp")
        
        # 1. Monotonic Checks
        if self._highest_sth:
            old_size = self._highest_sth.get("tree_size")
            old_ts = self._highest_sth.get("timestamp")
            
            if new_size < old_size:
                logger.error(f"[Witness {self.witness_id}] REJECTED: Tree Shrank from {old_size} to {new_size}")
                return None
                
            if datetime.datetime.fromisoformat(new_ts) < datetime.datetime.fromisoformat(old_ts):
                logger.error(f"[Witness {self.witness_id}] REJECTED: Timestamp rewrites history backwards.")
                return None
                
            # 2. Cryptographic Consistency Check
            if not consistency_engine.verify_consistency(
                old_size, new_size, 
                self._highest_sth.get("root").encode(), 
                sth.get("root").encode(), 
                consistency_proof
            ):
                logger.error(f"[Witness {self.witness_id}] REJECTED: Cryptographic Consistency Proof FAILED.")
                return None
        
        # 3. Everything checks out. Sign the STH and locally commit.
        sig_payload = canonical_json_bytes({
            "root": sth.get("root"),
            "tree_size": new_size,
            "timestamp": new_ts
        })
        
        sig = self._private_key.sign(sig_payload, ec.ECDSA(hashes.SHA256()))
        sig_b64 = base64.b64encode(sig).decode('utf-8')
        
        self._sth_history.append(sth)
        self._highest_sth = sth
        
        logger.info(f"[Witness {self.witness_id}] SIGNED Valid STH Tree Size {new_size}.")
        return sig_b64

    def gossip_sync(self, peer: 'IndependentWitnessNode') -> bool:
        """
        Anti-Split-Brain Protocol: Witnesses periodically compare highest STHs.
        If sizes match but roots DO NOT match, emit durable conflict proof bundle.
        """
        if not self._highest_sth or not peer._highest_sth:
            return True
            
        my_size = self._highest_sth.get("tree_size")
        peer_size = peer._highest_sth.get("tree_size")
        
        if my_size == peer_size:
            if self._highest_sth.get("root") != peer._highest_sth.get("root"):
                logger.critical(f"SPLIT BRAIN DETECTED between {self.witness_id} and {peer.witness_id} at size {my_size}")
                
                import json
                conflict_bundle = {
                    "alert": "SPLIT_BRAIN_DETECTED",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "tree_size": my_size,
                    "evidence": {
                        self.witness_id: self._highest_sth,
                        peer.witness_id: peer._highest_sth
                    }
                }

                # C-NEW-6 FIX: /tmp is ephemeral in containers — emit as a structured
                # CRITICAL log so it is captured by Sentry / CloudWatch / log shipping.
                # The full JSON bundle is included in the structured log payload.
                logger.critical(
                    "SPLIT_BRAIN_DETECTED: Durable conflict proof follows. "
                    "Persist this log entry immediately. "
                    "Conflict bundle: %s",
                    json.dumps(conflict_bundle, indent=2)
                )
                return False
                
        return True
