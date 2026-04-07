import time
from typing import Callable

from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "path", "status"],
)

LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency (seconds)",
    ["service", "method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13),
)

PROMPT_TESTS = Counter(
    "prompt_tests_total",
    "Total prompt test operations",
    ["service", "category", "result"],
)

PROMPT_QUALITY = Histogram(
    "prompt_quality_score",
    "Prompt quality score distribution",
    ["service", "category"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

CATEGORY_USAGE = Counter(
    "prompt_category_usage_total",
    "Prompt usage by category",
    ["service", "category"],
)

TOKEN_ESTIMATE = Counter(
    "prompt_token_estimate_total",
    "Estimated token usage for prompt tests",
    ["service", "direction"],
)

EXPORT_OPS = Counter(
    "prompt_export_total",
    "Total prompt library export operations",
    ["service", "format"],
)


def prom_middleware(service_name: str):
    async def middleware(request, call_next: Callable):
        path = request.url.path
        method = request.method
        start = time.perf_counter()
        status = "500"
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            dur = time.perf_counter() - start
            REQUESTS.labels(service=service_name, method=method, path=path, status=status).inc()
            LATENCY.labels(service=service_name, method=method, path=path).observe(dur)

    return middleware
