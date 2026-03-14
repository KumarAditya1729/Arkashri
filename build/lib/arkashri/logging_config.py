# pyre-ignore-all-errors
"""
Production-ready logging configuration for Arkashri
Provides structured logging with correlation IDs, performance tracking, and security monitoring
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

import structlog
from pythonjsonlogger import jsonlogger

from arkashri.config import get_settings

# Create specialized loggers
analytics_logger = structlog.get_logger("analytics")
blockchain_logger = structlog.get_logger("blockchain")


class RequestFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional security and performance fields"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Add custom fields
        if not hasattr(record, 'request_id'):
            record.request_id = getattr(record, 'request_id', 'none')
        if not hasattr(record, 'tenant_id'):
            record.tenant_id = getattr(record, 'tenant_id', 'unknown')
        if not hasattr(record, 'user_id'):
            record.user_id = getattr(record, 'user_id', 'anonymous')
        if not hasattr(record, 'duration_ms'):
            record.duration_ms = getattr(record, 'duration_ms', None)
        
        # Sanitize sensitive data
        record.message = self._sanitize_message(record.getMessage())
        
        return super().format(record)
    
    def _sanitize_message(self, message: str) -> str:
        """Remove potential sensitive data from log messages"""
        sensitive_patterns = [
            'password', 'token', 'secret', 'key', 'credential',
            'authorization', 'bearer', 'signature'
        ]
        msg_lower = message.lower()
        for pattern in sensitive_patterns:
            if pattern in msg_lower:
                return "[REDACTED_SENSITIVE_DATA]"
        return message


class SecurityLogger:
    """Specialized logger for security events"""
    
    def __init__(self):
        self.logger = structlog.get_logger("security")
    
    def log_auth_attempt(self, email: str, success: bool, ip: str, user_agent: str):
        """Log authentication attempts"""
        self.logger.info(
            "authentication_attempt",
            email=email,
            success=success,
            ip_address=ip,
            user_agent=user_agent,
            event_type="security"
        )
    
    def log_permission_denied(self, user_id: str, resource: str, action: str):
        """Log permission denied events"""
        self.logger.warning(
            "permission_denied",
            user_id=user_id,
            resource=resource,
            action=action,
            event_type="security"
        )
    
    def log_suspicious_activity(self, description: str, context: Dict[str, Any]):
        """Log suspicious activities"""
        self.logger.error(
            "suspicious_activity",
            description=description,
            **context,
            event_type="security"
        )


class PerformanceLogger:
    """Specialized logger for performance monitoring"""
    
    def __init__(self):
        self.logger = structlog.get_logger("performance")
    
    @asynccontextmanager
    async def log_request_duration(self, endpoint: str, method: str, **kwargs):
        """Context manager to log request duration"""
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        try:
            yield request_id
            duration = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            self.logger.info(
                "request_completed",
                endpoint=endpoint,
                method=method,
                duration_ms=duration,
                request_id=request_id,
                status="success",
                event_type="performance",
                **kwargs
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            
            self.logger.error(
                "request_failed",
                endpoint=endpoint,
                method=method,
                duration_ms=duration,
                request_id=request_id,
                status="error",
                error=str(e),
                event_type="performance",
                **kwargs
            )
            raise
    
    def log_database_query(self, query: str, duration_ms: float, rows_affected: int = None):
        """Log database query performance"""
        self.logger.info(
            "database_query",
            query_hash=hash(query) % 10000,  # Don't log full queries for security
            duration_ms=duration_ms,
            rows_affected=rows_affected,
            event_type="performance"
        )
    
    def log_cache_operation(self, operation: str, key: str, hit: bool = None):
        """Log cache operations"""
        self.logger.info(
            "cache_operation",
            operation=operation,
            key_hash=hash(key) % 10000,
            hit=hit,
            event_type="performance"
        )


class AuditLogger:
    """Specialized logger for audit trails"""
    
    def __init__(self):
        self.logger = structlog.get_logger("audit")
    
    def log_data_access(self, user_id: str, resource_type: str, resource_id: str, action: str):
        """Log data access for audit compliance"""
        self.logger.info(
            "data_access",
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            event_type="audit"
        )
    
    def log_data_modification(self, user_id: str, resource_type: str, resource_id: str, changes: Dict[str, Any]):
        """Log data modifications for audit compliance"""
        self.logger.info(
            "data_modification",
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes,
            event_type="audit"
        )
    
    def log_system_event(self, event_type: str, description: str, context: Dict[str, Any]):
        """Log system events for audit compliance"""
        self.logger.info(
            "system_event",
            event_type="audit",
            description=description,
            **context
        )


def setup_logging() -> None:
    """Configure production-ready logging"""
    settings = get_settings()
    
    # Remove default handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Set log level based on environment
    log_level = logging.DEBUG if settings.app_env == "dev" else logging.INFO
    root_logger.setLevel(log_level)
    
    # Console handler for development
    if settings.app_env == "dev":
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(RequestFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s'
        ))
        root_logger.addHandler(console_handler)
    
    # File handler for production
    if settings.app_env in ["staging", "production"]:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "arkashri.log",
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=10
        )
        file_handler.setFormatter(RequestFormatter(
            '%(asctime)s %(name)s %(levelname)s %(request_id)s %(tenant_id)s %(user_id)s %(message)s'
        ))
        root_logger.addHandler(file_handler)
        
        # Error file handler
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / "arkashri-errors.log",
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=5
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(RequestFormatter(
            '%(asctime)s %(name)s %(levelname)s %(request_id)s %(tenant_id)s %(user_id)s %(message)s'
        ))
        root_logger.addHandler(error_handler)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# Global logger instances
security_logger = SecurityLogger()
performance_logger = PerformanceLogger()
audit_logger = AuditLogger()
