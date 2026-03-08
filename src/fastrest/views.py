"""APIView base class matching DRF's view API."""

from __future__ import annotations

from typing import Any

from fastrest.request import Request
from fastrest.response import Response
from fastrest.exceptions import MethodNotAllowed, PermissionDenied, NotAuthenticated, APIException, exception_handler
from fastrest.permissions import AllowAny


class APIView:
    request: Request
    kwargs: dict[str, Any]

    permission_classes: list = [AllowAny]
    authentication_classes: list = []
    throttle_classes: list = []
    renderer_classes: list = []
    parser_classes: list = []

    def __init__(self, **kwargs: Any):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def _resolve_classes(self, attr_name: str, setting_name: str) -> list:
        """Resolve a class list: viewset attr → app config → framework default."""
        from fastrest.settings import get_settings
        val = getattr(self, attr_name, None)
        if val:
            return val
        settings = get_settings(self.request) if hasattr(self, 'request') else None
        if settings:
            return getattr(settings, setting_name, []) or []
        return []

    @classmethod
    def as_view(cls, **initkwargs: Any):
        async def view(request: Any, **kwargs: Any) -> Response:
            self = cls(**initkwargs)
            return await self.dispatch(request, **kwargs)
        view.cls = cls
        view.initkwargs = initkwargs
        return view

    async def dispatch(self, request: Any, **kwargs: Any) -> Response:
        # Wrap raw starlette request
        if not isinstance(request, Request):
            request = Request(request)

        self.request = request
        self.kwargs = kwargs

        try:
            await self.initial(request)
            method = request.method.lower()
            handler = getattr(self, method, None)
            if handler is None:
                raise MethodNotAllowed(request.method)
            response = await handler(request, **kwargs)
        except APIException as exc:
            response = self.handle_exception(exc)

        return response

    async def initial(self, request: Request) -> None:
        await self.perform_authentication(request)
        self.check_permissions(request)
        self.check_throttles(request)

    async def perform_authentication(self, request: Request) -> None:
        authenticators = self.get_authenticators()
        if not authenticators:
            return

        for authenticator in authenticators:
            result = authenticator.authenticate(request)
            if result is not None:
                request.user, request.auth = result
                request._authenticator = authenticator
                return

        # No authenticator returned a result — use defaults from settings
        from fastrest.settings import get_settings
        settings = get_settings(request)
        request.user = settings.UNAUTHENTICATED_USER
        request.auth = settings.UNAUTHENTICATED_TOKEN

    def get_authenticators(self) -> list:
        classes = self._resolve_classes('authentication_classes', 'DEFAULT_AUTHENTICATION_CLASSES')
        return [a() if isinstance(a, type) else a for a in classes]

    def check_permissions(self, request: Request) -> None:
        for permission_cls in self.get_permissions():
            if not permission_cls.has_permission(request, self):
                if request.user is None and self._has_authenticate_header(request):
                    raise NotAuthenticated()
                raise PermissionDenied()

    def _has_authenticate_header(self, request: Request) -> bool:
        for authenticator in self.get_authenticators():
            if authenticator.authenticate_header(request):
                return True
        return False

    def check_object_permissions(self, request: Request, obj: Any) -> None:
        for permission_cls in self.get_permissions():
            if not permission_cls.has_object_permission(request, self, obj):
                raise PermissionDenied()

    def get_permissions(self) -> list:
        classes = self._resolve_classes('permission_classes', 'DEFAULT_PERMISSION_CLASSES')
        return [p() if isinstance(p, type) else p for p in classes]

    def check_throttles(self, request: Request) -> None:
        from fastrest.exceptions import Throttled
        throttles = self.get_throttles()
        for throttle in throttles:
            if not throttle.allow_request(request, self):
                raise Throttled(throttle.wait())

    def get_throttles(self) -> list:
        classes = self._resolve_classes('throttle_classes', 'DEFAULT_THROTTLE_CLASSES')
        return [t() if isinstance(t, type) else t for t in classes]

    def handle_exception(self, exc: APIException) -> Response:
        result = exception_handler(exc, {"view": self, "request": self.request})
        if result is not None:
            return Response(data=result["data"], status=result["status"], headers=result.get("headers"))
        raise exc
