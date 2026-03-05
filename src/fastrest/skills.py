"""SKILL.md generation from FastREST viewsets, serializers, and routers."""

from __future__ import annotations

from typing import Any

from fastrest import fields as f


# Map field classes to human-readable type names
FIELD_TYPE_NAMES: dict[type, str] = {
    f.CharField: "string",
    f.EmailField: "string (email)",
    f.RegexField: "string",
    f.SlugField: "string (slug)",
    f.URLField: "string (URL)",
    f.IPAddressField: "string (IP)",
    f.IntegerField: "integer",
    f.FloatField: "float",
    f.BooleanField: "boolean",
    f.DecimalField: "decimal",
    f.DateTimeField: "datetime",
    f.DateField: "date",
    f.TimeField: "time",
    f.DurationField: "duration",
    f.UUIDField: "UUID",
    f.ListField: "array",
    f.DictField: "object",
    f.JSONField: "JSON",
    f.FileField: "file",
    f.ImageField: "image",
    f.ChoiceField: "choice",
    f.MultipleChoiceField: "array",
    f.SerializerMethodField: "computed",
    f.ReadOnlyField: "any",
    f.HiddenField: "hidden",
}


def _type_name(field: f.Field) -> str:
    for cls in type(field).__mro__:
        if cls in FIELD_TYPE_NAMES:
            return FIELD_TYPE_NAMES[cls]
    return "any"


def _field_constraints(field: f.Field) -> list[str]:
    """Extract human-readable constraints from a field."""
    constraints = []
    if hasattr(field, 'max_length') and field.max_length is not None:
        constraints.append(f"max {field.max_length} chars")
    if hasattr(field, 'min_length') and field.min_length is not None:
        constraints.append(f"min {field.min_length} chars")
    if hasattr(field, 'max_value') and field.max_value is not None:
        constraints.append(f"max {field.max_value}")
    if hasattr(field, 'min_value') and field.min_value is not None:
        constraints.append(f"min {field.min_value}")
    if hasattr(field, 'choices') and field.choices:
        if len(field.choices) <= 6:
            constraints.append(f"choices: {field.choices}")
    return constraints


def _example_value(field: f.Field, field_name: str) -> Any:
    """Generate a plausible example value for a field."""
    type_name = _type_name(field)
    if type_name == "integer":
        return 1
    elif type_name == "float" or type_name == "decimal":
        return 9.99
    elif type_name == "boolean":
        return True
    elif type_name == "string (email)":
        return "user@example.com"
    elif type_name == "string (URL)":
        return "https://example.com"
    elif type_name == "UUID":
        return "550e8400-e29b-41d4-a716-446655440000"
    elif type_name.startswith("string"):
        return f"example_{field_name}"
    elif type_name == "datetime":
        return "2026-01-01T00:00:00Z"
    elif type_name == "date":
        return "2026-01-01"
    elif type_name == "array":
        return []
    elif type_name == "object" or type_name == "JSON":
        return {}
    return "value"


class SkillGenerator:
    """Generates SKILL.md content from a FastREST router's registry."""

    def __init__(self, router: Any, config: dict[str, Any] | None = None):
        self.router = router
        self.config = config or {}

    def generate(self, resources: list[str] | None = None) -> str:
        """Generate a complete SKILL.md document.

        Args:
            resources: Optional list of resource prefixes to include.
                       If None, all registered resources are included.
        """
        registry = self._filtered_registry(resources)
        if not registry:
            return self._render_frontmatter(resources) + "\n\nNo resources found.\n"

        sections = []
        sections.append(self._render_frontmatter(resources))
        sections.append(self._render_header(registry))

        auth_section = self._render_auth_section(registry)
        if auth_section:
            sections.append(auth_section)

        sections.append("## Resources\n")
        for prefix, viewset, basename in registry:
            sections.append(self._render_resource(prefix, viewset, basename, registry))

        sections.append(self._render_error_section())

        if self.config.get("SKILL_INCLUDE_EXAMPLES", True):
            examples = self._render_examples(registry)
            if examples:
                sections.append(examples)

        return "\n\n".join(sections) + "\n"

    def _filtered_registry(self, resources: list[str] | None) -> list[tuple]:
        registry = []
        for prefix, viewset, basename in self.router.registry:
            if not getattr(viewset, 'skill_enabled', True):
                continue
            if resources and prefix not in resources:
                continue
            registry.append((prefix, viewset, basename))
        return registry

    def _render_frontmatter(self, resources: list[str] | None = None) -> str:
        name = self.config.get("SKILL_NAME") or "api"
        if resources:
            name = f"{name}-{'-'.join(resources)}"

        description = self.config.get("SKILL_DESCRIPTION")
        if not description:
            resource_names = [p for p, _, _ in self.router.registry]
            if resources:
                resource_names = [r for r in resource_names if r in resources]
            description = (
                f"Interact with the API to manage {', '.join(resource_names)}. "
                f"Use when the user needs to create, read, update, or delete "
                f"{' or '.join(resource_names)}."
            )

        lines = [
            "---",
            f"name: {name}",
            f"description: {description}",
            "---",
        ]
        return "\n".join(lines)

    def _render_header(self, registry: list[tuple]) -> str:
        name = self.config.get("SKILL_NAME") or "API"
        base_url = self.config.get("SKILL_BASE_URL") or ""
        lines = [f"# {name.replace('-', ' ').title()}"]
        if base_url:
            lines.append(f"\nBase URL: `{base_url}`")
        return "\n".join(lines)

    def _render_auth_section(self, registry: list[tuple]) -> str | None:
        """Describe authentication requirements across all resources."""
        custom_desc = self.config.get("SKILL_AUTH_DESCRIPTION")
        if custom_desc:
            return f"## Authentication\n\n{custom_desc}"

        auth_info = []
        for prefix, viewset, basename in registry:
            auth_classes = getattr(viewset, 'authentication_classes', [])
            perm_classes = getattr(viewset, 'permission_classes', [])
            if auth_classes or self._has_auth_permission(perm_classes):
                auth_info.append((prefix, auth_classes, perm_classes))

        if not auth_info:
            return None

        lines = ["## Authentication\n"]
        for prefix, auth_classes, perm_classes in auth_info:
            auth_types = []
            for ac in auth_classes:
                cls = ac if isinstance(ac, type) else type(ac)
                name = cls.__name__
                if "Token" in name or "Bearer" in name:
                    auth_types.append("Bearer token")
                elif "Basic" in name:
                    auth_types.append("HTTP Basic")
                elif "Session" in name:
                    auth_types.append("Session")
                else:
                    auth_types.append(name)

            perm_desc = self._describe_permissions(perm_classes)
            if auth_types:
                lines.append(
                    f"- **{prefix}**: {', '.join(auth_types)} authentication. {perm_desc}"
                )
        return "\n".join(lines)

    def _has_auth_permission(self, perm_classes: list) -> bool:
        from fastrest.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser
        for p in perm_classes:
            cls = p if isinstance(p, type) else type(p)
            if cls in (IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser):
                return True
        return False

    def _describe_permissions(self, perm_classes: list) -> str:
        from fastrest.permissions import (
            AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser,
        )
        parts = []
        for p in perm_classes:
            cls = p if isinstance(p, type) else type(p)
            if cls is AllowAny:
                parts.append("Public access")
            elif cls is IsAuthenticated:
                parts.append("Authentication required for all operations")
            elif cls is IsAuthenticatedOrReadOnly:
                parts.append("Read operations are public; write operations require authentication")
            elif cls is IsAdminUser:
                parts.append("Admin access only")
            else:
                parts.append(cls.__name__)
        return ". ".join(parts) if parts else ""

    def _render_resource(self, prefix: str, viewset: type, basename: str,
                         registry: list[tuple]) -> str:
        lines = []
        human_name = prefix.replace('-', ' ').replace('_', ' ').title()

        # Description
        description = getattr(viewset, 'skill_description', None) or viewset.__doc__ or ""
        lines.append(f"### {human_name}\n")
        if description:
            lines.append(description.strip())

        # Fields table
        ser_cls = getattr(viewset, 'serializer_class', None)
        exclude_fields = set(getattr(viewset, 'skill_exclude_fields', []))
        if ser_cls:
            lines.append(self._render_fields_table(ser_cls, exclude_fields))

        # Endpoints
        lines.append(self._render_endpoints(prefix, viewset, basename))

        # Custom actions
        actions_section = self._render_custom_actions(prefix, viewset, basename)
        if actions_section:
            lines.append(actions_section)

        # Filters / search / pagination
        filters_section = self._render_filters(viewset)
        if filters_section:
            lines.append(filters_section)

        # Pagination response format
        pagination_cls = getattr(viewset, 'pagination_class', None)
        if pagination_cls:
            lines.append("**Paginated response format:**")
            lines.append('```json\n{"count": 42, "next": "?page=2", "previous": null, "results": [...]}\n```')

        # Validation rules
        validation = self._render_validation(ser_cls)
        if validation:
            lines.append(validation)

        # Relationships
        relationships = self._render_relationships(ser_cls, registry, exclude_fields)
        if relationships:
            lines.append(relationships)

        # Permissions
        perm_classes = getattr(viewset, 'permission_classes', [])
        perm_desc = self._describe_permissions(perm_classes)
        if perm_desc and "Public" not in perm_desc:
            lines.append(f"**Permissions:** {perm_desc}")

        # Throttling
        throttle_classes = getattr(viewset, 'throttle_classes', [])
        if throttle_classes:
            rates = []
            for tc in throttle_classes:
                cls = tc if isinstance(tc, type) else type(tc)
                rate = getattr(cls, 'rate', None) or getattr(tc, 'rate', None)
                if rate:
                    rates.append(rate)
            if rates:
                lines.append(f"**Rate limit:** {', '.join(rates)}")

        return "\n\n".join(lines)

    def _render_fields_table(self, ser_cls: type, exclude_fields: set) -> str:
        fields = ser_cls().fields
        lines = [
            "**Fields:**",
            "| Field | Type | Required | Constraints | Notes |",
            "|-------|------|----------|-------------|-------|",
        ]
        for name, field in fields.items():
            if name in exclude_fields:
                continue
            type_name = _type_name(field)
            required = "—" if field.read_only else ("yes" if field.required else "no")
            constraints = ", ".join(_field_constraints(field)) or ""
            notes = []
            if field.read_only:
                notes.append("read-only")
            if field.write_only:
                notes.append("write-only")
            if field.allow_null:
                notes.append("nullable")
            if getattr(field, 'help_text', None):
                notes.append(field.help_text)
            notes_str = ", ".join(notes)
            lines.append(f"| {name} | {type_name} | {required} | {constraints} | {notes_str} |")
        return "\n".join(lines)

    def _render_endpoints(self, prefix: str, viewset: type, basename: str) -> str:
        base = self.config.get("SKILL_BASE_URL") or ""
        exclude_actions = set(getattr(viewset, 'skill_exclude_actions', []))

        lines = ["**Endpoints:**"]
        crud_actions = [
            ("list", "GET", f"/{prefix}", "List all", False),
            ("create", "POST", f"/{prefix}", "Create", False),
            ("retrieve", "GET", f"/{prefix}/{{id}}", "Get", True),
            ("update", "PUT", f"/{prefix}/{{id}}", "Update", True),
            ("partial_update", "PATCH", f"/{prefix}/{{id}}", "Partial update", True),
            ("destroy", "DELETE", f"/{prefix}/{{id}}", "Delete", True),
        ]
        for action_name, method, path, verb, detail in crud_actions:
            if action_name in exclude_actions:
                continue
            if not hasattr(viewset, action_name):
                continue
            url = f"{base}{path}"
            lines.append(f"- `{method} {url}` — {verb}")

        return "\n".join(lines)

    def _render_custom_actions(self, prefix: str, viewset: type, basename: str) -> str | None:
        base = self.config.get("SKILL_BASE_URL") or ""
        exclude_actions = set(getattr(viewset, 'skill_exclude_actions', []))
        actions = []

        for attr_name in dir(viewset):
            attr = getattr(viewset, attr_name, None)
            if not callable(attr) or not hasattr(attr, 'detail') or not hasattr(attr, 'mapping'):
                continue
            if attr_name in exclude_actions:
                continue
            if not getattr(attr, 'skill', True):
                continue

            methods = [m.upper() for m in attr.mapping.keys()]
            url_path = attr.url_path
            if attr.detail:
                url = f"{base}/{prefix}/{{id}}/{url_path}"
            else:
                url = f"{base}/{prefix}/{url_path}"

            doc = attr.__doc__ or ""
            desc = doc.strip().split("\n")[0] if doc else attr_name.replace("_", " ").title()

            for method in methods:
                actions.append(f"- `{method} {url}` — {desc}")

        if not actions:
            return None

        lines = ["**Custom actions:**"] + actions
        return "\n".join(lines)

    def _render_filters(self, viewset: type) -> str | None:
        parts = []
        search_fields = getattr(viewset, 'search_fields', None)
        ordering_fields = getattr(viewset, 'ordering_fields', None)
        ordering_default = getattr(viewset, 'ordering', None)
        pagination_cls = getattr(viewset, 'pagination_class', None)

        if search_fields:
            parts.append(f"- `?search=<term>` — Search across: {', '.join(search_fields)}")
        if ordering_fields:
            desc = ', '.join(ordering_fields)
            parts.append(f"- `?ordering=<field>` — Order by: {desc} (prefix `-` for descending)")
        if ordering_default:
            default = ', '.join(ordering_default) if isinstance(ordering_default, (list, tuple)) else ordering_default
            parts.append(f"- Default ordering: {default}")
        if pagination_cls:
            page_size = getattr(pagination_cls, 'page_size', 20)
            max_size = getattr(pagination_cls, 'max_page_size', 100)
            cls_name = pagination_cls.__name__
            if "LimitOffset" in cls_name:
                parts.append(f"- `?limit=<n>&offset=<n>` — Pagination (default limit: {page_size}, max: {max_size})")
            else:
                parts.append(f"- `?page=<n>&page_size=<n>` — Pagination ({page_size} per page, max {max_size})")

        if not parts:
            return None

        lines = ["**Query parameters:**"] + parts
        return "\n".join(lines)

    def _render_validation(self, ser_cls: type | None) -> str | None:
        if ser_cls is None:
            return None

        rules = []
        # Check for validate_<field> methods
        for attr_name in dir(ser_cls):
            if attr_name.startswith("validate_") and attr_name != "validate":
                field_name = attr_name[len("validate_"):]
                method = getattr(ser_cls, attr_name)
                doc = method.__doc__
                if doc:
                    rules.append(f"- `{field_name}`: {doc.strip()}")
                else:
                    rules.append(f"- `{field_name}`: custom validation")

        # Check for validate() method
        if hasattr(ser_cls, 'validate') and ser_cls.validate is not getattr(ser_cls.__bases__[0], 'validate', None):
            doc = ser_cls.validate.__doc__
            if doc:
                rules.append(f"- Object-level: {doc.strip()}")
            else:
                rules.append("- Object-level validation")

        if not rules:
            return None

        lines = ["**Validation rules:**"] + rules
        return "\n".join(lines)

    def _render_relationships(self, ser_cls: type | None, registry: list[tuple],
                              exclude_fields: set) -> str | None:
        if ser_cls is None:
            return None

        fields = ser_cls().fields
        registry_map = {p: b for p, _, b in registry}
        relationships = []

        for name, field in fields.items():
            if name in exclude_fields:
                continue
            if name.endswith("_id"):
                resource_name = name[:-3] + "s"  # author_id → authors
                if resource_name in registry_map:
                    relationships.append(f"- `{name}` → {resource_name}")

        if not relationships:
            return None

        lines = ["**Relationships:**"] + relationships
        return "\n".join(lines)

    def _render_error_section(self) -> str:
        return "\n".join([
            "## Error Responses\n",
            "- `400` — Validation error (field-level details in response body)",
            "- `401` — Authentication required or invalid credentials",
            "- `403` — Permission denied",
            "- `404` — Resource not found",
            "- `429` — Rate limited (check Retry-After header)",
        ])

    def _render_examples(self, registry: list[tuple]) -> str | None:
        max_per_resource = self.config.get("SKILL_MAX_EXAMPLES_PER_RESOURCE", 3)
        base = self.config.get("SKILL_BASE_URL") or ""
        all_examples = []

        for prefix, viewset, basename in registry:
            # Check for custom examples
            custom_examples = getattr(viewset, 'skill_examples', None)
            if custom_examples:
                for ex in custom_examples[:max_per_resource]:
                    desc = ex.get("description", "")
                    req = ex.get("request", "")
                    resp = ex.get("response", "")
                    all_examples.append(f"{desc}:\n```\n{req}\n→ {resp}\n```")
                continue

            # Auto-generate examples from serializer
            ser_cls = getattr(viewset, 'serializer_class', None)
            if not ser_cls:
                continue

            exclude_fields = set(getattr(viewset, 'skill_exclude_fields', []))
            fields = ser_cls().fields
            example_count = 0

            # Create example
            if hasattr(viewset, 'create') and example_count < max_per_resource:
                body = {}
                for name, field in fields.items():
                    if field.read_only or name in exclude_fields:
                        continue
                    if field.required:
                        body[name] = _example_value(field, name)
                if body:
                    import json
                    body_str = json.dumps(body)
                    all_examples.append(
                        f"Create a {basename}:\n```\nPOST {base}/{prefix} {body_str}\n→ 201\n```"
                    )
                    example_count += 1

            # List example
            if hasattr(viewset, 'list') and example_count < max_per_resource:
                search_fields = getattr(viewset, 'search_fields', None)
                if search_fields:
                    all_examples.append(
                        f"Search {prefix}:\n```\nGET {base}/{prefix}?search=example\n→ 200\n```"
                    )
                else:
                    all_examples.append(
                        f"List {prefix}:\n```\nGET {base}/{prefix}\n→ 200\n```"
                    )
                example_count += 1

        if not all_examples:
            return None

        lines = ["## Examples\n"] + all_examples
        return "\n\n".join(lines)
