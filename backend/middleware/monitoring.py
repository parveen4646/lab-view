"""
HTTP monitoring middleware.

Per-request:
  - Structured JSON log (Datadog / CloudWatch compatible)
  - Updates in-memory MetricsStore
  - Attaches X-Request-ID and X-Response-Time-Ms response headers

Import and add to the FastAPI app AFTER CORSMiddleware:
    app.add_middleware(MonitoringMiddleware)
"""
import time
import uuid
import logging
import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from utils.metrics import metrics_store

logger = logging.getLogger("vitals.access")

# Paths we don't want to flood logs with (liveness probes, metric scrapes)
_SILENT_PATHS = {"/health", "/metrics", "/"}


class MonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        path = request.url.path

        metrics_store.record_request(
            path=path,
            method=request.method,
            status=response.status_code,
            duration_ms=duration_ms,
        )

        if path not in _SILENT_PATHS:
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": path,
                        "status": response.status_code,
                        "duration_ms": round(duration_ms, 2),
                        "client_ip": request.client.host if request.client else None,
                        "user_agent": request.headers.get("user-agent", ""),
                    }
                )
            )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))
        return response
