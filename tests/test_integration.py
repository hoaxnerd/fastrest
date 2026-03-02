"""End-to-end integration test: model → serializer → viewset → router → HTTP."""

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request as FastAPIRequest
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from fastrest.serializers import ModelSerializer
from fastrest.viewsets import ModelViewSet
from fastrest.routers import DefaultRouter
from fastrest.test import APIClient


class TestBase(DeclarativeBase):
    pass


class Book(TestBase):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False)
    author = Column(String(200), nullable=False)
    price = Column(Float, nullable=False)


class BookSerializer(ModelSerializer):
    class Meta:
        model = Book
        fields = ["id", "title", "author", "price"]


class BookViewSet(ModelViewSet):
    serializer_class = BookSerializer
    queryset = Book


@pytest_asyncio.fixture
async def integration_app():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    router = DefaultRouter()
    router.register("books", BookViewSet, basename="book")
    app.include_router(router.urls)

    @app.middleware("http")
    async def inject_session(request: FastAPIRequest, call_next):
        async with session_factory() as session:
            async with session.begin():
                original_init = BookViewSet.__init__

                def patched_init(self, **kwargs):
                    original_init(self, **kwargs)
                    self._session = session

                BookViewSet.__init__ = patched_init
                try:
                    response = await call_next(request)
                finally:
                    BookViewSet.__init__ = original_init
                return response

    yield APIClient(app)
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_crud(integration_app):
    client = integration_app

    # Create
    resp = await client.post("/books", json={
        "title": "The Pragmatic Programmer",
        "author": "Hunt & Thomas",
        "price": 49.99,
    })
    assert resp.status_code == 201
    book = resp.json()
    assert book["title"] == "The Pragmatic Programmer"
    book_id = book["id"]

    # List
    resp = await client.get("/books")
    assert resp.status_code == 200
    books = resp.json()
    assert len(books) == 1

    # Retrieve
    resp = await client.get(f"/books/{book_id}")
    assert resp.status_code == 200
    assert resp.json()["author"] == "Hunt & Thomas"

    # Update
    resp = await client.put(f"/books/{book_id}", json={
        "title": "The Pragmatic Programmer (20th Anniversary)",
        "author": "Hunt & Thomas",
        "price": 54.99,
    })
    assert resp.status_code == 200
    assert "20th Anniversary" in resp.json()["title"]

    # Partial update
    resp = await client.patch(f"/books/{book_id}", json={"price": 39.99})
    assert resp.status_code == 200
    assert resp.json()["price"] == 39.99

    # Delete
    resp = await client.delete(f"/books/{book_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = await client.get(f"/books/{book_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_root(integration_app):
    client = integration_app
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "books" in data


@pytest.mark.asyncio
async def test_create_validation(integration_app):
    client = integration_app
    # Missing required fields — FastAPI returns 422 for Pydantic validation errors
    resp = await client.post("/books", json={})
    assert resp.status_code == 422
