"""ViewSet mixins matching DRF's mixin API."""

from __future__ import annotations

from typing import Any

from fastrest.response import Response
from fastrest import status


class CreateModelMixin:
    async def create(self, request: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        await self.perform_create(serializer)
        return Response(data=serializer.data, status=status.HTTP_201_CREATED)

    async def perform_create(self, serializer: Any) -> None:
        await serializer.save()


class ListModelMixin:
    async def list(self, request: Any, **kwargs: Any) -> Response:
        queryset = await self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(data=serializer.data)


class RetrieveModelMixin:
    async def retrieve(self, request: Any, **kwargs: Any) -> Response:
        instance = await self.get_object()
        serializer = self.get_serializer(instance)
        return Response(data=serializer.data)


class UpdateModelMixin:
    async def update(self, request: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop("partial", False)
        instance = await self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        await self.perform_update(serializer)
        return Response(data=serializer.data)

    async def perform_update(self, serializer: Any) -> None:
        await serializer.save()

    async def partial_update(self, request: Any, **kwargs: Any) -> Response:
        kwargs["partial"] = True
        return await self.update(request, **kwargs)


class DestroyModelMixin:
    async def destroy(self, request: Any, **kwargs: Any) -> Response:
        instance = await self.get_object()
        await self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    async def perform_destroy(self, instance: Any) -> None:
        session = self.get_session()
        await self.adapter.delete(instance, session)
