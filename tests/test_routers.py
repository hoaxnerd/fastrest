from fastrest.routers import SimpleRouter, DefaultRouter
from fastrest.viewsets import ModelViewSet, ReadOnlyModelViewSet
from fastrest.serializers import ModelSerializer
from fastrest.decorators import action
from fastrest.response import Response
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
