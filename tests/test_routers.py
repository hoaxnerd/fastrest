from fastapi import APIRouter
from fastrest.routers import SimpleRouter, DefaultRouter
from fastrest.viewsets import ModelViewSet, ReadOnlyModelViewSet
from fastrest.serializers import ModelSerializer
from fastrest.decorators import action
from fastrest.response import Response
from fastrest.pagination import PageNumberPagination
from tests.conftest import Item


class ItemSerializer(ModelSerializer):
    class Meta:
        model = Item
        fields = "__all__"


class ItemViewSet(ModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item

    @action(methods=["get"], detail=False, url_path="recent")
    async def recent(self, request, **kwargs):
        return Response(data=[])

    @action(methods=["post"], detail=True, url_path="archive")
    async def archive(self, request, **kwargs):
        return Response(data={"archived": True})


class TestSimpleRouter:
    def test_register(self):
        router = SimpleRouter()
        router.register("items", ItemViewSet)
        assert len(router.registry) == 1

    def test_urls_generated(self):
        router = SimpleRouter()
        router.register("items", ItemViewSet)
        api_router = router.urls
        routes = api_router.routes
        assert len(routes) > 0

    def test_route_names(self):
        router = SimpleRouter()
        router.register("items", ItemViewSet, basename="item")
        api_router = router.urls
        route_names = [r.name for r in api_router.routes]
        assert "item-list" in route_names
        assert "item-detail" in route_names

    def test_custom_action_routes(self):
        router = SimpleRouter()
        router.register("items", ItemViewSet, basename="item")
        api_router = router.urls
        route_names = [r.name for r in api_router.routes]
        assert "item-recent" in route_names
        assert "item-archive" in route_names


class TestDefaultRouter:
    def test_includes_root(self):
        router = DefaultRouter()
        router.register("items", ItemViewSet)
        api_router = router.urls
        route_names = [r.name for r in api_router.routes]
        assert "api-root" in route_names

    def test_basename_auto(self):
        router = DefaultRouter()
        router.register("items", ItemViewSet)
        assert router.registry[0][2] == "items"


class TestCustomAPIRouter:
    def test_custom_router_instance_used(self):
        """Custom APIRouter instance is used when passed."""
        custom = APIRouter(prefix="/api/v1")
        router = SimpleRouter(router=custom)
        router.register("items", ItemViewSet, basename="item")
        api_router = router.get_urls()
        assert api_router is custom

    def test_routes_registered_on_custom_router(self):
        """Routes are registered on the custom router, not a new one."""
        custom = APIRouter()
        router = SimpleRouter(router=custom)
        router.register("items", ItemViewSet, basename="item")
        api_router = router.get_urls()
        route_names = [r.name for r in api_router.routes]
        assert "item-list" in route_names
        assert "item-detail" in route_names

    def test_url_cache_returns_same_object(self):
        """router.urls returns the same object on repeated calls."""
        router = SimpleRouter()
        router.register("items", ItemViewSet, basename="item")
        first = router.urls
        second = router.urls
        assert first is second

    def test_backward_compatibility_no_router_param(self):
        """No router param still works (backward compatible)."""
        router = SimpleRouter()
        router.register("items", ItemViewSet, basename="item")
        api_router = router.urls
        assert isinstance(api_router, APIRouter)
        route_names = [r.name for r in api_router.routes]
        assert "item-list" in route_names

    def test_default_router_custom_router(self):
        """DefaultRouter also respects custom APIRouter."""
        custom = APIRouter()
        router = DefaultRouter(router=custom)
        router.register("items", ItemViewSet, basename="item")
        api_router = router.urls
        assert api_router is custom
        route_names = [r.name for r in api_router.routes]
        assert "api-root" in route_names

    def test_default_router_url_cache(self):
        """DefaultRouter.urls caching works."""
        router = DefaultRouter()
        router.register("items", ItemViewSet, basename="item")
        first = router.urls
        second = router.urls
        assert first is second


class TestTypedActionRoutes:
    """Verify that @action with serializer_class produces typed endpoints."""

    def test_action_with_response_serializer(self):
        """@action with response_serializer_class generates response_model."""

        class ArchiveSerializer(ModelSerializer):
            class Meta:
                model = Item
                fields = ["id", "name"]

        class TypedViewSet(ModelViewSet):
            serializer_class = ItemSerializer
            queryset = Item

            @action(methods=["get"], detail=False, url_path="recent",
                    response_serializer_class=ArchiveSerializer)
            async def recent(self, request, **kwargs):
                return Response(data=[])

        router = SimpleRouter()
        router.register("items", TypedViewSet, basename="item")
        api_router = router.urls
        routes = {r.name: r for r in api_router.routes}
        assert "item-recent" in routes

    def test_action_with_request_serializer(self):
        """@action with serializer_class generates request body schema."""

        class BulkSerializer(ModelSerializer):
            class Meta:
                model = Item
                fields = ["name", "price"]

        class TypedViewSet(ModelViewSet):
            serializer_class = ItemSerializer
            queryset = Item

            @action(methods=["post"], detail=False, url_path="bulk-create",
                    serializer_class=BulkSerializer)
            async def bulk_create(self, request, **kwargs):
                return Response(data=[])

        router = SimpleRouter()
        router.register("items", TypedViewSet, basename="item")
        api_router = router.urls
        route_names = [r.name for r in api_router.routes]
        assert "item-bulk-create" in route_names

    def test_action_without_serializers_still_works(self):
        """@action without serializer params works as before."""
        router = SimpleRouter()
        router.register("items", ItemViewSet, basename="item")
        api_router = router.urls
        route_names = [r.name for r in api_router.routes]
        assert "item-recent" in route_names
        assert "item-archive" in route_names

    def test_action_mcp_flag(self):
        """@action mcp and skill flags are set correctly."""

        class FlaggedViewSet(ModelViewSet):
            serializer_class = ItemSerializer
            queryset = Item

            @action(methods=["get"], detail=False, url_path="hidden", mcp=False, skill=False)
            async def hidden(self, request, **kwargs):
                return Response(data=[])

            @action(methods=["get"], detail=False, url_path="visible")
            async def visible(self, request, **kwargs):
                return Response(data=[])

        hidden = getattr(FlaggedViewSet, 'hidden')
        visible = getattr(FlaggedViewSet, 'visible')
        assert hidden.mcp is False
        assert hidden.skill is False
        assert visible.mcp is True
        assert visible.skill is True


class TestReadOnlyViewSetRoutes:
    def test_only_list_and_retrieve(self):
        class ROViewSet(ReadOnlyModelViewSet):
            serializer_class = ItemSerializer
            queryset = Item

        router = SimpleRouter()
        router.register("items", ROViewSet, basename="item")
        api_router = router.urls
        route_names = [r.name for r in api_router.routes]
        assert "item-list" in route_names
        assert "item-detail" in route_names


class TestPaginatedResponseSchema:
    """Verify that the list endpoint uses the correct response model based on pagination."""

    def test_paginated_viewset_uses_paginated_response_model(self):
        """A viewset with pagination_class should produce a paginated envelope response model."""
        class PaginatedItemViewSet(ModelViewSet):
            serializer_class = ItemSerializer
            queryset = Item
            pagination_class = PageNumberPagination

        endpoints = PaginatedItemViewSet.get_action_endpoints(
            actions={'get': 'list', 'post': 'create'},
            basename='items',
        )
        resp_model = endpoints['list']['response_model']
        # Should be a Pydantic model with count, next, previous, results fields
        field_names = set(resp_model.model_fields.keys())
        assert field_names == {'count', 'next', 'previous', 'results'}
        # Check field types
        assert resp_model.model_fields['count'].annotation is int
        assert resp_model.__name__ == 'ItemPaginatedResponse'

    def test_unpaginated_viewset_uses_list_response_model(self):
        """A viewset without pagination_class should produce list[Model] response."""
        endpoints = ItemViewSet.get_action_endpoints(
            actions={'get': 'list', 'post': 'create'},
            basename='items',
        )
        resp_model = endpoints['list']['response_model']
        # Should be list[...], not a paginated model
        assert hasattr(resp_model, '__origin__'), "Expected a generic list type"
        assert resp_model.__origin__ is list
