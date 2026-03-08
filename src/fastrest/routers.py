"""Router classes matching DRF's router API."""

from __future__ import annotations

from collections import namedtuple
from typing import Any

from fastapi import APIRouter, Request as FastAPIRequest


Route = namedtuple("Route", ["url", "mapping", "name", "detail", "initkwargs"])
DynamicRoute = namedtuple("DynamicRoute", ["url", "name", "detail", "initkwargs"])


class BaseRouter:
    def __init__(self, router: APIRouter | None = None):
        self.registry: list[tuple[str, type, str]] = []
        self._custom_router = router
        self._url_cache: APIRouter | None = None

    def register(self, prefix: str, viewset: type, basename: str | None = None) -> None:
        if basename is None:
            basename = prefix.strip("/").replace("/", "-")
        self.registry.append((prefix, viewset, basename))

    @property
    def urls(self) -> APIRouter:
        if self._url_cache is None:
            self._url_cache = self.get_urls()
        return self._url_cache

    def get_urls(self) -> APIRouter:
        raise NotImplementedError


class SimpleRouter(BaseRouter):
    routes = [
        Route(
            url="",
            mapping={"get": "list", "post": "create"},
            name="{basename}-list",
            detail=False,
            initkwargs={},
        ),
        Route(
            url="/{pk}",
            mapping={"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"},
            name="{basename}-detail",
            detail=True,
            initkwargs={},
        ),
    ]

    def get_urls(self) -> APIRouter:
        router = self._custom_router or APIRouter()

        for prefix, viewset, basename in self.registry:
            self._register_viewset_routes(router, prefix, viewset, basename)

        return router

    def _register_viewset_routes(self, router: APIRouter, prefix: str, viewset: type, basename: str) -> None:
        dependencies = getattr(viewset, 'dependencies', [])
        tags = [prefix]

        # Register non-detail @action routes first (before {pk} captures them)
        for action_func in self._get_dynamic_actions(viewset):
            if not action_func.detail:
                self._register_action_route(router, prefix, basename, viewset, action_func, tags, dependencies)

        # Register standard routes — one route per HTTP method
        for route in self.routes:
            mapping = {}
            for method, action_name in route.mapping.items():
                if hasattr(viewset, action_name):
                    mapping[method] = action_name

            if not mapping:
                continue

            url = f"/{prefix}{route.url}"
            ser_cls = getattr(viewset, 'serializer_class', None)

            # Get per-action endpoints with full metadata
            action_endpoints = viewset.get_action_endpoints(mapping, basename, ser_cls)

            # DRF-style naming: list route → basename-list, detail route → basename-detail
            drf_name = route.name.format(basename=basename)

            for action_name, ep in action_endpoints.items():
                name = drf_name

                # Extract per-action OpenAPI extras (deprecated, responses, description, etc.)
                openapi_extra_kwargs = ep.get('openapi_extra', {})

                router.add_api_route(
                    url,
                    ep['endpoint_fn'],
                    methods=ep['methods'],
                    name=name,
                    status_code=ep['status_code'],
                    response_model=ep['response_model'],
                    summary=ep['summary'],
                    operation_id=ep['operation_id'],
                    tags=tags,
                    dependencies=dependencies or None,
                    **openapi_extra_kwargs,
                )

        # Register detail @action routes after {pk}
        for action_func in self._get_dynamic_actions(viewset):
            if action_func.detail:
                self._register_action_route(router, prefix, basename, viewset, action_func, tags, dependencies)

    def _register_action_route(self, router: APIRouter, prefix: str, basename: str, viewset: type, action_func, tags=None, dependencies=None) -> None:
        url_path = action_func.url_path
        action_name = action_func.__name__

        if action_func.detail:
            url = f"/{prefix}/{{pk}}/{url_path}"
        else:
            url = f"/{prefix}/{url_path}"

        methods_list = list(action_func.mapping.keys())
        mapping = {m: action_name for m in methods_list}
        name = f"{basename}-{action_func.url_name}"

        operation_id = f"{basename}_{action_name}"
        human_name = basename.replace('-', ' ').replace('_', ' ')
        summary = f"{action_name.replace('_', ' ').title()} {human_name}"

        # Build typed endpoint if serializer classes are provided on the action
        req_ser = getattr(action_func, 'serializer_class', None)
        resp_ser = getattr(action_func, 'response_serializer_class', None)
        response_model = None
        request_model = None

        if req_ser or resp_ser:
            from fastrest.openapi import serializer_to_request_model, serializer_to_response_model
            if resp_ser:
                resp_name = resp_ser.__name__.replace('Serializer', '')
                response_model = serializer_to_response_model(resp_ser, f"{resp_name}ActionResponse")
            if req_ser:
                req_name = req_ser.__name__.replace('Serializer', '')
                request_model = serializer_to_request_model(req_ser, f"{req_name}ActionRequest")

        # Build a typed endpoint function
        endpoint_fn = self._make_action_endpoint(
            viewset, mapping, action_func.detail, request_model,
            getattr(viewset, 'lookup_field_type', int),
        )
        endpoint_fn.__name__ = f"{basename}_{action_name}"
        endpoint_fn.__qualname__ = f"{basename}_{action_name}"

        route_kwargs = dict(
            methods=[m.upper() for m in methods_list],
            name=name,
            tags=tags,
            summary=summary,
            operation_id=operation_id,
            dependencies=dependencies or None,
        )
        if response_model:
            route_kwargs['response_model'] = response_model

        router.add_api_route(url, endpoint_fn, **route_kwargs)

    @staticmethod
    def _make_action_endpoint(viewset_cls, actions, detail, request_model, pk_type):
        """Build a typed endpoint function for a custom @action."""
        from fastapi import Request as FastAPIRequest
        from typing import Any

        if detail and request_model:
            async def endpoint(request: FastAPIRequest, pk: int = 0, body=None) -> Any:
                return await viewset_cls._dispatch_view(actions, {}, request, pk=pk, _body=body)
            endpoint.__annotations__ = {'request': FastAPIRequest, 'pk': pk_type, 'body': request_model, 'return': Any}
        elif detail:
            async def endpoint(request: FastAPIRequest, pk: int) -> Any:
                return await viewset_cls._dispatch_view(actions, {}, request, pk=pk)
            endpoint.__annotations__['pk'] = pk_type
        elif request_model:
            async def endpoint(request: FastAPIRequest, body=None) -> Any:
                return await viewset_cls._dispatch_view(actions, {}, request, _body=body)
            endpoint.__annotations__ = {'request': FastAPIRequest, 'body': request_model, 'return': Any}
        else:
            async def endpoint(request: FastAPIRequest) -> Any:
                return await viewset_cls._dispatch_view(actions, {}, request)
        return endpoint

    def _get_dynamic_actions(self, viewset: type) -> list:
        actions = []
        for attr_name in dir(viewset):
            attr = getattr(viewset, attr_name, None)
            if callable(attr) and hasattr(attr, "detail") and hasattr(attr, "mapping"):
                actions.append(attr)
        return actions


class DefaultRouter(SimpleRouter):
    include_root_view: bool = True
    include_skill_route: bool = True
    include_manifest: bool = True

    def get_urls(self) -> APIRouter:
        router = super().get_urls()

        if self.include_root_view:
            async def api_root(request: Any = None) -> dict:
                ret = {}
                for prefix, viewset, basename in self.registry:
                    ret[prefix] = f"/{prefix}/"
                return ret

            router.add_api_route("/", api_root, methods=["GET"], name="api-root")

        if self.include_skill_route:
            self._register_skill_routes(router)

        if self.include_manifest:
            self._register_manifest_route(router)

        return router

    def _register_skill_routes(self, router: APIRouter) -> None:
        """Register SKILL.md endpoints for agent integration."""
        from fastrest.skills import SkillGenerator

        _self = self  # capture for closures

        async def skill_root(request: FastAPIRequest) -> Any:
            from fastapi.responses import PlainTextResponse, JSONResponse
            from fastrest.settings import get_settings
            settings = get_settings(request)
            if not settings.SKILL_ENABLED:
                return JSONResponse({"detail": "Not found."}, status_code=404)
            config = _self._skill_config(settings)
            gen = SkillGenerator(_self, config=config)
            return PlainTextResponse(gen.generate(), media_type="text/markdown")

        router.add_api_route(
            "/SKILL.md", skill_root, methods=["GET"],
            name="skill-root", include_in_schema=False,
        )

        # Per-resource SKILL.md routes — must be registered before {pk} detail routes
        # So we add them to the router at the beginning
        for prefix, viewset, basename in self.registry:
            _prefix = prefix

            async def skill_resource(request: FastAPIRequest, _pfx: str = _prefix) -> Any:
                from fastapi.responses import PlainTextResponse, JSONResponse
                from fastrest.settings import get_settings
                settings = get_settings(request)
                if not settings.SKILL_ENABLED:
                    return JSONResponse({"detail": "Not found."}, status_code=404)
                config = _self._skill_config(settings)
                gen = SkillGenerator(_self, config=config)
                content = gen.generate(resources=[_pfx])
                return PlainTextResponse(content, media_type="text/markdown")

            # Insert at position 0 so it takes priority over /{prefix}/{pk}
            from fastapi.routing import APIRoute
            route = APIRoute(
                f"/{prefix}/SKILL.md", skill_resource, methods=["GET"],
                name=f"skill-{basename}", include_in_schema=False,
            )
            router.routes.insert(0, route)

    def _register_manifest_route(self, router: APIRouter) -> None:
        """Register /manifest.json endpoint."""
        _self = self

        async def manifest_endpoint(request: FastAPIRequest) -> Any:
            from fastrest.settings import get_settings
            from fastrest.manifest import generate_manifest
            settings = get_settings(request)
            return generate_manifest(_self, settings=settings)

        router.add_api_route(
            "/manifest.json", manifest_endpoint, methods=["GET"],
            name="api-manifest", include_in_schema=False,
        )

    def _skill_config(self, settings) -> dict:
        return {
            "SKILL_NAME": settings.SKILL_NAME,
            "SKILL_BASE_URL": settings.SKILL_BASE_URL,
            "SKILL_DESCRIPTION": settings.SKILL_DESCRIPTION,
            "SKILL_AUTH_DESCRIPTION": settings.SKILL_AUTH_DESCRIPTION,
            "SKILL_INCLUDE_EXAMPLES": settings.SKILL_INCLUDE_EXAMPLES,
            "SKILL_MAX_EXAMPLES_PER_RESOURCE": settings.SKILL_MAX_EXAMPLES_PER_RESOURCE,
        }
