# pyre-ignore-all-errors
"""
Multi-Factor Authentication (MFA) Middleware
Provides TOTP-based and SMS-based MFA support
"""
from __future__ import annotations

import base64
import secrets
from typing import Dict
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
import pyotp
import qrcode
from io import BytesIO

from arkashri.config import get_settings

logger = structlog.get_logger(__name__)

class MFAMiddleware(BaseHTTPMiddleware):
    """Multi-Factor Authentication middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self.mfa_secrets: Dict[str, Dict] = {}  # Store MFA secrets
        self.mfa_tokens: Dict[str, Dict] = {}   # Store verification tokens
        
        # MFA configuration
        self.ttl_seconds = getattr(self.settings, 'mfa_ttl_seconds', 300)
        self.issuer = "Arkashri Audit OS"
    
    async def dispatch(self, request: Request, call_next):
        """Handle MFA authentication flow"""
        
        # Check if this is an MFA-related request
        if request.url.path.startswith("/api/mfa/"):
            return await self.handle_mfa_request(request)
        
        # For protected endpoints, check MFA requirement
        if self.is_protected_endpoint(request.url.path):
            # Check if user has completed MFA
            mfa_verified = await self.verify_mfa_session(request)
            if not mfa_verified:
                raise HTTPException(
                    status_code=401,
                    detail="Multi-factor authentication required"
                )
        
        return await call_next(request)
    
    async def handle_mfa_request(self, request: Request) -> Response:
        """Handle MFA-related requests"""
        
        path_parts = request.url.path.split("/")
        
        if len(path_parts) < 4:
            raise HTTPException(status_code=400, detail="Invalid MFA request")
        
        action = path_parts[3]
        
        try:
            if action == "setup":
                return await self.setup_mfa(request)
            elif action == "verify":
                return await self.verify_mfa(request)
            elif action == "qrcode":
                return await self.generate_qr_code(request)
            elif action == "sms":
                return await self.send_sms_code(request)
            else:
                raise HTTPException(status_code=400, detail="Invalid MFA action")
                
        except Exception as e:
            logger.error("mfa_request_error", error=str(e), action=action)
            raise HTTPException(status_code=500, detail="MFA request failed")
    
    async def setup_mfa(self, request: Request) -> Response:
        """Setup MFA for a user"""
        
        try:
            # Get user identifier from request (simplified)
            user_id = request.headers.get("X-User-ID", "demo_user")
            
            # Generate TOTP secret
            totp_secret = pyotp.random_base32()
            
            # Store secret (in production, use encrypted storage)
            self.mfa_secrets[user_id] = {
                "secret": totp_secret,
                "created_at": datetime.utcnow(),
                "verified": False
            }
            
            # Generate provisioning URI
            provisioning_uri = pyotp.totp.TOTP(totp_secret).provisioning_uri(
                name=user_id,
                issuer_name=self.issuer
            )
            
            logger.info("mfa_setup_initiated", user_id=user_id)
            
            return Response(
                content={
                    "success": True,
                    "secret": totp_secret,
                    "provisioning_uri": provisioning_uri
                },
                media_type="application/json"
            )
            
        except Exception as e:
            logger.error("mfa_setup_error", error=str(e))
            raise HTTPException(status_code=500, detail="MFA setup failed")
    
    async def verify_mfa(self, request: Request) -> Response:
        """Verify MFA code"""
        
        try:
            # Get user ID and code from request
            user_id = request.headers.get("X-User-ID", "demo_user")
            
            # Parse request body (simplified)
            body = await request.json()
            code = body.get("code")
            
            if not code:
                raise HTTPException(status_code=400, detail="MFA code required")
            
            # Get user's MFA secret
            if user_id not in self.mfa_secrets:
                raise HTTPException(status_code=400, detail="MFA not setup for user")
            
            mfa_data = self.mfa_secrets[user_id]
            totp_secret = mfa_data["secret"]
            
            # Verify TOTP code
            totp = pyotp.TOTP(totp_secret)
            is_valid = totp.verify(code, valid_window=1)
            
            if not is_valid:
                logger.warning("mfa_verification_failed", user_id=user_id)
                raise HTTPException(status_code=401, detail="Invalid MFA code")
            
            # Mark MFA as verified for this session
            session_token = secrets.token_urlsafe(32)
            self.mfa_tokens[session_token] = {
                "user_id": user_id,
                "verified_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
            }
            
            # Mark user's MFA as verified
            mfa_data["verified"] = True
            
            logger.info("mfa_verification_success", user_id=user_id)
            
            return Response(
                content={
                    "success": True,
                    "session_token": session_token,
                    "expires_at": self.mfa_tokens[session_token]["expires_at"].isoformat()
                },
                media_type="application/json"
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("mfa_verification_error", error=str(e))
            raise HTTPException(status_code=500, detail="MFA verification failed")
    
    async def generate_qr_code(self, request: Request) -> Response:
        """Generate QR code for TOTP setup"""
        
        try:
            user_id = request.headers.get("X-User-ID", "demo_user")
            
            if user_id not in self.mfa_secrets:
                raise HTTPException(status_code=400, detail="MFA not setup for user")
            
            mfa_data = self.mfa_secrets[user_id]
            totp_secret = mfa_data["secret"]
            
            # Generate provisioning URI
            provisioning_uri = pyotp.totp.TOTP(totp_secret).provisioning_uri(
                name=user_id,
                issuer_name=self.issuer
            )
            
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(provisioning_uri)
            qr.make(fit=True)
            
            # Convert to image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            qr_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            logger.info("qr_code_generated", user_id=user_id)
            
            return Response(
                content={
                    "success": True,
                    "qr_code": f"data:image/png;base64,{qr_base64}",
                    "provisioning_uri": provisioning_uri
                },
                media_type="application/json"
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("qr_code_generation_error", error=str(e))
            raise HTTPException(status_code=500, detail="QR code generation failed")
    
    async def send_sms_code(self, request: Request) -> Response:
        """Send SMS verification code (placeholder implementation)"""
        
        try:
            user_id = request.headers.get("X-User-ID", "demo_user")
            
            # Generate 6-digit code
            sms_code = f"{secrets.randbelow(1000000):06d}"
            
            # Store SMS code (in production, use encrypted storage)
            self.mfa_tokens[f"sms_{user_id}"] = {
                "code": sms_code,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(minutes=5)
            }
            
            # In production, integrate with SMS service (Twilio, etc.)
            logger.info("sms_code_generated", user_id=user_id, code=sms_code[:2] + "****")
            
            return Response(
                content={
                    "success": True,
                    "message": "SMS code sent successfully",
                    "expires_in": 300  # 5 minutes
                },
                media_type="application/json"
            )
            
        except Exception as e:
            logger.error("sms_code_error", error=str(e))
            raise HTTPException(status_code=500, detail="SMS code generation failed")
    
    async def verify_mfa_session(self, request: Request) -> bool:
        """Verify if user has valid MFA session"""
        
        # Get MFA session token from headers
        mfa_token = request.headers.get("X-MFA-Token")
        
        if not mfa_token:
            return False
        
        # Check if token exists and is valid
        if mfa_token not in self.mfa_tokens:
            return False
        
        token_data = self.mfa_tokens[mfa_token]
        
        # Check if token has expired
        if datetime.utcnow() > token_data["expires_at"]:
            del self.mfa_tokens[mfa_token]
            return False
        
        return True
    
    def is_protected_endpoint(self, path: str) -> bool:
        """Check if endpoint requires MFA protection"""
        
        # Define protected endpoints
        protected_patterns = [
            "/api/audits/",
            "/api/reports/",
            "/api/blockchain/",
            "/api/admin/",
            "/api/enterprise/"
        ]
        
        return any(path.startswith(pattern) for pattern in protected_patterns)
    
    def cleanup_expired_tokens(self):
        """Clean up expired MFA tokens"""
        
        current_time = datetime.utcnow()
        expired_tokens = [
            token for token, data in self.mfa_tokens.items()
            if current_time > data["expires_at"]
        ]
        
        for token in expired_tokens:
            del self.mfa_tokens[token]

def create_mfa_middleware(app):
    """Create and configure MFA middleware"""
    settings = get_settings()
    
    if getattr(settings, 'enable_mfa', False):
        return MFAMiddleware(app)
    
    return None
