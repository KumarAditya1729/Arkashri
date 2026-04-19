# pyre-ignore-all-errors
"""
Multi-Factor Authentication (MFA) Middleware
Provides TOTP-based and SMS-based MFA support
"""
from __future__ import annotations

import base64
import secrets
from typing import Any, Dict
from datetime import datetime, timedelta
from io import BytesIO

import httpx
import structlog
import pyotp
import qrcode
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from arkashri.config import get_settings
from arkashri.services.jwt_service import decode_token

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

    def _resolve_user_id(self, request: Request, *, required: bool = True) -> str | None:
        user_id = request.headers.get("X-User-ID")
        if user_id:
            return user_id

        authorization = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            claims = decode_token(authorization.removeprefix("Bearer ").strip())
            claim_user_id = claims.get("user_id") or claims.get("sub")
            if claim_user_id:
                return str(claim_user_id)

        session_user: Any = None
        try:
            session_user = request.session.get("user")
        except Exception:
            session_user = None

        if isinstance(session_user, dict):
            session_user_id = session_user.get("user_id") or session_user.get("sub") or session_user.get("id")
            if session_user_id:
                return str(session_user_id)

        if required:
            raise HTTPException(status_code=401, detail="Authenticated user identity required for MFA.")
        return None
    
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
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("mfa_request_error", error=str(e), action=action)
            raise HTTPException(status_code=500, detail="MFA request failed")
    
    async def setup_mfa(self, request: Request) -> Response:
        """Setup MFA for a user"""
        
        try:
            user_id = self._resolve_user_id(request)
            
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
            
            return JSONResponse(
                content={
                    "success": True,
                    "secret": totp_secret,
                    "provisioning_uri": provisioning_uri
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("mfa_setup_error", error=str(e))
            raise HTTPException(status_code=500, detail="MFA setup failed")
    
    async def verify_mfa(self, request: Request) -> Response:
        """Verify MFA code"""
        
        try:
            user_id = self._resolve_user_id(request)
            body = await request.json()
            code = body.get("code")
            method = str(body.get("method", "totp")).lower()
            
            if not code:
                raise HTTPException(status_code=400, detail="MFA code required")
            
            if method == "sms":
                sms_token = self.mfa_tokens.get(f"sms_{user_id}")
                is_valid = bool(
                    sms_token
                    and datetime.utcnow() <= sms_token["expires_at"]
                    and secrets.compare_digest(str(sms_token["code"]), str(code))
                )
            else:
                if user_id not in self.mfa_secrets:
                    raise HTTPException(status_code=400, detail="MFA not setup for user")

                mfa_data = self.mfa_secrets[user_id]
                totp_secret = mfa_data["secret"]
                totp = pyotp.TOTP(totp_secret)
                is_valid = totp.verify(code, valid_window=1)
            
            if not is_valid:
                logger.warning("mfa_verification_failed", user_id=user_id, method=method)
                raise HTTPException(status_code=401, detail="Invalid MFA code")
            
            # Mark MFA as verified for this session
            session_token = secrets.token_urlsafe(32)
            self.mfa_tokens[session_token] = {
                "user_id": user_id,
                "verified_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
            }
            
            if method == "sms":
                self.mfa_tokens.pop(f"sms_{user_id}", None)
            else:
                self.mfa_secrets[user_id]["verified"] = True
            
            logger.info("mfa_verification_success", user_id=user_id)
            
            return JSONResponse(
                content={
                    "success": True,
                    "session_token": session_token,
                    "expires_at": self.mfa_tokens[session_token]["expires_at"].isoformat()
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("mfa_verification_error", error=str(e))
            raise HTTPException(status_code=500, detail="MFA verification failed")
    
    async def generate_qr_code(self, request: Request) -> Response:
        """Generate QR code for TOTP setup"""
        
        try:
            user_id = self._resolve_user_id(request)
            
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
            
            return JSONResponse(
                content={
                    "success": True,
                    "qr_code": f"data:image/png;base64,{qr_base64}",
                    "provisioning_uri": provisioning_uri
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("qr_code_generation_error", error=str(e))
            raise HTTPException(status_code=500, detail="QR code generation failed")
    
    async def send_sms_code(self, request: Request) -> Response:
        """Send SMS verification code via the configured webhook backend."""
        
        try:
            user_id = self._resolve_user_id(request)
            if not self.settings.sms_webhook_url:
                raise HTTPException(status_code=501, detail="SMS delivery backend is not configured")

            body = await request.json()
            phone_number = body.get("phone_number")
            if not phone_number:
                raise HTTPException(status_code=400, detail="phone_number is required")

            sms_code = f"{secrets.randbelow(1000000):06d}"
            
            self.mfa_tokens[f"sms_{user_id}"] = {
                "code": sms_code,
                "phone_number": phone_number,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(minutes=5)
            }

            headers = {"Content-Type": "application/json"}
            if self.settings.sms_webhook_bearer_token:
                headers["Authorization"] = f"Bearer {self.settings.sms_webhook_bearer_token}"

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self.settings.sms_webhook_url,
                    headers=headers,
                    json={
                        "user_id": user_id,
                        "phone_number": phone_number,
                        "code": sms_code,
                        "expires_in_seconds": 300,
                    },
                )
                response.raise_for_status()

            logger.info("sms_code_generated", user_id=user_id, code=sms_code[:2] + "****")
            
            return JSONResponse(
                content={
                    "success": True,
                    "message": "SMS code sent successfully",
                    "expires_in": 300  # 5 minutes
                }
            )
            
        except HTTPException:
            raise
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
        user_id = self._resolve_user_id(request, required=False)
        
        # Check if token has expired
        if datetime.utcnow() > token_data["expires_at"]:
            del self.mfa_tokens[mfa_token]
            return False
        if user_id and token_data.get("user_id") != user_id:
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
