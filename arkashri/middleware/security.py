# pyre-ignore-all-errors
"""
Enhanced security middleware for production
Provides request validation, security headers, and threat detection
"""
from __future__ import annotations

import ipaddress
import re
import time
from typing import Dict, Set

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from arkashri.config import get_settings
from arkashri.logging_config import security_logger

logger = structlog.get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enhanced security headers middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self.logger = structlog.get_logger("security_headers")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Add comprehensive security headers"""
        response = await call_next(request)
        
        # Content Security Policy
        # H-4 FIX: Removed 'unsafe-inline' and 'unsafe-eval' — they completely defeat
        # XSS protection from CSP. If inline scripts are needed, migrate to nonces:
        # generate a random nonce per request and pass it to templates.
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self' wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )
        
        # HSTS (only in production with HTTPS)
        if self.settings.app_env == "production" and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        
        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Request validation and sanitization middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self.logger = structlog.get_logger("request_validation")
        
        # Malicious patterns
        self.malicious_patterns = [
            r'<script[^>]*>.*?</script>',  # XSS
            r'javascript:',  # JavaScript URLs
            r'on\w+\s*=',  # Event handlers
            r'union.*select',  # SQL injection
            r'drop\s+table',  # SQL injection
            r'exec\s*\(',  # Code execution
            r'eval\s*\(',  # Code execution
        ]
        
        # C-7 FIX: Removed private/internal IP ranges (10.x, 172.x, 192.168.x, 127.x).
        # Those ranges are used by Railway internal networking, Docker bridge, Kubernetes
        # pod CIDR, and localhost — blocking them caused all health checks to return 403
        # and made the service permanently unready.
        # Only block truly external-but-reserved ranges that should never originate
        # legitimate client traffic.
        self.blocked_ip_ranges = [
            ipaddress.IPv4Network('0.0.0.0/8'),      # RFC 1700 — this host
            ipaddress.IPv4Network('169.254.0.0/16'), # Link-local (RFC 3927)
            ipaddress.IPv4Network('224.0.0.0/4'),    # Multicast
            ipaddress.IPv4Network('240.0.0.0/4'),    # Reserved
        ]
        
        # Suspicious user agents
        self.suspicious_user_agents = {
            'sqlmap', 'nikto', 'dirb', 'nmap', 'masscan',
            'zap', 'burp', 'scanner', 'crawler', 'bot'
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Validate and sanitize requests"""
        # ── Always allow health/readiness probes through — never block them ──
        if request.url.path in {"/readyz", "/health", "/"}:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "").lower()
        
        # Check blocked IPs
        if self._is_ip_blocked(client_ip):
            security_logger.log_suspicious_activity(
                "Blocked IP access attempt",
                {"ip": client_ip, "user_agent": user_agent}
            )
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check suspicious user agents
        if self._is_suspicious_user_agent(user_agent):
            self.logger.warning(
                "suspicious_user_agent",
                ip=client_ip,
                user_agent=user_agent
            )
        
        # Validate request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.settings.max_request_size:
            raise HTTPException(
                status_code=413,
                detail=f"Request too large. Max size: {self.settings.max_request_size} bytes"
            )
        
        # Validate URL parameters
        if self._has_malicious_content(request.url.query):
            security_logger.log_suspicious_activity(
                "Malicious URL parameters detected",
                {"ip": client_ip, "url": str(request.url)}
            )
            raise HTTPException(status_code=400, detail="Invalid request")
        
        # For POST/PUT requests, validate body content
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
            if body and self._has_malicious_content(body.decode('utf-8', errors='ignore')):
                security_logger.log_suspicious_activity(
                    "Malicious request body detected",
                    {"ip": client_ip, "method": request.method, "path": request.url.path}
                )
                raise HTTPException(status_code=400, detail="Invalid request content")
        
        return await call_next(request)
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _is_ip_blocked(self, ip: str) -> bool:
        """Check if IP is in blocked ranges"""
        if ip in {"testclient", "unknown", ""}:
            return False  # Never block Railway internals or unknown proxy IPs
        try:
            client_ip = ipaddress.ip_address(ip)
            for blocked_range in self.blocked_ip_ranges:
                if client_ip in blocked_range:
                    return True
        except ValueError:
            # Invalid IP format — don't block, just let it through
            # Railway proxy sometimes sends non-standard values
            return False
        return False
    
    def _is_suspicious_user_agent(self, user_agent: str) -> bool:
        """Check for suspicious user agent patterns"""
        return any(suspicious in user_agent for suspicious in self.suspicious_user_agents)
    
    def _has_malicious_content(self, content: str) -> bool:
        """Check for malicious content patterns"""
        content_lower = content.lower()
        for pattern in self.malicious_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return True
        return False


class ThreatDetectionMiddleware(BaseHTTPMiddleware):
    """Threat detection and anomaly detection middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.logger = structlog.get_logger("threat_detection")
        
        # Track request patterns for anomaly detection
        self.request_patterns: Dict[str, Dict] = {}
        self.blocked_ips: Set[str] = set()
        self.suspicious_ips: Dict[str, int] = {}
        
        # Anomaly detection thresholds
        self.max_requests_per_minute = 1000
        self.max_unique_endpoints = 50
        self.max_failed_auth_attempts = 10
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Detect threats and anomalies"""
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # Check if IP is blocked
        if client_ip in self.blocked_ips:
            security_logger.log_suspicious_activity(
                "Blocked IP attempted access",
                {"ip": client_ip, "path": request.url.path}
            )
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Track request patterns
        self._track_request_pattern(client_ip, request, current_time)
        
        # Detect anomalies
        if self._detect_anomalies(client_ip, request):
            self._handle_suspicious_activity(client_ip, request)
        
        # Process request
        start_time = current_time
        response = await call_next(request)
        
        # Track response for anomaly detection
        self._track_response(client_ip, request, response, start_time)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _track_request_pattern(self, ip: str, request: Request, timestamp: float):
        """Track request patterns for anomaly detection"""
        if ip not in self.request_patterns:
            self.request_patterns[ip] = {
                'requests': [],
                'endpoints': set(),
                'failed_auth': 0,
                'last_activity': timestamp
            }
        
        pattern = self.request_patterns[ip]
        
        # Clean old requests (older than 1 minute)
        pattern['requests'] = [req_time for req_time in pattern['requests'] if req_time > timestamp - 60]
        
        # Add current request
        pattern['requests'].append(timestamp)
        pattern['endpoints'].add(request.url.path)
        pattern['last_activity'] = timestamp
        
        # Track failed authentication attempts
        if '/auth' in request.url.path or '/token' in request.url.path:
            # This would be updated based on actual response status
            # For now, we'll track all auth endpoint requests
            pattern['failed_auth'] += 1
    
    def _detect_anomalies(self, ip: str, request: Request) -> bool:
        """Detect anomalous behavior"""
        if ip not in self.request_patterns:
            return False
        
        pattern = self.request_patterns[ip]
        
        # Too many requests per minute
        if len(pattern['requests']) > self.max_requests_per_minute:
            self.logger.warning(
                "high_request_rate_detected",
                ip=ip,
                request_count=len(pattern['requests'])
            )
            return True
        
        # Too many unique endpoints (potential scraping)
        if len(pattern['endpoints']) > self.max_unique_endpoints:
            self.logger.warning(
                "endpoint_scraping_detected",
                ip=ip,
                unique_endpoints=len(pattern['endpoints'])
            )
            return True
        
        # Too many failed authentication attempts
        if pattern['failed_auth'] > self.max_failed_auth_attempts:
            self.logger.warning(
                "brute_force_detected",
                ip=ip,
                failed_attempts=pattern['failed_auth']
            )
            return True
        
        return False
    
    def _handle_suspicious_activity(self, ip: str, request: Request):
        """Handle suspicious activity"""
        # Increment suspicious counter
        self.suspicious_ips[ip] = self.suspicious_ips.get(ip, 0) + 1
        
        # Block IP after multiple offenses
        if self.suspicious_ips[ip] >= 3:
            self.blocked_ips.add(ip)
            self.logger.error(
                "ip_blocked_due_to_suspicious_activity",
                ip=ip,
                offenses=self.suspicious_ips[ip]
            )
            
            security_logger.log_suspicious_activity(
                "IP blocked due to suspicious activity",
                {
                    "ip": ip,
                    "offenses": self.suspicious_ips[ip],
                    "path": request.url.path
                }
            )
        
        # Log security event
        security_logger.log_suspicious_activity(
            "Suspicious activity detected",
            {
                "ip": ip,
                "path": request.url.path,
                "method": request.method,
                "offenses": self.suspicious_ips[ip]
            }
        )
    
    def _track_response(self, ip: str, request: Request, response: Response, start_time: float):
        """Track response patterns"""
        # Update failed auth count based on response status
        if ip in self.request_patterns:
            pattern = self.request_patterns[ip]
            
            # Reset failed auth counter on successful auth
            if '/auth' in request.url.path and response.status_code == 200:
                pattern['failed_auth'] = max(0, pattern['failed_auth'] - 1)


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """Request size limiting middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self.logger = structlog.get_logger("request_size")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Limit request size"""
        content_length = request.headers.get("content-length")
        
        if content_length:
            size = int(content_length)
            if size > self.settings.max_request_size:
                self.logger.warning(
                    "request_size_exceeded",
                    size=size,
                    max_size=self.settings.max_request_size,
                    ip=self._get_client_ip(request)
                )
                raise HTTPException(
                    status_code=413,
                    detail=f"Request too large. Max size: {self.settings.max_request_size} bytes"
                )
        
        return await call_next(request)
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
