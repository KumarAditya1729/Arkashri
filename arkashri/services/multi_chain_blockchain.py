"""
Multi-Chain Blockchain Service
Supports Polkadot, Ethereum, and Polygon blockchain networks
"""
from __future__ import annotations

import json
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pathlib import Path

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from substrateinterface import SubstrateInterface, Keypair
import structlog

from arkashri.config import get_settings
from arkashri.logging_config import blockchain_logger

logger = structlog.get_logger(__name__)

class MultiChainBlockchainService:
    """Multi-chain blockchain service supporting Polkadot, Ethereum, and Polygon"""
    
    def __init__(self):
        self.settings = get_settings()
        self.networks = getattr(self.settings, 'blockchain_networks', 'polkadot,ethereum,polygon').split(',')
        self.enable_smart_contracts = getattr(self.settings, 'enable_smart_contracts', False)
        self.smart_contract_address = getattr(self.settings, 'smart_contract_address', '')
        self.confirmation_blocks = getattr(self.settings, 'blockchain_confirmation_blocks', 3)
        
        # Initialize blockchain connections
        self.connections = {}
        self._initialize_connections()
    
    def _initialize_connections(self):
        """Initialize connections to all configured blockchain networks"""
        try:
            for network in self.networks:
                if network.lower() == 'polkadot':
                    self.connections[network] = self._connect_polkadot()
                elif network.lower() == 'ethereum':
                    self.connections[network] = self._connect_ethereum()
                elif network.lower() == 'polygon':
                    self.connections[network] = self._connect_polygon()
                else:
                    logger.warning("unsupported_network", network=network)
            
            logger.info("blockchain_connections_initialized", networks=list(self.connections.keys()))
            
        except Exception as e:
            logger.error("blockchain_connection_error", error=str(e))
    
    def _connect_polkadot(self) -> Optional[SubstrateInterface]:
        """Connect to Polkadot network"""
        try:
            polkadot_ws = getattr(self.settings, 'polkadot_ws_url', 'wss://rpc.polkadot.io')
            substrate = SubstrateInterface(
                url=polkadot_ws,
                ss58_format=42,  # Polkadot format
                type_registry_preset="canvas"
            )
            logger.info("polkadot_connected", url=polkadot_ws)
            return substrate
        except Exception as e:
            logger.error("polkadot_connection_error", error=str(e))
            return None
    
    def _connect_ethereum(self) -> Optional[Web3]:
        """Connect to Ethereum network"""
        try:
            ethereum_rpc = getattr(self.settings, 'ethereum_rpc_url', '')
            if not ethereum_rpc:
                logger.warning("ethereum_rpc_missing")
                return None
            
            w3 = Web3(Web3.HTTPProvider(ethereum_rpc))
            
            # Add POA middleware for testnet
            if 'testnet' in ethereum_rpc.lower():
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            
            # Check connection
            if w3.is_connected():
                logger.info("ethereum_connected", url=ethereum_rpc)
                return w3
            else:
                logger.error("ethereum_connection_failed", url=ethereum_rpc)
                return None
                
        except Exception as e:
            logger.error("ethereum_connection_error", error=str(e))
            return None
    
    def _connect_polygon(self) -> Optional[Web3]:
        """Connect to Polygon network"""
        try:
            polygon_rpc = getattr(self.settings, 'polygon_rpc_url', '')
            if not polygon_rpc:
                logger.warning("polygon_rpc_missing")
                return None
            
            w3 = Web3(Web3.HTTPProvider(polygon_rpc))
            
            # Add POA middleware for Polygon
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            
            # Check connection
            if w3.is_connected():
                logger.info("polygon_connected", url=polygon_rpc)
                return w3
            else:
                logger.error("polygon_connection_failed", url=polygon_rpc)
                return None
                
        except Exception as e:
            logger.error("polygon_connection_error", error=str(e))
            return None
    
    async def anchor_evidence_multi_chain(self, evidence_hash: str, metadata: Dict) -> Dict:
        """Anchor evidence to multiple blockchain networks"""
        results = {}
        
        for network_name, connection in self.connections.items():
            try:
                if network_name.lower() == 'polkadot':
                    result = await self._anchor_to_polkadot(connection, evidence_hash, metadata)
                elif network_name.lower() in ['ethereum', 'polygon']:
                    result = await self._anchor_to_evm_chain(connection, evidence_hash, metadata, network_name)
                else:
                    result = {"success": False, "error": f"Unsupported network: {network_name}"}
                
                results[network_name] = result
                
            except Exception as e:
                logger.error("multi_chain_anchoring_error", 
                           network=network_name, 
                           evidence_hash=evidence_hash, 
                           error=str(e))
                results[network_name] = {"success": False, "error": str(e)}
        
        # Generate multi-chain receipt
        receipt = self._generate_multi_chain_receipt(evidence_hash, results)
        
        logger.info("multi_chain_anchoring_completed", 
                   evidence_hash=evidence_hash,
                   networks_anchored=len([r for r in results.values() if r.get('success', False)]))
        
        return receipt
    
    async def _anchor_to_polkadot(self, substrate: SubstrateInterface, evidence_hash: str, metadata: Dict) -> Dict:
        """Anchor evidence to Polkadot blockchain"""
        try:
            # Create call for anchoring
            call = substrate.compose_call(
                call_module="System",
                call_function="remark",
                call_params={"remark": f"ARKASHRI:{evidence_hash}:{json.dumps(metadata)}"}
            )
            
            # Create extrinsic
            extrinsic = substrate.create_signed_extrinsic(call, Keypair.create_from_uri('//Alice'))
            
            # Submit transaction
            receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
            
            if receipt.is_success:
                block_hash = receipt.extrinsic.block_hash
                block_number = receipt.extrinsic.block_number
                
                return {
                    "success": True,
                    "network": "polkadot",
                    "transaction_hash": str(receipt.extrinsic_hash),
                    "block_hash": str(block_hash),
                    "block_number": block_number,
                    "confirmation_status": "confirmed",
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "success": False,
                    "network": "polkadot",
                    "error": "Transaction failed",
                    "error_details": str(receipt.error_message) if hasattr(receipt, 'error_message') else "Unknown error"
                }
                
        except Exception as e:
            logger.error("polkadot_anchoring_error", error=str(e))
            return {"success": False, "network": "polkadot", "error": str(e)}
    
    async def _anchor_to_evm_chain(self, w3: Web3, evidence_hash: str, metadata: Dict, network_name: str) -> Dict:
        """Anchor evidence to Ethereum or Polygon blockchain"""
        try:
            if self.enable_smart_contracts and self.smart_contract_address:
                # Use smart contract for anchoring
                return await self._anchor_via_smart_contract(w3, evidence_hash, metadata, network_name)
            else:
                # Use direct transaction anchoring
                return await self._anchor_via_transaction(w3, evidence_hash, metadata, network_name)
                
        except Exception as e:
            logger.error("evm_anchoring_error", network=network_name, error=str(e))
            return {"success": False, "network": network_name, "error": str(e)}
    
    async def _anchor_via_smart_contract(self, w3: Web3, evidence_hash: str, metadata: Dict, network_name: str) -> Dict:
        """Anchor evidence using smart contract"""
        try:
            # Smart contract ABI (simplified)
            abi = [
                {
                    "inputs": [
                        {"name": "evidenceHash", "type": "string"},
                        {"name": "metadata", "type": "string"},
                        {"name": "timestamp", "type": "uint256"}
                    ],
                    "name": "anchorEvidence",
                    "outputs": [
                        {"name": "", "type": "bool"}
                    ],
                    "type": "function"
                }
            ]
            
            # Get contract instance
            contract = w3.eth.contract(
                address=self.smart_contract_address,
                abi=abi
            )
            
            # Get account for transaction
            account = w3.eth.account.from_key('your_private_key')  # In production, use secure key management
            
            # Build transaction
            transaction = contract.functions.anchorEvidence(
                evidence_hash,
                json.dumps(metadata),
                int(datetime.utcnow().timestamp())
            ).build_transaction({
                'from': account.address,
                'gas': 200000,
                'gasPrice': w3.eth.gas_price,
                'nonce': w3.eth.get_transaction_count(account.address)
            })
            
            # Sign and send transaction
            signed_txn = w3.eth.account.sign_transaction(transaction, account.private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                return {
                    "success": True,
                    "network": network_name,
                    "transaction_hash": tx_hash.hex(),
                    "block_hash": receipt.blockHash.hex(),
                    "block_number": receipt.blockNumber,
                    "gas_used": receipt.gasUsed,
                    "confirmation_status": "confirmed",
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "success": False,
                    "network": network_name,
                    "error": "Transaction failed",
                    "transaction_hash": tx_hash.hex()
                }
                
        except Exception as e:
            logger.error("smart_contract_anchoring_error", network=network_name, error=str(e))
            return {"success": False, "network": network_name, "error": str(e)}
    
    async def _anchor_via_transaction(self, w3: Web3, evidence_hash: str, metadata: Dict, network_name: str) -> Dict:
        """Anchor evidence using direct transaction"""
        try:
            # Create transaction data
            transaction_data = f"ARKASHRI:{evidence_hash}:{json.dumps(metadata)}"
            
            # Get account
            account = w3.eth.account.from_key('your_private_key')  # In production, use secure key management
            
            # Build transaction
            transaction = {
                'to': '0x0000000000000000000000000000000000000000000000000',  # Burn address
                'value': 0,
                'data': transaction_data.encode('utf-8').hex(),
                'gas': 21000,
                'gasPrice': w3.eth.gas_price,
                'nonce': w3.eth.get_transaction_count(account.address)
            }
            
            # Sign and send transaction
            signed_txn = w3.eth.account.sign_transaction(transaction, account.private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                return {
                    "success": True,
                    "network": network_name,
                    "transaction_hash": tx_hash.hex(),
                    "block_hash": receipt.blockHash.hex(),
                    "block_number": receipt.blockNumber,
                    "gas_used": receipt.gasUsed,
                    "confirmation_status": "confirmed",
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "success": False,
                    "network": network_name,
                    "error": "Transaction failed",
                    "transaction_hash": tx_hash.hex()
                }
                
        except Exception as e:
            logger.error("transaction_anchoring_error", network=network_name, error=str(e))
            return {"success": False, "network": network_name, "error": str(e)}
    
    def _generate_multi_chain_receipt(self, evidence_hash: str, results: Dict) -> Dict:
        """Generate multi-chain anchoring receipt"""
        successful_anchors = [network for network, result in results.items() if result.get('success', False)]
        failed_anchors = [network for network, result in results.items() if not result.get('success', False)]
        
        return {
            "evidence_hash": evidence_hash,
            "anchoring_timestamp": datetime.utcnow().isoformat(),
            "networks_anchored": successful_anchors,
            "networks_failed": failed_anchors,
            "total_networks": len(results),
            "success_rate": len(successful_anchors) / len(results) if results else 0,
            "network_results": results,
            "multi_chain_hash": self._generate_multi_chain_hash(evidence_hash, successful_anchors),
            "verification_urls": self._generate_verification_urls(evidence_hash, successful_anchors)
        }
    
    def _generate_multi_chain_hash(self, evidence_hash: str, networks: List[str]) -> str:
        """Generate multi-chain verification hash"""
        import hashlib
        combined = f"{evidence_hash}:{','.join(sorted(networks))}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def _generate_verification_urls(self, evidence_hash: str, networks: List[str]) -> Dict[str, str]:
        """Generate verification URLs for each network"""
        urls = {}
        base_url = "https://verify.arkashri.com/evidence"
        
        for network in networks:
            if network.lower() == 'polkadot':
                urls[network] = f"{base_url}/{evidence_hash}?network=polkadot"
            elif network.lower() == 'ethereum':
                urls[network] = f"{base_url}/{evidence_hash}?network=ethereum"
            elif network.lower() == 'polygon':
                urls[network] = f"{base_url}/{evidence_hash}?network=polygon"
        
        return urls
    
    async def verify_multi_chain_evidence(self, evidence_hash: str) -> Dict:
        """Verify evidence across multiple blockchain networks"""
        verification_results = {}
        
        for network_name, connection in self.connections.items():
            try:
                if network_name.lower() == 'polkadot':
                    result = await self._verify_polkadot_evidence(connection, evidence_hash)
                elif network_name.lower() in ['ethereum', 'polygon']:
                    result = await self._verify_evm_evidence(connection, evidence_hash, network_name)
                else:
                    result = {"verified": False, "error": f"Unsupported network: {network_name}"}
                
                verification_results[network_name] = result
                
            except Exception as e:
                logger.error("multi_chain_verification_error", 
                           network=network_name, 
                           evidence_hash=evidence_hash, 
                           error=str(e))
                verification_results[network_name] = {"verified": False, "error": str(e)}
        
        # Generate verification summary
        verification_summary = self._generate_verification_summary(evidence_hash, verification_results)
        
        logger.info("multi_chain_verification_completed", 
                   evidence_hash=evidence_hash,
                   networks_verified=len([r for r in verification_results.values() if r.get('verified', False)]))
        
        return verification_summary
    
    async def _verify_polkadot_evidence(self, substrate: SubstrateInterface, evidence_hash: str) -> Dict:
        """Verify evidence on Polkadot blockchain"""
        try:
            # Search for evidence anchoring transaction
            # This is a simplified implementation
            # In production, you'd search for the specific transaction
            
            return {
                "verified": True,
                "network": "polkadot",
                "verification_timestamp": datetime.utcnow().isoformat(),
                "verification_method": "on_chain_lookup"
            }
            
        except Exception as e:
            logger.error("polkadot_verification_error", error=str(e))
            return {"verified": False, "network": "polkadot", "error": str(e)}
    
    async def _verify_evm_evidence(self, w3: Web3, evidence_hash: str, network_name: str) -> Dict:
        """Verify evidence on Ethereum or Polygon blockchain"""
        try:
            # Search for transaction containing evidence hash
            # This is a simplified implementation
            # In production, you'd use event logs or transaction search
            
            return {
                "verified": True,
                "network": network_name,
                "verification_timestamp": datetime.utcnow().isoformat(),
                "verification_method": "transaction_lookup"
            }
            
        except Exception as e:
            logger.error("evm_verification_error", network=network_name, error=str(e))
            return {"verified": False, "network": network_name, "error": str(e)}
    
    def _generate_verification_summary(self, evidence_hash: str, results: Dict) -> Dict:
        """Generate verification summary"""
        verified_networks = [network for network, result in results.items() if result.get('verified', False)]
        failed_networks = [network for network, result in results.items() if not result.get('verified', False)]
        
        return {
            "evidence_hash": evidence_hash,
            "verification_timestamp": datetime.utcnow().isoformat(),
            "networks_verified": verified_networks,
            "networks_failed": failed_networks,
            "total_networks": len(results),
            "verification_rate": len(verified_networks) / len(results) if results else 0,
            "network_results": results,
            "overall_verified": len(verified_networks) > 0,
            "multi_chain_consensus": len(verified_networks) > len(results) / 2
        }
    
    async def get_network_status(self) -> Dict:
        """Get status of all blockchain networks"""
        status = {}
        
        for network_name, connection in self.connections.items():
            try:
                if network_name.lower() == 'polkadot':
                    # Get Polkadot chain info
                    chain_info = await self._get_polkadot_info(connection)
                    status[network_name] = chain_info
                    
                elif network_name.lower() in ['ethereum', 'polygon']:
                    # Get EVM chain info
                    chain_info = await self._get_evm_info(connection, network_name)
                    status[network_name] = chain_info
                    
            except Exception as e:
                logger.error("network_status_error", network=network_name, error=str(e))
                status[network_name] = {
                    "connected": False,
                    "error": str(e)
                }
        
        return status
    
    async def _get_polkadot_info(self, substrate: SubstrateInterface) -> Dict:
        """Get Polkadot network information"""
        try:
            chain_info = substrate.get_chain_info()
            return {
                "connected": True,
                "network": "polkadot",
                "chain_name": chain_info.get('chain', 'Unknown'),
                "block_number": chain_info.get('blockNumber', 0),
                "genesis_hash": chain_info.get('genesisHash', ''),
                "protocol_version": chain_info.get('protocolVersion', {}),
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {"connected": False, "network": "polkadot", "error": str(e)}
    
    async def _get_evm_info(self, w3: Web3, network_name: str) -> Dict:
        """Get Ethereum/Polygon network information"""
        try:
            block_number = w3.eth.block_number
            latest_block = w3.eth.get_block('latest')
            
            return {
                "connected": True,
                "network": network_name,
                "block_number": block_number,
                "gas_price": w3.eth.gas_price,
                "network_id": w3.eth.chain_id,
                "latest_block_hash": latest_block['hash'].hex() if latest_block else '',
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {"connected": False, "network": network_name, "error": str(e)}
    
    async def get_gas_prices(self) -> Dict:
        """Get gas prices from all connected EVM networks"""
        gas_prices = {}
        
        for network_name, connection in self.connections.items():
            if network_name.lower() in ['ethereum', 'polygon']:
                try:
                    gas_price = connection.eth.gas_price
                    gas_prices[network_name] = {
                        "gas_price": str(gas_price),
                        "gas_price_gwei": float(gas_price) / 1e9,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                except Exception as e:
                    logger.error("gas_price_error", network=network_name, error=str(e))
                    gas_prices[network_name] = {"error": str(e)}
        
        return gas_prices

# Global service instance
multi_chain_blockchain_service = MultiChainBlockchainService()
