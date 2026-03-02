"""APIView base class matching DRF's view API."""

from __future__ import annotations

from typing import Any

from fastrest.request import Request
from fastrest.response import Response
from fastrest.exceptions import MethodNotAllowed, PermissionDenied, APIException, exception_handler
from fastrest.permissions import AllowAny


class APIView:
    permission_classes: list = [AllowAny]
    authentication_classes: list = []
    throttle_classes: list = []
    renderer_classes: list = []
    parser_classes: list = []

    def __init__(self, **kwargs: Any):
        for key, value in kwargs.items():
            setattr(self, key, value)

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

    async def perform_authentication(self, request: Request) -> None:
        pass

    def check_permissions(self, request: Request) -> None:
        for permission_cls in self.get_permissions():
            if not permission_cls.has_permission(request, self):
                raise PermissionDenied()

    def check_object_permissions(self, request: Request, obj: Any) -> None:
        for permission_cls in self.get_permissions():
            if not permission_cls.has_object_permission(request, self, obj):
                raise PermissionDenied()

    def get_permissions(self) -> list:
        return [p() if isinstance(p, type) else p for p in self.permission_classes]

    def handle_exception(self, exc: APIException) -> Response:
        result = exception_handler(exc, {"view": self, "request": self.request})
        if result is not None:
            return Response(data=result["data"], status=result["status"], headers=result.get("headers"))
        raise exc
