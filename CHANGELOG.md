# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-03-04

### Added
- `PageNumberPagination` — `?page=1&page_size=20` with configurable `page_size` and `max_page_size`
- `LimitOffsetPagination` — `?limit=20&offset=0` with configurable `default_limit` and `max_limit`
- Paginated response envelope: `{"count", "next", "previous", "results"}`
- `SearchFilter` — `?search=foo`, case-insensitive containment across `view.search_fields`
- `OrderingFilter` — `?ordering=-price,name`, respects `view.ordering_fields` whitelist and `view.ordering` default
- Filter and pagination query parameters auto-appear in OpenAPI `/docs`
- `pagination_class`, `filter_backends`, `search_fields`, `ordering_fields`, `ordering` viewset attributes

## [0.1.0] - 2026-03-02

### Added
- ModelSerializer with automatic field generation from SQLAlchemy models
- ModelViewSet and ReadOnlyModelViewSet with full CRUD support
- DefaultRouter and SimpleRouter with DRF-style URL patterns
- Per-method OpenAPI route registration with typed schemas
- Auto-generated Pydantic request/response models from serializers
- `@action` decorator for custom viewset endpoints
- Permission system with `&`, `|`, `~` composition operators
- Built-in permissions: AllowAny, IsAuthenticated, IsAdminUser, IsAuthenticatedOrReadOnly
- Field library: CharField, IntegerField, FloatField, BooleanField, DateTimeField, UUIDField, and more
- Validation: field-level, serializer-level, and per-field `validate_<name>` hooks
- Exception hierarchy matching DRF (ValidationError, NotFound, PermissionDenied, etc.)
- AsyncAPIClient for testing
- Pluggable ORM adapter (SQLAlchemy adapter included)
