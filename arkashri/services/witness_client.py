# pyre-ignore-all-errors
import logging
import asyncio
import httpx
from typing import Dict, List
from arkashri.config import get_settings

logger = logging.getLogger("witness_client")

class WitnessNetworkClient:
    """
    Handles Arkashri's outbound broadcasting to the Independent Witness Gossip Network.
    Enforces the Time-Bounded Quorum Rule.
    """
    def __init__(self):
        self.settings = get_settings()
        self.witness_urls = self.settings.witness_node_urls or []
        
    async def request_quorum_signatures(self, sth: Dict, consistency_proof: List[bytes]) -> List[Dict]:
        """
        Broadcasts the STH to all nodes simultaneously via HTTP.
        Demands at least 3/5 signatures within the configured timeout.
        """
        if not self.witness_urls:
            # Fallback for local development if NO URLs are configured.
            # In production, this should likely raise an error if witness network is mandatory.
            logger.warning("No WITNESS_NODE_URLS configured. Achieving 'quorum' via zero-witness bypass (INSECURE).")
            return []

        logger.info(f"Broadcasting STH (Size: {sth.get('tree_size')}) to {len(self.witness_urls)} Witness Nodes...")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            tasks = []
            for url in self.witness_urls:
                tasks.append(self._send_to_node(client, url, sth, consistency_proof))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        signatures = [res for res in results if isinstance(res, dict) and "signature" in res]
        
        # Hard Quorum Check: 3/5 is the standard for 5 nodes. 
        # For arbitrary clusters, we use (n // 2) + 1.
        required = (len(self.witness_urls) // 2) + 1
        if len(signatures) < required:
            logger.error(f"QUORUM_FAILURE: Needed {required}, got {len(signatures)} signatures.")
            raise PermissionError(
                f"CRITICAL: Failed to achieve Witness Quorum (Needed {required}, Got {len(signatures)}). "
                f"Audit state transition rejected."
            )
            
        logger.info(f"STH Finalized Successfully. Attained {len(signatures)}/{len(self.witness_urls)} Witness Signatures.")
        return signatures

    async def _send_to_node(self, client: httpx.AsyncClient, url: str, sth: Dict, consistency_proof: List[bytes]) -> Dict | None:
        """Internal helper to send request to a single node."""
        endpoint = f"{url.rstrip('/')}/v1/witness/sign"
        try:
            payload = {
                "sth": sth,
                "consistency_proof": [p.hex() if isinstance(p, bytes) else p for p in consistency_proof]
            }
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Witness node {url} failed: {str(e)}")
            return None

witness_network = WitnessNetworkClient()
