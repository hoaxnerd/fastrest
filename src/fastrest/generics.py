"""Generic views matching DRF's generic view API."""

from __future__ import annotations

from typing import Any

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
    queryset = None  # Model class
    serializer_class = None
    lookup_field: str = "pk"
    lookup_url_kwarg: str | None = None
    dependencies: list = []

    _session = None
    _adapter = None

    @property
    def adapter(self):
        if self._adapter is None:
            from fastrest.compat.orm.sqlalchemy import adapter
            self._adapter = adapter
        return self._adapter

    def get_session(self):
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

    def get_serializer_context(self) -> dict:
        return {
            "request": getattr(self, "request", None),
            "view": self,
            "session": self.get_session(),
        }

    def filter_queryset(self, queryset: list) -> list:
        return queryset

    def paginate_queryset(self, queryset: list) -> list | None:
        return None


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
