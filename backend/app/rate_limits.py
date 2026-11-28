"""Bounded per-process request budgets for expensive public-facing routes."""

from collections import OrderedDict
from time import monotonic

from fastapi import Request
from fastapi.responses import JSONResponse

_windows: OrderedDict[tuple[str, str], tuple[float, int]] = OrderedDict()
_capacity = 4096
_window_seconds = 60
_limits = {
    "/api/auth/login": 30,
    "/api/events": 1200,
    "/api/events/upload-csv": 20,
    "/api/scenarios/generate": 12,
    "/api/datasets/seed": 10,
    "/api/datasets/research-training": 10,
}


async def apply_rate_limits(request: Request, call_next):
    route = request.url.path
    if request.method != "POST" or route not in _limits:
        return await call_next(request)
    identity = request.client.host if request.client else "unknown"
    key = (identity, route)
    current = monotonic()
    expires, used = _windows.get(key, (current + _window_seconds, 0))
    if expires <= current:
        expires, used = current + _window_seconds, 0
    if used >= _limits[route]:
        return JSONResponse(
            {"detail": "Request limit reached; retry after the current window"},
            status_code=429,
            headers={"Retry-After": str(max(1, int(expires - current) + 1))},
        )
    _windows[key] = (expires, used + 1)
    _windows.move_to_end(key)
    if len(_windows) > _capacity:
        _windows.popitem(last=False)
    return await call_next(request)
