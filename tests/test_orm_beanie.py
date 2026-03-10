"""Tests for the Beanie ODM adapter (MongoDB)."""

import datetime
import decimal
import uuid

import pytest
import pytest_asyncio
from beanie import Document, init_beanie
from mongomock_motor import AsyncMongoMockClient
from pydantic import Field

from fastrest.compat.orm.beanie import BeanieAdapter, _PYTHON_TYPE_MAP, _resolve_type
from fastrest.compat.orm.base import FieldInfo
from tests.adapter_contract import AdapterContractTests


# ── Test models ──

class BAuthor(Document):
    name: str
    bio: str | None = None
    is_active: bool = True

    class Settings:
        name = "b_authors"


class BBook(Document):
    title: str
    price: float
    in_stock: bool = True
    author_id: str | None = None

    class Settings:
        name = "b_books"


class BReview(Document):
    rating: int
    comment: str | None = None
    book_id: str | None = None

    class Settings:
        name = "b_reviews"


# Model with diverse field types for type mapping tests
class BAllTypes(Document):
    int_field: int
    str_field: str
    float_field: float
    bool_field: bool
    decimal_field: decimal.Decimal
    datetime_field: datetime.datetime
    date_field: datetime.date
    time_field: datetime.time
    timedelta_field: datetime.timedelta
    uuid_field: uuid.UUID
    bytes_field: bytes
    dict_field: dict
    list_field: list
    optional_str: str | None = None

    class Settings:
        name = "b_all_types"


# ── Fixtures ──

@pytest_asyncio.fixture
async def beanie_db():
    client = AsyncMongoMockClient()
    await init_beanie(
        database=client.testdb,
        document_models=[BAuthor, BBook, BReview, BAllTypes],
    )
    yield client
    # Clean up collections
    for model in [BAuthor, BBook, BReview, BAllTypes]:
        await model.delete_all()


@pytest.fixture
def adapter():
    return BeanieAdapter()


# ── Contract tests ──

class TestBeanieAdapterContract(AdapterContractTests):
    expected_field_names = {"id", "name", "bio", "is_active"}
    create_kwargs = {"name": "Test Author", "bio": "A bio", "is_active": True}
    update_kwargs = {"name": "Updated Author"}
    nonexistent_lookup = {"id": "000000000000000000000000"}
    filter_kwargs = {"name": "Test Author"}

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, beanie_db, adapter):
        self.adapter = adapter
        self.model = BAuthor
        self.session = None  # Beanie doesn't use sessions
        # Clean before each test
        await BAuthor.delete_all()


# ── Field introspection tests ──

class TestBeanieFieldIntrospection:
    def test_author_fields(self, adapter):
        fields_list = adapter.get_fields(BAuthor)
        field_map = {f.name: f for f in fields_list}

        assert "id" in field_map
        assert field_map["id"].primary_key is True

        assert "name" in field_map
        assert field_map["name"].field_type == "string"

        assert "bio" in field_map
        assert field_map["bio"].nullable is True

        assert "is_active" in field_map
        assert field_map["is_active"].field_type == "boolean"

    def test_book_fields(self, adapter):
        fields_list = adapter.get_fields(BBook)
        field_map = {f.name: f for f in fields_list}

        assert "title" in field_map
        assert field_map["title"].field_type == "string"

        assert "price" in field_map
        assert field_map["price"].field_type == "float"

        assert "in_stock" in field_map
        assert field_map["in_stock"].field_type == "boolean"

    def test_pk_field(self, adapter):
        pk = adapter.get_pk_field(BAuthor)
        assert pk.primary_key is True
        assert pk.name == "id"

    def test_relations_empty_for_non_link(self, adapter):
        rels = adapter.get_relations(BAuthor)
        assert isinstance(rels, list)


# ── Comprehensive type mapping tests ──

class TestBeanieTypeMapping:
    def test_all_field_types(self, adapter):
        fields_list = adapter.get_fields(BAllTypes)
        type_map = {f.name: f.field_type for f in fields_list}

        assert type_map["int_field"] == "integer"
        assert type_map["str_field"] == "string"
        assert type_map["float_field"] == "float"
        assert type_map["bool_field"] == "boolean"
        assert type_map["decimal_field"] == "decimal"
        assert type_map["datetime_field"] == "datetime"
        assert type_map["date_field"] == "date"
        assert type_map["time_field"] == "time"
        assert type_map["timedelta_field"] == "duration"
        assert type_map["uuid_field"] == "uuid"
        assert type_map["bytes_field"] == "binary"
        assert type_map["dict_field"] == "json"
        assert type_map["list_field"] == "list"

    def test_optional_resolved_correctly(self, adapter):
        fields_list = adapter.get_fields(BAllTypes)
        field_map = {f.name: f for f in fields_list}
        assert field_map["optional_str"].field_type == "string"
        assert field_map["optional_str"].nullable is True

    def test_python_type_map_complete(self):
        """Verify _PYTHON_TYPE_MAP covers all expected Python types."""
        expected = {
            int, str, float, bool, decimal.Decimal,
            datetime.datetime, datetime.date, datetime.time, datetime.timedelta,
            uuid.UUID, bytes, dict, list, set, tuple,
        }
        for t in expected:
            assert t in _PYTHON_TYPE_MAP, f"Python type '{t}' not in _PYTHON_TYPE_MAP"

    def test_resolve_type_edge_cases(self):
        assert _resolve_type(int) == "integer"
        assert _resolve_type(str) == "string"
        assert _resolve_type(str | None) == "string"
        assert _resolve_type(list[int]) == "list"
        assert _resolve_type(dict[str, int]) == "json"

    def test_requires_session_false(self, adapter):
        assert adapter.requires_session is False


# ── CRUD tests ──

class TestBeanieCRUD:
    async def test_create_and_retrieve(self, beanie_db, adapter):
        author = await adapter.create(BAuthor, None, name="Jane", bio="Writer")
        assert author.id is not None
        found = await adapter.get_object(BAuthor, None, id=author.id)
        assert found.name == "Jane"

    async def test_create_book(self, beanie_db, adapter):
        author = await adapter.create(BAuthor, None, name="Jane")
        book = await adapter.create(BBook, None, title="My Book", price=9.99, author_id=str(author.id))
        assert book.author_id == str(author.id)

    async def test_update(self, beanie_db, adapter):
        author = await adapter.create(BAuthor, None, name="Jane")
        updated = await adapter.update(author, None, name="Janet", bio="Updated bio")
        assert updated.name == "Janet"
        assert updated.bio == "Updated bio"

    async def test_delete(self, beanie_db, adapter):
        author = await adapter.create(BAuthor, None, name="ToDelete")
        aid = author.id
        await adapter.delete(author, None)
        found = await adapter.get_object(BAuthor, None, id=aid)
        assert found is None

    async def test_list_and_count(self, beanie_db, adapter):
        await adapter.create(BAuthor, None, name="A1")
        await adapter.create(BAuthor, None, name="A2")
        items = await adapter.get_queryset(BAuthor, None)
        assert len(items) >= 2
        count = await adapter.count(BAuthor, None)
        assert count >= 2

    async def test_exists(self, beanie_db, adapter):
        author = await adapter.create(BAuthor, None, name="Exists")
        assert await adapter.exists(BAuthor, None, id=author.id) is True

    async def test_filter_queryset(self, beanie_db, adapter):
        await adapter.create(BAuthor, None, name="FilterMe")
        await adapter.create(BAuthor, None, name="Other")
        results = await adapter.filter_queryset(BAuthor, None, name="FilterMe")
        assert len(results) == 1
        assert results[0].name == "FilterMe"

    async def test_get_object_not_found(self, beanie_db, adapter):
        from bson import ObjectId
        result = await adapter.get_object(BAuthor, None, id=ObjectId())
        assert result is None
