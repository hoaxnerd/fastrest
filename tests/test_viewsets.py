import pytest
import pytest_asyncio
from fastapi import FastAPI, Request as FastAPIRequest
from starlette.requests import Request as StarletteRequest

from fastrest.serializers import ModelSerializer
from fastrest.viewsets import ModelViewSet
from fastrest.routers import DefaultRouter
from fastrest.decorators import action
from fastrest.response import Response
from fastrest.test import APIClient
from tests.conftest import Item, Base

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


class ItemSerializer(ModelSerializer):
    class Meta:
        model = Item
        fields = ["id", "name", "description", "price"]


class ItemViewSet(ModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item

    @action(methods=["get"], detail=False)
    async def featured(self, request, **kwargs):
        return Response(data=[], status=200)


@pytest_asyncio.fixture
async def setup_app():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    router = DefaultRouter()
    router.register("items", ItemViewSet, basename="item")
    app.include_router(router.urls)

    # Middleware to inject session into viewset
    @app.middleware("http")
    async def inject_session(request: FastAPIRequest, call_next):
        async with session_factory() as session:
            async with session.begin():
                request.state.db_session = session
                # Monkey-patch the viewset to use session
                orig_as_view = ItemViewSet.as_view

                original_init = ItemViewSet.__init__

                def patched_init(self, **kwargs):
                    original_init(self, **kwargs)
                    self._session = session

                ItemViewSet.__init__ = patched_init
                try:
                    response = await call_next(request)
                finally:
                    ItemViewSet.__init__ = original_init
                return response

    client = APIClient(app)
    yield client, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_item(setup_app):
    client, _ = setup_app
    resp = await client.post("/items", json={"name": "Widget", "price": 9.99})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Widget"
    assert data["price"] == 9.99
    assert "id" in data


@pytest.mark.asyncio
async def test_list_items(setup_app):
    client, _ = setup_app
    await client.post("/items", json={"name": "A", "price": 1.0})
    await client.post("/items", json={"name": "B", "price": 2.0})
    resp = await client.get("/items")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_retrieve_item(setup_app):
    client, _ = setup_app
    create_resp = await client.post("/items", json={"name": "C", "price": 3.0})
    item_id = create_resp.json()["id"]
    resp = await client.get(f"/items/{item_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "C"


@pytest.mark.asyncio
async def test_update_item(setup_app):
    client, _ = setup_app
    create_resp = await client.post("/items", json={"name": "D", "price": 4.0})
    item_id = create_resp.json()["id"]
    resp = await client.put(f"/items/{item_id}", json={"name": "D Updated", "price": 4.5})
    assert resp.status_code == 200
    assert resp.json()["name"] == "D Updated"


@pytest.mark.asyncio
async def test_delete_item(setup_app):
    client, _ = setup_app
    create_resp = await client.post("/items", json={"name": "E", "price": 5.0})
    item_id = create_resp.json()["id"]
    resp = await client.delete(f"/items/{item_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_custom_action(setup_app):
    client, _ = setup_app
    resp = await client.get("/items/featured")
    assert resp.status_code == 200
