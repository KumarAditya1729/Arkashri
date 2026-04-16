# pyre-ignore-all-errors
"""
OAuth2 Authentication Middleware
Provides OAuth2 integration with multiple providers (Google, Microsoft, GitHub)
"""
from __future__ import annotations

import json
import secrets
from typing import Dict, Optional, List
from urllib.parse import urlencode, parse_qs

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from arkashri.config import get_settings

logger = structlog.get_logger(__name__)

class OAuth2Middleware(BaseHTTPMiddleware):
    """OAuth2 authentication middleware with multi-provider support"""
    
    def __init__(self, app, providers: Optional[List[str]] = None):
        super().__init__(app)
        self.settings = get_settings()
        self.providers = providers or ["google", "microsoft", "github"]
        self.oauth_states: Dict[str, Dict] = {}  # Store OAuth states
        
        # OAuth provider configurations
        self.provider_configs = {
            "google": {
                "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "user_info_url": "https://www.googleapis.com/oauth2/v2/userinfo",
                "scope": "openid email profile",
                "client_id": getattr(self.settings, 'oauth2_google_client_id', ''),
                "client_secret": getattr(self.settings, 'oauth2_google_client_secret', ''),
                "redirect_uri": f"{getattr(self.settings, 'frontend_url', 'http://localhost:3000')}/api/oauth2/google/callback"
            },
            "microsoft": {
                "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "user_info_url": "https://graph.microsoft.com/v1.0/me",
                "scope": "openid email profile",
                "client_id": getattr(self.settings, 'oauth2_microsoft_client_id', ''),
                "client_secret": getattr(self.settings, 'oauth2_microsoft_client_secret', ''),
                "redirect_uri": f"{getattr(self.settings, 'frontend_url', 'http://localhost:3000')}/api/oauth2/microsoft/callback"
            },
            "github": {
                "auth_url": "https://github.com/login/oauth/authorize",
                "token_url": "https://github.com/login/oauth/access_token",
                "user_info_url": "https://api.github.com/user",
                "scope": "user:email",
                "client_id": getattr(self.settings, 'oauth2_github_client_id', ''),
                "client_secret": getattr(self.settings, 'oauth2_github_client_secret', ''),
                "redirect_uri": f"{getattr(self.settings, 'frontend_url', 'http://localhost:3000')}/api/oauth2/github/callback"
            }
        }
    
    async def dispatch(self, request: Request, call_next):
        """Handle OAuth2 authentication flow"""
        
        # Check if this is an OAuth2 callback
        if request.url.path.startswith("/api/oauth2/"):
            return await self.handle_oauth_callback(request)
        
        # Check if this is an OAuth2 login request
        if request.url.path.startswith("/oauth2/"):
            return await self.handle_oauth_login(request)
        
        # Continue with normal request processing
        return await call_next(request)
    
    async def handle_oauth_login(self, request: Request) -> Response:
        """Handle OAuth2 login initiation"""
        
        try:
            # Extract provider from path
            path_parts = request.url.path.split("/")
            if len(path_parts) < 3:
                raise HTTPException(status_code=400, detail="Invalid OAuth2 request")
            
            provider = path_parts[2]
            
            if provider not in self.providers:
                raise HTTPException(status_code=400, detail=f"Unsupported OAuth2 provider: {provider}")
            
            # Generate state for security
            state = secrets.token_urlsafe(32)
            self.oauth_states[state] = {
                "provider": provider,
                "created_at": secrets.randbelow(1000000)
            }
            
            # Build authorization URL
            config = self.provider_configs[provider]
            auth_params = {
                "client_id": config["client_id"],
                "redirect_uri": config["redirect_uri"],
                "scope": config["scope"],
                "response_type": "code",
                "state": state,
                "access_type": "offline" if provider == "google" else None
            }
            
            # Remove None values
            auth_params = {k: v for k, v in auth_params.items() if v is not None}
            
            auth_url = f"{config['auth_url']}?{urlencode(auth_params)}"
            
            logger.info("oauth_login_initiated", provider=provider, state=state[:8])
            
            # Redirect to OAuth provider
            return Response(
                content=json.dumps({"redirect_url": auth_url, "state": state}),
                media_type="application/json"
            )
            
        except Exception as e:
            logger.error("oauth_login_error", error=str(e), provider=provider)
            raise HTTPException(status_code=500, detail="OAuth2 login failed")
    
    async def handle_oauth_callback(self, request: Request) -> Response:
        """Handle OAuth2 callback from provider"""
        
        try:
            # Extract provider from path
            path_parts = request.url.path.split("/")
            if len(path_parts) < 4:
                raise HTTPException(status_code=400, detail="Invalid OAuth2 callback")
            
            provider = path_parts[3]
            
            if provider not in self.providers:
                raise HTTPException(status_code=400, detail=f"Unsupported OAuth2 provider: {provider}")
            
            # Parse callback parameters
            query_params = parse_qs(request.url.query)
            code = query_params.get("code", [None])[0]
            state = query_params.get("state", [None])[0]
            error = query_params.get("error", [None])[0]
            
            if error:
                logger.error("oauth_callback_error", error=error, provider=provider)
                raise HTTPException(status_code=400, detail=f"OAuth2 error: {error}")
            
            if not code or not state:
                raise HTTPException(status_code=400, detail="Missing OAuth2 parameters")
            
            # Validate state
            if state not in self.oauth_states:
                raise HTTPException(status_code=400, detail="Invalid OAuth2 state")
            
            stored_state = self.oauth_states.pop(state)
            if stored_state["provider"] != provider:
                raise HTTPException(status_code=400, detail="State provider mismatch")
            
            # Exchange authorization code for access token
            config = self.provider_configs[provider]
            token_data = await self.exchange_code_for_token(config, code)
            
            # Get user information
            user_info = await self.get_user_info(config, token_data["access_token"])
            
            # Create or update user session
            session_data = {
                "provider": provider,
                "user_id": user_info["id"],
                "email": user_info["email"],
                "name": user_info.get("name", ""),
                "avatar": user_info.get("avatar_url", ""),
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": token_data.get("expires_in")
            }
            
            logger.info("oauth_callback_success", provider=provider, user_id=user_info["id"])
            
            # Return session data
            return Response(
                content=json.dumps({"success": True, "user": session_data}),
                media_type="application/json"
            )
            
        except Exception as e:
            logger.error("oauth_callback_error", error=str(e), provider=provider)
            raise HTTPException(status_code=500, detail="OAuth2 callback failed")
    
    async def exchange_code_for_token(self, config: Dict, code: str) -> Dict:
        """Exchange authorization code for access token"""
        
        import httpx
        
        async with httpx.AsyncClient() as client:
            token_data = {
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": code,
                "redirect_uri": config["redirect_uri"],
                "grant_type": "authorization_code"
            }
            
            headers = {"Accept": "application/json"}
            
            response = await client.post(
                config["token_url"],
                data=token_data,
                headers=headers
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"Token exchange failed: {response.text}"
                )
            
            return response.json()
    
    async def get_user_info(self, config: Dict, access_token: str) -> Dict:
        """Get user information from OAuth2 provider"""
        
        import httpx
        
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            
            response = await client.get(
                config["user_info_url"],
                headers=headers
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"User info request failed: {response.text}"
                )
            
            user_data = response.json()
            
            # Standardize user data format
            return {
                "id": str(user_data.get("id", "")),
                "email": user_data.get("email", ""),
                "name": user_data.get("name", user_data.get("login", "")),
                "avatar_url": user_data.get("picture", user_data.get("avatar_url", ""))
            }

def create_oauth2_middleware(app):
    """Create and configure OAuth2 middleware"""
    settings = get_settings()
    
    if getattr(settings, 'enable_oauth2', False):
        providers = getattr(settings, 'oauth2_providers', 'google,microsoft,github').split(',')
        return OAuth2Middleware(app, providers)
    
    return None
