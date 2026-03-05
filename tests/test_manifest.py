"""Tests for the manifest endpoint and generation."""

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import DeclarativeBase

from fastrest.serializers import ModelSerializer
from fastrest.viewsets import ModelViewSet, ReadOnlyModelViewSet
from fastrest.routers import DefaultRouter
from fastrest.decorators import action
from fastrest.response import Response
from fastrest.pagination import PageNumberPagination
from fastrest.filters import SearchFilter, OrderingFilter
from fastrest.permissions import IsAuthenticated
from fastrest.settings import configure, APISettings
from fastrest.manifest import generate_manifest


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "manifest_products"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    price = Column(Float)


class ProductSerializer(ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "price"]
        read_only_fields = ["id"]


class ProductPagination(PageNumberPagination):
    page_size = 25
    max_page_size = 100


class ProductViewSet(ModelViewSet):
    queryset = Product
    serializer_class = ProductSerializer
    pagination_class = ProductPagination
    filter_backends = [SearchFilter]
    search_fields = ["name"]
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["post"])
    async def archive(self, request, **kwargs):
        return Response({"status": "archived"})


class CategoryViewSet(ReadOnlyModelViewSet):
    queryset = Product
    serializer_class = ProductSerializer


def _make_router():
    router = DefaultRouter()
    router.register("products", ProductViewSet)
    router.register("categories", CategoryViewSet)
    return router


class TestGenerateManifest:
    def test_basic_structure(self):
        router = _make_router()
        manifest = generate_manifest(router)
        assert manifest["version"] == "1.0"
        assert "resources" in manifest
        assert len(manifest["resources"]) == 2

    def test_resource_names(self):
        router = _make_router()
        manifest = generate_manifest(router)
        names = [r["name"] for r in manifest["resources"]]
        assert "products" in names
        assert "categories" in names

    def test_resource_actions(self):
        router = _make_router()
        manifest = generate_manifest(router)
        products = next(r for r in manifest["resources"] if r["name"] == "products")
        action_names = [a["name"] for a in products["actions"]]
        assert "list" in action_names
        assert "create" in action_names
        assert "retrieve" in action_names
        assert "archive" in action_names

    def test_readonly_actions(self):
        router = _make_router()
        manifest = generate_manifest(router)
        categories = next(r for r in manifest["resources"] if r["name"] == "categories")
        action_names = [a["name"] for a in categories["actions"]]
        assert "list" in action_names
        assert "retrieve" in action_names
        assert "create" not in action_names

    def test_fields(self):
        router = _make_router()
        manifest = generate_manifest(router)
        products = next(r for r in manifest["resources"] if r["name"] == "products")
        field_names = [f["name"] for f in products["fields"]]
        assert "id" in field_names
        assert "name" in field_names
        assert "price" in field_names

    def test_field_attributes(self):
        router = _make_router()
        manifest = generate_manifest(router)
        products = next(r for r in manifest["resources"] if r["name"] == "products")
        id_field = next(f for f in products["fields"] if f["name"] == "id")
        assert id_field["read_only"] is True
        assert id_field["required"] is False

    def test_permissions(self):
        router = _make_router()
        manifest = generate_manifest(router)
        products = next(r for r in manifest["resources"] if r["name"] == "products")
        assert "IsAuthenticated" in products["permissions"]

    def test_pagination(self):
        router = _make_router()
        manifest = generate_manifest(router)
        products = next(r for r in manifest["resources"] if r["name"] == "products")
        assert products["pagination"]["page_size"] == 25
        assert products["pagination"]["max_page_size"] == 100

    def test_filters(self):
        router = _make_router()
        manifest = generate_manifest(router)
        products = next(r for r in manifest["resources"] if r["name"] == "products")
        assert "name" in products["filters"]["search_fields"]

    def test_custom_name(self):
        router = _make_router()
        settings = APISettings(user_settings={"SKILL_NAME": "my-store"})
        manifest = generate_manifest(router, settings=settings)
        assert manifest["name"] == "my-store"

    def test_base_url(self):
        router = _make_router()
        settings = APISettings(user_settings={"SKILL_BASE_URL": "https://api.store.com"})
        manifest = generate_manifest(router, settings=settings)
        assert manifest["base_url"] == "https://api.store.com"

    def test_mcp_info(self):
        router = _make_router()
        manifest = generate_manifest(router)
        assert manifest["mcp"]["enabled"] is True
        assert manifest["mcp"]["prefix"] == "/mcp"

    def test_skills_info(self):
        router = _make_router()
        manifest = generate_manifest(router)
        assert manifest["skills"]["enabled"] is True

    def test_mcp_disabled(self):
        router = _make_router()
        settings = APISettings(user_settings={"MCP_ENABLED": False})
        manifest = generate_manifest(router, settings=settings)
        assert "mcp" not in manifest


class TestManifestEndpoint:
    async def test_manifest_json(self):
        app = FastAPI()
        router = DefaultRouter()
        router.register("products", ProductViewSet)
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/manifest.json")
            assert resp.status_code == 200
            data = resp.json()
            assert data["version"] == "1.0"
            assert len(data["resources"]) == 1
            assert data["resources"][0]["name"] == "products"

    async def test_manifest_with_settings(self):
        app = FastAPI()
        configure(app, {"SKILL_NAME": "bookstore"})
        router = DefaultRouter()
        router.register("products", ProductViewSet)
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/manifest.json")
            assert resp.status_code == 200
            assert resp.json()["name"] == "bookstore"

    async def test_manifest_not_in_openapi(self):
        app = FastAPI()
        router = DefaultRouter()
        router.register("products", ProductViewSet)
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/openapi.json")
            paths = list(resp.json().get("paths", {}).keys())
            assert "/manifest.json" not in paths
