"""
Production-ready error handling and retry mechanisms
Provides circuit breakers, retry policies, and graceful degradation
"""
from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import structlog
from circuitbreaker import circuit, CircuitBreakerError
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from arkashri.logging_config import performance_logger

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class ErrorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    NETWORK = "network"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    EXTERNAL_SERVICE = "external_service"
    SYSTEM = "system"
    BUSINESS_LOGIC = "business_logic"


@dataclass
class ErrorContext:
    """Context information for error handling"""
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    request_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    additional_context: Optional[Dict[str, Any]] = None


class ArkashriException(Exception):
    """Base exception for Arkashri application"""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        error_code: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.error_code = error_code
        self.context = context
        self.cause = cause
        self.timestamp = time.time()


class DatabaseException(ArkashriException):
    """Database-related exceptions"""
    
    def __init__(self, message: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.HIGH,
            context=context,
            cause=cause
        )


class ExternalServiceException(ArkashriException):
    """External service-related exceptions"""
    
    def __init__(
        self,
        message: str,
        service_name: str,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(
            message=message,
            category=ErrorCategory.EXTERNAL_SERVICE,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            cause=cause
        )
        self.service_name = service_name


class ValidationException(ArkashriException):
    """Validation-related exceptions"""
    
    def __init__(self, message: str, field: Optional[str] = None, context: Optional[ErrorContext] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            error_code=f"VALIDATION_ERROR_{field.upper()}" if field else "VALIDATION_ERROR",
            context=context
        )
        self.field = field


class SecurityException(ArkashriException):
    """Security-related exceptions"""
    
    def __init__(self, message: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.HIGH,
            error_code="SECURITY_ERROR",
            context=context,
            cause=cause
        )


class ErrorHandler:
    """Centralized error handling and reporting"""
    
    def __init__(self):
        self.logger = structlog.get_logger("error_handler")
        self._error_counts: Dict[str, int] = {}
        self._error_thresholds = {
            ErrorSeverity.LOW: 100,
            ErrorSeverity.MEDIUM: 50,
            ErrorSeverity.HIGH: 10,
            ErrorSeverity.CRITICAL: 1
        }
    
    def handle_exception(
        self,
        exception: Exception,
        context: Optional[ErrorContext] = None,
        reraise: bool = True
    ) -> Optional[Exception]:
        """Handle and log exceptions appropriately"""
        
        # Convert to ArkashriException if needed
        if not isinstance(exception, ArkashriException):
            if isinstance(exception, SQLAlchemyError):
                arkashri_exc = DatabaseException(
                    message=str(exception),
                    context=context,
                    cause=exception
                )
            elif isinstance(exception, HTTPException):
                arkashri_exc = ArkashriException(
                    message=exception.detail,
                    category=ErrorCategory.SYSTEM,
                    severity=ErrorSeverity.MEDIUM,
                    context=context,
                    cause=exception
                )
            else:
                arkashri_exc = ArkashriException(
                    message=str(exception),
                    category=ErrorCategory.SYSTEM,
                    severity=ErrorSeverity.HIGH,
                    context=context,
                    cause=exception
                )
        else:
            arkashri_exc = exception
        
        # Log the error
        self._log_error(arkashri_exc)
        
        # Track error counts
        self._track_error(arkashri_exc)
        
        # Check if threshold exceeded
        self._check_thresholds(arkashri_exc)
        
        if reraise:
            raise arkashri_exc
        
        return arkashri_exc
    
    def _log_error(self, exception: ArkashriException) -> None:
        """Log error with appropriate level and context"""
        log_data = {
            "error_type": exception.__class__.__name__,
            "category": exception.category,
            "severity": exception.severity,
            "error_code": exception.error_code,
            "timestamp": exception.timestamp,
        }
        
        if exception.context:
            log_data.update({
                "user_id": exception.context.user_id,
                "tenant_id": exception.context.tenant_id,
                "request_id": exception.context.request_id,
                "endpoint": exception.context.endpoint,
                "method": exception.context.method,
            })
        
        if exception.context and exception.context.additional_context:
            log_data.update(exception.context.additional_context)
        
        if exception.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(exception.message, **log_data)
        elif exception.severity == ErrorSeverity.HIGH:
            self.logger.error(exception.message, **log_data)
        elif exception.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(exception.message, **log_data)
        else:
            self.logger.info(exception.message, **log_data)
    
    def _track_error(self, exception: ArkashriException) -> None:
        """Track error counts for monitoring"""
        error_key = f"{exception.category.value}:{exception.error_code or 'unknown'}"
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
    
    def _check_thresholds(self, exception: ArkashriException) -> None:
        """Check if error thresholds are exceeded"""
        threshold = self._error_thresholds[exception.severity]
        error_key = f"{exception.category.value}:{exception.error_code or 'unknown'}"
        count = self._error_counts.get(error_key, 0)
        
        if count >= threshold:
            self.logger.error(
                "error_threshold_exceeded",
                error_key=error_key,
                count=count,
                threshold=threshold,
                severity=exception.severity
            )


# Retry decorators for different scenarios
def database_retry(
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0
):
    """Retry decorator for database operations"""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        retry=retry_if_exception_type(SQLAlchemyError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )


def external_service_retry(
    service_name: str,
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0
):
    """Retry decorator for external service calls"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise ExternalServiceException(
                            message=f"Service {service_name} failed after {max_attempts} attempts: {str(e)}",
                            service_name=service_name,
                            cause=e
                        )
                    
                    wait_time = min(wait_min * (2 ** attempt), wait_max) + random.uniform(0, 1)
                    logger.warning(
                        f"external_service_retry_attempt",
                        service=service_name,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        wait_time=wait_time,
                        error=str(e)
                    )
                    await asyncio.sleep(wait_time)
            
            return None  # This line should never be reached
        
        return wrapper
    return decorator


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 30,
    expected_exception: type = Exception
):
    """Circuit breaker decorator for external services"""
    return circuit(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exception=expected_exception
    )


class GracefulDegradation:
    """Handle service failures with graceful degradation"""
    
    def __init__(self):
        self.logger = structlog.get_logger("graceful_degradation")
        self._service_status: Dict[str, bool] = {}
    
    @asynccontextmanager
    async def fallback_to_cache(
        self,
        service_name: str,
        cache_key: str,
        fallback_value: Any = None
    ):
        """Context manager for graceful degradation to cache"""
        try:
            yield
        except Exception as e:
            self.logger.warning(
                "service_fallback_to_cache",
                service=service_name,
                cache_key=cache_key,
                error=str(e)
            )
            
            # Mark service as down
            self._service_status[service_name] = False
            
            # Context managers cannot return values, so we just log and continue
            # The caller should handle the fallback logic
    
    def is_service_healthy(self, service_name: str) -> bool:
        """Check if service is healthy"""
        return self._service_status.get(service_name, True)
    
    def mark_service_healthy(self, service_name: str) -> None:
        """Mark service as healthy"""
        self._service_status[service_name] = True
        self.logger.info("service_marked_healthy", service=service_name)


# Global error handler instance
error_handler = ErrorHandler()


def handle_errors(
    context: Optional[ErrorContext] = None,
    reraise: bool = True,
    default_return: Any = None
):
    """Decorator for automatic error handling"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Union[T, Any]:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_handler.handle_exception(e, context, reraise=False)
                
                if not reraise:
                    return default_return
                raise
        
        return wrapper
    return decorator


# Performance monitoring decorator
def monitor_performance(endpoint: str):
    """Decorator to monitor function performance"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            async with performance_logger.log_request_duration(
                endpoint=endpoint,
                method=func.__name__
            ):
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator
