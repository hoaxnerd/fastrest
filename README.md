<p align="center">
  <img src=".github/banner.png" alt="FastREST" width="600">
</p>

<p align="center">
  <a href="https://github.com/hoaxnerd/fastrest/actions/workflows/ci.yml"><img src="https://github.com/hoaxnerd/fastrest/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/fastrest/"><img src="https://img.shields.io/pypi/v/fastrest" alt="PyPI"></a>
  <a href="https://pypi.org/project/fastrest/"><img src="https://img.shields.io/pypi/pyversions/fastrest" alt="Python"></a>
  <a href="https://github.com/hoaxnerd/fastrest/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hoaxnerd/fastrest" alt="License"></a>
</p>

# FastREST

**The REST framework that speaks to AI agents out of the box.**

FastREST builds async REST APIs from your models and auto-generates MCP tools, agent skill documents, and structured API manifests — so both humans and AI agents can consume your API without extra work.

Built on FastAPI + Pydantic. Inspired by Django REST Framework. Works with SQLAlchemy, Tortoise ORM, SQLModel, and Beanie (MongoDB).

```python
router.serve(Model)  # SQLAlchemy, Tortoise, SQLModel, or Beanie — any ORM model
```

```bash
pip install fastrest[sqlalchemy]  # or fastrest[tortoise], fastrest[sqlmodel], fastrest[beanie]
```

That one line gives you:

| Endpoint | What it does |
|----------|-------------|
| `GET /api/authors` | List, search, paginate, order |
| `POST /api/authors` | Create with validated fields |
| `GET /api/authors/{pk}` | Retrieve by primary key |
| `PUT/PATCH /api/authors/{pk}` | Full or partial update |
| `DELETE /api/authors/{pk}` | Delete (204) |
| `GET /api/SKILL.md` | Agent-readable API documentation |
| `GET /api/authors/SKILL.md` | Per-resource agent docs |
| `GET /api/manifest.json` | Structured API metadata (JSON) |
| `GET /api/mcp` | MCP server with auto-generated tools |
| `GET /api/` | API root listing all resources |
| `GET /docs` | Swagger UI with typed schemas |

> **Status:** Beta (0.1.4). Core API is stable across serializers, viewsets, routers, permissions, pagination, filtering, auth, throttling, content negotiation, and agent integration.

---

## Multi-ORM Support

Use any Python ORM. FastREST adapts automatically:

| ORM | Install | Session Required | Auto-Detected |
|-----|---------|-----------------|---------------|
| **SQLAlchemy** | `pip install fastrest[sqlalchemy]` | Yes | Yes (default) |
| **Tortoise ORM** | `pip install fastrest[tortoise]` | No | Yes |
| **SQLModel** | `pip install fastrest[sqlmodel]` | Yes | No* |
| **Beanie** (MongoDB) | `pip install fastrest[beanie]` | No | Yes |

\* SQLModel co-installs SQLAlchemy, so auto-detection picks SQLAlchemy. Set the adapter explicitly:

```python
from fastrest.compat.orm import set_default_adapter
from fastrest.compat.orm.sqlmodel import SQLModelAdapter
set_default_adapter(SQLModelAdapter())
```

### Any ORM, Same API

The same `router.serve()` and `ModelViewSet` patterns work regardless of your ORM:

```python
# SQLAlchemy
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Author(Base):
    __tablename__ = "authors"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
```

```python
# Tortoise ORM — no session middleware needed
from tortoise.models import Model
from tortoise import fields

class Author(Model):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=200)
    class Meta:
        table = "authors"
```

```python
# SQLModel
from sqlmodel import SQLModel, Field

class Author(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
```

```python
# Beanie (MongoDB) — auto-detects string PK
from beanie import Document

class Author(Document):
    name: str
    class Settings:
        name = "authors"
```

```python
# Same code for all of them
router = DefaultRouter()
router.serve(Author)
```

**Tortoise ORM** and **Beanie** don't require session injection middleware — they manage connections internally.

**Custom adapters**: Subclass `ORMAdapter` from `fastrest.compat.orm.base` and call `set_default_adapter()`.

---

## AI Agent Integration

FastREST is the first REST framework with **built-in agent support**. Define your viewsets once, and agents can discover and use your API automatically.

### MCP Server — Tools for AI Agents

Mount a [Model Context Protocol](https://modelcontextprotocol.io) server with one line. Every viewset action becomes an MCP tool that agents can call directly:

```python
from fastrest.mcp import mount_mcp

mount_mcp(app, router)
# Auto-generates tools: authors_list, authors_create, authors_retrieve,
#                        books_list, books_create, books_retrieve, ...
```

MCP tools run through the **full request pipeline** — authentication, permissions, and throttling all apply to agent tool calls, exactly like HTTP requests. No separate auth layer to maintain.

```python
# Exclude specific actions from MCP
class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer

    @action(methods=["post"], detail=True, mcp=False)  # hidden from MCP
    async def internal_sync(self, request, **kwargs):
        ...
```

Configure via settings:

```python
configure(app, {
    "MCP_ENABLED": True,
    "MCP_PREFIX": "/mcp",
    "MCP_TOOL_NAME_FORMAT": "{basename}_{action}",
    "MCP_EXCLUDE_VIEWSETS": ["InternalViewSet"],
})
```

### SKILL.md — API Documentation for Agents

FastREST auto-generates Markdown skill documents that AI agents can read to understand your API. Includes fields, types, constraints, endpoints, query parameters, auth requirements, and example requests:

```
GET /api/SKILL.md            → Full API skill document
GET /api/books/SKILL.md      → Per-resource skill document
```

The output is a living spec — it regenerates from your code on every request, so it's always in sync with your actual API.

```python
# Customize what agents see per-viewset
class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer
    skill_description = "Manage the book catalog. Supports search by title and ordering by price."
    skill_exclude_actions = ["destroy"]          # hide delete from agents
    skill_exclude_fields = ["internal_notes"]    # hide sensitive fields
    skill_examples = [
        {
            "description": "Search for Python books",
            "request": "GET /books?search=python",
            "response": "200"
        }
    ]
```

Configure via settings:

```python
configure(app, {
    "SKILL_ENABLED": True,
    "SKILL_NAME": "bookstore-api",
    "SKILL_BASE_URL": "https://api.example.com",
    "SKILL_DESCRIPTION": "A bookstore API with full CRUD and search.",
    "SKILL_AUTH_DESCRIPTION": "Use Bearer token in the Authorization header.",
    "SKILL_INCLUDE_EXAMPLES": True,
    "SKILL_MAX_EXAMPLES_PER_RESOURCE": 3,
})
```

### API Manifest — Machine-Readable Metadata

A structured JSON endpoint at `GET /manifest.json` that describes your entire API:

```json
{
  "version": "1.0",
  "name": "bookstore-api",
  "base_url": "https://api.example.com",
  "resources": [
    {
      "name": "book",
      "prefix": "books",
      "actions": ["list", "create", "retrieve", "update", "partial_update", "destroy", "in_stock"],
      "fields": [
        {"name": "id", "type": "integer", "read_only": true},
        {"name": "title", "type": "string", "max_length": 300, "required": true},
        {"name": "price", "type": "float", "required": true}
      ],
      "permissions": ["IsAuthenticated"],
      "pagination": {"type": "PageNumberPagination", "page_size": 20},
      "filters": {"search_fields": ["title", "description"], "ordering_fields": ["title", "price"]}
    }
  ],
  "mcp": {"enabled": true, "prefix": "/mcp"},
  "skills": {"enabled": true, "endpoint": "/SKILL.md"}
}
```

---

## DRF-Inspired Developer Experience

If you've used Django REST Framework, you already know FastREST. Same patterns, async stack:

| | DRF | FastREST |
|---|---|---|
| **Framework** | Django | FastAPI |
| **ORM** | Django ORM | SQLAlchemy, Tortoise, SQLModel, Beanie |
| **Validation** | DRF fields | DRF fields + Pydantic |
| **Async** | No | Native async/await |
| **OpenAPI** | Via drf-spectacular | Built-in (per-method typed routes) |
| **Agent support** | No | MCP + SKILL.md + Manifest |

---

## Quick Start

### Zero-Config: `router.serve()`

One line per model. Auto-generates serializers, viewsets, and routes:

```python
from fastapi import FastAPI
from fastrest.routers import DefaultRouter
from models import Author, Book, Tag

router = DefaultRouter()
router.serve(Author)                                          # → /authors, /authors/{pk}
router.serve(Book, search_fields=["title"], ordering_fields=["price"])
router.serve(Tag, readonly=True)                              # GET only

app = FastAPI(title="My API")
app.include_router(router.urls, prefix="/api")
```

Prefixes are auto-inferred from model names: `Author` → `authors`, `BookReview` → `book-reviews`, `Category` → `categories`.

`serve()` returns the viewset class for further customization:

```python
BookViewSet = router.serve(Book,
    exclude=["secret_field"],
    pagination_class=PageNumberPagination,
    filter_backends=[SearchFilter, OrderingFilter],
    search_fields=["title", "description"],
    ordering_fields=["price", "title"],
    permission_classes=[IsAuthenticated()],
)
BookViewSet.skill_description = "Manage the book catalog."
```

**All `serve()` options**: `prefix`, `basename`, `fields`, `exclude`, `read_only_fields`, `serializer_class`, `readonly`, `viewset_class`, `permission_classes`, `authentication_classes`, `throttle_classes`, `pagination_class`, `filter_backends`, `search_fields`, `ordering_fields`, `ordering`.

### Full Control: Serializer + ViewSet + Router

For complete customization, define each layer explicitly:

```python
from fastrest.serializers import ModelSerializer
from fastrest.viewsets import ModelViewSet
from fastrest.routers import DefaultRouter

class AuthorSerializer(ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name", "bio", "is_active"]
        read_only_fields = ["id"]

class AuthorViewSet(ModelViewSet):
    queryset = Author
    serializer_class = AuthorSerializer

router = DefaultRouter()
router.register("authors", AuthorViewSet, basename="author")

app = FastAPI()
app.include_router(router.urls, prefix="/api")
```

---

## Features

### Serializers

ModelSerializer auto-generates fields from your model and supports DRF-style validation:

```python
from fastrest.serializers import ModelSerializer
from fastrest.fields import FloatField
from fastrest.exceptions import ValidationError

class BookSerializer(ModelSerializer):
    price = FloatField(min_value=0.01)  # override auto-generated field

    class Meta:
        model = Book
        fields = ["id", "title", "isbn", "price", "author_id"]
        read_only_fields = ["id"]

    def validate_isbn(self, value):
        if value and len(value) not in (10, 13):
            raise ValidationError("ISBN must be 10 or 13 characters.")
        return value
```

**Field library:** CharField, IntegerField, FloatField, BooleanField, DecimalField, DateTimeField, DateField, TimeField, UUIDField, EmailField, URLField, SlugField, IPAddressField, DurationField, ListField, DictField, JSONField, ChoiceField, SerializerMethodField, and more.

### ViewSets & Custom Actions

```python
from fastrest.viewsets import ModelViewSet
from fastrest.decorators import action
from fastrest.response import Response

class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BookDetailSerializer
        return BookSerializer

    @action(methods=["get"], detail=False, url_path="in-stock")
    async def in_stock(self, request, **kwargs):
        """GET /api/books/in-stock"""
        books = await self.adapter.filter_queryset(Book, self.get_session(), in_stock=True)
        serializer = self.get_serializer(books, many=True)
        return Response(data=serializer.data)

    @action(methods=["post"], detail=True, url_path="toggle-stock",
            mcp_description="Toggle the in-stock status of a book")
    async def toggle_stock(self, request, **kwargs):
        """POST /api/books/{pk}/toggle-stock"""
        book = await self.get_object()
        session = self.get_session()
        await self.adapter.update(book, session, in_stock=not book.in_stock)
        serializer = self.get_serializer(book)
        return Response(data=serializer.data)
```

The `@action` decorator supports: `methods`, `detail`, `url_path`, `url_name`, `serializer_class`, `response_serializer_class`, `mcp` (include in MCP tools), `mcp_description`, `skill` (include in SKILL.md).

### Pagination

```python
from fastrest.pagination import PageNumberPagination, LimitOffsetPagination

class BookPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100

class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer
    pagination_class = BookPagination
```

```json
{
  "count": 42,
  "next": "?page=2&page_size=20",
  "previous": null,
  "results": [...]
}
```

Also available: `LimitOffsetPagination` with `?limit=20&offset=0`.

### Filtering & Search

```python
from fastrest.filters import SearchFilter, OrderingFilter

class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "description", "isbn"]
    ordering_fields = ["title", "price"]
    ordering = ["title"]  # default ordering
```

- `GET /api/books?search=django` — case-insensitive search across `search_fields`
- `GET /api/books?ordering=-price` — sort by price descending
- `GET /api/books?ordering=title,price` — multi-field sort
- All query parameters appear automatically in OpenAPI `/docs`

### Permissions

Composable permission classes with `&`, `|`, `~` operators:

```python
from fastrest.permissions import BasePermission, IsAuthenticated, IsAdminUser, HasScope

class IsOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id

class ArticleViewSet(ModelViewSet):
    queryset = Article
    serializer_class = ArticleSerializer
    # Compose with operators — works on instances
    permission_classes = [IsAuthenticated() & (IsOwner() | IsAdminUser())]
```

Scope-based access control:

```python
class ArticleViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated() & HasScope("articles:write")]
```

Scopes are read from `request.auth.scopes` (set by your authentication backend).

Built-in: `AllowAny`, `IsAuthenticated`, `IsAdminUser`, `IsAuthenticatedOrReadOnly`, `HasScope`.

### Authentication

Pluggable backends, just like DRF:

```python
from fastrest.authentication import TokenAuthentication, BasicAuthentication, SessionAuthentication

token_auth = TokenAuthentication(get_user_by_token=my_token_lookup)
basic_auth = BasicAuthentication(get_user_by_credentials=my_credentials_check)
session_auth = SessionAuthentication(get_user_from_session=my_session_resolver)

class ArticleViewSet(ModelViewSet):
    queryset = Article
    serializer_class = ArticleSerializer
    authentication_classes = [token_auth]
    permission_classes = [IsAuthenticated()]
```

- **`TokenAuthentication`** — `Authorization: Token <key>` (or `Bearer` with `keyword="Bearer"`)
- **`BasicAuthentication`** — HTTP Basic with a callback
- **`SessionAuthentication`** — Session-based with a callback

Unauthenticated requests return **401** (not 403) when authentication backends provide `authenticate_header`.

### Throttling

Rate-limit requests per user, IP, or custom key:

```python
from fastrest.throttling import SimpleRateThrottle, AnonRateThrottle, UserRateThrottle

class BurstRateThrottle(SimpleRateThrottle):
    rate = "60/min"

    def get_cache_key(self, request, view):
        return f"burst_{self.get_ident(request)}"

class ArticleViewSet(ModelViewSet):
    queryset = Article
    serializer_class = ArticleSerializer
    throttle_classes = [BurstRateThrottle()]
```

- **`AnonRateThrottle`** — Throttle unauthenticated requests by IP
- **`UserRateThrottle`** — Throttle authenticated requests by user ID, anonymous by IP
- Rate strings: `"100/hour"`, `"10/min"`, `"1000/day"`, `"5/sec"`
- Throttled responses return **429** with a `Retry-After` header

### App Configuration

Django-style settings per app:

```python
from fastrest.settings import configure

app = FastAPI()
configure(app, {
    "DEFAULT_PAGINATION_CLASS": "fastrest.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_PERMISSION_CLASSES": [IsAuthenticated()],
    "DEFAULT_AUTHENTICATION_CLASSES": [token_auth],
    "DEFAULT_THROTTLE_CLASSES": [AnonRateThrottle()],
    "DEFAULT_FILTER_BACKENDS": [SearchFilter, OrderingFilter],
    "SKILL_NAME": "my-api",
    "SKILL_BASE_URL": "https://api.example.com",
    "MCP_PREFIX": "/mcp",
})
```

Settings resolve in order: **viewset attribute > app config > framework default**. Unknown keys raise `ValueError` by default (set `STRICT_SETTINGS=False` to allow).

### Content Negotiation

Select response format based on the `Accept` header:

```python
from fastrest.negotiation import DefaultContentNegotiation, JSONRenderer, BrowsableAPIRenderer

negotiation = DefaultContentNegotiation()
renderer, media_type = negotiation.select_renderer(request, [JSONRenderer(), BrowsableAPIRenderer()])
```

Supports quality factors (`Accept: application/json;q=0.9`), format suffixes, and wildcard matching.

### Validation

Three levels of validation, same as DRF:

```python
class ReviewSerializer(ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "book_id", "reviewer_name", "rating", "comment"]

    # 1. Field-level: validate_{field_name}
    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise ValidationError("Rating must be between 1 and 5.")
        return value

    # 2. Object-level: validate()
    def validate(self, attrs):
        if attrs.get("rating", 0) < 3 and not attrs.get("comment"):
            raise ValidationError("Low ratings require a comment.")
        return attrs

    # 3. Field constraints via kwargs
    # CharField(max_length=500), IntegerField(min_value=1, max_value=100)
```

### Routers

```python
from fastrest.routers import DefaultRouter, SimpleRouter

# DefaultRouter adds API root, SKILL.md, and manifest.json
router = DefaultRouter()
router.register("authors", AuthorViewSet, basename="author")
router.register("books", BookViewSet, basename="book")

# Or use serve() for zero-config
router.serve(Author)
router.serve(Book, prefix="books")

# SimpleRouter — just the resource routes
router = SimpleRouter()
```

Each HTTP method gets its own OpenAPI route with correct status codes (201 for create, 204 for delete), typed path parameters, and auto-generated Pydantic request/response schemas.

### Generic Views

For when you don't need the full viewset:

```python
from fastrest.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

class AuthorList(ListCreateAPIView):
    queryset = Author
    serializer_class = AuthorSerializer

class AuthorDetail(RetrieveUpdateDestroyAPIView):
    queryset = Author
    serializer_class = AuthorSerializer
```

Available: `CreateAPIView`, `ListAPIView`, `RetrieveAPIView`, `DestroyAPIView`, `UpdateAPIView`, `ListCreateAPIView`, `RetrieveUpdateAPIView`, `RetrieveDestroyAPIView`, `RetrieveUpdateDestroyAPIView`.

### Testing

Built-in async test client:

```python
import pytest
from fastrest.test import APIClient

@pytest.fixture
def client(app):
    return APIClient(app)

@pytest.mark.asyncio
async def test_create_author(client):
    resp = await client.post("/api/authors", json={
        "name": "Ursula K. Le Guin",
        "bio": "Science fiction author",
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "Ursula K. Le Guin"

@pytest.mark.asyncio
async def test_list_authors(client):
    resp = await client.get("/api/authors")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

---

## Full Example

See the [fastrest-example](https://github.com/hoaxnerd/fastrest-example) repo for a complete bookstore API with authors, books, tags, reviews, authentication, pagination, search, agent integration, and tests for SQLAlchemy, Tortoise, SQLModel, and Beanie.

---

## DRF Compatibility

| DRF | FastREST | Status |
|---|---|---|
| `ModelSerializer` | `ModelSerializer` | Done |
| `ModelViewSet` | `ModelViewSet` | Done |
| `ReadOnlyModelViewSet` | `ReadOnlyModelViewSet` | Done |
| `DefaultRouter` | `DefaultRouter` | Done |
| `@action` | `@action` | Done |
| `permission_classes` | `permission_classes` | Done |
| `ValidationError` | `ValidationError` | Done |
| Field library | Field library | Done |
| `APIClient` (test) | `APIClient` (test) | Done |
| Pagination | `PageNumberPagination`, `LimitOffsetPagination` | Done |
| Filtering/Search | `SearchFilter`, `OrderingFilter` | Done |
| Authentication | `TokenAuthentication`, `BasicAuthentication`, `SessionAuthentication` | Done |
| Throttling | `SimpleRateThrottle`, `AnonRateThrottle`, `UserRateThrottle` | Done |
| Content negotiation | `DefaultContentNegotiation`, `JSONRenderer`, `BrowsableAPIRenderer` | Done |
| App configuration | `configure(app, settings)`, `get_settings(request)` | Done |
| Auth scopes | `HasScope` permission class | Done |
| — | `router.serve(Model)` — zero-config CRUD | Done |
| — | MCP Server — AI agent tools | Done |
| — | SKILL.md — agent skill documents | Done |
| — | API Manifest — structured metadata | Done |

---

## Requirements

- Python 3.10+
- FastAPI 0.100+
- Pydantic 2.0+
- ORM of your choice via optional extras

## License

BSD 3-Clause. See [LICENSE](LICENSE).
