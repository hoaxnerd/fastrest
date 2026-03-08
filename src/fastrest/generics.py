"""Generic views matching DRF's generic view API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastrest.compat.orm.base import ORMAdapter
    from fastrest.pagination import BasePagination
    from fastrest.filters import BaseFilterBackend

from fastrest.views import APIView
from fastrest.response import Response
from fastrest.exceptions import NotFound
from fastrest.mixins import (
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
)


class GenericAPIView(APIView):
    queryset: type | None = None  # Model class
    serializer_class: type | None = None
    lookup_field: str = "pk"
    lookup_url_kwarg: str | None = None
    lookup_field_type: type = int
    dependencies: list[Any] = []
    pagination_class: type[BasePagination] | None = None
    filter_backends: list[type[BaseFilterBackend]] | None = None

    # Session type is ORM-dependent (e.g. AsyncSession for SQLAlchemy).
    # Can't type it here without coupling to a specific backend.
    _session: Any = None
    _paginator: BasePagination | None = None
    _adapter: ORMAdapter | None = None

    @property
    def adapter(self) -> ORMAdapter:
        if self._adapter is None:
            from fastrest.compat.orm import get_default_adapter
            self._adapter = get_default_adapter()
        return self._adapter

    def get_session(self) -> Any:
        return self._session

    def set_session(self, session: Any) -> None:
        self._session = session

    async def get_queryset(self) -> list:
        session = self.get_session()
        return await self.adapter.get_queryset(self.queryset, session)

    async def get_object(self) -> Any:
        session = self.get_session()
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)

        # Map 'pk' to actual PK field name
        lookup_key = self.lookup_field
        if lookup_key == "pk":
            pk_field = self.adapter.get_pk_field(self.queryset)
            lookup_key = pk_field.name

        obj = await self.adapter.get_object(self.queryset, session, **{lookup_key: lookup_value})
        if obj is None:
            raise NotFound()

        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer(self, *args: Any, **kwargs: Any) -> Any:
        serializer_class = self.get_serializer_class()
        kwargs.setdefault("context", self.get_serializer_context())
        return serializer_class(*args, **kwargs)

    def get_serializer_class(self) -> type:
        return self.serializer_class

    def get_serializer_context(self) -> dict[str, Any]:
        return {
            "request": getattr(self, "request", None),
            "view": self,
            "session": self.get_session(),
        }

    def filter_queryset(self, queryset: list) -> list:
        from fastrest.settings import get_settings
        backends = self.filter_backends
        if backends is None:
            settings = get_settings(self.request) if hasattr(self, 'request') else None
            backends = (getattr(settings, 'DEFAULT_FILTER_BACKENDS', None) if settings else None) or []
        for backend_cls in backends:
            backend = backend_cls() if isinstance(backend_cls, type) else backend_cls
            queryset = backend.filter_queryset(self.request, queryset, self)
        return queryset

    def paginate_queryset(self, queryset: list) -> list | None:
        from fastrest.settings import get_settings
        cls = self.pagination_class
        if cls is None:
            settings = get_settings(self.request) if hasattr(self, 'request') else None
            cls = getattr(settings, 'DEFAULT_PAGINATION_CLASS', None) if settings else None
        if cls is None:
            return None
        self._paginator = cls()
        return self._paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data: list) -> dict[str, Any]:
        return self._paginator.get_paginated_response(data)


# Concrete generic views

class CreateAPIView(CreateModelMixin, GenericAPIView):
    async def post(self, request: Any, **kwargs: Any) -> Response:
        return await self.create(request, **kwargs)


class ListAPIView(ListModelMixin, GenericAPIView):
    async def get(self, request: Any, **kwargs: Any) -> Response:
        return await self.list(request, **kwargs)


class RetrieveAPIView(RetrieveModelMixin, GenericAPIView):
    async def get(self, request: Any, **kwargs: Any) -> Response:
        return await self.retrieve(request, **kwargs)


class DestroyAPIView(DestroyModelMixin, GenericAPIView):
    async def delete(self, request: Any, **kwargs: Any) -> Response:
        return await self.destroy(request, **kwargs)


class UpdateAPIView(UpdateModelMixin, GenericAPIView):
    async def put(self, request: Any, **kwargs: Any) -> Response:
        return await self.update(request, **kwargs)

    async def patch(self, request: Any, **kwargs: Any) -> Response:
        return await self.partial_update(request, **kwargs)


class ListCreateAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    async def get(self, request: Any, **kwargs: Any) -> Response:
        return await self.list(request, **kwargs)

    async def post(self, request: Any, **kwargs: Any) -> Response:
        return await self.create(request, **kwargs)


class RetrieveUpdateAPIView(RetrieveModelMixin, UpdateModelMixin, GenericAPIView):
    async def get(self, request: Any, **kwargs: Any) -> Response:
        return await self.retrieve(request, **kwargs)

    async def put(self, request: Any, **kwargs: Any) -> Response:
        return await self.update(request, **kwargs)

    async def patch(self, request: Any, **kwargs: Any) -> Response:
        return await self.partial_update(request, **kwargs)


class RetrieveDestroyAPIView(RetrieveModelMixin, DestroyModelMixin, GenericAPIView):
    async def get(self, request: Any, **kwargs: Any) -> Response:
        return await self.retrieve(request, **kwargs)

    async def delete(self, request: Any, **kwargs: Any) -> Response:
        return await self.destroy(request, **kwargs)


class RetrieveUpdateDestroyAPIView(RetrieveModelMixin, UpdateModelMixin, DestroyModelMixin, GenericAPIView):
    async def get(self, request: Any, **kwargs: Any) -> Response:
        return await self.retrieve(request, **kwargs)

    async def put(self, request: Any, **kwargs: Any) -> Response:
        return await self.update(request, **kwargs)

    async def patch(self, request: Any, **kwargs: Any) -> Response:
        return await self.partial_update(request, **kwargs)

    async def delete(self, request: Any, **kwargs: Any) -> Response:
        return await self.destroy(request, **kwargs)
