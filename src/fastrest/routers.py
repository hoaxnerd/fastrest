"""Router classes matching DRF's router API."""

from __future__ import annotations

from collections import namedtuple
from typing import Any

from fastapi import APIRouter, Request as FastAPIRequest


Route = namedtuple("Route", ["url", "mapping", "name", "detail", "initkwargs"])
DynamicRoute = namedtuple("DynamicRoute", ["url", "name", "detail", "initkwargs"])


class BaseRouter:
    def __init__(self):
        self.registry: list[tuple[str, type, str]] = []

    def register(self, prefix: str, viewset: type, basename: str | None = None) -> None:
        if basename is None:
            basename = prefix.strip("/").replace("/", "-")
        self.registry.append((prefix, viewset, basename))

    @property
    def urls(self) -> APIRouter:
        return self.get_urls()

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
        router = APIRouter()

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
        view = viewset.as_view(actions=mapping)
        name = f"{basename}-{action_func.url_name}"

        operation_id = f"{basename}_{action_name}"
        human_name = basename.replace('-', ' ').replace('_', ' ')
        summary = f"{action_name.replace('_', ' ').title()} {human_name}"

        router.add_api_route(
            url,
            view,
            methods=[m.upper() for m in methods_list],
            name=name,
            tags=tags,
            summary=summary,
            operation_id=operation_id,
            dependencies=dependencies or None,
        )

    def _get_dynamic_actions(self, viewset: type) -> list:
        actions = []
        for attr_name in dir(viewset):
            attr = getattr(viewset, attr_name, None)
            if callable(attr) and hasattr(attr, "detail") and hasattr(attr, "mapping"):
                actions.append(attr)
        return actions


class DefaultRouter(SimpleRouter):
    include_root_view: bool = True

    def get_urls(self) -> APIRouter:
        router = super().get_urls()

        if self.include_root_view:
            async def api_root(request: Any = None) -> dict:
                ret = {}
                for prefix, viewset, basename in self.registry:
                    ret[prefix] = f"/{prefix}/"
                return ret

            router.add_api_route("/", api_root, methods=["GET"], name="api-root")

        return router
