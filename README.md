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

**DRF inspired REST Framework for FastAPI.**

FastREST lets you build async REST APIs using the patterns you already know from DRF — serializers, viewsets, routers, permissions — running on FastAPI with Pydantic validation and auto-generated OpenAPI docs.

```
pip install fastrest
```

> **Status:** Alpha (0.1.1). The core API is stable for serializers, viewsets, routers, pagination, and filtering. Authentication backends are coming in future releases.

---

## Why FastREST?

If you've used Django REST Framework, you know how productive it is. But DRF is synchronous and tied to Django's ORM. FastREST gives you the same developer experience on a modern async stack:

| | DRF | FastREST |
|---|---|---|
| **Framework** | Django | FastAPI |
| **ORM** | Django ORM | SQLAlchemy (async) |
| **Validation** | DRF fields | DRF fields + Pydantic |
| **Async** | No | Native async/await |
| **OpenAPI** | Via drf-spectacular | Built-in (per-method routes) |
| **Type hints** | Optional | First-class |

## Quick Start

### 1. Define your model (SQLAlchemy)

```python
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Author(Base):
    __tablename__ = "authors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    bio = Column(String(1000))
    is_active = Column(Boolean, default=True)
```

### 2. Define your serializer

```python
from fastrest.serializers import ModelSerializer

class AuthorSerializer(ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name", "bio", "is_active"]
        read_only_fields = ["id"]
```

### 3. Define your viewset

```python
from fastrest.viewsets import ModelViewSet

class AuthorViewSet(ModelViewSet):
    queryset = Author
    serializer_class = AuthorSerializer
```

### 4. Register routes and create the app

```python
from fastapi import FastAPI
from fastrest.routers import DefaultRouter

router = DefaultRouter()
router.register("authors", AuthorViewSet, basename="author")

app = FastAPI(title="My API")
app.include_router(router.urls, prefix="/api")
```

That's it. You now have:

- `GET /api/authors` — List all authors
- `POST /api/authors` — Create an author (201)
- `GET /api/authors/{pk}` — Retrieve an author
- `PUT /api/authors/{pk}` — Update an author
- `PATCH /api/authors/{pk}` — Partial update
- `DELETE /api/authors/{pk}` — Delete an author (204)
- `GET /api/` — API root listing all resources
- `GET /docs` — Interactive Swagger UI with typed schemas
- `GET /redoc` — ReDoc documentation

---

## Features

### Serializers

ModelSerializer auto-generates fields from your SQLAlchemy model, just like DRF:

```python
from fastrest.serializers import ModelSerializer
from fastrest.fields import FloatField
from fastrest.exceptions import ValidationError

class BookSerializer(ModelSerializer):
    # Override auto-generated fields
    price = FloatField(min_value=0.01)

    class Meta:
        model = Book
        fields = ["id", "title", "isbn", "price", "author_id"]
        read_only_fields = ["id"]

    # Per-field validation hooks
    def validate_isbn(self, value):
        if value and len(value) not in (10, 13):
            raise ValidationError("ISBN must be 10 or 13 characters.")
        return value
```

**Supported fields:** CharField, IntegerField, FloatField, BooleanField, DecimalField, DateTimeField, DateField, TimeField, UUIDField, EmailField, URLField, SlugField, ListField, DictField, JSONField, SerializerMethodField, and more.

### ViewSets

```python
from fastrest.viewsets import ModelViewSet, ReadOnlyModelViewSet

class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer

    # Switch serializer based on action
    def get_serializer_class(self):
        if self.action == "retrieve":
            return BookDetailSerializer
        return BookSerializer
```

### Custom Actions

Add custom endpoints to viewsets with the `@action` decorator:

```python
from fastrest.decorators import action
from fastrest.response import Response

class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer

    @action(methods=["get"], detail=False, url_path="in-stock")
    async def in_stock(self, request, **kwargs):
        """GET /api/books/in-stock — List only in-stock books."""
        books = await self.adapter.filter_queryset(
            Book, self.get_session(), in_stock=True
        )
        serializer = self.get_serializer(books, many=True)
        return Response(data=serializer.data)

    @action(methods=["post"], detail=True, url_path="toggle-stock")
    async def toggle_stock(self, request, **kwargs):
        """POST /api/books/{pk}/toggle-stock — Toggle in_stock flag."""
        book = await self.get_object()
        session = self.get_session()
        await self.adapter.update(book, session, in_stock=not book.in_stock)
        serializer = self.get_serializer(book)
        return Response(data=serializer.data)
```

### Pagination

Add pagination to any viewset:

```python
from fastrest.pagination import PageNumberPagination

class BookPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100

class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer
    pagination_class = BookPagination
```

Paginated list responses return an envelope:

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

Add search and ordering with filter backends:

```python
from fastrest.filters import SearchFilter, OrderingFilter

class BookViewSet(ModelViewSet):
    queryset = Book
    serializer_class = BookSerializer
    pagination_class = BookPagination
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
from fastrest.permissions import BasePermission, IsAuthenticated

class IsOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id

class ArticleViewSet(ModelViewSet):
    queryset = Article
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated & IsOwner]
```

Built-in: `AllowAny`, `IsAuthenticated`, `IsAdminUser`, `IsAuthenticatedOrReadOnly`.

### Routers

```python
from fastrest.routers import DefaultRouter, SimpleRouter

# DefaultRouter adds an API root view at /
router = DefaultRouter()
router.register("authors", AuthorViewSet, basename="author")
router.register("books", BookViewSet, basename="book")

# SimpleRouter without the root view
router = SimpleRouter()
```

Each HTTP method gets its own OpenAPI route with:
- Correct status codes (201 for create, 204 for delete)
- Typed `pk: int` path parameters
- Request/response Pydantic schemas auto-generated from serializers
- Tag-based grouping by resource
- Unique operation IDs

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

    # 3. Field constraints via field kwargs
    # e.g., CharField(max_length=500), IntegerField(min_value=1)
```

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

### Generic Views

For when you don't need the full viewset:

```python
from fastrest.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)

class AuthorList(ListCreateAPIView):
    queryset = Author
    serializer_class = AuthorSerializer

class AuthorDetail(RetrieveUpdateDestroyAPIView):
    queryset = Author
    serializer_class = AuthorSerializer
```

Available: `CreateAPIView`, `ListAPIView`, `RetrieveAPIView`, `DestroyAPIView`, `UpdateAPIView`, `ListCreateAPIView`, `RetrieveUpdateAPIView`, `RetrieveDestroyAPIView`, `RetrieveUpdateDestroyAPIView`.

---

## Full Example

See the [fastrest-example](https://github.com/hoaxnerd/fastrest-example) repo for a complete bookstore API with authors, books, tags, and reviews.

---

## DRF Compatibility

FastREST implements the core DRF public API. If you've used DRF, you already know FastREST:

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
| Authentication backends | — | Planned |
| Throttling | — | Planned |
| Content negotiation | — | Planned |

---

## Requirements

- Python 3.10+
- FastAPI 0.100+
- Pydantic 2.0+
- SQLAlchemy 2.0+ (async)

## License

BSD 3-Clause. See [LICENSE](LICENSE).
