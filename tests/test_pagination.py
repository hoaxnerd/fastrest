"""Tests for pagination backends."""

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request as FastAPIRequest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from fastrest.serializers import ModelSerializer
from fastrest.viewsets import ModelViewSet
from fastrest.routers import SimpleRouter
from fastrest.pagination import PageNumberPagination, LimitOffsetPagination
from fastrest.test import APIClient

from tests.conftest import Base, Item


class ItemSerializer(ModelSerializer):
    class Meta:
        model = Item
        fields = "__all__"


class SmallPagePagination(PageNumberPagination):
    page_size = 3
    max_page_size = 10


class SmallLimitOffset(LimitOffsetPagination):
    default_limit = 3
    max_limit = 10


class PagedItemViewSet(ModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item
    pagination_class = SmallPagePagination


class LimitOffsetItemViewSet(ModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item
    pagination_class = SmallLimitOffset


@pytest_asyncio.fixture
async def paged_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    router = SimpleRouter()
    router.register("items", PagedItemViewSet, basename="item")
    app.include_router(router.urls)

    @app.middleware("http")
    async def inject(request: FastAPIRequest, call_next):
        async with sf() as session:
            async with session.begin():
                orig = PagedItemViewSet.__init__
                def patched(self, **kw): orig(self, **kw); self._session = session
                PagedItemViewSet.__init__ = patched
                try:
                    resp = await call_next(request)
                finally:
                    PagedItemViewSet.__init__ = orig
                return resp

    client = APIClient(app)
    # Seed 10 items
    for i in range(1, 11):
        await client.post("/items", json={"name": f"Item {i}", "price": float(i)})
    yield client
    await engine.dispose()


@pytest_asyncio.fixture
async def lo_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    router = SimpleRouter()
    router.register("items", LimitOffsetItemViewSet, basename="item")
    app.include_router(router.urls)

    @app.middleware("http")
    async def inject(request: FastAPIRequest, call_next):
        async with sf() as session:
            async with session.begin():
                orig = LimitOffsetItemViewSet.__init__
                def patched(self, **kw): orig(self, **kw); self._session = session
                LimitOffsetItemViewSet.__init__ = patched
                try:
                    resp = await call_next(request)
                finally:
                    LimitOffsetItemViewSet.__init__ = orig
                return resp

    client = APIClient(app)
    for i in range(1, 11):
        await client.post("/items", json={"name": f"Item {i}", "price": float(i)})
    yield client
    await engine.dispose()


# --- PageNumberPagination tests ---

@pytest.mark.asyncio
async def test_page_number_first_page(paged_client):
    resp = await paged_client.get("/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 10
    assert len(data["results"]) == 3
    assert data["previous"] is None
    assert data["next"] is not None


@pytest.mark.asyncio
async def test_page_number_second_page(paged_client):
    resp = await paged_client.get("/items?page=2")
    data = resp.json()
    assert len(data["results"]) == 3
    assert data["previous"] is not None
    assert data["next"] is not None


@pytest.mark.asyncio
async def test_page_number_last_page(paged_client):
    resp = await paged_client.get("/items?page=4")
    data = resp.json()
    assert len(data["results"]) == 1  # 10 items, 3 per page, page 4 has 1
    assert data["next"] is None
    assert data["previous"] is not None


@pytest.mark.asyncio
async def test_page_number_out_of_range(paged_client):
    resp = await paged_client.get("/items?page=100")
    data = resp.json()
    assert data["count"] == 10
    assert len(data["results"]) == 0
    assert data["next"] is None


@pytest.mark.asyncio
async def test_page_size_override(paged_client):
    resp = await paged_client.get("/items?page_size=5")
    data = resp.json()
    assert len(data["results"]) == 5


@pytest.mark.asyncio
async def test_page_size_capped_by_max(paged_client):
    resp = await paged_client.get("/items?page_size=100")
    data = resp.json()
    assert len(data["results"]) == 10  # max_page_size=10, all 10 items fit


@pytest.mark.asyncio
async def test_envelope_structure(paged_client):
    resp = await paged_client.get("/items")
    data = resp.json()
    assert "count" in data
    assert "next" in data
    assert "previous" in data
    assert "results" in data
    assert isinstance(data["results"], list)


# --- LimitOffsetPagination tests ---

@pytest.mark.asyncio
async def test_limit_offset_default(lo_client):
    resp = await lo_client.get("/items")
    data = resp.json()
    assert data["count"] == 10
    assert len(data["results"]) == 3  # default_limit=3


@pytest.mark.asyncio
async def test_limit_offset_custom(lo_client):
    resp = await lo_client.get("/items?limit=5&offset=2")
    data = resp.json()
    assert len(data["results"]) == 5
    assert data["count"] == 10


@pytest.mark.asyncio
async def test_limit_offset_next_prev(lo_client):
    resp = await lo_client.get("/items?limit=3&offset=3")
    data = resp.json()
    assert data["previous"] is not None
    assert data["next"] is not None


@pytest.mark.asyncio
async def test_limit_offset_end(lo_client):
    resp = await lo_client.get("/items?limit=3&offset=9")
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["next"] is None


@pytest.mark.asyncio
async def test_limit_capped_by_max(lo_client):
    resp = await lo_client.get("/items?limit=100")
    data = resp.json()
    assert len(data["results"]) == 10  # max_limit=10


# --- No pagination ---

@pytest.mark.asyncio
async def test_no_pagination_returns_plain_list():
    """When pagination_class is None, list returns a plain array."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    class UnpagedViewSet(ModelViewSet):
        serializer_class = ItemSerializer
        queryset = Item

    app = FastAPI()
    router = SimpleRouter()
    router.register("items", UnpagedViewSet, basename="item")
    app.include_router(router.urls)

    @app.middleware("http")
    async def inject(request: FastAPIRequest, call_next):
        async with sf() as session:
            async with session.begin():
                orig = UnpagedViewSet.__init__
                def patched(self, **kw): orig(self, **kw); self._session = session
                UnpagedViewSet.__init__ = patched
                try:
                    resp = await call_next(request)
                finally:
                    UnpagedViewSet.__init__ = orig
                return resp

    client = APIClient(app)
    await client.post("/items", json={"name": "X", "price": 1.0})
    resp = await client.get("/items")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    await engine.dispose()
