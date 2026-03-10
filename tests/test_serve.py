"""Comprehensive tests for router.serve() — zero-config CRUD API."""

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request as FastAPIRequest
from sqlalchemy import Column, Integer, String, Boolean, Float, Text, ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from fastrest.routers import DefaultRouter, SimpleRouter, _model_name_to_prefix
from fastrest.test import APIClient
from fastrest.pagination import PageNumberPagination, LimitOffsetPagination
from fastrest.filters import SearchFilter, OrderingFilter
from fastrest.permissions import AllowAny, IsAuthenticated
from fastrest.viewsets import ReadOnlyModelViewSet
from fastrest.serializers import ModelSerializer
from fastrest.fields import CharField


# ── SQLAlchemy test models ──

class Base(DeclarativeBase):
    pass


class SAuthor(Base):
    __tablename__ = "s_serve_authors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    bio = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    secret_token = Column(String(64), nullable=True)


class SBook(Base):
    __tablename__ = "s_serve_books"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False)
    price = Column(Float, nullable=False)
    in_stock = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    author_id = Column(Integer, ForeignKey("s_serve_authors.id"), nullable=True)


# ── Fixtures ──

@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _make_app_with_session(router, session_factory, viewsets):
    """Create a FastAPI app with session injection for the given viewsets."""
    app = FastAPI()
    app.include_router(router.urls, prefix="/api")

    @app.middleware("http")
    async def inject_session(request: FastAPIRequest, call_next):
        async with session_factory() as session:
            async with session.begin():
                originals = {}
                for vs in viewsets:
                    originals[vs] = vs.__init__

                    def make_patched(original):
                        def patched_init(self, **kwargs):
                            original(self, **kwargs)
                            self._session = session
                        return patched_init

                    vs.__init__ = make_patched(originals[vs])
                try:
                    response = await call_next(request)
                finally:
                    for vs in viewsets:
                        vs.__init__ = originals[vs]
                return response

    return app


# ══════════════════════════════════════════════════════════════════
# 1. PREFIX INFERENCE TESTS
# ══════════════════════════════════════════════════════════════════

class TestModelNameToPrefix:
    def test_simple_names(self):
        assert _model_name_to_prefix("Author") == "authors"
        assert _model_name_to_prefix("Book") == "books"
        assert _model_name_to_prefix("User") == "users"
        assert _model_name_to_prefix("Tag") == "tags"

    def test_camel_case_names(self):
        assert _model_name_to_prefix("BookReview") == "book-reviews"
        assert _model_name_to_prefix("ApiToken") == "api-tokens"
        assert _model_name_to_prefix("UserProfile") == "user-profiles"

    def test_pluralization_y_to_ies(self):
        assert _model_name_to_prefix("Category") == "categories"
        assert _model_name_to_prefix("Story") == "stories"
        assert _model_name_to_prefix("Company") == "companies"

    def test_pluralization_y_after_vowel(self):
        assert _model_name_to_prefix("Key") == "keys"
        assert _model_name_to_prefix("Day") == "days"
        assert _model_name_to_prefix("Boy") == "boys"

    def test_pluralization_s_sh_ch_x_z(self):
        assert _model_name_to_prefix("Address") == "addresses"
        assert _model_name_to_prefix("Bus") == "buses"
        assert _model_name_to_prefix("Tax") == "taxes"
        assert _model_name_to_prefix("Status") == "statuses"
        assert _model_name_to_prefix("Match") == "matches"
        assert _model_name_to_prefix("Brush") == "brushes"

    def test_multi_word_pluralization(self):
        assert _model_name_to_prefix("BookCategory") == "book-categories"
        assert _model_name_to_prefix("UserAddress") == "user-addresses"


# ══════════════════════════════════════════════════════════════════
# 2. BASIC SERVE TESTS (SQLAlchemy)
# ══════════════════════════════════════════════════════════════════

class TestServeBasicCRUD:
    async def test_serve_creates_crud_endpoints(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors")
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        # Create
        resp = await client.post("/api/authors", json={"name": "Jane"})
        assert resp.status_code == 201
        author_id = resp.json()["id"]
        assert resp.json()["name"] == "Jane"

        # List
        resp = await client.get("/api/authors")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Retrieve
        resp = await client.get(f"/api/authors/{author_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Jane"

        # Update
        resp = await client.put(f"/api/authors/{author_id}", json={
            "name": "Janet", "is_active": False
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Janet"

        # Partial update
        resp = await client.patch(f"/api/authors/{author_id}", json={"bio": "A bio"})
        assert resp.status_code == 200
        assert resp.json()["bio"] == "A bio"

        # Delete
        resp = await client.delete(f"/api/authors/{author_id}")
        assert resp.status_code == 204

        # Verify deleted
        resp = await client.get(f"/api/authors/{author_id}")
        assert resp.status_code == 404

    async def test_serve_auto_prefix(self, session_factory):
        router = DefaultRouter()
        router.serve(SAuthor)
        # SAuthor → "sauthors" (no split since 'S' is not preceded by lowercase)
        assert any(p == "sauthors" for p, _, _ in router.registry)

    async def test_serve_auto_prefix_camel_case(self, session_factory):
        """CamelCase model names split and pluralize correctly."""
        router = DefaultRouter()
        router.serve(SBook)
        # SBook → "sbooks" (no lowercase before S)
        assert any(p == "sbooks" for p, _, _ in router.registry)

    async def test_serve_explicit_prefix(self, session_factory):
        router = DefaultRouter()
        router.serve(SAuthor, prefix="writers")
        assert any(p == "writers" for p, _, _ in router.registry)

    async def test_serve_explicit_basename(self, session_factory):
        router = DefaultRouter()
        router.serve(SAuthor, prefix="authors", basename="my-author")
        assert any(b == "my-author" for _, _, b in router.registry)

    async def test_serve_returns_viewset_class(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors")
        assert vs.queryset is SAuthor
        assert hasattr(vs, "serializer_class")
        assert vs.__name__ == "SAuthorAutoViewSet"

    async def test_serve_works_with_simple_router(self, session_factory):
        router = SimpleRouter()
        vs = router.serve(SAuthor, prefix="authors")
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        resp = await client.post("/api/authors", json={"name": "Test"})
        assert resp.status_code == 201

    async def test_serve_multiple_models(self, session_factory):
        router = DefaultRouter()
        vs_author = router.serve(SAuthor, prefix="authors")
        vs_book = router.serve(SBook, prefix="books")
        app = _make_app_with_session(router, session_factory, [vs_author, vs_book])
        client = APIClient(app)

        resp = await client.post("/api/authors", json={"name": "Jane"})
        assert resp.status_code == 201
        author_id = resp.json()["id"]

        resp = await client.post("/api/books", json={
            "title": "My Book", "price": 9.99, "author_id": author_id
        })
        assert resp.status_code == 201
        assert resp.json()["title"] == "My Book"


# ══════════════════════════════════════════════════════════════════
# 3. SERIALIZER OPTIONS
# ══════════════════════════════════════════════════════════════════

class TestServeSerializerOptions:
    async def test_fields_whitelist(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", fields=["id", "name"])
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        resp = await client.post("/api/authors", json={"name": "Jane"})
        assert resp.status_code == 201
        data = resp.json()
        assert "name" in data
        assert "id" in data
        assert "bio" not in data
        assert "secret_token" not in data

    async def test_exclude_fields(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", exclude=["secret_token"])
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        resp = await client.post("/api/authors", json={"name": "Jane"})
        assert resp.status_code == 201
        data = resp.json()
        assert "name" in data
        assert "secret_token" not in data

    async def test_read_only_fields(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", read_only_fields=["is_active"])
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        # Create — is_active should be ignored in input (uses default)
        resp = await client.post("/api/authors", json={"name": "Jane", "is_active": False})
        assert resp.status_code == 201
        assert resp.json()["is_active"] is True  # default, not the provided value

    async def test_custom_serializer_class(self, session_factory):
        class CustomAuthorSerializer(ModelSerializer):
            display_name = CharField(source="name", read_only=True)

            class Meta:
                model = SAuthor
                fields = ["id", "name", "display_name"]

        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", serializer_class=CustomAuthorSerializer)
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        resp = await client.post("/api/authors", json={"name": "Jane"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_name"] == "Jane"
        assert "bio" not in data  # Custom serializer controls fields


# ══════════════════════════════════════════════════════════════════
# 4. VIEWSET OPTIONS
# ══════════════════════════════════════════════════════════════════

class TestServeViewSetOptions:
    async def test_readonly(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", readonly=True)
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        # GET should work (but empty)
        resp = await client.get("/api/authors")
        assert resp.status_code == 200

        # POST should fail (405 or 404 since route doesn't exist)
        resp = await client.post("/api/authors", json={"name": "Jane"})
        assert resp.status_code in (404, 405)

    async def test_readonly_with_explicit_viewset_class(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", viewset_class=ReadOnlyModelViewSet)
        assert issubclass(vs, ReadOnlyModelViewSet)

    async def test_pagination_class(self, session_factory):
        class SmallPagination(PageNumberPagination):
            page_size = 2

        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", pagination_class=SmallPagination)
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        # Create 5 authors
        for i in range(5):
            await client.post("/api/authors", json={"name": f"Author {i}"})

        resp = await client.get("/api/authors")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 5
        assert len(data["results"]) == 2  # page_size=2

    async def test_filter_backends_and_search(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(
            SAuthor, prefix="authors",
            filter_backends=[SearchFilter],
            search_fields=["name", "bio"],
        )
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        await client.post("/api/authors", json={"name": "Jane", "bio": "Writer"})
        await client.post("/api/authors", json={"name": "Bob", "bio": "Artist"})

        resp = await client.get("/api/authors?search=Jane")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Jane"

    async def test_ordering_fields(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(
            SAuthor, prefix="authors",
            filter_backends=[OrderingFilter],
            ordering_fields=["name"],
        )
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        await client.post("/api/authors", json={"name": "Zara"})
        await client.post("/api/authors", json={"name": "Alice"})

        resp = await client.get("/api/authors?ordering=name")
        assert resp.status_code == 200
        names = [a["name"] for a in resp.json()]
        assert names == sorted(names)

        resp = await client.get("/api/authors?ordering=-name")
        assert resp.status_code == 200
        names = [a["name"] for a in resp.json()]
        assert names == sorted(names, reverse=True)

    async def test_search_and_ordering_combined(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(
            SBook, prefix="books",
            filter_backends=[SearchFilter, OrderingFilter],
            search_fields=["title"],
            ordering_fields=["price"],
            ordering=["price"],
        )
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        await client.post("/api/books", json={"title": "Python A", "price": 30.0})
        await client.post("/api/books", json={"title": "Python B", "price": 10.0})
        await client.post("/api/books", json={"title": "Java", "price": 20.0})

        resp = await client.get("/api/books?search=Python&ordering=price")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["price"] == 10.0
        assert data[1]["price"] == 30.0

    async def test_pagination_with_search(self, session_factory):
        class SmallPagination(PageNumberPagination):
            page_size = 2

        router = DefaultRouter()
        vs = router.serve(
            SAuthor, prefix="authors",
            pagination_class=SmallPagination,
            filter_backends=[SearchFilter],
            search_fields=["name"],
        )
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        for i in range(5):
            await client.post("/api/authors", json={"name": f"Test Author {i}"})
        await client.post("/api/authors", json={"name": "Other"})

        resp = await client.get("/api/authors?search=Test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 5
        assert len(data["results"]) == 2

    async def test_permission_classes(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(
            SAuthor, prefix="authors",
            permission_classes=[IsAuthenticated()],
        )
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        # Should be denied without auth
        resp = await client.get("/api/authors")
        assert resp.status_code in (401, 403)

    async def test_return_value_customization(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors")
        # Modify after creation
        vs.skill_description = "Manage authors."
        assert vs.skill_description == "Manage authors."


# ══════════════════════════════════════════════════════════════════
# 5. OPENAPI SCHEMA TESTS
# ══════════════════════════════════════════════════════════════════

class TestServeOpenAPI:
    async def test_openapi_schema_generated(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors")
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = schema["paths"]

        assert "/api/authors" in paths
        assert "/api/authors/{pk}" in paths

        # List endpoint
        list_ops = paths["/api/authors"]
        assert "get" in list_ops
        assert "post" in list_ops

        # Detail endpoint
        detail_ops = paths["/api/authors/{pk}"]
        assert "get" in detail_ops
        assert "put" in detail_ops
        assert "patch" in detail_ops
        assert "delete" in detail_ops

    async def test_openapi_field_whitelist(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", fields=["id", "name"])
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        resp = await client.get("/openapi.json")
        schema = resp.json()

        # Find the response schema
        components = schema.get("components", {}).get("schemas", {})
        # Look for the response model containing only id and name
        found_limited = False
        for schema_name, schema_def in components.items():
            props = schema_def.get("properties", {})
            if "name" in props and "bio" not in props and "secret_token" not in props:
                found_limited = True
                break
        assert found_limited, "OpenAPI schema should only contain whitelisted fields"

    async def test_openapi_exclude_fields(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", exclude=["secret_token"])
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        resp = await client.get("/openapi.json")
        schema = resp.json()

        components = schema.get("components", {}).get("schemas", {})
        for schema_name, schema_def in components.items():
            props = schema_def.get("properties", {})
            if "name" in props:
                assert "secret_token" not in props, \
                    f"Schema '{schema_name}' should not contain excluded field 'secret_token'"

    async def test_openapi_readonly_no_write_endpoints(self, session_factory):
        router = DefaultRouter()
        vs = router.serve(SAuthor, prefix="authors", readonly=True)
        app = _make_app_with_session(router, session_factory, [vs])
        client = APIClient(app)

        resp = await client.get("/openapi.json")
        schema = resp.json()
        paths = schema["paths"]

        # List should only have GET
        if "/api/authors" in paths:
            assert "get" in paths["/api/authors"]
            assert "post" not in paths["/api/authors"]

        # Detail should only have GET
        if "/api/authors/{pk}" in paths:
            assert "get" in paths["/api/authors/{pk}"]
            assert "put" not in paths["/api/authors/{pk}"]
            assert "delete" not in paths["/api/authors/{pk}"]

    async def test_openapi_multiple_served_models(self, session_factory):
        router = DefaultRouter()
        vs_a = router.serve(SAuthor, prefix="authors")
        vs_b = router.serve(SBook, prefix="books")
        app = _make_app_with_session(router, session_factory, [vs_a, vs_b])
        client = APIClient(app)

        resp = await client.get("/openapi.json")
        schema = resp.json()
        paths = schema["paths"]

        assert "/api/authors" in paths
        assert "/api/books" in paths
        assert "/api/authors/{pk}" in paths
        assert "/api/books/{pk}" in paths


# ══════════════════════════════════════════════════════════════════
# 6. TORTOISE ORM SERVE TESTS
# ══════════════════════════════════════════════════════════════════

class TestServeTortoise:
    async def test_serve_tortoise_model(self):
        from tortoise import Tortoise, fields
        from tortoise.models import Model
        from fastrest.compat.orm import set_default_adapter, reset_default_adapter
        from fastrest.compat.orm.tortoise import TortoiseAdapter

        # Define at module level so Tortoise can discover it
        import types
        temp_module = types.ModuleType("_tortoise_serve_models")

        class TServeItem(Model):
            id = fields.IntField(primary_key=True)
            name = fields.CharField(max_length=100)
            price = fields.FloatField()

            class Meta:
                table = "t_serve_items"

        temp_module.TServeItem = TServeItem
        import sys
        sys.modules["_tortoise_serve_models"] = temp_module

        await Tortoise.init(
            db_url="sqlite://:memory:",
            modules={"models": ["_tortoise_serve_models"]},
        )
        await Tortoise.generate_schemas()

        try:
            set_default_adapter(TortoiseAdapter())
            router = DefaultRouter()
            vs = router.serve(TServeItem, prefix="items")
            app = FastAPI()
            app.include_router(router.urls, prefix="/api")
            client = APIClient(app)

            resp = await client.post("/api/items", json={"name": "Widget", "price": 5.99})
            assert resp.status_code == 201
            item_id = resp.json()["id"]

            resp = await client.get(f"/api/items/{item_id}")
            assert resp.status_code == 200
            assert resp.json()["name"] == "Widget"

            resp = await client.get("/api/items")
            assert resp.status_code == 200
            assert len(resp.json()) >= 1

            resp = await client.delete(f"/api/items/{item_id}")
            assert resp.status_code == 204
        finally:
            reset_default_adapter()
            await Tortoise.close_connections()


# ══════════════════════════════════════════════════════════════════
# 7. BEANIE SERVE TESTS
# ══════════════════════════════════════════════════════════════════

class TestServeBeanie:
    async def test_serve_beanie_model_with_string_pk(self):
        from beanie import Document, init_beanie
        from mongomock_motor import AsyncMongoMockClient
        from fastrest.compat.orm import set_default_adapter, reset_default_adapter
        from fastrest.compat.orm.beanie import BeanieAdapter

        class BServeItem(Document):
            name: str
            price: float

            class Settings:
                name = "b_serve_items"

        client_mongo = AsyncMongoMockClient()
        await init_beanie(database=client_mongo.testdb, document_models=[BServeItem])

        try:
            set_default_adapter(BeanieAdapter())
            router = DefaultRouter()
            vs = router.serve(BServeItem, prefix="items")

            # Should auto-detect string PK
            assert vs.lookup_field_type is str

            app = FastAPI()
            app.include_router(router.urls, prefix="/api")
            client = APIClient(app)

            resp = await client.post("/api/items", json={"name": "Widget", "price": 5.99})
            assert resp.status_code == 201
            item_id = resp.json()["id"]
            assert isinstance(item_id, str)

            resp = await client.get(f"/api/items/{item_id}")
            assert resp.status_code == 200
            assert resp.json()["name"] == "Widget"

            resp = await client.get("/api/items")
            assert resp.status_code == 200

            resp = await client.delete(f"/api/items/{item_id}")
            assert resp.status_code == 204
        finally:
            await BServeItem.delete_all()
            reset_default_adapter()


# ══════════════════════════════════════════════════════════════════
# 8. SQLMODEL SERVE TESTS
# ══════════════════════════════════════════════════════════════════

class TestServeSQLModel:
    async def test_serve_sqlmodel_model(self):
        from sqlmodel import SQLModel, Field as SMField
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from fastrest.compat.orm import set_default_adapter, reset_default_adapter
        from fastrest.compat.orm.sqlmodel import SQLModelAdapter

        class SMServeItem(SQLModel, table=True):
            __tablename__ = "sm_serve_items"
            id: int | None = SMField(default=None, primary_key=True)
            name: str = SMField(max_length=100)
            price: float = 0.0

        eng = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with eng.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        sf = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

        try:
            set_default_adapter(SQLModelAdapter())
            router = DefaultRouter()
            vs = router.serve(SMServeItem, prefix="items")
            app = _make_app_with_session(router, sf, [vs])
            client = APIClient(app)

            resp = await client.post("/api/items", json={"name": "Widget", "price": 5.99})
            assert resp.status_code == 201

            resp = await client.get("/api/items")
            assert resp.status_code == 200
            assert len(resp.json()) >= 1
        finally:
            reset_default_adapter()
            await eng.dispose()
