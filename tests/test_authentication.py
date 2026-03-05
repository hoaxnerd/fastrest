"""Tests for authentication backends."""

import base64

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request as FastAPIRequest
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from fastrest.authentication import (
    BaseAuthentication,
    BasicAuthentication,
    TokenAuthentication,
    SessionAuthentication,
)
from fastrest.exceptions import AuthenticationFailed
from fastrest.permissions import IsAuthenticated, AllowAny
from fastrest.serializers import ModelSerializer
from fastrest.viewsets import ModelViewSet
from fastrest.routers import DefaultRouter
from fastrest.test import APIClient


# --- Unit tests for authentication classes ---


class FakeRequest:
    def __init__(self, headers=None, session=None):
        self.headers = headers or {}
        if session is not None:
            self.session = session


class FakeUser:
    def __init__(self, id=1, username="testuser", is_staff=False):
        self.id = id
        self.username = username
        self.is_staff = is_staff

    def __bool__(self):
        return True


USERS_DB = {
    "admin": {"password": "secret", "user": FakeUser(id=1, username="admin")},
    "bob": {"password": "pass123", "user": FakeUser(id=2, username="bob")},
}

TOKENS_DB = {
    "valid-token-123": FakeUser(id=1, username="admin"),
    "bob-token-456": FakeUser(id=2, username="bob"),
}


def get_user_by_credentials(username, password):
    entry = USERS_DB.get(username)
    if entry and entry["password"] == password:
        return entry["user"]
    return None


def get_user_by_token(token_key):
    return TOKENS_DB.get(token_key)


class TestBaseAuthentication:
    def test_not_implemented(self):
        with pytest.raises(NotImplementedError):
            BaseAuthentication().authenticate(FakeRequest())

    def test_authenticate_header_returns_none(self):
        assert BaseAuthentication().authenticate_header(FakeRequest()) is None


class TestBasicAuthentication:
    def _make_auth_header(self, username, password):
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return f"Basic {encoded}"

    def test_valid_credentials(self):
        auth = BasicAuthentication(get_user_by_credentials=get_user_by_credentials)
        req = FakeRequest(headers={"authorization": self._make_auth_header("admin", "secret")})
        result = auth.authenticate(req)
        assert result is not None
        user, token = result
        assert user.username == "admin"
        assert token is None

    def test_invalid_credentials(self):
        auth = BasicAuthentication(get_user_by_credentials=get_user_by_credentials)
        req = FakeRequest(headers={"authorization": self._make_auth_header("admin", "wrong")})
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(req)

    def test_no_auth_header(self):
        auth = BasicAuthentication(get_user_by_credentials=get_user_by_credentials)
        req = FakeRequest(headers={})
        assert auth.authenticate(req) is None

    def test_non_basic_header(self):
        auth = BasicAuthentication(get_user_by_credentials=get_user_by_credentials)
        req = FakeRequest(headers={"authorization": "Token abc"})
        assert auth.authenticate(req) is None

    def test_malformed_base64(self):
        auth = BasicAuthentication(get_user_by_credentials=get_user_by_credentials)
        req = FakeRequest(headers={"authorization": "Basic !!!invalid!!!"})
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(req)

    def test_no_backend_configured(self):
        auth = BasicAuthentication()
        req = FakeRequest(headers={"authorization": self._make_auth_header("admin", "secret")})
        with pytest.raises(AuthenticationFailed, match="not configured"):
            auth.authenticate(req)

    def test_authenticate_header_value(self):
        auth = BasicAuthentication()
        assert auth.authenticate_header(FakeRequest()) == 'Basic realm="api"'


class TestTokenAuthentication:
    def test_valid_token(self):
        auth = TokenAuthentication(get_user_by_token=get_user_by_token)
        req = FakeRequest(headers={"authorization": "Token valid-token-123"})
        result = auth.authenticate(req)
        assert result is not None
        user, token = result
        assert user.username == "admin"
        assert token == "valid-token-123"

    def test_bearer_keyword(self):
        auth = TokenAuthentication(get_user_by_token=get_user_by_token, keyword="Bearer")
        req = FakeRequest(headers={"authorization": "Bearer valid-token-123"})
        result = auth.authenticate(req)
        assert result is not None
        assert result[0].username == "admin"

    def test_invalid_token(self):
        auth = TokenAuthentication(get_user_by_token=get_user_by_token)
        req = FakeRequest(headers={"authorization": "Token invalid-token"})
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(req)

    def test_no_auth_header(self):
        auth = TokenAuthentication(get_user_by_token=get_user_by_token)
        req = FakeRequest(headers={})
        assert auth.authenticate(req) is None

    def test_wrong_keyword(self):
        auth = TokenAuthentication(get_user_by_token=get_user_by_token)
        req = FakeRequest(headers={"authorization": "Basic abc"})
        assert auth.authenticate(req) is None

    def test_empty_token(self):
        auth = TokenAuthentication(get_user_by_token=get_user_by_token)
        req = FakeRequest(headers={"authorization": "Token "})
        with pytest.raises(AuthenticationFailed, match="No token"):
            auth.authenticate(req)

    def test_no_backend_configured(self):
        auth = TokenAuthentication()
        req = FakeRequest(headers={"authorization": "Token some-token"})
        with pytest.raises(AuthenticationFailed, match="not configured"):
            auth.authenticate(req)

    def test_authenticate_header_value(self):
        auth = TokenAuthentication()
        assert auth.authenticate_header(FakeRequest()) == "Token"

        auth2 = TokenAuthentication(keyword="Bearer")
        assert auth2.authenticate_header(FakeRequest()) == "Bearer"


class TestSessionAuthentication:
    def test_with_session_callback(self):
        def get_user(request):
            return FakeUser(id=42, username="session_user")

        auth = SessionAuthentication(get_user_from_session=get_user)
        result = auth.authenticate(FakeRequest())
        assert result is not None
        assert result[0].username == "session_user"

    def test_callback_returns_none(self):
        auth = SessionAuthentication(get_user_from_session=lambda r: None)
        assert auth.authenticate(FakeRequest()) is None

    def test_starlette_session_fallback(self):
        auth = SessionAuthentication()
        req = FakeRequest(session={"user_id": 99})
        result = auth.authenticate(req)
        assert result is not None
        assert result[0]["id"] == 99

    def test_no_session(self):
        auth = SessionAuthentication()
        req = FakeRequest()
        assert auth.authenticate(req) is None

    def test_authenticate_header_none(self):
        auth = SessionAuthentication()
        assert auth.authenticate_header(FakeRequest()) is None


# --- Integration tests: auth + viewset + router ---

class AuthTestBase(DeclarativeBase):
    pass


class Widget(AuthTestBase):
    __tablename__ = "widgets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    weight = Column(Float, nullable=False)


class WidgetSerializer(ModelSerializer):
    class Meta:
        model = Widget
        fields = ["id", "name", "weight"]
        read_only_fields = ["id"]


token_auth = TokenAuthentication(get_user_by_token=get_user_by_token)


class WidgetViewSet(ModelViewSet):
    serializer_class = WidgetSerializer
    queryset = Widget
    authentication_classes = [token_auth]
    permission_classes = [IsAuthenticated]


@pytest_asyncio.fixture
async def auth_app():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(AuthTestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    router = DefaultRouter()
    router.register("widgets", WidgetViewSet, basename="widget")
    app.include_router(router.urls)

    @app.middleware("http")
    async def inject_session(request: FastAPIRequest, call_next):
        async with session_factory() as session:
            async with session.begin():
                original_init = WidgetViewSet.__init__

                def patched_init(self, **kwargs):
                    original_init(self, **kwargs)
                    self._session = session

                WidgetViewSet.__init__ = patched_init
                try:
                    response = await call_next(request)
                finally:
                    WidgetViewSet.__init__ = original_init
                return response

    yield app
    await engine.dispose()


@pytest.fixture
def auth_client(auth_app):
    return APIClient(auth_app)


class TestAuthIntegration:
    async def test_unauthenticated_request_returns_401(self, auth_client):
        resp = await auth_client.get("/widgets")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, auth_client):
        resp = await auth_client.get("/widgets", headers={"Authorization": "Token bad-token"})
        assert resp.status_code == 401

    async def test_valid_token_allows_list(self, auth_client):
        resp = await auth_client.get("/widgets", headers={"Authorization": "Token valid-token-123"})
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_valid_token_allows_create(self, auth_client):
        resp = await auth_client.post(
            "/widgets",
            json={"name": "Gadget", "weight": 1.5},
            headers={"Authorization": "Token valid-token-123"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Gadget"

    async def test_valid_token_crud_flow(self, auth_client):
        headers = {"Authorization": "Token valid-token-123"}

        # Create
        resp = await auth_client.post("/widgets", json={"name": "Bolt", "weight": 0.1}, headers=headers)
        assert resp.status_code == 201
        pk = resp.json()["id"]

        # Retrieve
        resp = await auth_client.get(f"/widgets/{pk}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Bolt"

        # Update
        resp = await auth_client.put(f"/widgets/{pk}", json={"name": "Nut", "weight": 0.2}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Nut"

        # Delete
        resp = await auth_client.delete(f"/widgets/{pk}", headers=headers)
        assert resp.status_code == 204
