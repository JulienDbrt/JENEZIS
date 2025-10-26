"""
Prometheus metrics for monitoring API performance and usage.
"""

import time
from functools import wraps
from typing import Any, Callable

from fastapi import Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Request metrics
REQUEST_COUNT = Counter(
    "api_requests_total", "Total number of API requests", ["method", "endpoint", "status"]
)

REQUEST_DURATION = Histogram(
    "api_request_duration_seconds", "API request duration in seconds", ["method", "endpoint"]
)

# Cache metrics
CACHE_SIZE = Gauge("cache_size", "Current size of the in-memory cache", ["cache_type"])

# Database metrics
DB_QUERY_COUNT = Counter(
    "database_queries_total", "Total number of database queries", ["query_type"]
)

DB_QUERY_DURATION = Histogram(
    "database_query_duration_seconds", "Database query duration in seconds", ["query_type"]
)

# Harmonization metrics
HARMONIZATION_COUNT = Counter(
    "harmonization_total",
    "Total number of skills harmonized",
    ["status"],  # known, unknown
)

# Entity resolution metrics
ENTITY_RESOLUTION_COUNT = Counter(
    "entity_resolution_total",
    "Total number of entities resolved",
    ["entity_type", "status"],  # company/school, known/unknown
)

# Error metrics
ERROR_COUNT = Counter("api_errors_total", "Total number of API errors", ["error_type", "endpoint"])


def track_request_metrics(method: str, endpoint: str, status_code: int, duration: float) -> None:
    """Track request metrics for Prometheus."""
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status_code)).inc()
    REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)


def track_cache_metrics(cache_type: str, size: int) -> None:
    """Update cache size metrics."""
    CACHE_SIZE.labels(cache_type=cache_type).set(size)


def track_harmonization(status: str, count: int = 1) -> None:
    """Track harmonization metrics."""
    HARMONIZATION_COUNT.labels(status=status).inc(count)


def track_entity_resolution(entity_type: str, status: str, count: int = 1) -> None:
    """Track entity resolution metrics."""
    ENTITY_RESOLUTION_COUNT.labels(entity_type=entity_type, status=status).inc(count)


def track_database_query(query_type: str, duration: float) -> None:
    """Track database query metrics."""
    DB_QUERY_COUNT.labels(query_type=query_type).inc()
    DB_QUERY_DURATION.labels(query_type=query_type).observe(duration)


def track_error(error_type: str, endpoint: str) -> None:
    """Track error metrics."""
    ERROR_COUNT.labels(error_type=error_type, endpoint=endpoint).inc()


def metrics_endpoint() -> Response:
    """Generate Prometheus metrics endpoint response."""
    return Response(content=generate_latest(), media_type="text/plain")


def time_database_query(query_type: str) -> Callable:
    """Decorator to time database queries."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                track_database_query(query_type, duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                track_database_query(query_type, duration)
                raise e

        return wrapper

    return decorator
