# pyre-ignore-all-errors
"""
Enhanced Security Headers Middleware
Provides CSP, HSTS, XSS protection, and other security headers
"""
from __future__ import annotations


from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from arkashri.config import get_settings

logger = structlog.get_logger(__name__)

class EnhancedSecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enhanced security headers middleware with CSP, HSTS, and XSS protection"""
    
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        
        # Security configuration
        self.csp_enabled = getattr(self.settings, 'enable_csp', True)
        self.hsts_enabled = getattr(self.settings, 'enable_hsts', True)
        self.xss_protection = getattr(self.settings, 'enable_xss_protection', True)
        self.content_type_nosniff = getattr(self.settings, 'enable_content_type_nosniff', True)
        
        # CSP policy
        self.csp_policy = getattr(self.settings, 'csp_policy', 
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' ws: wss: https:"
        )
        
        # HSTS configuration
        self.hsts_max_age = getattr(self.settings, 'hsts_max_age', 31536000)
        self.hsts_include_subdomains = True
        self.hsts_preload = True
        
        # Additional security headers
        self.referrer_policy = "strict-origin-when-cross-origin"
        self.permissions_policy = self._build_permissions_policy()
        self.cross_origin_embedder_policy = "require-corp"
        self.cross_origin_opener_policy = "same-origin"
        self.cross_origin_resource_policy = "same-origin"
    
    async def dispatch(self, request: Request, call_next):
        """Add enhanced security headers to response"""
        
        response = await call_next(request)
        
        # Add security headers
        self._add_security_headers(request, response)
        
        # Log security events
        self._log_security_event(request)
        
        return response
    
    def _add_security_headers(self, request: Request, response: Response):
        """Add security headers to response"""
        
        try:
            # Content Security Policy (CSP)
            if self.csp_enabled:
                csp_header = self._build_csp_header(request)
                response.headers["Content-Security-Policy"] = csp_header
            
            # HTTP Strict Transport Security (HSTS)
            if self.hsts_enabled and request.url.scheme == "https":
                hsts_header = f"max-age={self.hsts_max_age}"
                if self.hsts_include_subdomains:
                    hsts_header += "; includeSubDomains"
                if self.hsts_preload:
                    hsts_header += "; preload"
                response.headers["Strict-Transport-Security"] = hsts_header
            
            # XSS Protection
            if self.xss_protection:
                response.headers["X-XSS-Protection"] = "1; mode=block"
            
            # Content Type No Sniff
            if self.content_type_nosniff:
                response.headers["X-Content-Type-Options"] = "nosniff"
            
            # Referrer Policy
            response.headers["Referrer-Policy"] = self.referrer_policy
            
            # Permissions Policy
            response.headers["Permissions-Policy"] = self.permissions_policy
            
            # Cross-Origin Headers
            response.headers["Cross-Origin-Embedder-Policy"] = self.cross_origin_embedder_policy
            response.headers["Cross-Origin-Opener-Policy"] = self.cross_origin_opener_policy
            response.headers["Cross-Origin-Resource-Policy"] = self.cross_origin_resource_policy
            
            # Additional security headers
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
            response.headers["X-Download-Options"] = "noopen"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            
            # Cache control for sensitive endpoints
            if self._is_sensitive_endpoint(request.url.path):
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            
            logger.debug("security_headers_added", path=request.url.path)
            
        except Exception as e:
            logger.error("security_headers_error", error=str(e), path=request.url.path)
    
    def _build_csp_header(self, request: Request) -> str:
        """Build Content Security Policy header"""
        
        # Base CSP policy
        csp_directives = {
            "default-src": ["'self'"],
            "script-src": ["'self'", "'unsafe-inline'"],
            "style-src": ["'self'", "'unsafe-inline'"],
            "img-src": ["'self'", "data:", "https:"],
            "font-src": ["'self'", "data:"],
            "connect-src": ["'self'", "ws:", "wss:", "https:"],
            "frame-ancestors": ["'none'"],
            "base-uri": ["'self'"],
            "form-action": ["'self'"],
            "frame-src": ["'self'"],
            "media-src": ["'self'"],
            "object-src": ["'none'"],
            "script-src-elem": ["'self'"],
            "style-src-elem": ["'self'", "'unsafe-inline'"],
            "worker-src": ["'self'", "blob:"],
            "manifest-src": ["'self'"],
            "upgrade-insecure-requests": []
        }
        
        # Add WebSocket support for specific endpoints
        if request.url.path.startswith("/ws/"):
            csp_directives["connect-src"].extend(["ws:", "wss:"])
        
        # Add API endpoints
        if request.url.path.startswith("/api/"):
            csp_directives["connect-src"].append("'self'")
        
        # Build CSP string
        csp_parts = []
        for directive, sources in csp_directives.items():
            if sources:
                csp_parts.append(f"{directive} {' '.join(sources)}")
        
        return "; ".join(csp_parts)
    
    def _build_permissions_policy(self) -> str:
        """Build Permissions Policy header"""
        
        permissions = [
            "geolocation=()",
            "microphone=()",
            "camera=()",
            "payment=()",
            "usb=()",
            "magnetometer=()",
            "gyroscope=()",
            "accelerometer=()",
            "ambient-light-sensor=()",
            "autoplay=()",
            "encrypted-media=()",
            "fullscreen=(self)",
            "picture-in-picture=()",
            "speaker=()",
            "vr=()",
            "interest-cohort=()"
        ]
        
        return ", ".join(permissions)
    
    def _is_sensitive_endpoint(self, path: str) -> bool:
        """Check if endpoint is sensitive and should not be cached"""
        
        sensitive_patterns = [
            "/api/auth/",
            "/api/admin/",
            "/api/users/",
            "/api/mfa/",
            "/api/oauth2/",
            "/api/blockchain/",
            "/api/enterprise/"
        ]
        
        return any(path.startswith(pattern) for pattern in sensitive_patterns)
    
    def _log_security_event(self, request: Request):
        """Log security-related events"""
        
        # Log suspicious requests
        if self._is_suspicious_request(request):
            logger.warning(
                "suspicious_request",
                path=request.url.path,
                method=request.method,
                user_agent=request.headers.get("user-agent", ""),
                ip=request.client.host if request.client else "unknown"
            )
        
        # Log API access
        if request.url.path.startswith("/api/"):
            logger.info(
                "api_access",
                path=request.url.path,
                method=request.method,
                status="success"
            )
    
    def _is_suspicious_request(self, request: Request) -> bool:
        """Check if request is suspicious"""
        
        suspicious_indicators = []
        
        # Check for suspicious user agents
        user_agent = request.headers.get("user-agent", "").lower()
        suspicious_agents = ["bot", "crawler", "scanner", "hack", "exploit"]
        if any(agent in user_agent for agent in suspicious_agents):
            suspicious_indicators.append("suspicious_user_agent")
        
        # Check for unusual headers
        suspicious_headers = ["x-forwarded-for", "x-real-ip", "x-originating-ip"]
        for header in suspicious_headers:
            if header in request.headers:
                suspicious_indicators.append(f"has_{header.replace('-', '_')}")
        
        # Check for large payloads
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 10485760:  # 10MB
            suspicious_indicators.append("large_payload")
        
        # Check for SQL injection patterns
        query_string = request.url.query.lower()
        sql_patterns = ["union", "select", "drop", "insert", "delete", "update"]
        if any(pattern in query_string for pattern in sql_patterns):
            suspicious_indicators.append("sql_injection_pattern")
        
        # Check for XSS patterns
        xss_patterns = ["<script", "javascript:", "onerror=", "onload="]
        if any(pattern in query_string for pattern in xss_patterns):
            suspicious_indicators.append("xss_pattern")
        
        return len(suspicious_indicators) > 1

def create_enhanced_security_middleware(app):
    """Create and configure enhanced security headers middleware"""
    settings = get_settings()
    
    if getattr(settings, 'enable_advanced_security_headers', False):
        return EnhancedSecurityHeadersMiddleware(app)
    
    return None
