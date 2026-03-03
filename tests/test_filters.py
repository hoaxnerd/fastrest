"""Tests for filter backends."""

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request as FastAPIRequest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from fastrest.serializers import ModelSerializer
from fastrest.viewsets import ModelViewSet
from fastrest.routers import SimpleRouter
from fastrest.pagination import PageNumberPagination
from fastrest.filters import SearchFilter, OrderingFilter
from fastrest.test import APIClient

from tests.conftest import Base, Item


class ItemSerializer(ModelSerializer):
    class Meta:
        model = Item
        fields = "__all__"


class SmallPage(PageNumberPagination):
    page_size = 5


class FilteredItemViewSet(ModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "price"]
    ordering = ["name"]


class FilteredPagedViewSet(ModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item
    pagination_class = SmallPage
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "price"]


@pytest_asyncio.fixture
async def filtered_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    router = SimpleRouter()
    router.register("items", FilteredItemViewSet, basename="item")
    app.include_router(router.urls)

    @app.middleware("http")
    async def inject(request: FastAPIRequest, call_next):
        async with sf() as session:
            async with session.begin():
                orig = FilteredItemViewSet.__init__
                def patched(self, **kw): orig(self, **kw); self._session = session
                FilteredItemViewSet.__init__ = patched
                try:
                    resp = await call_next(request)
                finally:
                    FilteredItemViewSet.__init__ = orig
                return resp

    client = APIClient(app)
    # Seed items
    items = [
        {"name": "Alpha Widget", "description": "A great widget", "price": 30.0},
        {"name": "Beta Gadget", "description": "A cool gadget", "price": 10.0},
        {"name": "Gamma Widget", "description": "Another widget", "price": 20.0},
        {"name": "Delta Tool", "description": "A useful tool", "price": 50.0},
        {"name": "Alpha Tool", "description": "Best alpha tool", "price": 5.0},
    ]
    for item in items:
        await client.post("/items", json=item)
    yield client
    await engine.dispose()


@pytest_asyncio.fixture
async def combo_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    router = SimpleRouter()
    router.register("items", FilteredPagedViewSet, basename="item")
    app.include_router(router.urls)

    @app.middleware("http")
    async def inject(request: FastAPIRequest, call_next):
        async with sf() as session:
            async with session.begin():
                orig = FilteredPagedViewSet.__init__
                def patched(self, **kw): orig(self, **kw); self._session = session
                FilteredPagedViewSet.__init__ = patched
                try:
                    resp = await call_next(request)
                finally:
                    FilteredPagedViewSet.__init__ = orig
                return resp

    client = APIClient(app)
    for i in range(1, 13):
        await client.post("/items", json={"name": f"Item {i:02d}", "price": float(i)})
    yield client
    await engine.dispose()


# --- SearchFilter tests ---

@pytest.mark.asyncio
async def test_search_by_name(filtered_client):
    resp = await filtered_client.get("/items?search=widget")
    data = resp.json()
    assert len(data) == 2
    names = [d["name"] for d in data]
    assert "Alpha Widget" in names
    assert "Gamma Widget" in names


@pytest.mark.asyncio
async def test_search_by_description(filtered_client):
    resp = await filtered_client.get("/items?search=cool")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Beta Gadget"


@pytest.mark.asyncio
async def test_search_case_insensitive(filtered_client):
    resp = await filtered_client.get("/items?search=ALPHA")
    data = resp.json()
    assert len(data) == 2  # Alpha Widget + Alpha Tool


@pytest.mark.asyncio
async def test_search_no_match(filtered_client):
    resp = await filtered_client.get("/items?search=nonexistent")
    data = resp.json()
    assert len(data) == 0


@pytest.mark.asyncio
async def test_no_search_returns_all(filtered_client):
    resp = await filtered_client.get("/items")
    data = resp.json()
    assert len(data) == 5


# --- OrderingFilter tests ---

@pytest.mark.asyncio
async def test_ordering_asc(filtered_client):
    resp = await filtered_client.get("/items?ordering=price")
    data = resp.json()
    prices = [d["price"] for d in data]
    assert prices == sorted(prices)


@pytest.mark.asyncio
async def test_ordering_desc(filtered_client):
    resp = await filtered_client.get("/items?ordering=-price")
    data = resp.json()
    prices = [d["price"] for d in data]
    assert prices == sorted(prices, reverse=True)


@pytest.mark.asyncio
async def test_ordering_by_name(filtered_client):
    resp = await filtered_client.get("/items?ordering=name")
    data = resp.json()
    names = [d["name"] for d in data]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_default_ordering(filtered_client):
    """Default ordering is ['name'] on FilteredItemViewSet."""
    resp = await filtered_client.get("/items")
    data = resp.json()
    names = [d["name"] for d in data]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_ordering_fields_whitelist(filtered_client):
    """Ordering by a field not in ordering_fields is ignored."""
    resp = await filtered_client.get("/items?ordering=description")
    data = resp.json()
    # description is not in ordering_fields, so it's skipped
    assert len(data) == 5  # all items returned, just no custom sorting


# --- Combined search + ordering ---

@pytest.mark.asyncio
async def test_search_and_ordering(filtered_client):
    resp = await filtered_client.get("/items?search=alpha&ordering=-price")
    data = resp.json()
    assert len(data) == 2
    assert data[0]["price"] > data[1]["price"]


# --- Combined search + ordering + pagination ---

@pytest.mark.asyncio
async def test_search_with_pagination(combo_client):
    resp = await combo_client.get("/items?search=Item&page_size=3")
    data = resp.json()
    assert data["count"] == 12
    assert len(data["results"]) == 3
    assert data["next"] is not None


@pytest.mark.asyncio
async def test_ordering_with_pagination(combo_client):
    resp = await combo_client.get("/items?ordering=-price")
    data = resp.json()
    prices = [d["price"] for d in data["results"]]
    assert prices == sorted(prices, reverse=True)
