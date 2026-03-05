"""Manifest endpoint — structured metadata about the API."""

from __future__ import annotations

from typing import Any

from fastrest.skills import _type_name


def generate_manifest(router: Any, settings: Any = None) -> dict:
    """Generate a structured manifest from a FastREST router.

    Returns a JSON-serializable dict describing all registered
    resources, their fields, endpoints, permissions, and configuration.
    """
    from fastrest.settings import api_settings
    settings = settings or api_settings

    resources = []
    for prefix, viewset, basename in router.registry:
        resources.append(_build_resource(prefix, viewset, basename, settings))

    manifest = {
        "version": "1.0",
        "name": getattr(settings, "SKILL_NAME", None) or "api",
        "resources": resources,
    }

    base_url = getattr(settings, "SKILL_BASE_URL", None)
    if base_url:
        manifest["base_url"] = base_url

    # MCP info
    if settings.MCP_ENABLED:
        manifest["mcp"] = {
            "enabled": True,
            "prefix": settings.MCP_PREFIX,
        }

    # Skills info
    if settings.SKILL_ENABLED:
        manifest["skills"] = {
            "enabled": True,
            "endpoint": "/SKILL.md",
        }

    return manifest


def _build_resource(prefix: str, viewset: type, basename: str, settings: Any) -> dict:
    resource: dict[str, Any] = {
        "name": basename,
        "prefix": prefix,
        "actions": _get_actions(viewset),
    }

    # Fields from serializer
    ser_cls = getattr(viewset, "serializer_class", None)
    if ser_cls:
        resource["fields"] = _get_fields(ser_cls)

    # Permissions
    perm_classes = getattr(viewset, "permission_classes", [])
    if perm_classes:
        resource["permissions"] = [
            (p if isinstance(p, type) else type(p)).__name__
            for p in perm_classes
        ]

    # Auth
    auth_classes = getattr(viewset, "authentication_classes", [])
    if auth_classes:
        resource["authentication"] = [
            (a if isinstance(a, type) else type(a)).__name__
            for a in auth_classes
        ]

    # Pagination
    pagination_cls = getattr(viewset, "pagination_class", None)
    if pagination_cls:
        resource["pagination"] = {
            "class": pagination_cls.__name__,
            "page_size": getattr(pagination_cls, "page_size", None),
            "max_page_size": getattr(pagination_cls, "max_page_size", None),
        }

    # Filters
    filter_backends = getattr(viewset, "filter_backends", None)
    if filter_backends:
        resource["filters"] = {}
        search_fields = getattr(viewset, "search_fields", None)
        if search_fields:
            resource["filters"]["search_fields"] = list(search_fields)
        ordering_fields = getattr(viewset, "ordering_fields", None)
        if ordering_fields:
            resource["filters"]["ordering_fields"] = list(ordering_fields)

    # Throttling
    throttle_classes = getattr(viewset, "throttle_classes", [])
    if throttle_classes:
        rates = []
        for tc in throttle_classes:
            cls = tc if isinstance(tc, type) else type(tc)
            rate = getattr(cls, "rate", None) or getattr(tc, "rate", None)
            if rate:
                rates.append(rate)
        if rates:
            resource["throttle_rates"] = rates

    return resource


def _get_actions(viewset: type) -> list[dict]:
    actions = []
    crud = {
        "list": {"method": "GET", "detail": False},
        "create": {"method": "POST", "detail": False},
        "retrieve": {"method": "GET", "detail": True},
        "update": {"method": "PUT", "detail": True},
        "partial_update": {"method": "PATCH", "detail": True},
        "destroy": {"method": "DELETE", "detail": True},
    }
    for name, meta in crud.items():
        if hasattr(viewset, name):
            actions.append({"name": name, **meta})

    # Custom @actions
    for attr_name in dir(viewset):
        attr = getattr(viewset, attr_name, None)
        if not callable(attr) or not hasattr(attr, "detail") or not hasattr(attr, "mapping"):
            continue
        methods = [m.upper() for m in attr.mapping.keys()]
        actions.append({
            "name": attr_name,
            "method": methods[0] if len(methods) == 1 else methods,
            "detail": attr.detail,
            "custom": True,
        })

    return actions


def _get_fields(ser_cls: type) -> list[dict]:
    fields = []
    instance = ser_cls()
    for name, field in instance.fields.items():
        info: dict[str, Any] = {
            "name": name,
            "type": _type_name(field),
            "required": field.required and not field.read_only,
        }
        if field.read_only:
            info["read_only"] = True
        if field.write_only:
            info["write_only"] = True
        if field.allow_null:
            info["nullable"] = True
        fields.append(info)
    return fields
