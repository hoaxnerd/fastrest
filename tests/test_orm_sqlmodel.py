"""Tests for the SQLModel ORM adapter."""

import pytest
import pytest_asyncio
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from fastrest.compat.orm.sqlmodel import SQLModelAdapter
from fastrest.compat.orm.base import FieldInfo
from tests.adapter_contract import AdapterContractTests


# ── Test models ──

class SMAuthor(SQLModel, table=True):
    __tablename__ = "sm_authors"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    bio: str | None = Field(default=None, max_length=500)
    is_active: bool = Field(default=True)
    books: list["SMBook"] = Relationship(back_populates="author")


class SMBook(SQLModel, table=True):
    __tablename__ = "sm_books"
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=300)
    price: float
    in_stock: bool = Field(default=True)
    author_id: int | None = Field(default=None, foreign_key="sm_authors.id")
    author: SMAuthor | None = Relationship(back_populates="books")


# ── Fixtures ──

@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture
def adapter():
    return SQLModelAdapter()


# ── Contract tests ──

class TestSQLModelAdapterContract(AdapterContractTests):
    expected_field_names = {"id", "name", "bio", "is_active"}
    create_kwargs = {"name": "Test Author", "bio": "A bio", "is_active": True}
    update_kwargs = {"name": "Updated Author"}
    nonexistent_lookup = {"id": 99999}
    filter_kwargs = {"name": "Test Author"}

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, adapter, session):
        self.adapter = adapter
        self.model = SMAuthor
        self.session = session


# ── Field introspection tests ──

class TestSQLModelFieldIntrospection:
    def test_author_fields(self, adapter):
        fields = adapter.get_fields(SMAuthor)
        field_map = {f.name: f for f in fields}

        assert "id" in field_map
        assert field_map["id"].primary_key is True
        assert field_map["id"].field_type == "integer"

        assert "name" in field_map
        assert field_map["name"].field_type == "string"

        assert "bio" in field_map
        assert field_map["bio"].nullable is True

        assert "is_active" in field_map
        assert field_map["is_active"].field_type == "boolean"

    def test_book_fields(self, adapter):
        fields = adapter.get_fields(SMBook)
        field_map = {f.name: f for f in fields}

        assert "title" in field_map
        assert field_map["title"].field_type == "string"

        assert "price" in field_map
        assert field_map["price"].field_type == "float"

        assert "in_stock" in field_map
        assert field_map["in_stock"].field_type == "boolean"

        assert "author_id" in field_map
        assert field_map["author_id"].field_type == "integer"

    def test_pk_field(self, adapter):
        pk = adapter.get_pk_field(SMAuthor)
        assert pk.name == "id"
        assert pk.primary_key is True

    def test_relations(self, adapter):
        rels = adapter.get_relations(SMAuthor)
        assert len(rels) >= 1
        rel_names = {r.name for r in rels}
        assert "books" in rel_names


# ── CRUD tests ──

class TestSQLModelCRUD:
    async def test_create_and_retrieve(self, adapter, session):
        author = await adapter.create(SMAuthor, session, name="Jane", bio="Writer")
        assert author.id is not None
        found = await adapter.get_object(SMAuthor, session, id=author.id)
        assert found.name == "Jane"

    async def test_create_with_fk(self, adapter, session):
        author = await adapter.create(SMAuthor, session, name="Jane")
        book = await adapter.create(SMBook, session, title="My Book", price=9.99, author_id=author.id)
        assert book.author_id == author.id

    async def test_update(self, adapter, session):
        author = await adapter.create(SMAuthor, session, name="Jane")
        updated = await adapter.update(author, session, name="Janet", bio="Updated bio")
        assert updated.name == "Janet"
        assert updated.bio == "Updated bio"

    async def test_delete(self, adapter, session):
        author = await adapter.create(SMAuthor, session, name="ToDelete")
        await adapter.delete(author, session)
        found = await adapter.get_object(SMAuthor, session, id=author.id)
        assert found is None

    async def test_list_and_count(self, adapter, session):
        await adapter.create(SMAuthor, session, name="A1")
        await adapter.create(SMAuthor, session, name="A2")
        items = await adapter.get_queryset(SMAuthor, session)
        assert len(items) >= 2
        count = await adapter.count(SMAuthor, session)
        assert count >= 2

    async def test_exists(self, adapter, session):
        author = await adapter.create(SMAuthor, session, name="Exists")
        assert await adapter.exists(SMAuthor, session, id=author.id) is True
        assert await adapter.exists(SMAuthor, session, id=99999) is False

    async def test_filter_queryset(self, adapter, session):
        await adapter.create(SMAuthor, session, name="FilterMe")
        await adapter.create(SMAuthor, session, name="Other")
        results = await adapter.filter_queryset(SMAuthor, session, name="FilterMe")
        assert len(results) == 1
        assert results[0].name == "FilterMe"


# ── Type mapping tests ──

class TestSQLModelTypeMapping:
    def test_all_expected_types_mapped(self, adapter):
        fields = adapter.get_fields(SMBook)
        type_map = {f.name: f.field_type for f in fields}
        assert type_map["id"] == "integer"
        assert type_map["title"] == "string"
        assert type_map["price"] == "float"
        assert type_map["in_stock"] == "boolean"
        assert type_map["author_id"] == "integer"

    def test_requires_session(self, adapter):
        # SQLModel uses SQLAlchemy sessions
        assert adapter.requires_session is True
