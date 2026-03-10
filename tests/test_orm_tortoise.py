"""Tests for the Tortoise ORM adapter."""

import pytest
import pytest_asyncio
from tortoise import Tortoise, fields
from tortoise.models import Model

from fastrest.compat.orm.tortoise import TortoiseAdapter, _TYPE_MAP
from fastrest.compat.orm.base import FieldInfo, RelationInfo
from tests.adapter_contract import AdapterContractTests


# ── Test models ──

class TAuthor(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=200)
    bio = fields.TextField(null=True)
    is_active = fields.BooleanField(default=True)

    class Meta:
        table = "t_authors"


class TTag(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)

    class Meta:
        table = "t_tags"


class TBook(Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=300)
    price = fields.FloatField()
    in_stock = fields.BooleanField(default=True)
    author = fields.ForeignKeyField("models.TAuthor", related_name="books", null=True)
    tags = fields.ManyToManyField("models.TTag", related_name="books")

    class Meta:
        table = "t_books"


class TReview(Model):
    id = fields.IntField(pk=True)
    rating = fields.IntField()
    comment = fields.TextField(null=True)
    book = fields.ForeignKeyField("models.TBook", related_name="reviews")

    class Meta:
        table = "t_reviews"


# Model with diverse field types for type mapping tests
class TAllTypes(Model):
    id = fields.IntField(pk=True)
    big_int = fields.BigIntField()
    small_int = fields.SmallIntField()
    char = fields.CharField(max_length=50)
    text = fields.TextField()
    bool_field = fields.BooleanField()
    float_field = fields.FloatField()
    decimal_field = fields.DecimalField(max_digits=10, decimal_places=2)
    date_field = fields.DateField()
    datetime_field = fields.DatetimeField(auto_now_add=True)
    time_field = fields.TimeField()
    timedelta_field = fields.TimeDeltaField()
    json_field = fields.JSONField()
    uuid_field = fields.UUIDField()
    binary_field = fields.BinaryField()

    class Meta:
        table = "t_all_types"


# ── Fixtures ──

@pytest_asyncio.fixture
async def tortoise_db():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["tests.test_orm_tortoise"]},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.fixture
def adapter():
    return TortoiseAdapter()


# ── Contract tests ──

class TestTortoiseAdapterContract(AdapterContractTests):
    expected_field_names = {"id", "name", "bio", "is_active"}
    create_kwargs = {"name": "Test Author", "bio": "A bio", "is_active": True}
    update_kwargs = {"name": "Updated Author"}
    nonexistent_lookup = {"id": 99999}
    filter_kwargs = {"name": "Test Author"}

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, tortoise_db, adapter):
        self.adapter = adapter
        self.model = TAuthor
        self.session = None  # Tortoise doesn't use sessions


# ── Field introspection tests ──

class TestTortoiseFieldIntrospection:
    async def test_author_fields(self, tortoise_db, adapter):
        fields_list = adapter.get_fields(TAuthor)
        field_map = {f.name: f for f in fields_list}

        assert "id" in field_map
        assert field_map["id"].primary_key is True
        assert field_map["id"].field_type == "integer"

        assert "name" in field_map
        assert field_map["name"].field_type == "string"
        assert field_map["name"].max_length == 200

        assert "bio" in field_map
        assert field_map["bio"].field_type == "text"
        assert field_map["bio"].nullable is True

        assert "is_active" in field_map
        assert field_map["is_active"].field_type == "boolean"

    async def test_book_fields_include_fk(self, tortoise_db, adapter):
        fields_list = adapter.get_fields(TBook)
        field_map = {f.name: f for f in fields_list}

        assert "title" in field_map
        assert field_map["title"].field_type == "string"

        assert "price" in field_map
        assert field_map["price"].field_type == "float"

        # FK column should appear as author_id
        assert "author_id" in field_map

    async def test_pk_field(self, tortoise_db, adapter):
        pk = adapter.get_pk_field(TAuthor)
        assert pk.name == "id"
        assert pk.primary_key is True
        assert pk.field_type == "integer"

    async def test_relations(self, tortoise_db, adapter):
        rels = adapter.get_relations(TBook)
        rel_names = {r.name for r in rels}
        assert "author" in rel_names  # FK
        assert "tags" in rel_names  # M2M

        # Check relation types
        rel_map = {r.name: r for r in rels}
        assert rel_map["author"].relation_type == "many_to_one"
        assert rel_map["tags"].relation_type == "many_to_many"

    async def test_backward_relations(self, tortoise_db, adapter):
        rels = adapter.get_relations(TAuthor)
        rel_names = {r.name for r in rels}
        assert "books" in rel_names
        rel_map = {r.name: r for r in rels}
        assert rel_map["books"].relation_type == "one_to_many"
        assert rel_map["books"].reverse is True


# ── Comprehensive type mapping tests ──

class TestTortoiseTypeMapping:
    async def test_all_field_types(self, tortoise_db, adapter):
        fields_list = adapter.get_fields(TAllTypes)
        type_map = {f.name: f.field_type for f in fields_list}

        assert type_map["id"] == "integer"
        assert type_map["big_int"] == "integer"
        assert type_map["small_int"] == "integer"
        assert type_map["char"] == "string"
        assert type_map["text"] == "text"
        assert type_map["bool_field"] == "boolean"
        assert type_map["float_field"] == "float"
        assert type_map["decimal_field"] == "decimal"
        assert type_map["date_field"] == "date"
        assert type_map["datetime_field"] == "datetime"
        assert type_map["time_field"] == "time"
        assert type_map["timedelta_field"] == "duration"
        assert type_map["json_field"] == "json"
        assert type_map["uuid_field"] == "uuid"
        assert type_map["binary_field"] == "binary"

    def test_type_map_covers_all_tortoise_fields(self):
        """Verify _TYPE_MAP covers known Tortoise field types."""
        expected = {
            "IntField", "BigIntField", "SmallIntField", "IntEnumField",
            "CharField", "CharEnumField", "TextField",
            "BooleanField", "FloatField", "DecimalField",
            "DateField", "DatetimeField", "TimeField", "TimeDeltaField",
            "JSONField", "UUIDField", "BinaryField",
            "GeometryField", "TSVectorField",
        }
        for ft in expected:
            assert ft in _TYPE_MAP, f"Tortoise field type '{ft}' not in _TYPE_MAP"

    async def test_max_length_on_charfield(self, tortoise_db, adapter):
        fields_list = adapter.get_fields(TAllTypes)
        field_map = {f.name: f for f in fields_list}
        assert field_map["char"].max_length == 50

    def test_requires_session_false(self, adapter):
        assert adapter.requires_session is False


# ── CRUD tests ──

class TestTortoiseCRUD:
    async def test_create_and_retrieve(self, tortoise_db, adapter):
        author = await adapter.create(TAuthor, None, name="Jane", bio="Writer")
        assert author.id is not None
        found = await adapter.get_object(TAuthor, None, id=author.id)
        assert found.name == "Jane"

    async def test_create_with_fk(self, tortoise_db, adapter):
        author = await adapter.create(TAuthor, None, name="Jane")
        book = await adapter.create(TBook, None, title="My Book", price=9.99, author_id=author.id)
        assert book.author_id == author.id

    async def test_update(self, tortoise_db, adapter):
        author = await adapter.create(TAuthor, None, name="Jane")
        updated = await adapter.update(author, None, name="Janet", bio="Updated bio")
        assert updated.name == "Janet"
        assert updated.bio == "Updated bio"

    async def test_delete(self, tortoise_db, adapter):
        author = await adapter.create(TAuthor, None, name="ToDelete")
        aid = author.id
        await adapter.delete(author, None)
        found = await adapter.get_object(TAuthor, None, id=aid)
        assert found is None

    async def test_list_and_count(self, tortoise_db, adapter):
        await adapter.create(TAuthor, None, name="A1")
        await adapter.create(TAuthor, None, name="A2")
        items = await adapter.get_queryset(TAuthor, None)
        assert len(items) >= 2
        count = await adapter.count(TAuthor, None)
        assert count >= 2

    async def test_exists(self, tortoise_db, adapter):
        author = await adapter.create(TAuthor, None, name="Exists")
        assert await adapter.exists(TAuthor, None, id=author.id) is True
        assert await adapter.exists(TAuthor, None, id=99999) is False

    async def test_filter_queryset(self, tortoise_db, adapter):
        await adapter.create(TAuthor, None, name="FilterMe")
        await adapter.create(TAuthor, None, name="Other")
        results = await adapter.filter_queryset(TAuthor, None, name="FilterMe")
        assert len(results) == 1
        assert results[0].name == "FilterMe"

    async def test_get_object_not_found(self, tortoise_db, adapter):
        result = await adapter.get_object(TAuthor, None, id=99999)
        assert result is None
