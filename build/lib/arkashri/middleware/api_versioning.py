# pyre-ignore-all-errors
"""
API versioning and deprecation middleware for production
Provides version management, deprecation warnings, and migration support
"""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from arkashri.logging_config import audit_logger

logger = structlog.get_logger(__name__)


class APIVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"
    LATEST = "latest"


class VersionStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    BETA = "beta"


@dataclass
class VersionInfo:
    """API version information"""
    version: APIVersion
    status: VersionStatus
    introduced_date: datetime.datetime
    deprecation_date: Optional[datetime.datetime] = None
    sunset_date: Optional[datetime.datetime] = None
    migration_guide: Optional[str] = None
    breaking_changes: List[str] = None
    
    def __post_init__(self):
        if self.breaking_changes is None:
            self.breaking_changes = []


class APIVersionManager:
    """Manages API versioning and deprecation policies"""
    
    def __init__(self):
        self.logger = structlog.get_logger("api_version_manager")
        
        # Define version lifecycle
        self.versions = self._define_versions()
        
        # Default version
        self.default_version = APIVersion.V1
        
        # Version deprecation warnings
        self.deprecation_warnings_sent: Dict[str, set] = {}
    
    def _define_versions(self) -> Dict[APIVersion, VersionInfo]:
        """Define API versions and their lifecycle"""
        now = datetime.datetime.now()
        
        return {
            APIVersion.V1: VersionInfo(
                version=APIVersion.V1,
                status=VersionStatus.ACTIVE,
                introduced_date=now - datetime.timedelta(days=365),
                deprecation_date=None,
                sunset_date=None,
                migration_guide="/api/v1/migration-guide",
                breaking_changes=[]
            ),
            
            APIVersion.V2: VersionInfo(
                version=APIVersion.V2,
                status=VersionStatus.BETA,
                introduced_date=now - datetime.timedelta(days=30),
                deprecation_date=None,
                sunset_date=None,
                migration_guide="/api/v2/migration-guide",
                breaking_changes=[
                    "Authentication header format changed",
                    "Response envelope structure updated",
                    "Error response format standardized"
                ]
            ),
            
            APIVersion.LATEST: VersionInfo(
                version=APIVersion.LATEST,
                status=VersionStatus.ACTIVE,
                introduced_date=now,
                deprecation_date=None,
                sunset_date=None,
                migration_guide=None,
                breaking_changes=[]
            ),
        }
    
    def get_version_from_request(self, request: Request) -> APIVersion:
        """Extract API version from request"""
        # Check URL path version
        path_parts = request.url.path.strip("/").split("/")
        if len(path_parts) >= 2 and path_parts[0] == "api":
            version_str = path_parts[1]
            if version_str.startswith("v"):
                try:
                    return APIVersion(version_str)
                except ValueError:
                    pass
        
        # Check header version
        version_header = request.headers.get("X-API-Version")
        if version_header:
            try:
                return APIVersion(version_header)
            except ValueError:
                pass
        
        # Check query parameter version
        version_query = request.query_params.get("version")
        if version_query:
            try:
                return APIVersion(version_query)
            except ValueError:
                pass
        
        # Return default version
        return self.default_version
    
    def validate_version(self, version: APIVersion) -> Tuple[bool, Optional[str]]:
        """Validate API version and return status"""
        if version not in self.versions:
            return False, f"Unknown API version: {version.value}"
        
        version_info = self.versions[version]
        
        if version_info.status == VersionStatus.SUNSET:
            return False, f"API version {version.value} has been sunset"
        
        if version_info.status == VersionStatus.DEPRECATED:
            return True, f"API version {version.value} is deprecated"
        
        return True, None
    
    def get_deprecation_warning(self, version: APIVersion) -> Optional[Dict[str, any]]:
        """Get deprecation warning for version"""
        version_info = self.versions[version]
        
        if version_info.status == VersionStatus.DEPRECATED:
            return {
                "warning": "API version deprecated",
                "version": version.value,
                "deprecation_date": version_info.deprecation_date.isoformat() if version_info.deprecation_date else None,
                "sunset_date": version_info.sunset_date.isoformat() if version_info.sunset_date else None,
                "migration_guide": version_info.migration_guide,
                "breaking_changes": version_info.breaking_changes
            }
        
        return None
    
    def should_send_deprecation_warning(self, request: Request, version: APIVersion) -> bool:
        """Check if deprecation warning should be sent"""
        client_id = self._get_client_identifier(request)
        
        if client_id not in self.deprecation_warnings_sent:
            self.deprecation_warnings_sent[client_id] = set()
        
        return version not in self.deprecation_warnings_sent[client_id]
    
    def mark_deprecation_warning_sent(self, request: Request, version: APIVersion):
        """Mark deprecation warning as sent for client"""
        client_id = self._get_client_identifier(request)
        
        if client_id not in self.deprecation_warnings_sent:
            self.deprecation_warnings_sent[client_id] = set()
        
        self.deprecation_warnings_sent[client_id].add(version)
    
    def _get_client_identifier(self, request: Request) -> str:
        """Get unique client identifier"""
        # Use combination of IP and User-Agent for client identification
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")
        
        # Create hash for privacy
        import hashlib
        client_string = f"{client_ip}:{user_agent}"
        return hashlib.sha256(client_string.encode()).hexdigest()[:16]


class APIVersioningMiddleware(BaseHTTPMiddleware):
    """API versioning and deprecation middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.version_manager = APIVersionManager()
        self.logger = structlog.get_logger("api_versioning")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with versioning"""
        # Extract version from request
        version = self.version_manager.get_version_from_request(request)
        
        # Validate version
        is_valid, message = self.version_manager.validate_version(version)
        
        if not is_valid:
            self.logger.warning(
                "invalid_api_version",
                version=version.value,
                message=message,
                path=request.url.path
            )
            
            audit_logger.log_system_event(
                event_type="invalid_api_version",
                description=f"Invalid API version {version.value}: {message}",
                context={
                    "version": version.value,
                    "path": request.url.path,
                    "method": request.method
                }
            )
            
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid API version",
                    "message": message,
                    "supported_versions": [v.value for v in self.version_manager.versions.keys()],
                    "default_version": self.version_manager.default_version.value
                }
            )
        
        # Check for deprecation warning
        warning = self.version_manager.get_deprecation_warning(version)
        should_warn = warning and self.version_manager.should_send_deprecation_warning(request, version)
        
        # Process request
        response = await call_next(request)
        
        # Add version headers
        response.headers["X-API-Version"] = version.value
        response.headers["X-API-Default-Version"] = self.version_manager.default_version.value
        response.headers["X-API-Supported-Versions"] = ",".join([v.value for v in self.version_manager.versions.keys()])
        
        # Add deprecation warning if needed
        if should_warn:
            response.headers["X-API-Deprecation-Warning"] = "true"
            response.headers["X-API-Deprecation-Date"] = warning["deprecation_date"] or ""
            response.headers["X-API-Sunset-Date"] = warning["sunset_date"] or ""
            response.headers["X-API-Migration-Guide"] = warning["migration_guide"] or ""
            
            # Mark warning as sent
            self.version_manager.mark_deprecation_warning_sent(request, version)
            
            # Log deprecation warning
            self.logger.info(
                "api_deprecation_warning_sent",
                version=version.value,
                client_ip=request.client.host if request.client else "unknown"
            )
        
        # Add version information to response body if it's JSON
        if response.headers.get("content-type", "").startswith("application/json"):
            try:
                import json
                content = json.loads(response.body.decode())
                
                if isinstance(content, dict):
                    content["_meta"] = {
                        "api_version": version.value,
                        "default_version": self.version_manager.default_version.value,
                        "supported_versions": [v.value for v in self.version_manager.versions.keys()],
                        "deprecation_warning": warning if should_warn else None
                    }
                    
                    response.body = json.dumps(content).encode()
                    response.headers["content-length"] = str(len(response.body))
                    
            except (json.JSONDecodeError, UnicodeDecodeError):
                # If we can't parse the response, just add headers
                pass
        
        return response


class APIDeprecationMiddleware(BaseHTTPMiddleware):
    """API deprecation enforcement middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.version_manager = APIVersionManager()
        self.logger = structlog.get_logger("api_deprecation")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Enforce deprecation policies"""
        version = self.version_manager.get_version_from_request(request)
        version_info = self.version_manager.versions.get(version)
        
        if not version_info:
            return await call_next(request)
        
        # Enforce sunset versions
        if version_info.status == VersionStatus.SUNSET:
            self.logger.warning(
                "sunset_api_version_access",
                version=version.value,
                path=request.url.path
            )
            
            raise HTTPException(
                status_code=410,
                detail={
                    "error": "API version sunset",
                    "message": f"API version {version.value} has been sunset and is no longer available",
                    "migration_guide": version_info.migration_guide,
                    "supported_versions": [v.value for v in self.version_manager.versions.keys()],
                    "default_version": self.version_manager.default_version.value
                }
            )
        
        # Add rate limiting for deprecated versions
        if version_info.status == VersionStatus.DEPRECATED:
            # This would integrate with rate limiting middleware
            # For now, just log the access
            self.logger.info(
                "deprecated_api_version_access",
                version=version.value,
                path=request.url.path
            )
        
        return await call_next(request)


class APICompatibilityMiddleware(BaseHTTPMiddleware):
    """API compatibility and migration middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.logger = structlog.get_logger("api_compatibility")
        
        # Define compatibility rules
        self.compatibility_rules = self._define_compatibility_rules()
    
    def _define_compatibility_rules(self) -> Dict[str, Dict]:
        """Define API compatibility rules"""
        return {
            "authentication": {
                "v1": {
                    "header": "X-Arkashri-Key",
                    "format": "api_key"
                },
                "v2": {
                    "header": "Authorization",
                    "format": "Bearer <token>"
                }
            },
            "response_format": {
                "v1": {
                    "envelope": False,
                    "error_format": "simple"
                },
                "v2": {
                    "envelope": True,
                    "error_format": "standardized"
                }
            }
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Handle API compatibility"""
        # Extract version
        version = request.url.path.strip("/").split("/")[1] if "/api/" in request.url.path else "v1"
        
        # Apply compatibility transformations
        request = self._apply_request_compatibility(request, version)
        
        # Process request
        response = await call_next(request)
        
        # Apply response compatibility
        response = self._apply_response_compatibility(response, version)
        
        return response
    
    def _apply_request_compatibility(self, request: Request, version: str) -> Request:
        """Apply request compatibility transformations"""
        # Handle authentication header compatibility
        if version == "v1":
            # Convert v1 auth to v2 format if needed
            api_key = request.headers.get("X-Arkashri-Key")
            if api_key and not request.headers.get("Authorization"):
                # This would be handled by the authentication middleware
                pass
        
        return request
    
    def _apply_response_compatibility(self, response: Response, version: str) -> Response:
        """Apply response compatibility transformations"""
        # Handle response format compatibility
        if version == "v1":
            # Convert v2 response format to v1 if needed
            if response.headers.get("content-type", "").startswith("application/json"):
                try:
                    import json
                    content = json.loads(response.body.decode())
                    
                    # Remove v2 envelope for v1 compatibility
                    if isinstance(content, dict) and "_meta" in content:
                        content.pop("_meta", None)
                        response.body = json.dumps(content).encode()
                        response.headers["content-length"] = str(len(response.body))
                        
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
        
        return response


# Global version manager instance
api_version_manager = APIVersionManager()
