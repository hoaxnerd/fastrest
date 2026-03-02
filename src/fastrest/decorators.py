"""Decorators matching DRF's decorator API."""

from __future__ import annotations

from typing import Any, Callable
from functools import wraps


class MethodMapper(dict):
    """Maps HTTP methods to view handler names, used by @action."""

    def __init__(self, action: Any, methods: list[str]):
        super().__init__()
        self.action = action
        for method in methods:
            self[method.lower()] = action.__name__


def action(
    methods: list[str] | None = None,
    detail: bool = False,
    url_path: str | None = None,
    url_name: str | None = None,
    **kwargs: Any,
) -> Callable:
    methods = methods or ["get"]

    def decorator(func: Callable) -> Callable:
        func.mapping = MethodMapper(func, methods)
        func.detail = detail
        func.url_path = url_path or func.__name__
        func.url_name = url_name or func.__name__.replace("_", "-")
        func.kwargs = kwargs
        return func

    return decorator


def api_view(methods: list[str] | None = None) -> Callable:
    methods = [m.upper() for m in (methods or ["GET"])]

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def view(request: Any, **kwargs: Any) -> Any:
            return await func(request, **kwargs)

        view.methods = methods
        view.cls = None  # Marker for function-based views
        return view

    return decorator


def permission_classes(classes: list) -> Callable:
    def decorator(func: Callable) -> Callable:
        func.permission_classes = classes
        return func
    return decorator


def authentication_classes(classes: list) -> Callable:
    def decorator(func: Callable) -> Callable:
        func.authentication_classes = classes
        return func
    return decorator
