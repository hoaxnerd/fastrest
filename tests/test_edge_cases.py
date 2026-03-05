"""Comprehensive edge-case tests covering routing, OpenAPI, settings combos,
permissions+auth interactions, viewset inheritance, and more."""

import pytest
import pytest_asyncio
from fastapi import FastAPI, APIRouter, Request as FastAPIRequest, Depends
from httpx import AsyncClient, ASGITransport
from sqlalchemy import Column, Integer, String, Float, Boolean
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from fastrest.serializers import ModelSerializer
from fastrest.fields import CharField, IntegerField, FloatField, BooleanField
from fastrest.viewsets import ModelViewSet, ReadOnlyModelViewSet, GenericViewSet
from fastrest.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, ListAPIView
from fastrest.mixins import ListModelMixin, CreateModelMixin, RetrieveModelMixin, DestroyModelMixin
from fastrest.routers import SimpleRouter, DefaultRouter
from fastrest.decorators import action
from fastrest.response import Response
from fastrest.permissions import (
    AllowAny, IsAuthenticated, IsAdminUser, IsAuthenticatedOrReadOnly,
    BasePermission, HasScope,
)
from fastrest.authentication import TokenAuthentication, BasicAuthentication
from fastrest.throttling import SimpleRateThrottle
from fastrest.pagination import PageNumberPagination, LimitOffsetPagination
from fastrest.filters import SearchFilter, OrderingFilter
from fastrest.settings import configure, get_settings, APISettings, api_settings
from fastrest.test import APIClient
from fastrest.exceptions import ValidationError


# ────────────────────────────────────────────────────────────────
# Shared models / serializers
# ────────────────────────────────────────────────────────────────

class EBase(DeclarativeBase):
    pass


class Product(EBase):
    __tablename__ = "edge_products"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    price = Column(Float, nullable=False)
    in_stock = Column(Boolean, default=True)


class Category(EBase):
    __tablename__ = "edge_categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(100), nullable=False)


class ProductSerializer(ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "price", "in_stock"]
        read_only_fields = ["id"]


class CategorySerializer(ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "label"]
        read_only_fields = ["id"]


# ────────────────────────────────────────────────────────────────
# 1. ROUTING EDGE CASES
# ────────────────────────────────────────────────────────────────

class TestNestedRouterInclusion:
    """Test including one FastREST router inside another via FastAPI's include_router."""

    def test_two_routers_nested_under_different_prefixes(self):
        """Two SimpleRouters included under /v1 and /v2 prefixes produce distinct routes."""
        class V1ViewSet(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        class V2ViewSet(ReadOnlyModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        r1 = SimpleRouter()
        r1.register("products", V1ViewSet, basename="v1-product")

        r2 = SimpleRouter()
        r2.register("products", V2ViewSet, basename="v2-product")

        app = FastAPI()
        app.include_router(r1.urls, prefix="/v1")
        app.include_router(r2.urls, prefix="/v2")

        schema = app.openapi()
        paths = list(schema["paths"].keys())
        # v1 should have full CRUD
        assert "/v1/products" in paths
        assert "/v1/products/{pk}" in paths
        # v2 should only have GET
        v2_list_methods = set(schema["paths"]["/v2/products"].keys())
        assert "get" in v2_list_methods
        assert "post" not in v2_list_methods

    def test_default_router_nested_under_prefix(self):
        """DefaultRouter inside a prefix — api root, SKILL.md, manifest all accessible."""
        class ProdViewSet(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        router = DefaultRouter()
        router.register("products", ProdViewSet, basename="product")

        app = FastAPI()
        app.include_router(router.urls, prefix="/api/v1")

        schema = app.openapi()
        paths = list(schema["paths"].keys())
        assert "/api/v1/products" in paths
        assert "/api/v1/products/{pk}" in paths
        # api-root is registered at "/" of the router, so it's /api/v1/
        assert "/api/v1/" in paths

    def test_two_default_routers_same_app(self):
        """Two DefaultRouters don't conflict."""
        class ViewSetA(ReadOnlyModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        class ViewSetB(ReadOnlyModelViewSet):
            serializer_class = CategorySerializer
            queryset = Category

        r1 = DefaultRouter()
        r1.register("products", ViewSetA, basename="product")

        r2 = DefaultRouter()
        r2.register("categories", ViewSetB, basename="category")

        app = FastAPI()
        app.include_router(r1.urls, prefix="/shop")
        app.include_router(r2.urls, prefix="/catalog")

        schema = app.openapi()
        paths = list(schema["paths"].keys())
        assert "/shop/products" in paths
        assert "/catalog/categories" in paths


class TestCustomAPIRouterParams:
    """Test that custom APIRouter kwargs (tags, redirect_slashes, etc.) propagate."""

    def test_custom_router_tags(self):
        """Tags set on the custom APIRouter should propagate to routes."""
        custom = APIRouter(tags=["custom-tag"])
        router = SimpleRouter(router=custom)
        router.register("products", ModelViewSet, basename="product")

        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        r = SimpleRouter(router=APIRouter(tags=["shop"]))
        r.register("products", VS, basename="product")
        api = r.urls

        # The underlying APIRouter has the custom tags
        assert api.tags == ["shop"]

    def test_redirect_slashes_false(self):
        """Custom APIRouter with redirect_slashes=False."""
        custom = APIRouter(redirect_slashes=False)
        router = SimpleRouter(router=custom)

        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        router.register("products", VS, basename="product")
        api = router.urls
        assert api.redirect_slashes is False

    def test_custom_router_with_dependencies(self):
        """Custom APIRouter with global dependencies should keep them."""
        called = []

        async def track_dep():
            called.append(True)

        custom = APIRouter(dependencies=[Depends(track_dep)])
        router = SimpleRouter(router=custom)

        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        router.register("products", VS, basename="product")
        api = router.urls
        # Dependencies list should include our dep
        assert len(api.dependencies) == 1

    def test_custom_router_prefix(self):
        """Custom APIRouter with prefix set — routes should be nested."""
        custom = APIRouter(prefix="/api")
        router = SimpleRouter(router=custom)

        class VS(ReadOnlyModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        router.register("products", VS, basename="product")
        api = router.urls

        app = FastAPI()
        app.include_router(api)

        schema = app.openapi()
        paths = list(schema["paths"].keys())
        assert "/api/products" in paths
        assert "/api/products/{pk}" in paths


class TestOpenAPISchemaCompleteness:
    """Verify OpenAPI schema reflects the full feature set."""

    def _schema(self, viewset_cls, prefix="items", basename="item"):
        app = FastAPI()
        router = DefaultRouter()
        router.register(prefix, viewset_cls, basename=basename)
        app.include_router(router.urls)
        return app.openapi()

    def test_crud_methods_present(self):
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        schema = self._schema(VS, "products", "product")
        list_path = schema["paths"]["/products"]
        detail_path = schema["paths"]["/products/{pk}"]

        assert "get" in list_path  # list
        assert "post" in list_path  # create
        assert "get" in detail_path  # retrieve
        assert "put" in detail_path  # update
        assert "patch" in detail_path  # partial_update
        assert "delete" in detail_path  # destroy

    def test_readonly_no_write_methods(self):
        class VS(ReadOnlyModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        schema = self._schema(VS, "products", "product")
        list_path = schema["paths"]["/products"]
        detail_path = schema["paths"]["/products/{pk}"]

        assert "get" in list_path
        assert "post" not in list_path
        assert "get" in detail_path
        assert "put" not in detail_path
        assert "delete" not in detail_path

    def test_status_codes_correct(self):
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        schema = self._schema(VS, "products", "product")
        list_ops = schema["paths"]["/products"]
        detail_ops = schema["paths"]["/products/{pk}"]

        # Create should return 201
        assert "201" in list_ops["post"]["responses"]
        # Delete should return 204
        assert "204" in detail_ops["delete"]["responses"]
        # List returns 200
        assert "200" in list_ops["get"]["responses"]

    def test_pagination_query_params_in_openapi(self):
        class Pag(PageNumberPagination):
            page_size = 10

        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product
            pagination_class = Pag

        schema = self._schema(VS, "products", "product")
        list_op = schema["paths"]["/products"]["get"]
        param_names = [p["name"] for p in list_op.get("parameters", [])]
        assert "page" in param_names
        assert "page_size" in param_names

    def test_limit_offset_params_in_openapi(self):
        class LO(LimitOffsetPagination):
            default_limit = 20

        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product
            pagination_class = LO

        schema = self._schema(VS, "products", "product")
        list_op = schema["paths"]["/products"]["get"]
        param_names = [p["name"] for p in list_op.get("parameters", [])]
        assert "limit" in param_names
        assert "offset" in param_names

    def test_search_ordering_params_in_openapi(self):
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product
            filter_backends = [SearchFilter, OrderingFilter]
            search_fields = ["name"]
            ordering_fields = ["price"]

        schema = self._schema(VS, "products", "product")
        list_op = schema["paths"]["/products"]["get"]
        param_names = [p["name"] for p in list_op.get("parameters", [])]
        assert "search" in param_names
        assert "ordering" in param_names

    def test_pagination_plus_filters_combined(self):
        """All query params appear when pagination AND filters are both set."""
        class Pag(PageNumberPagination):
            page_size = 5

        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product
            pagination_class = Pag
            filter_backends = [SearchFilter, OrderingFilter]
            search_fields = ["name"]
            ordering_fields = ["price"]

        schema = self._schema(VS, "products", "product")
        list_op = schema["paths"]["/products"]["get"]
        param_names = [p["name"] for p in list_op.get("parameters", [])]
        assert "page" in param_names
        assert "page_size" in param_names
        assert "search" in param_names
        assert "ordering" in param_names

    def test_paginated_response_schema(self):
        class Pag(PageNumberPagination):
            page_size = 5

        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product
            pagination_class = Pag

        schema = self._schema(VS, "products", "product")
        list_resp = schema["paths"]["/products"]["get"]["responses"]["200"]
        # Should reference a paginated model with count/next/previous/results
        resp_schema = list_resp["content"]["application/json"]["schema"]
        # Could be a $ref; resolve it
        if "$ref" in resp_schema:
            ref_name = resp_schema["$ref"].split("/")[-1]
            model_schema = schema["components"]["schemas"][ref_name]
        else:
            model_schema = resp_schema
        assert "count" in model_schema["properties"]
        assert "results" in model_schema["properties"]

    def test_custom_action_appears_in_openapi(self):
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

            @action(methods=["get"], detail=False, url_path="featured")
            async def featured(self, request, **kwargs):
                return Response(data=[])

            @action(methods=["post"], detail=True, url_path="archive")
            async def archive(self, request, **kwargs):
                return Response(data={"ok": True})

        schema = self._schema(VS, "products", "product")
        paths = list(schema["paths"].keys())
        assert "/products/featured" in paths
        assert "/products/{pk}/archive" in paths

    def test_action_with_typed_serializers_in_openapi(self):
        class DiscountSerializer(ModelSerializer):
            class Meta:
                model = Product
                fields = ["price"]

        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

            @action(methods=["post"], detail=True, url_path="apply-discount",
                    serializer_class=DiscountSerializer,
                    response_serializer_class=ProductSerializer)
            async def apply_discount(self, request, **kwargs):
                return Response(data={})

        schema = self._schema(VS, "products", "product")
        op = schema["paths"]["/products/{pk}/apply-discount"]["post"]
        # Should have a request body
        assert "requestBody" in op
        # Should have a response model
        assert "200" in op["responses"]

    def test_multiple_viewsets_unique_operation_ids(self):
        class VS1(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        class VS2(ReadOnlyModelViewSet):
            serializer_class = CategorySerializer
            queryset = Category

        app = FastAPI()
        router = DefaultRouter()
        router.register("products", VS1, basename="product")
        router.register("categories", VS2, basename="category")
        app.include_router(router.urls)
        schema = app.openapi()

        # Collect all operation IDs
        op_ids = []
        for path_ops in schema["paths"].values():
            for method, op in path_ops.items():
                if isinstance(op, dict) and "operationId" in op:
                    op_ids.append(op["operationId"])

        # All unique
        assert len(op_ids) == len(set(op_ids)), f"Duplicate operation IDs: {op_ids}"

    def test_skill_and_manifest_excluded_from_schema(self):
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        schema = self._schema(VS, "products", "product")
        paths = list(schema["paths"].keys())
        assert "/SKILL.md" not in paths
        assert "/manifest.json" not in paths
        skill_paths = [p for p in paths if "SKILL" in p]
        assert skill_paths == []


class TestRouterEdgeCases:
    def test_register_multiple_viewsets(self):
        router = DefaultRouter()

        class VS1(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        class VS2(ReadOnlyModelViewSet):
            serializer_class = CategorySerializer
            queryset = Category

        router.register("products", VS1)
        router.register("categories", VS2)
        api = router.urls

        route_names = [r.name for r in api.routes if hasattr(r, 'name')]
        assert "products-list" in route_names
        assert "categories-list" in route_names
        assert "api-root" in route_names

    def test_basename_auto_generated_from_prefix(self):
        router = SimpleRouter()

        class VS(ReadOnlyModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        router.register("my-products", VS)
        assert router.registry[0][2] == "my-products"

    def test_basename_auto_from_nested_prefix(self):
        router = SimpleRouter()

        class VS(ReadOnlyModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        router.register("shop/products", VS)
        assert router.registry[0][2] == "shop-products"

    def test_empty_router_no_crash(self):
        router = DefaultRouter()
        api = router.urls
        route_names = [r.name for r in api.routes if hasattr(r, 'name')]
        assert "api-root" in route_names

    def test_url_cache_invalidation_not_needed(self):
        """Once urls is built, new registrations don't affect the cached router."""
        router = SimpleRouter()

        class VS(ReadOnlyModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        router.register("products", VS)
        api1 = router.urls
        route_count_1 = len(api1.routes)

        # Register more after cache built
        router.register("more", VS)
        api2 = router.urls  # should return cached
        assert api1 is api2
        assert len(api2.routes) == route_count_1


# ────────────────────────────────────────────────────────────────
# 2. PERMISSIONS + AUTH + SETTINGS COMBOS
# ────────────────────────────────────────────────────────────────

TOKENS = {
    "admin-tok": type("User", (), {"id": 1, "username": "admin", "is_staff": True, "__bool__": lambda s: True})(),
    "user-tok": type("User", (), {"id": 2, "username": "user", "is_staff": False, "__bool__": lambda s: True})(),
}

token_auth = TokenAuthentication(get_user_by_token=lambda k: TOKENS.get(k))


class AuthProductViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product
    authentication_classes = [token_auth]
    permission_classes = [IsAuthenticated]


class AdminOnlyViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product
    authentication_classes = [token_auth]
    permission_classes = [IsAuthenticated() & IsAdminUser()]


class ReadOnlyUnlessAuthViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product
    authentication_classes = [token_auth]
    permission_classes = [IsAuthenticatedOrReadOnly]


async def _make_app_client(*viewset_registrations):
    """Helper: build app with given viewsets, seed one product, return client."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(EBase.metadata.create_all)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    router = DefaultRouter()
    for prefix, vs, basename in viewset_registrations:
        router.register(prefix, vs, basename=basename)
    app.include_router(router.urls)

    viewset_classes = [vs for _, vs, _ in viewset_registrations]

    @app.middleware("http")
    async def inject(request: FastAPIRequest, call_next):
        async with sf() as session:
            async with session.begin():
                originals = {}
                for vs_cls in viewset_classes:
                    originals[vs_cls] = vs_cls.__init__
                    def make_p(orig):
                        def p(self, **kw): orig(self, **kw); self._session = session
                        return p
                    vs_cls.__init__ = make_p(originals[vs_cls])
                try:
                    resp = await call_next(request)
                finally:
                    for vs_cls in viewset_classes:
                        vs_cls.__init__ = originals[vs_cls]
                return resp

    client = APIClient(app)
    return client, engine


class TestAuthPermissionCombos:
    async def test_unauthed_gets_401(self):
        client, engine = await _make_app_client(("products", AuthProductViewSet, "product"))
        try:
            resp = await client.get("/products")
            assert resp.status_code == 401
        finally:
            await engine.dispose()

    async def test_authed_user_can_list(self):
        client, engine = await _make_app_client(("products", AuthProductViewSet, "product"))
        try:
            resp = await client.get("/products", headers={"Authorization": "Token user-tok"})
            assert resp.status_code == 200
        finally:
            await engine.dispose()

    async def test_admin_only_rejects_normal_user(self):
        client, engine = await _make_app_client(("products", AdminOnlyViewSet, "product"))
        try:
            resp = await client.get("/products", headers={"Authorization": "Token user-tok"})
            assert resp.status_code == 403
        finally:
            await engine.dispose()

    async def test_admin_only_allows_admin(self):
        client, engine = await _make_app_client(("products", AdminOnlyViewSet, "product"))
        try:
            resp = await client.get("/products", headers={"Authorization": "Token admin-tok"})
            assert resp.status_code == 200
        finally:
            await engine.dispose()

    async def test_read_only_unless_auth_allows_get(self):
        client, engine = await _make_app_client(("products", ReadOnlyUnlessAuthViewSet, "product"))
        try:
            resp = await client.get("/products")
            assert resp.status_code == 200
        finally:
            await engine.dispose()

    async def test_read_only_unless_auth_blocks_post(self):
        client, engine = await _make_app_client(("products", ReadOnlyUnlessAuthViewSet, "product"))
        try:
            resp = await client.post("/products", json={"name": "X", "price": 1.0})
            # No auth → 401 (because we have auth backends that return authenticate_header)
            assert resp.status_code == 401
        finally:
            await engine.dispose()

    async def test_read_only_unless_auth_allows_post_with_token(self):
        client, engine = await _make_app_client(("products", ReadOnlyUnlessAuthViewSet, "product"))
        try:
            resp = await client.post(
                "/products",
                json={"name": "Widget", "price": 5.0},
                headers={"Authorization": "Token user-tok"},
            )
            assert resp.status_code == 201
        finally:
            await engine.dispose()


# ────────────────────────────────────────────────────────────────
# 3. APP CONFIGURATION + SETTINGS RESOLUTION
# ────────────────────────────────────────────────────────────────

class TestSettingsResolution:
    def test_viewset_attr_wins_over_app_config(self):
        """Viewset-level permission_classes overrides app-level DEFAULT_PERMISSION_CLASSES."""
        app = FastAPI()
        configure(app, {"DEFAULT_PERMISSION_CLASSES": ["fastrest.permissions.IsAuthenticated"]})

        class PublicViewSet(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product
            permission_classes = [AllowAny]  # Explicitly public

        router = DefaultRouter()
        router.register("products", PublicViewSet, basename="product")
        app.include_router(router.urls)

        schema = app.openapi()
        # If the viewset-level AllowAny works, the routes exist (no auth barrier)
        assert "/products" in schema["paths"]

    def test_two_apps_different_settings(self):
        """Two FastAPI apps with different configure() calls are independent."""
        app1 = FastAPI()
        configure(app1, {"PAGE_SIZE": 10, "SKILL_NAME": "app1"})

        app2 = FastAPI()
        configure(app2, {"PAGE_SIZE": 50, "SKILL_NAME": "app2"})

        s1 = get_settings(app1)
        s2 = get_settings(app2)

        assert s1.PAGE_SIZE == 10
        assert s2.PAGE_SIZE == 50
        assert s1.SKILL_NAME == "app1"
        assert s2.SKILL_NAME == "app2"

    def test_unconfigured_app_uses_global_defaults(self):
        app = FastAPI()
        s = get_settings(app)
        assert s is api_settings
        assert s.PAGE_SIZE is None

    def test_strict_settings_catches_typo(self):
        app = FastAPI()
        with pytest.raises(ValueError, match="Unknown"):
            configure(app, {"PAFE_SIZE": 10})  # typo

    def test_non_strict_allows_unknown_keys(self):
        app = FastAPI()
        configure(app, {"CUSTOM_KEY": "value", "STRICT_SETTINGS": False})
        s = get_settings(app)
        assert s.CUSTOM_KEY == "value"

    def test_settings_from_request_like_object(self):
        app = FastAPI()
        configure(app, {"PAGE_SIZE": 42})

        class FakeReq:
            pass
        req = FakeReq()
        req.app = app

        s = get_settings(req)
        assert s.PAGE_SIZE == 42

    def test_settings_reload(self):
        s = APISettings(user_settings={"PAGE_SIZE": 10})
        assert s.PAGE_SIZE == 10
        s.reload(user_settings={"PAGE_SIZE": 99})
        assert s.PAGE_SIZE == 99

    def test_import_strings_resolved(self):
        s = APISettings()
        perms = s.DEFAULT_PERMISSION_CLASSES
        assert perms[0] is AllowAny


# ────────────────────────────────────────────────────────────────
# 4. VIEWSET INHERITANCE AND CUSTOM MIXINS
# ────────────────────────────────────────────────────────────────

class TestViewSetInheritance:
    def test_custom_mixin_viewset(self):
        """A viewset with only List + Create (no detail routes)."""
        class ListCreateViewSet(CreateModelMixin, ListModelMixin, GenericViewSet):
            pass

        class VS(ListCreateViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        app = FastAPI()
        router = SimpleRouter()
        router.register("products", VS, basename="product")
        app.include_router(router.urls)

        schema = app.openapi()
        paths = list(schema["paths"].keys())
        assert "/products" in paths
        # Should NOT have detail routes
        assert "/products/{pk}" not in paths
        # Should have GET and POST only on list
        methods = set(schema["paths"]["/products"].keys())
        assert "get" in methods
        assert "post" in methods

    def test_list_destroy_only(self):
        """Custom viewset with only list + destroy."""
        class ListDestroyViewSet(ListModelMixin, DestroyModelMixin, RetrieveModelMixin, GenericViewSet):
            pass

        class VS(ListDestroyViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        app = FastAPI()
        router = SimpleRouter()
        router.register("products", VS, basename="product")
        app.include_router(router.urls)

        schema = app.openapi()
        list_methods = set(schema["paths"]["/products"].keys())
        assert "get" in list_methods
        assert "post" not in list_methods

        detail_methods = set(schema["paths"]["/products/{pk}"].keys())
        assert "get" in detail_methods
        assert "delete" in detail_methods
        assert "put" not in detail_methods

    def test_override_get_serializer_class(self):
        """ViewSet that returns different serializer per action."""
        class MinimalSerializer(ModelSerializer):
            class Meta:
                model = Product
                fields = ["id", "name"]

        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

            def get_serializer_class(self):
                if self.action == "list":
                    return MinimalSerializer
                return ProductSerializer

        # Should still register routes without error
        app = FastAPI()
        router = SimpleRouter()
        router.register("products", VS, basename="product")
        app.include_router(router.urls)
        schema = app.openapi()
        assert "/products" in schema["paths"]


# ────────────────────────────────────────────────────────────────
# 5. ACTION DECORATOR EDGE CASES
# ────────────────────────────────────────────────────────────────

class TestActionEdgeCases:
    def test_multi_method_action(self):
        """@action with multiple methods."""
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

            @action(methods=["get", "post"], detail=False, url_path="bulk")
            async def bulk(self, request, **kwargs):
                return Response(data=[])

        app = FastAPI()
        router = SimpleRouter()
        router.register("products", VS, basename="product")
        app.include_router(router.urls)

        schema = app.openapi()
        assert "/products/bulk" in schema["paths"]

    def test_detail_and_list_actions_coexist(self):
        """Both detail and non-detail custom actions."""
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

            @action(methods=["get"], detail=False, url_path="stats")
            async def stats(self, request, **kwargs):
                return Response(data={"count": 0})

            @action(methods=["post"], detail=True, url_path="clone")
            async def clone(self, request, **kwargs):
                return Response(data={"cloned": True})

        app = FastAPI()
        router = SimpleRouter()
        router.register("products", VS, basename="product")
        app.include_router(router.urls)

        schema = app.openapi()
        paths = list(schema["paths"].keys())
        assert "/products/stats" in paths
        assert "/products/{pk}/clone" in paths

    def test_action_custom_url_path_and_name(self):
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

            @action(methods=["get"], detail=False,
                    url_path="special-items", url_name="special")
            async def special_items(self, request, **kwargs):
                return Response(data=[])

        router = SimpleRouter()
        router.register("products", VS, basename="product")
        api = router.urls
        route_names = [r.name for r in api.routes if hasattr(r, 'name')]
        assert "product-special" in route_names

    def test_action_mcp_false_skill_false(self):
        """Actions with mcp=False and skill=False don't appear in MCP/SKILL."""
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

            @action(methods=["get"], detail=False, mcp=False, skill=False)
            async def internal(self, request, **kwargs):
                return Response(data=[])

        from fastrest.skills import SkillGenerator
        from fastrest.mcp import MCPBridge

        router = DefaultRouter()
        router.register("products", VS, basename="product")

        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "internal" not in doc

        bridge = MCPBridge(router)
        mcp = bridge.build_mcp()
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "product_internal" not in tool_names

        # But it SHOULD appear in OpenAPI
        app = FastAPI()
        app.include_router(router.urls)
        schema = app.openapi()
        assert "/products/internal" in schema["paths"]


# ────────────────────────────────────────────────────────────────
# 6. SERIALIZER EDGE CASES IN OPENAPI
# ────────────────────────────────────────────────────────────────

class TestSerializerOpenAPIEdgeCases:
    def test_write_only_field_not_in_response(self):
        class S(ModelSerializer):
            password = CharField(write_only=True)

            class Meta:
                model = Product
                fields = ["id", "name", "password"]

        from fastrest.openapi import serializer_to_response_model
        model = serializer_to_response_model(S, "TestResp")
        field_names = set(model.model_fields.keys())
        assert "password" not in field_names
        assert "name" in field_names

    def test_read_only_field_not_in_request(self):
        from fastrest.openapi import serializer_to_request_model
        model = serializer_to_request_model(ProductSerializer, "TestReq")
        field_names = set(model.model_fields.keys())
        assert "id" not in field_names
        assert "name" in field_names

    def test_partial_request_all_optional(self):
        from fastrest.openapi import serializer_to_request_model
        model = serializer_to_request_model(ProductSerializer, "TestPatch", partial=True)
        for field_info in model.model_fields.values():
            # All fields should have a default (be optional)
            assert field_info.default is None

    def test_nullable_field_in_response(self):
        from typing import get_args, get_origin, Union
        import types

        class S(ModelSerializer):
            notes = CharField(allow_null=True, required=False)

            class Meta:
                model = Product
                fields = ["id", "notes"]

        from fastrest.openapi import serializer_to_response_model
        model = serializer_to_response_model(S, "NullableResp")
        ann = model.model_fields["notes"].annotation
        # Should be Optional[str] — i.e. str | None
        origin = get_origin(ann)
        assert origin is Union or origin is types.UnionType


# ────────────────────────────────────────────────────────────────
# 7. INTEGRATION: FULL STACK WITH MULTIPLE FEATURES
# ────────────────────────────────────────────────────────────────

class SmallPage(PageNumberPagination):
    page_size = 2
    max_page_size = 5


class FullFeatureViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product
    pagination_class = SmallPage
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "price"]
    ordering = ["name"]
    authentication_classes = [token_auth]
    permission_classes = [IsAuthenticatedOrReadOnly]

    @action(methods=["get"], detail=False, url_path="cheap")
    async def cheap(self, request, **kwargs):
        """Get cheap products."""
        return Response(data=[])

    @action(methods=["post"], detail=True, url_path="discount")
    async def discount(self, request, **kwargs):
        """Apply discount."""
        return Response(data={"discounted": True})


class TestFullStackIntegration:
    @pytest_asyncio.fixture
    async def full_client(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(EBase.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        app = FastAPI()
        configure(app, {
            "SKILL_NAME": "test-api",
            "SKILL_BASE_URL": "http://localhost",
        })
        router = DefaultRouter()
        router.register("products", FullFeatureViewSet, basename="product")
        app.include_router(router.urls)

        @app.middleware("http")
        async def inject(request: FastAPIRequest, call_next):
            async with sf() as session:
                async with session.begin():
                    orig = FullFeatureViewSet.__init__
                    def p(self, **kw): orig(self, **kw); self._session = session
                    FullFeatureViewSet.__init__ = p
                    try:
                        resp = await call_next(request)
                    finally:
                        FullFeatureViewSet.__init__ = orig
                    return resp

        client = APIClient(app)
        # Seed data
        headers = {"Authorization": "Token user-tok"}
        for name, price in [("Alpha", 10), ("Beta", 20), ("Gamma", 5), ("Delta", 15), ("Epsilon", 3)]:
            await client.post("/products", json={"name": name, "price": price}, headers=headers)
        yield client
        await engine.dispose()

    async def test_list_paginated(self, full_client):
        resp = await full_client.get("/products")
        data = resp.json()
        assert data["count"] == 5
        assert len(data["results"]) == 2  # page_size=2

    async def test_search_with_pagination(self, full_client):
        resp = await full_client.get("/products?search=Alpha")
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["name"] == "Alpha"

    async def test_ordering(self, full_client):
        resp = await full_client.get("/products?ordering=price&page_size=5")
        data = resp.json()
        prices = [r["price"] for r in data["results"]]
        assert prices == sorted(prices)

    async def test_ordering_descending(self, full_client):
        resp = await full_client.get("/products?ordering=-price&page_size=5")
        data = resp.json()
        prices = [r["price"] for r in data["results"]]
        assert prices == sorted(prices, reverse=True)

    async def test_unauthed_can_list(self, full_client):
        resp = await full_client.get("/products")
        assert resp.status_code == 200

    async def test_unauthed_cannot_create(self, full_client):
        resp = await full_client.post("/products", json={"name": "X", "price": 1})
        assert resp.status_code == 401

    async def test_authed_can_create(self, full_client):
        resp = await full_client.post(
            "/products", json={"name": "New", "price": 99},
            headers={"Authorization": "Token user-tok"},
        )
        assert resp.status_code == 201

    async def test_custom_action_list(self, full_client):
        resp = await full_client.get("/products/cheap")
        assert resp.status_code == 200

    async def test_custom_action_detail_needs_auth(self, full_client):
        resp = await full_client.post("/products/1/discount")
        assert resp.status_code == 401

    async def test_skill_md_reflects_config(self, full_client):
        resp = await full_client.get("/SKILL.md")
        assert resp.status_code == 200
        assert "name: test-api" in resp.text
        assert "Products" in resp.text
        assert "search" in resp.text

    async def test_manifest_reflects_config(self, full_client):
        resp = await full_client.get("/manifest.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-api"
        assert data["resources"][0]["pagination"]["page_size"] == 2

    async def test_openapi_has_everything(self, full_client):
        schema = full_client.app.openapi()
        list_op = schema["paths"]["/products"]["get"]
        param_names = [p["name"] for p in list_op.get("parameters", [])]
        assert "page" in param_names
        assert "search" in param_names
        assert "ordering" in param_names


# ────────────────────────────────────────────────────────────────
# 8. HAS_SCOPE + AUTH INTEGRATION
# ────────────────────────────────────────────────────────────────

class ScopedToken:
    """Token with scopes."""
    def __init__(self, scopes):
        self.scopes = scopes


SCOPED_TOKENS = {
    "reader": (
        type("U", (), {"id": 1, "username": "reader", "__bool__": lambda s: True})(),
        ScopedToken(["products:read"]),
    ),
    "writer": (
        type("U", (), {"id": 2, "username": "writer", "__bool__": lambda s: True})(),
        ScopedToken(["products:read", "products:write"]),
    ),
}


class ScopedTokenAuth(TokenAuthentication):
    def __init__(self):
        super().__init__(get_user_by_token=self._lookup)

    def _lookup(self, key):
        entry = SCOPED_TOKENS.get(key)
        return entry[0] if entry else None

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token_key = result
        entry = SCOPED_TOKENS.get(token_key)
        if entry:
            return (user, entry[1])
        return result


scoped_auth = ScopedTokenAuth()


class ScopedViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product
    authentication_classes = [scoped_auth]
    permission_classes = [IsAuthenticated() & HasScope("products:read")]


class WriteScopedViewSet(ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product
    authentication_classes = [scoped_auth]

    # Read needs read scope, write needs write scope
    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), HasScope("products:write")]
        return [IsAuthenticated(), HasScope("products:read")]


class TestScopedPermissions:
    async def test_reader_can_list(self):
        client, engine = await _make_app_client(("products", ScopedViewSet, "product"))
        try:
            resp = await client.get("/products", headers={"Authorization": "Token reader"})
            assert resp.status_code == 200
        finally:
            await engine.dispose()

    async def test_no_token_gets_401(self):
        client, engine = await _make_app_client(("products", ScopedViewSet, "product"))
        try:
            resp = await client.get("/products")
            assert resp.status_code == 401
        finally:
            await engine.dispose()

    async def test_write_scoped_reader_cannot_create(self):
        client, engine = await _make_app_client(("products", WriteScopedViewSet, "product"))
        try:
            resp = await client.post(
                "/products", json={"name": "X", "price": 1},
                headers={"Authorization": "Token reader"},
            )
            assert resp.status_code == 403
        finally:
            await engine.dispose()

    async def test_write_scoped_writer_can_create(self):
        client, engine = await _make_app_client(("products", WriteScopedViewSet, "product"))
        try:
            resp = await client.post(
                "/products", json={"name": "X", "price": 1},
                headers={"Authorization": "Token writer"},
            )
            assert resp.status_code == 201
        finally:
            await engine.dispose()

    async def test_write_scoped_reader_can_list(self):
        client, engine = await _make_app_client(("products", WriteScopedViewSet, "product"))
        try:
            resp = await client.get("/products", headers={"Authorization": "Token reader"})
            assert resp.status_code == 200
        finally:
            await engine.dispose()


# ────────────────────────────────────────────────────────────────
# 9. VALIDATION EDGE CASES THROUGH HTTP
# ────────────────────────────────────────────────────────────────

class StrictProductSerializer(ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "price", "in_stock"]
        read_only_fields = ["id"]

    def validate_price(self, value):
        """Price must be positive."""
        if value is not None and value <= 0:
            raise ValidationError("Price must be positive.")
        return value

    def validate(self, attrs):
        if attrs.get("name", "").lower() == "banned":
            raise ValidationError("This product name is banned.")
        return attrs


class StrictViewSet(ModelViewSet):
    serializer_class = StrictProductSerializer
    queryset = Product


class TestValidationThroughHTTP:
    @pytest_asyncio.fixture
    async def strict_client(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(EBase.metadata.create_all)
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        app = FastAPI()
        router = SimpleRouter()
        router.register("products", StrictViewSet, basename="product")
        app.include_router(router.urls)

        @app.middleware("http")
        async def inject(request: FastAPIRequest, call_next):
            async with sf() as session:
                async with session.begin():
                    orig = StrictViewSet.__init__
                    def p(self, **kw): orig(self, **kw); self._session = session
                    StrictViewSet.__init__ = p
                    try:
                        resp = await call_next(request)
                    finally:
                        StrictViewSet.__init__ = orig
                    return resp

        yield APIClient(app)
        await engine.dispose()

    async def test_valid_create(self, strict_client):
        resp = await strict_client.post("/products", json={"name": "Good", "price": 10.0})
        assert resp.status_code == 201

    async def test_negative_price_rejected(self, strict_client):
        resp = await strict_client.post("/products", json={"name": "Bad", "price": -5.0})
        assert resp.status_code == 400

    async def test_banned_name_rejected(self, strict_client):
        resp = await strict_client.post("/products", json={"name": "banned", "price": 10.0})
        assert resp.status_code == 400

    async def test_missing_required_field(self, strict_client):
        # Missing 'name' and 'price' — Pydantic validates at the FastAPI level
        resp = await strict_client.post("/products", json={})
        assert resp.status_code == 422

    async def test_partial_update_validates(self, strict_client):
        create = await strict_client.post("/products", json={"name": "Widget", "price": 5.0})
        pk = create.json()["id"]
        resp = await strict_client.patch(f"/products/{pk}", json={"price": -1.0})
        assert resp.status_code == 400


# ────────────────────────────────────────────────────────────────
# 10. SKILL.MD AND MANIFEST UNDER NESTED PREFIXES
# ────────────────────────────────────────────────────────────────

class TestAgentEndpointsNested:
    async def test_skill_under_api_prefix(self):
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        app = FastAPI()
        router = DefaultRouter()
        router.register("products", VS)
        app.include_router(router.urls, prefix="/api/v2")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v2/SKILL.md")
            assert resp.status_code == 200
            assert "Products" in resp.text

    async def test_manifest_under_api_prefix(self):
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        app = FastAPI()
        router = DefaultRouter()
        router.register("products", VS)
        app.include_router(router.urls, prefix="/api/v2")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v2/manifest.json")
            assert resp.status_code == 200
            assert resp.json()["version"] == "1.0"

    async def test_per_resource_skill_under_prefix(self):
        class VS(ModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        app = FastAPI()
        router = DefaultRouter()
        router.register("products", VS)
        app.include_router(router.urls, prefix="/api")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/products/SKILL.md")
            assert resp.status_code == 200
            assert "Products" in resp.text

    async def test_skill_disabled_via_include_skill_route(self):
        """Router with include_skill_route=False should not serve SKILL.md."""
        class VS(ReadOnlyModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        router = DefaultRouter()
        router.include_skill_route = False
        router.register("products", VS)

        app = FastAPI()
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/SKILL.md")
            assert resp.status_code == 404 or resp.status_code == 405

    async def test_manifest_disabled_via_include_manifest(self):
        class VS(ReadOnlyModelViewSet):
            serializer_class = ProductSerializer
            queryset = Product

        router = DefaultRouter()
        router.include_manifest = False
        router.register("products", VS)

        app = FastAPI()
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/manifest.json")
            assert resp.status_code == 404 or resp.status_code == 405
