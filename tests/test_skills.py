"""Tests for SKILL.md generation and endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import DeclarativeBase

from fastrest.serializers import ModelSerializer
from fastrest import fields as f
from fastrest.viewsets import ModelViewSet, ReadOnlyModelViewSet
from fastrest.routers import DefaultRouter
from fastrest.permissions import IsAuthenticated, AllowAny
from fastrest.pagination import PageNumberPagination
from fastrest.filters import SearchFilter, OrderingFilter
from fastrest.decorators import action
from fastrest.response import Response
from fastrest.settings import configure
from fastrest.skills import SkillGenerator, _type_name, _field_constraints, _example_value


# --- Fixtures ---

class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    price = Column(Float)
    category = Column(String(50))


class ItemSerializer(ModelSerializer):
    class Meta:
        model = Item
        fields = ["id", "name", "price", "category"]
        read_only_fields = ["id"]


class ItemPagination(PageNumberPagination):
    page_size = 10
    max_page_size = 50


class ItemViewSet(ModelViewSet):
    queryset = Item
    serializer_class = ItemSerializer
    pagination_class = ItemPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "category"]
    ordering_fields = ["name", "price"]
    ordering = ["-price"]

    @action(detail=True, methods=["post"], skill=True)
    async def discount(self, request, **kwargs):
        """Apply a discount to this item."""
        return Response({"status": "discounted"})

    @action(detail=False, methods=["get"], skill=False)
    async def hidden_action(self, request, **kwargs):
        """This action is hidden from SKILL.md."""
        return Response({"status": "hidden"})


class HiddenViewSet(ModelViewSet):
    """This viewset is hidden."""
    queryset = Item
    serializer_class = ItemSerializer
    skill_enabled = False


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    label = Column(String(50))


class TagSerializer(ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "label"]
        read_only_fields = ["id"]


class TagViewSet(ReadOnlyModelViewSet):
    queryset = Tag
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]


def _make_router():
    router = DefaultRouter()
    router.register("items", ItemViewSet)
    router.register("tags", TagViewSet)
    router.register("hidden", HiddenViewSet)
    return router


# --- Unit tests: helpers ---

class TestHelpers:
    def test_type_name_charfield(self):
        assert _type_name(f.CharField()) == "string"

    def test_type_name_intfield(self):
        assert _type_name(f.IntegerField()) == "integer"

    def test_type_name_email(self):
        assert _type_name(f.EmailField()) == "string (email)"

    def test_type_name_unknown(self):
        assert _type_name(f.Field()) == "any"

    def test_field_constraints_max_length(self):
        field = f.CharField(max_length=255)
        c = _field_constraints(field)
        assert "max 255 chars" in c

    def test_field_constraints_min_value(self):
        field = f.IntegerField(min_value=0, max_value=100)
        c = _field_constraints(field)
        assert "min 0" in c
        assert "max 100" in c

    def test_example_value_integer(self):
        assert _example_value(f.IntegerField(), "count") == 1

    def test_example_value_email(self):
        assert _example_value(f.EmailField(), "email") == "user@example.com"

    def test_example_value_string(self):
        assert _example_value(f.CharField(), "title") == "example_title"

    def test_example_value_bool(self):
        assert _example_value(f.BooleanField(), "active") is True


# --- Unit tests: SkillGenerator ---

class TestSkillGenerator:
    def test_generate_full_document(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "---" in doc
        assert "Items" in doc
        assert "Tags" in doc
        # Hidden viewset should not appear
        assert "Hidden" not in doc

    def test_generate_single_resource(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate(resources=["items"])
        assert "Items" in doc
        assert "Tags" not in doc

    def test_frontmatter(self):
        router = _make_router()
        gen = SkillGenerator(router, config={"SKILL_NAME": "my-api"})
        doc = gen.generate()
        assert "name: my-api" in doc

    def test_frontmatter_with_resources(self):
        router = _make_router()
        gen = SkillGenerator(router, config={"SKILL_NAME": "my-api"})
        doc = gen.generate(resources=["items"])
        assert "name: my-api-items" in doc

    def test_custom_description(self):
        router = _make_router()
        gen = SkillGenerator(router, config={"SKILL_DESCRIPTION": "Custom description"})
        doc = gen.generate()
        assert "description: Custom description" in doc

    def test_base_url(self):
        router = _make_router()
        gen = SkillGenerator(router, config={"SKILL_BASE_URL": "https://api.example.com"})
        doc = gen.generate()
        assert "`https://api.example.com`" in doc
        assert "https://api.example.com/items" in doc

    def test_fields_table(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "| name |" in doc
        assert "| price |" in doc
        assert "read-only" in doc  # id field

    def test_endpoints_section(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "`GET /items`" in doc
        assert "`POST /items`" in doc
        assert "`GET /items/{id}`" in doc
        assert "`PUT /items/{id}`" in doc
        assert "`PATCH /items/{id}`" in doc
        assert "`DELETE /items/{id}`" in doc

    def test_readonly_viewset_endpoints(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "`GET /tags`" in doc
        assert "`GET /tags/{id}`" in doc
        # Should NOT have write endpoints for tags
        assert "`POST /tags`" not in doc

    def test_custom_actions(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "discount" in doc
        assert "Apply a discount" in doc
        # hidden_action has skill=False
        assert "hidden_action" not in doc

    def test_filter_section(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "?search=<term>" in doc
        assert "name, category" in doc
        assert "?ordering=<field>" in doc

    def test_pagination_info(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "?page=<n>" in doc
        assert "10 per page" in doc

    def test_auth_section(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "Authentication" in doc
        assert "Authentication required" in doc

    def test_custom_auth_description(self):
        router = _make_router()
        gen = SkillGenerator(router, config={"SKILL_AUTH_DESCRIPTION": "Use Bearer token"})
        doc = gen.generate()
        assert "Use Bearer token" in doc

    def test_error_section(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "Error Responses" in doc
        assert "`400`" in doc
        assert "`404`" in doc

    def test_examples_section(self):
        router = _make_router()
        gen = SkillGenerator(router, config={"SKILL_INCLUDE_EXAMPLES": True})
        doc = gen.generate()
        assert "Examples" in doc
        assert "POST" in doc

    def test_examples_disabled(self):
        router = _make_router()
        gen = SkillGenerator(router, config={"SKILL_INCLUDE_EXAMPLES": False})
        doc = gen.generate()
        # Should not have examples section
        assert "## Examples" not in doc

    def test_empty_registry(self):
        router = DefaultRouter()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "No resources found" in doc

    def test_paginated_response_format(self):
        router = _make_router()
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert '"count"' in doc
        assert '"results"' in doc


# --- Validation rendering ---

class ValidatedSerializer(ModelSerializer):
    class Meta:
        model = Item
        fields = ["id", "name", "price"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        """Name must not be empty."""
        if not value:
            raise ValueError("empty")
        return value


class ValidatedViewSet(ModelViewSet):
    queryset = Item
    serializer_class = ValidatedSerializer


class TestValidationRendering:
    def test_validation_rules(self):
        router = DefaultRouter()
        router.register("validated", ValidatedViewSet)
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "Validation rules" in doc
        assert "Name must not be empty" in doc


# --- Integration: HTTP endpoint ---

class TestSkillEndpoint:
    async def test_skill_md_endpoint(self):
        app = FastAPI()
        router = DefaultRouter()
        router.register("items", ItemViewSet)
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/SKILL.md")
            assert resp.status_code == 200
            assert "text/markdown" in resp.headers["content-type"]
            assert "Items" in resp.text
            assert "---" in resp.text

    async def test_skill_resource_endpoint(self):
        app = FastAPI()
        router = DefaultRouter()
        router.register("items", ItemViewSet)
        router.register("tags", TagViewSet)
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/items/SKILL.md")
            assert resp.status_code == 200
            assert "Items" in resp.text
            assert "Tags" not in resp.text

    async def test_skill_disabled(self):
        app = FastAPI()
        configure(app, {"SKILL_ENABLED": False})
        router = DefaultRouter()
        router.register("items", ItemViewSet)
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/SKILL.md")
            assert resp.status_code == 404

    async def test_skill_with_configured_settings(self):
        app = FastAPI()
        configure(app, {"SKILL_NAME": "bookstore", "SKILL_BASE_URL": "https://api.bookstore.com"})
        router = DefaultRouter()
        router.register("items", ItemViewSet)
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/SKILL.md")
            assert resp.status_code == 200
            assert "name: bookstore" in resp.text
            assert "https://api.bookstore.com" in resp.text

    async def test_skill_not_in_openapi_schema(self):
        app = FastAPI()
        router = DefaultRouter()
        router.register("items", ItemViewSet)
        app.include_router(router.urls)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/openapi.json")
            schema = resp.json()
            paths = list(schema.get("paths", {}).keys())
            assert "/SKILL.md" not in paths
            assert "/{resource}/SKILL.md" not in paths


# --- Viewset-level customization ---

class CustomSkillViewSet(ModelViewSet):
    queryset = Item
    serializer_class = ItemSerializer
    skill_description = "Manage inventory items with full CRUD."
    skill_exclude_actions = ["destroy"]
    skill_exclude_fields = ["category"]


class TestViewSetCustomization:
    def test_custom_description(self):
        router = DefaultRouter()
        router.register("custom", CustomSkillViewSet)
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "Manage inventory items with full CRUD" in doc

    def test_exclude_actions(self):
        router = DefaultRouter()
        router.register("custom", CustomSkillViewSet)
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "`DELETE" not in doc

    def test_exclude_fields(self):
        router = DefaultRouter()
        router.register("custom", CustomSkillViewSet)
        gen = SkillGenerator(router)
        doc = gen.generate()
        assert "| category |" not in doc


# --- Custom examples ---

class ExampleViewSet(ModelViewSet):
    queryset = Item
    serializer_class = ItemSerializer
    skill_examples = [
        {
            "description": "Create a widget",
            "request": "POST /items {\"name\": \"Widget\", \"price\": 9.99}",
            "response": "201 Created",
        }
    ]


class TestCustomExamples:
    def test_custom_examples_rendered(self):
        router = DefaultRouter()
        router.register("items", ExampleViewSet)
        gen = SkillGenerator(router, config={"SKILL_INCLUDE_EXAMPLES": True})
        doc = gen.generate()
        assert "Create a widget" in doc
        assert "Widget" in doc
