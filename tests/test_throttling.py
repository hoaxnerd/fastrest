"""Tests for throttling backends."""

import time

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request as FastAPIRequest
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from fastrest.throttling import (
    BaseThrottle,
    SimpleRateThrottle,
    AnonRateThrottle,
    UserRateThrottle,
)
from fastrest.permissions import AllowAny
from fastrest.serializers import ModelSerializer
from fastrest.viewsets import ModelViewSet
from fastrest.routers import DefaultRouter
from fastrest.test import APIClient


# --- Unit tests ---


class FakeRequest:
    def __init__(self, user=None, headers=None):
        self.user = user
        self.headers = headers or {}
        self.client = type("Client", (), {"host": "127.0.0.1"})()


class FakeUser:
    def __init__(self, id=1):
        self.id = id

    def __bool__(self):
        return True


class TestBaseThrottle:
    def test_not_implemented(self):
        with pytest.raises(NotImplementedError):
            BaseThrottle().allow_request(FakeRequest(), None)

    def test_wait_returns_none(self):
        assert BaseThrottle().wait() is None

    def test_get_ident_from_client(self):
        req = FakeRequest()
        assert BaseThrottle().get_ident(req) == "127.0.0.1"

    def test_get_ident_from_xff(self):
        req = FakeRequest(headers={"x-forwarded-for": "10.0.0.1, 10.0.0.2"})
        assert BaseThrottle().get_ident(req) == "10.0.0.1"


class ThreePerMinute(SimpleRateThrottle):
    rate = "3/min"

    def get_cache_key(self, request, view):
        return f"test_{self.get_ident(request)}"


class TestSimpleRateThrottle:
    def setup_method(self):
        ThreePerMinute.cache.clear()

    def test_allows_under_limit(self):
        throttle = ThreePerMinute()
        req = FakeRequest()
        assert throttle.allow_request(req, None) is True
        assert throttle.allow_request(req, None) is True
        assert throttle.allow_request(req, None) is True

    def test_blocks_over_limit(self):
        throttle = ThreePerMinute()
        req = FakeRequest()
        for _ in range(3):
            throttle.allow_request(req, None)
        assert throttle.allow_request(req, None) is False

    def test_wait_returns_value(self):
        throttle = ThreePerMinute()
        req = FakeRequest()
        for _ in range(3):
            throttle.allow_request(req, None)
        throttle.allow_request(req, None)
        assert throttle.wait() is not None
        assert throttle.wait() > 0

    def test_none_cache_key_always_allows(self):
        class NoKeyThrottle(SimpleRateThrottle):
            rate = "1/min"
            def get_cache_key(self, request, view):
                return None

        throttle = NoKeyThrottle()
        req = FakeRequest()
        for _ in range(10):
            assert throttle.allow_request(req, None) is True

    def test_parse_rate_periods(self):
        throttle = ThreePerMinute()
        assert throttle.parse_rate("10/s") == (10, 1)
        assert throttle.parse_rate("10/sec") == (10, 1)
        assert throttle.parse_rate("10/m") == (10, 60)
        assert throttle.parse_rate("10/min") == (10, 60)
        assert throttle.parse_rate("10/h") == (10, 3600)
        assert throttle.parse_rate("10/hour") == (10, 3600)
        assert throttle.parse_rate("10/d") == (10, 86400)
        assert throttle.parse_rate("10/day") == (10, 86400)

    def test_parse_rate_invalid_period(self):
        throttle = ThreePerMinute()
        with pytest.raises(ValueError, match="Unknown rate period"):
            throttle.parse_rate("10/week")

    def test_no_rate_raises(self):
        class NoRate(SimpleRateThrottle):
            def get_cache_key(self, request, view):
                return "key"

        throttle = NoRate()
        with pytest.raises(ValueError, match="No rate set"):
            throttle.allow_request(FakeRequest(), None)

    def test_scope_based_rate(self):
        class ScopedThrottle(SimpleRateThrottle):
            scope = "test"
            THROTTLE_RATES = {"test": "5/min"}
            def get_cache_key(self, request, view):
                return "scoped_key"

        throttle = ScopedThrottle()
        assert throttle.allow_request(FakeRequest(), None) is True

    def test_separate_caches_per_subclass(self):
        class ThrottleA(SimpleRateThrottle):
            rate = "2/min"
            def get_cache_key(self, request, view):
                return "shared_key"

        class ThrottleB(SimpleRateThrottle):
            rate = "2/min"
            def get_cache_key(self, request, view):
                return "shared_key"

        req = FakeRequest()
        a = ThrottleA()
        b = ThrottleB()
        a.allow_request(req, None)
        a.allow_request(req, None)
        assert a.allow_request(req, None) is False
        # B should have its own cache
        assert b.allow_request(req, None) is True


class TestAnonRateThrottle:
    def setup_method(self):
        AnonRateThrottle.cache.clear()

    def test_throttles_anonymous(self):
        AnonRateThrottle.rate = "2/min"
        throttle = AnonRateThrottle()
        req = FakeRequest(user=None)
        assert throttle.allow_request(req, None) is True
        assert throttle.allow_request(req, None) is True
        assert throttle.allow_request(req, None) is False

    def test_skips_authenticated(self):
        AnonRateThrottle.rate = "1/min"
        throttle = AnonRateThrottle()
        req = FakeRequest(user=FakeUser())
        for _ in range(10):
            assert throttle.allow_request(req, None) is True


class TestUserRateThrottle:
    def setup_method(self):
        UserRateThrottle.cache.clear()

    def test_throttles_by_user_id(self):
        UserRateThrottle.rate = "2/min"
        throttle = UserRateThrottle()
        req = FakeRequest(user=FakeUser(id=1))
        assert throttle.allow_request(req, None) is True
        assert throttle.allow_request(req, None) is True
        assert throttle.allow_request(req, None) is False

    def test_different_users_separate(self):
        UserRateThrottle.rate = "2/min"
        throttle = UserRateThrottle()
        req1 = FakeRequest(user=FakeUser(id=1))
        req2 = FakeRequest(user=FakeUser(id=2))
        throttle.allow_request(req1, None)
        throttle.allow_request(req1, None)
        assert throttle.allow_request(req1, None) is False
        assert throttle.allow_request(req2, None) is True

    def test_anonymous_throttled_by_ip(self):
        UserRateThrottle.rate = "2/min"
        throttle = UserRateThrottle()
        req = FakeRequest(user=None)
        assert throttle.allow_request(req, None) is True
        assert throttle.allow_request(req, None) is True
        assert throttle.allow_request(req, None) is False


# --- Integration test: throttling + viewset ---

class ThrottleTestBase(DeclarativeBase):
    pass


class Gizmo(ThrottleTestBase):
    __tablename__ = "gizmos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)


class GizmoSerializer(ModelSerializer):
    class Meta:
        model = Gizmo
        fields = ["id", "name"]
        read_only_fields = ["id"]


class TwoPerMinuteThrottle(SimpleRateThrottle):
    rate = "2/min"

    def get_cache_key(self, request, view):
        return f"gizmo_{self.get_ident(request)}"


class GizmoViewSet(ModelViewSet):
    serializer_class = GizmoSerializer
    queryset = Gizmo
    permission_classes = [AllowAny]
    throttle_classes = [TwoPerMinuteThrottle]


@pytest_asyncio.fixture
async def throttle_app():
    TwoPerMinuteThrottle.cache.clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ThrottleTestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    router = DefaultRouter()
    router.register("gizmos", GizmoViewSet, basename="gizmo")
    app.include_router(router.urls)

    @app.middleware("http")
    async def inject_session(request: FastAPIRequest, call_next):
        async with session_factory() as session:
            async with session.begin():
                original_init = GizmoViewSet.__init__

                def patched_init(self, **kwargs):
                    original_init(self, **kwargs)
                    self._session = session

                GizmoViewSet.__init__ = patched_init
                try:
                    response = await call_next(request)
                finally:
                    GizmoViewSet.__init__ = original_init
                return response

    yield app
    await engine.dispose()


@pytest.fixture
def throttle_client(throttle_app):
    return APIClient(throttle_app)


class TestThrottleIntegration:
    async def test_allows_under_limit(self, throttle_client):
        resp = await throttle_client.get("/gizmos")
        assert resp.status_code == 200

        resp = await throttle_client.get("/gizmos")
        assert resp.status_code == 200

    async def test_blocks_over_limit(self, throttle_client):
        await throttle_client.get("/gizmos")
        await throttle_client.get("/gizmos")
        resp = await throttle_client.get("/gizmos")
        assert resp.status_code == 429

    async def test_throttle_response_has_retry_after(self, throttle_client):
        await throttle_client.get("/gizmos")
        await throttle_client.get("/gizmos")
        resp = await throttle_client.get("/gizmos")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
