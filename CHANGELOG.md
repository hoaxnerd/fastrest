# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
