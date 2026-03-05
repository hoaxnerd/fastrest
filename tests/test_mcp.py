"""Tests for the built-in MCP server bridge."""

import json
import pytest

from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import DeclarativeBase

from fastrest.serializers import ModelSerializer
from fastrest import fields as f
from fastrest.viewsets import ModelViewSet, ReadOnlyModelViewSet
from fastrest.routers import DefaultRouter
from fastrest.decorators import action
from fastrest.response import Response
from fastrest.pagination import PageNumberPagination
from fastrest.filters import SearchFilter, OrderingFilter
from fastrest.permissions import IsAuthenticated
from fastrest.mcp import (
    MCPBridge,
    _singularize,
    _build_tool_params,
    _type_to_json_schema,
    _execute_viewset_action,
    mount_mcp,
    CRUD_ACTIONS,
)


# --- Models ---

class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "mcp_books"
    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    author = Column(String(100))
    price = Column(Float)


class BookSerializer(ModelSerializer):
    class Meta:
        model = Book
        fields = ["id", "title", "author", "price"]
        read_only_fields = ["id"]


class BookPagination(PageNumberPagination):
    page_size = 20


class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer
    pagination_class = BookPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "author"]
    ordering_fields = ["title", "price"]

    @action(detail=True, methods=["post"], mcp=True, mcp_description="Apply a discount to a book")
    async def discount(self, request, **kwargs):
        """Apply a discount to this book."""
        return Response({"status": "discounted"})

    @action(detail=False, methods=["get"], mcp=False)
    async def hidden(self, request, **kwargs):
        """Hidden from MCP."""
        return Response({"status": "hidden"})


class TagViewSet(ReadOnlyModelViewSet):
    queryset = Book  # reuse for simplicity
    serializer_class = BookSerializer


def _make_router():
    router = DefaultRouter()
    router.register("books", BookViewSet)
    router.register("tags", TagViewSet)
    return router


# --- Helper tests ---

class TestSingularize:
    def test_books(self):
        assert _singularize("books") == "book"

    def test_categories(self):
        assert _singularize("categories") == "category"

    def test_boxes(self):
        assert _singularize("boxes") == "box"

    def test_addresses(self):
        assert _singularize("addresses") == "address"

    def test_already_singular(self):
        assert _singularize("person") == "person"


class TestTypeToJsonSchema:
    def test_string(self):
        assert _type_to_json_schema("string") == "string"

    def test_integer(self):
        assert _type_to_json_schema("integer") == "integer"

    def test_float(self):
        assert _type_to_json_schema("float") == "number"

    def test_boolean(self):
        assert _type_to_json_schema("boolean") == "boolean"

    def test_unknown(self):
        assert _type_to_json_schema("unknown") == "string"


class TestBuildToolParams:
    def test_detail_action(self):
        params = _build_tool_params(BookViewSet, "retrieve", detail=True)
        assert "id" in params["properties"]
        assert "id" in params["required"]

    def test_create_action(self):
        params = _build_tool_params(BookViewSet, "create", detail=False)
        props = params["properties"]
        assert "title" in props
        assert "author" in props
        assert "price" in props
        # id should not be in create params (read_only)
        assert "id" not in props

    def test_partial_update_no_required_fields(self):
        params = _build_tool_params(BookViewSet, "partial_update", detail=True)
        # Only "id" should be required (for detail), not the body fields
        assert "id" in params.get("required", [])
        # Body fields should not be required for partial update
        required = params.get("required", [])
        assert "title" not in required
        assert "author" not in required

    def test_list_with_search(self):
        params = _build_tool_params(BookViewSet, "list", detail=False)
        props = params["properties"]
        assert "search" in props
        assert "ordering" in props
        assert "page" in props

    def test_list_without_search(self):
        params = _build_tool_params(TagViewSet, "list", detail=False)
        props = params["properties"]
        assert "search" not in props


# --- MCPBridge tests ---

class TestMCPBridge:
    def test_build_mcp(self):
        router = _make_router()
        bridge = MCPBridge(router)
        mcp = bridge.build_mcp(name="test-api")
        assert mcp is not None

    def test_tools_registered(self):
        router = _make_router()
        bridge = MCPBridge(router)
        mcp = bridge.build_mcp()
        # Get registered tool names
        tool_manager = mcp._tool_manager
        tool_names = list(tool_manager._tools.keys())

        # CRUD tools for books: list, create, retrieve, update, partial_update, destroy
        assert "books_list" in tool_names
        assert "books_create" in tool_names
        assert "books_retrieve" in tool_names
        assert "books_update" in tool_names
        assert "books_partial_update" in tool_names
        assert "books_destroy" in tool_names

        # Custom action with mcp=True
        assert "books_discount" in tool_names

        # Hidden action (mcp=False) should NOT be registered
        assert "books_hidden" not in tool_names

        # Tags (ReadOnly): only list and retrieve
        assert "tags_list" in tool_names
        assert "tags_retrieve" in tool_names
        assert "tags_create" not in tool_names

    def test_custom_tool_name_format(self):
        from fastrest.settings import APISettings
        settings = APISettings(user_settings={"MCP_TOOL_NAME_FORMAT": "{basename}.{action}"})
        router = _make_router()
        bridge = MCPBridge(router, settings=settings)
        mcp = bridge.build_mcp()
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "books.list" in tool_names

    def test_exclude_viewsets(self):
        from fastrest.settings import APISettings
        settings = APISettings(user_settings={"MCP_EXCLUDE_VIEWSETS": ["tags"]})
        router = _make_router()
        bridge = MCPBridge(router, settings=settings)
        mcp = bridge.build_mcp()
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "tags_list" not in tool_names
        assert "books_list" in tool_names

    def test_tool_has_description(self):
        router = _make_router()
        bridge = MCPBridge(router)
        mcp = bridge.build_mcp()
        tools = mcp._tool_manager._tools
        assert "List all books" in tools["books_list"].description
        assert "Apply a discount" in tools["books_discount"].description


# --- mount_mcp tests ---

class TestMountMCP:
    def test_mount_mcp(self):
        from fastapi import FastAPI
        app = FastAPI()
        router = _make_router()
        mcp = mount_mcp(app, router)
        assert mcp is not None
        # Check that a mount route exists
        mount_paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert any("/mcp" in p for p in mount_paths)

    def test_mount_mcp_disabled(self):
        from fastapi import FastAPI
        from fastrest.settings import APISettings
        app = FastAPI()
        router = _make_router()
        settings = APISettings(user_settings={"MCP_ENABLED": False})
        result = mount_mcp(app, router, settings=settings)
        assert result is None

    def test_mount_mcp_custom_prefix(self):
        from fastapi import FastAPI
        app = FastAPI()
        router = _make_router()
        mcp = mount_mcp(app, router, path="/tools")
        assert mcp is not None
        mount_paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert any("/tools" in p for p in mount_paths)


# --- Execution tests (simplified, no real DB) ---

class SimpleViewSet(ModelViewSet):
    """A simple viewset for testing execution without DB."""
    queryset = Book
    serializer_class = BookSerializer

    async def list(self, request, **kwargs):
        return Response([{"id": 1, "title": "Test", "author": "Author", "price": 9.99}])

    async def retrieve(self, request, **kwargs):
        return Response({"id": 1, "title": "Test", "author": "Author", "price": 9.99})

    async def create(self, request, **kwargs):
        return Response({"id": 2, "title": "New", "author": "Author", "price": 19.99}, status=201)


class TestExecution:
    async def test_execute_list(self):
        result = await _execute_viewset_action(SimpleViewSet, "list", "get", False, {})
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["title"] == "Test"

    async def test_execute_retrieve(self):
        result = await _execute_viewset_action(SimpleViewSet, "retrieve", "get", True, {"id": "1"})
        data = json.loads(result)
        assert data["title"] == "Test"

    async def test_execute_create(self):
        result = await _execute_viewset_action(
            SimpleViewSet, "create", "post", False,
            {"title": "New Book", "author": "Author", "price": 19.99}
        )
        data = json.loads(result)
        assert data["title"] == "New"
