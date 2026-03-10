"""Permission classes matching DRF's permission API."""

from __future__ import annotations

from typing import Any


class OperationHolderMixin:
    def __and__(self, other: BasePermission) -> _AND:
        return _AND(self, other)

    def __or__(self, other: BasePermission) -> _OR:
        return _OR(self, other)

    def __invert__(self) -> _NOT:
        return _NOT(self)


class BasePermission(OperationHolderMixin):
    def has_permission(self, request: Any, view: Any) -> bool:
        return True

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        return True


def _resolve_perm(perm: Any) -> Any:
    """Resolve a permission to an instance: instantiate classes, pass through instances."""
    if isinstance(perm, (BasePermission, _AND, _OR, _NOT)):
        return perm
    if isinstance(perm, type):
        return perm()
    return perm


class _AND(OperationHolderMixin):
    def __init__(self, left: Any, right: Any):
        self.left = left
        self.right = right

    def has_permission(self, request: Any, view: Any) -> bool:
        left = _resolve_perm(self.left)
        right = _resolve_perm(self.right)
        return left.has_permission(request, view) and right.has_permission(request, view)

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        left = _resolve_perm(self.left)
        right = _resolve_perm(self.right)
        return left.has_object_permission(request, view, obj) and right.has_object_permission(request, view, obj)


class _OR(OperationHolderMixin):
    def __init__(self, left: Any, right: Any):
        self.left = left
        self.right = right

    def has_permission(self, request: Any, view: Any) -> bool:
        left = _resolve_perm(self.left)
        right = _resolve_perm(self.right)
        return left.has_permission(request, view) or right.has_permission(request, view)

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        left = _resolve_perm(self.left)
        right = _resolve_perm(self.right)
        return left.has_object_permission(request, view, obj) or right.has_object_permission(request, view, obj)


class _NOT(OperationHolderMixin):
    def __init__(self, perm: Any):
        self.perm = perm

    def has_permission(self, request: Any, view: Any) -> bool:
        p = _resolve_perm(self.perm)
        return not p.has_permission(request, view)

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        p = _resolve_perm(self.perm)
        return not p.has_object_permission(request, view, obj)


class AllowAny(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        return True


class IsAuthenticated(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        return request.user is not None and bool(request.user)


class IsAdminUser(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        return request.user is not None and getattr(request.user, "is_staff", False)


class IsAuthenticatedOrReadOnly(BasePermission):
    SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

    def has_permission(self, request: Any, view: Any) -> bool:
        if request.method in self.SAFE_METHODS:
            return True
        return request.user is not None and bool(request.user)


class HasScope(BasePermission):
    """Check that the request's auth token has required scopes.

    Scopes are read from request.auth.scopes (a list of strings).
    If no required scopes are specified, permission is granted.
    """

    def __init__(self, *required_scopes: str):
        self.required_scopes = set(required_scopes)

    def has_permission(self, request: Any, view: Any) -> bool:
        if not self.required_scopes:
            return True
        token_scopes = set(getattr(getattr(request, "auth", None) or object(), "scopes", []))
        return self.required_scopes.issubset(token_scopes)
