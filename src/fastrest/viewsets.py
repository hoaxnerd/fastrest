"""ViewSets matching DRF's viewset API."""

from __future__ import annotations

from typing import Any

from fastapi import Request as FastAPIRequest
from fastrest.generics import GenericAPIView
from fastrest.mixins import (
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
)


class ViewSetMixin:
    """Provides action mapping and @action support for viewsets."""

    # Set by the router
    action: str | None = None
    basename: str | None = None
    lookup_field_type: type = int
    action_map: dict[str, str] = {}

    @classmethod
    def as_view(cls, actions: dict[str, str] | None = None, **initkwargs: Any):
        if actions is None:
            raise TypeError("The `actions` argument must be provided when calling `.as_view()` on a ViewSet.")

        # Check if any action is a detail action (needs pk param)
        has_detail = any(
            a in ("retrieve", "update", "partial_update", "destroy")
            for a in actions.values()
        )
        for action_name in actions.values():
            method = getattr(cls, action_name, None)
            if method and getattr(method, "detail", False):
                has_detail = True

        if has_detail:
            async def view(request: FastAPIRequest, pk: int) -> Any:
                return await cls._dispatch_view(actions, initkwargs, request, pk=pk)
        else:
            async def view(request: FastAPIRequest) -> Any:
                return await cls._dispatch_view(actions, initkwargs, request)

        view.cls = cls
        view.actions = actions
        view.initkwargs = initkwargs
        return view

    @classmethod
    def get_action_endpoints(cls, actions: dict[str, str], basename: str, serializer_class: type | None = None):
        """Produce separate endpoint functions per action with full metadata."""
        from fastrest.openapi import serializer_to_response_model, serializer_to_request_model

        ser_cls = serializer_class or getattr(cls, 'serializer_class', None)
        pk_type = getattr(cls, 'lookup_field_type', int)
        endpoints = {}

        # Build pydantic models from serializer
        response_model = None
        request_model = None
        patch_model = None
        if ser_cls:
            # Use serializer class name for unique Pydantic model naming
            cap_basename = ser_cls.__name__.replace('Serializer', '')
            response_model = serializer_to_response_model(ser_cls, f"{cap_basename}Response")
            request_model = serializer_to_request_model(ser_cls, f"{cap_basename}Request")
            patch_model = serializer_to_request_model(ser_cls, f"{cap_basename}PatchRequest", partial=True)

        ACTION_META = {
            'list':           {'method': 'GET',    'status_code': 200, 'detail': False, 'verb': 'List'},
            'create':         {'method': 'POST',   'status_code': 201, 'detail': False, 'verb': 'Create'},
            'retrieve':       {'method': 'GET',    'status_code': 200, 'detail': True,  'verb': 'Retrieve'},
            'update':         {'method': 'PUT',    'status_code': 200, 'detail': True,  'verb': 'Update'},
            'partial_update': {'method': 'PATCH',  'status_code': 200, 'detail': True,  'verb': 'Partial update'},
            'destroy':        {'method': 'DELETE', 'status_code': 204, 'detail': True,  'verb': 'Destroy'},
        }

        for method, action_name in actions.items():
            meta = ACTION_META.get(action_name)
            if meta is None:
                continue

            status_code = meta['status_code']
            is_detail = meta['detail']
            verb = meta['verb']
            human_name = basename.replace('-', ' ').replace('_', ' ')
            summary = f"{verb} {human_name}"
            operation_id = f"{basename}_{action_name}"

            # Determine response model for this action
            if action_name == 'destroy':
                action_response_model = None
            elif action_name == 'list':
                pagination_cls = getattr(cls, 'pagination_class', None)
                if pagination_cls and response_model:
                    from fastrest.openapi import paginated_response_model
                    action_response_model = paginated_response_model(
                        response_model, f"{cap_basename}PaginatedResponse"
                    )
                elif response_model:
                    action_response_model = list[response_model]
                else:
                    action_response_model = None
            else:
                action_response_model = response_model

            # Determine if this action needs a request body
            needs_body = action_name in ('create', 'update', 'partial_update')
            body_model = patch_model if action_name == 'partial_update' else request_model

            # Build endpoint function
            if is_detail and needs_body:
                endpoint_fn = cls._make_body_detail_endpoint(
                    {method: action_name}, body_model, pk_type
                )
            elif is_detail:
                endpoint_fn = cls._make_detail_endpoint({method: action_name}, pk_type)
            elif needs_body:
                endpoint_fn = cls._make_body_endpoint({method: action_name}, body_model)
            else:
                endpoint_fn = cls._make_list_endpoint({method: action_name})

            endpoint_fn.__name__ = f"{basename}_{action_name}"
            endpoint_fn.__qualname__ = f"{basename}_{action_name}"

            endpoint_info = {
                'endpoint_fn': endpoint_fn,
                'methods': [method.upper()],
                'status_code': status_code,
                'response_model': action_response_model,
                'summary': summary,
                'operation_id': operation_id,
            }

            # Merge per-action OpenAPI metadata if defined on the viewset
            openapi_meta = getattr(cls, 'openapi_meta', None)
            if openapi_meta and action_name in openapi_meta:
                endpoint_info['openapi_extra'] = openapi_meta[action_name]

            endpoints[action_name] = endpoint_info

        return endpoints

    @classmethod
    def _make_list_endpoint(cls, actions: dict):
        from fastapi import Query as FastAPIQuery
        from fastrest.pagination import PageNumberPagination, LimitOffsetPagination
        from fastrest.filters import SearchFilter, OrderingFilter

        # Build query params based on configured pagination/filter backends
        pagination_cls = getattr(cls, 'pagination_class', None)
        filter_backends = getattr(cls, 'filter_backends', None) or []

        query_params = {}
        if pagination_cls:
            if issubclass(pagination_cls, PageNumberPagination):
                query_params['page'] = (int | None, FastAPIQuery(None, description="Page number"))
                query_params['page_size'] = (int | None, FastAPIQuery(None, description="Number of results per page"))
            elif issubclass(pagination_cls, LimitOffsetPagination):
                query_params['limit'] = (int | None, FastAPIQuery(None, description="Number of results to return"))
                query_params['offset'] = (int | None, FastAPIQuery(None, description="Starting position"))

        for backend_cls in filter_backends:
            if issubclass(backend_cls, SearchFilter):
                query_params['search'] = (str | None, FastAPIQuery(None, description="Search term"))
            elif issubclass(backend_cls, OrderingFilter):
                query_params['ordering'] = (str | None, FastAPIQuery(None, description="Ordering fields (comma-separated, prefix with - for desc)"))

        # Build endpoint with query params in signature for OpenAPI
        if query_params:
            async def endpoint(request: FastAPIRequest, **kwargs) -> Any:
                return await cls._dispatch_view(actions, {}, request)
            # Set annotations so FastAPI picks up the query params
            annotations = {'request': FastAPIRequest, 'return': Any}
            annotations.update({k: v[0] for k, v in query_params.items()})
            endpoint.__annotations__ = annotations
            # Set defaults
            import inspect
            params = [inspect.Parameter('request', inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=FastAPIRequest)]
            for name, (type_, default) in query_params.items():
                params.append(inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=default, annotation=type_))
            endpoint.__signature__ = inspect.Signature(params, return_annotation=Any)
        else:
            async def endpoint(request: FastAPIRequest) -> Any:
                return await cls._dispatch_view(actions, {}, request)
        return endpoint

    @classmethod
    def _make_detail_endpoint(cls, actions: dict, pk_type: type):
        async def endpoint(request: FastAPIRequest, pk: int) -> Any:
            return await cls._dispatch_view(actions, {}, request, pk=pk)
        return endpoint

    @classmethod
    def _make_body_endpoint(cls, actions: dict, request_model):
        if request_model:
            async def endpoint(request: FastAPIRequest, body=None) -> Any:
                return await cls._dispatch_view(actions, {}, request, _body=body)
            # Set actual type annotation (not string) so FastAPI resolves it
            endpoint.__annotations__ = {'request': FastAPIRequest, 'body': request_model, 'return': Any}
        else:
            async def endpoint(request: FastAPIRequest) -> Any:
                return await cls._dispatch_view(actions, {}, request)
        return endpoint

    @classmethod
    def _make_body_detail_endpoint(cls, actions: dict, request_model, pk_type: type):
        if request_model:
            async def endpoint(request: FastAPIRequest, pk: int = 0, body=None) -> Any:
                return await cls._dispatch_view(actions, {}, request, pk=pk, _body=body)
            endpoint.__annotations__ = {'request': FastAPIRequest, 'pk': int, 'body': request_model, 'return': Any}
        else:
            async def endpoint(request: FastAPIRequest, pk: int) -> Any:
                return await cls._dispatch_view(actions, {}, request, pk=pk)
        return endpoint

    @classmethod
    async def _dispatch_view(cls, actions: dict, initkwargs: dict, request: Any, _body=None, **kwargs: Any) -> Any:
        self = cls(**initkwargs)
        self.action_map = actions

        from fastrest.request import Request
        if not isinstance(request, Request):
            request = Request(request)

        # Parse body: prefer typed _body param, fall back to raw JSON
        if request.method in ("POST", "PUT", "PATCH"):
            if _body is not None:
                # For PATCH, exclude fields not explicitly set
                if hasattr(_body, 'model_dump'):
                    request.data = _body.model_dump(exclude_unset=True)
                else:
                    request.data = dict(_body)
            else:
                try:
                    request.data = await request._request.json()
                except Exception:
                    request.data = {}

        self.request = request
        self.kwargs = kwargs

        method = request.method.lower()
        action_name = actions.get(method)
        if action_name is None:
            from fastrest.exceptions import MethodNotAllowed
            raise MethodNotAllowed(request.method)

        self.action = action_name
        handler = getattr(self, action_name)

        from fastrest.exceptions import APIException
        try:
            await self.initial(request)
            response = await handler(request, **kwargs)
        except APIException as exc:
            response = self.handle_exception(exc)
        return response

    def get_extra_actions(self) -> list:
        actions = []
        for attr_name in dir(type(self)):
            attr = getattr(type(self), attr_name, None)
            if callable(attr) and hasattr(attr, "detail"):
                actions.append(attr)
        return actions


class ViewSet(ViewSetMixin, GenericAPIView):
    pass


class GenericViewSet(ViewSetMixin, GenericAPIView):
    pass


class ModelViewSet(
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    GenericViewSet,
):
    pass


class ReadOnlyModelViewSet(
    RetrieveModelMixin,
    ListModelMixin,
    GenericViewSet,
):
    pass
