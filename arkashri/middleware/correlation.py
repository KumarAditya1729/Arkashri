# pyre-ignore-all-errors
from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
from structlog.contextvars import bind_contextvars

logger = structlog.get_logger("middleware.correlation")

class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for end-to-end request correlation.
    Supports W3C Traceparent and X-Correlation-ID.
    Injects the trace ID into structlog contextvars for unified logging.
    """
    
    def __init__(self, app, header_name: str = "X-Correlation-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Extract or Generate Correlation ID
        # Support standard traceparent (W3C) or common X-Correlation-ID
        correlation_id = (
            request.headers.get("X-Correlation-ID") or 
            request.headers.get("X-Request-ID") or
            request.headers.get("traceparent") or # W3C Trace Context
            str(uuid.uuid4())
        )

        # 2. Bind to structlog context for the duration of the request
        # This ensures all log calls (Audit, Security, App) share this ID
        bind_contextvars(correlation_id=correlation_id)
        
        # 3. Store in request scope for downstream access if needed
        request.state.correlation_id = correlation_id

        # 4. Process the request
        response: Response = await call_next(request)

        # 5. Propagation: Set the ID in the response header
        response.headers[self.header_name] = correlation_id
        
        return response
