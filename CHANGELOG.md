# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-03-06

### Changed
- SQLAlchemy is now an optional dependency — install via `pip install fastrest[sqlalchemy]`
- ORM adapter is auto-detected from installed packages; custom adapters can be set via `set_default_adapter()`

### Added
- Authentication backends: `BaseAuthentication`, `TokenAuthentication`, `BasicAuthentication`, `SessionAuthentication`
- `perform_authentication` now runs configured authentication backends on each request
- Unauthenticated requests return 401 (not 403) when authentication backends provide `authenticate_header`
- `authentication_classes` viewset/view attribute and `DEFAULT_AUTHENTICATION_CLASSES` setting
- Throttling backends: `BaseThrottle`, `SimpleRateThrottle`, `AnonRateThrottle`, `UserRateThrottle`
- Rate limiting with configurable rates (e.g. `'100/hour'`, `'10/min'`)
- `throttle_classes` viewset/view attribute and `DEFAULT_THROTTLE_CLASSES` setting
- `Throttled` responses include `Retry-After` header
- **App configuration layer**: `configure(app, settings)` binds per-app settings; `get_settings(request)` resolves from `request.app.state`
- **Settings validation**: `STRICT_SETTINGS` flag (default `True`) catches typos in setting keys
- **Resolution order**: viewset attribute → app config → framework default (consistent across auth, permissions, throttle, pagination, filters)
- **`HasScope` permission class**: Check `request.auth.scopes` for required scopes; composable with `&`, `|`, `~`
- **SKILL.md generation**: Auto-generates agent skill documents from viewsets, serializers, and routers
  - `GET /SKILL.md` — Full API skill document
  - `GET /{resource}/SKILL.md` — Per-resource skill document
  - Viewset-level customization: `skill_enabled`, `skill_description`, `skill_exclude_actions`, `skill_exclude_fields`, `skill_examples`
  - Configurable via settings: `SKILL_ENABLED`, `SKILL_NAME`, `SKILL_BASE_URL`, `SKILL_DESCRIPTION`, `SKILL_INCLUDE_EXAMPLES`
- **Built-in MCP server**: Auto-generates MCP tools from viewsets and dispatches through the full viewset pipeline
  - `mount_mcp(app, router)` — Mount MCP SSE server on your FastAPI app
  - Tools for all CRUD actions + custom `@action` endpoints
  - Auth, permissions, and throttling apply to MCP tool calls
  - Configurable via settings: `MCP_ENABLED`, `MCP_PREFIX`, `MCP_TOOL_NAME_FORMAT`, `MCP_EXCLUDE_VIEWSETS`
  - `@action(mcp=False)` to exclude specific actions from MCP
- **Manifest endpoint**: `GET /manifest.json` — Structured JSON metadata about the API (resources, fields, actions, permissions, pagination, filters)
- **Content negotiation**: `DefaultContentNegotiation`, `JSONRenderer`, `BrowsableAPIRenderer`
  - Accept header parsing with quality factors
  - Format suffix support
  - Media type matching with wildcard support
- **Router enhancements**: Custom `APIRouter` passthrough, paginated response schemas in OpenAPI, typed `@action` routes, per-action OpenAPI metadata

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
