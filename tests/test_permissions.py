from fastrest.permissions import (
    AllowAny, IsAuthenticated, IsAdminUser, IsAuthenticatedOrReadOnly,
    BasePermission, HasScope,
)


class FakeRequest:
    def __init__(self, user=None, method="GET"):
        self.user = user
        self.method = method


class FakeUser:
    def __init__(self, is_staff=False):
        self.is_staff = is_staff

    def __bool__(self):
        return True


class FakeAuth:
    def __init__(self, scopes=None):
        self.scopes = scopes or []


class TestAllowAny:
    def test_allows(self):
        assert AllowAny().has_permission(FakeRequest(), None) is True


class TestIsAuthenticated:
    def test_authenticated(self):
        req = FakeRequest(user=FakeUser())
        assert IsAuthenticated().has_permission(req, None) is True

    def test_unauthenticated(self):
        req = FakeRequest(user=None)
        assert IsAuthenticated().has_permission(req, None) is False


class TestIsAdminUser:
    def test_admin(self):
        req = FakeRequest(user=FakeUser(is_staff=True))
        assert IsAdminUser().has_permission(req, None) is True

    def test_non_admin(self):
        req = FakeRequest(user=FakeUser(is_staff=False))
        assert IsAdminUser().has_permission(req, None) is False


class TestIsAuthenticatedOrReadOnly:
    def test_read_unauthenticated(self):
        req = FakeRequest(user=None, method="GET")
        assert IsAuthenticatedOrReadOnly().has_permission(req, None) is True

    def test_write_unauthenticated(self):
        req = FakeRequest(user=None, method="POST")
        assert IsAuthenticatedOrReadOnly().has_permission(req, None) is False

    def test_write_authenticated(self):
        req = FakeRequest(user=FakeUser(), method="POST")
        assert IsAuthenticatedOrReadOnly().has_permission(req, None) is True


class TestComposition:
    def test_and(self):
        perm = IsAuthenticated() & IsAdminUser()
        req = FakeRequest(user=FakeUser(is_staff=True))
        assert perm.has_permission(req, None) is True

        req2 = FakeRequest(user=FakeUser(is_staff=False))
        assert perm.has_permission(req2, None) is False

    def test_or(self):
        perm = IsAuthenticated() | IsAdminUser()
        req = FakeRequest(user=FakeUser(is_staff=False))
        assert perm.has_permission(req, None) is True

    def test_not(self):
        perm = ~IsAuthenticated()
        req = FakeRequest(user=None)
        assert perm.has_permission(req, None) is True

        req2 = FakeRequest(user=FakeUser())
        assert perm.has_permission(req2, None) is False


class TestHasScope:
    def test_no_scopes_required_allows(self):
        perm = HasScope()
        req = FakeRequest(user=FakeUser())
        req.auth = FakeAuth(scopes=[])
        assert perm.has_permission(req, None) is True

    def test_matching_scopes_allows(self):
        perm = HasScope("books:read")
        req = FakeRequest(user=FakeUser())
        req.auth = FakeAuth(scopes=["books:read", "books:write"])
        assert perm.has_permission(req, None) is True

    def test_missing_scope_denies(self):
        perm = HasScope("books:write")
        req = FakeRequest(user=FakeUser())
        req.auth = FakeAuth(scopes=["books:read"])
        assert perm.has_permission(req, None) is False

    def test_multiple_required_scopes(self):
        perm = HasScope("books:read", "books:write")
        req = FakeRequest(user=FakeUser())
        req.auth = FakeAuth(scopes=["books:read"])
        assert perm.has_permission(req, None) is False

        req.auth = FakeAuth(scopes=["books:read", "books:write"])
        assert perm.has_permission(req, None) is True

    def test_no_auth_on_request_denies(self):
        perm = HasScope("books:read")
        req = FakeRequest(user=FakeUser())
        # req.auth is None by default (no auth attribute)
        assert perm.has_permission(req, None) is False

    def test_composition_with_is_authenticated(self):
        perm = IsAuthenticated() & HasScope("admin")
        req = FakeRequest(user=FakeUser())
        req.auth = FakeAuth(scopes=["admin"])
        assert perm.has_permission(req, None) is True

        req2 = FakeRequest(user=None)
        req2.auth = FakeAuth(scopes=["admin"])
        assert perm.has_permission(req2, None) is False
