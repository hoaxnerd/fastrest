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


# --- Per-action OpenAPI metadata tests ---


class MetaItemSerializer(ModelSerializer):
    class Meta:
        model = Item
        fields = ["id", "name", "description", "price"]


class MetaItemViewSet(ModelViewSet):
    serializer_class = MetaItemSerializer
    queryset = Item
    openapi_meta = {
        "destroy": {"deprecated": True},
        "retrieve": {"responses": {404: {"description": "Item not found"}}},
        "list": {"description": "List all available items"},
    }


class NoMetaItemViewSet(ModelViewSet):
    serializer_class = MetaItemSerializer
    queryset = Item


def _build_openapi(viewset_cls, prefix="items", basename="item"):
    """Helper to build a FastAPI app and return its OpenAPI schema."""
    app = FastAPI()
    router = DefaultRouter()
    router.register(prefix, viewset_cls, basename=basename)
    app.include_router(router.urls)
    return app.openapi()


def test_openapi_meta_deprecated():
    """Viewset with openapi_meta marking destroy as deprecated should set deprecated on the DELETE endpoint."""
    schema = _build_openapi(MetaItemViewSet)
    delete_op = schema["paths"]["/items/{pk}"]["delete"]
    assert delete_op.get("deprecated") is True

    # Other endpoints should NOT be deprecated
    get_op = schema["paths"]["/items/{pk}"]["get"]
    assert get_op.get("deprecated") is not True


def test_openapi_meta_responses():
    """Viewset with openapi_meta responses should pass them through to the OpenAPI schema."""
    schema = _build_openapi(MetaItemViewSet)
    get_op = schema["paths"]["/items/{pk}"]["get"]
    assert "404" in get_op["responses"]
    assert get_op["responses"]["404"]["description"] == "Item not found"


def test_openapi_meta_description():
    """Viewset with openapi_meta description should override/set the endpoint description."""
    schema = _build_openapi(MetaItemViewSet)
    list_op = schema["paths"]["/items"]["get"]
    assert list_op.get("description") == "List all available items"


def test_viewset_without_openapi_meta():
    """Viewsets without openapi_meta should still work normally."""
    schema = _build_openapi(NoMetaItemViewSet)
    # All standard endpoints should exist
    assert "get" in schema["paths"]["/items"]
    assert "post" in schema["paths"]["/items"]
    assert "get" in schema["paths"]["/items/{pk}"]
    assert "put" in schema["paths"]["/items/{pk}"]
    assert "delete" in schema["paths"]["/items/{pk}"]

    # No deprecated flags
    delete_op = schema["paths"]["/items/{pk}"]["delete"]
    assert delete_op.get("deprecated") is not True
