"""Built-in MCP server driven by FastREST viewsets and serializers."""

from __future__ import annotations

import json
from typing import Any


# Standard CRUD actions and their MCP tool descriptions
CRUD_ACTIONS = {
    "list": {
        "method": "get",
        "detail": False,
        "description": "List all {resource}",
    },
    "create": {
        "method": "post",
        "detail": False,
        "description": "Create a new {resource_singular}",
    },
    "retrieve": {
        "method": "get",
        "detail": True,
        "description": "Get a single {resource_singular} by ID",
    },
    "update": {
        "method": "put",
        "detail": True,
        "description": "Update a {resource_singular} by ID",
    },
    "partial_update": {
        "method": "patch",
        "detail": True,
        "description": "Partially update a {resource_singular} by ID",
    },
    "destroy": {
        "method": "delete",
        "detail": True,
        "description": "Delete a {resource_singular} by ID",
    },
}


def _singularize(name: str) -> str:
    """Naive singularization for tool descriptions."""
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("ses") or name.endswith("xes"):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def _build_tool_params(viewset: type, action_name: str, detail: bool) -> dict[str, Any]:
    """Build a JSON Schema-compatible parameter dict for a tool."""
    properties = {}
    required = []

    if detail:
        properties["id"] = {"type": "string", "description": "The ID of the resource"}
        required.append("id")

    # For write actions, extract writable fields from serializer
    if action_name in ("create", "update", "partial_update"):
        ser_cls = getattr(viewset, "serializer_class", None)
        if ser_cls:
            instance = ser_cls()
            for name, field in instance.fields.items():
                if field.read_only:
                    continue
                from fastrest.skills import _type_name
                type_name = _type_name(field)
                json_type = _type_to_json_schema(type_name)
                prop: dict[str, Any] = {"type": json_type}
                if hasattr(field, "help_text") and field.help_text:
                    prop["description"] = field.help_text
                properties[name] = prop
                if field.required and action_name != "partial_update":
                    required.append(name)

    # For list actions, add query params
    if action_name == "list":
        search_fields = getattr(viewset, "search_fields", None)
        if search_fields:
            properties["search"] = {"type": "string", "description": "Search term"}
        ordering_fields = getattr(viewset, "ordering_fields", None)
        if ordering_fields:
            properties["ordering"] = {
                "type": "string",
                "description": f"Order by field. Options: {', '.join(ordering_fields)}",
            }
        pagination_cls = getattr(viewset, "pagination_class", None)
        if pagination_cls:
            cls_name = pagination_cls.__name__
            if "LimitOffset" in cls_name:
                properties["limit"] = {"type": "integer", "description": "Number of results"}
                properties["offset"] = {"type": "integer", "description": "Starting position"}
            else:
                properties["page"] = {"type": "integer", "description": "Page number"}
                properties["page_size"] = {"type": "integer", "description": "Results per page"}

    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _type_to_json_schema(type_name: str) -> str:
    mapping = {
        "string": "string",
        "string (email)": "string",
        "string (URL)": "string",
        "string (slug)": "string",
        "string (IP)": "string",
        "integer": "integer",
        "float": "number",
        "decimal": "string",
        "boolean": "boolean",
        "datetime": "string",
        "date": "string",
        "time": "string",
        "duration": "string",
        "UUID": "string",
        "array": "array",
        "object": "object",
        "JSON": "object",
    }
    return mapping.get(type_name, "string")


class MCPBridge:
    """Bridges FastREST viewsets/router to an MCP server.

    Introspects the router registry and auto-registers MCP tools
    for each viewset action. Tools dispatch through the viewset's
    _dispatch_view pipeline so auth/permissions/throttling all apply.
    """

    def __init__(self, router: Any, settings: Any = None):
        self.router = router
        self.settings = settings
        self._mcp = None

    def build_mcp(self, name: str = "fastrest") -> Any:
        """Build and return a FastMCP server with tools from the router."""
        from mcp.server.fastmcp import FastMCP

        self._mcp = FastMCP(name)
        self._register_tools()
        return self._mcp

    def _tool_name(self, basename: str, action_name: str) -> str:
        fmt = "{basename}_{action}"
        if self.settings:
            fmt = getattr(self.settings, "MCP_TOOL_NAME_FORMAT", fmt)
        return fmt.format(basename=basename, action=action_name)

    def _register_tools(self) -> None:
        exclude_viewsets = []
        if self.settings:
            exclude_viewsets = getattr(self.settings, "MCP_EXCLUDE_VIEWSETS", [])

        for prefix, viewset, basename in self.router.registry:
            if viewset in exclude_viewsets or basename in exclude_viewsets:
                continue

            # Register CRUD tools
            for action_name, meta in CRUD_ACTIONS.items():
                if not hasattr(viewset, action_name):
                    continue

                resource = prefix.replace("-", " ").replace("_", " ")
                resource_singular = _singularize(resource)
                description = meta["description"].format(
                    resource=resource, resource_singular=resource_singular
                )
                tool_name = self._tool_name(basename, action_name)

                self._register_crud_tool(
                    tool_name=tool_name,
                    description=description,
                    viewset=viewset,
                    action_name=action_name,
                    method=meta["method"],
                    detail=meta["detail"],
                    prefix=prefix,
                )

            # Register @action tools
            for attr_name in dir(viewset):
                attr = getattr(viewset, attr_name, None)
                if not callable(attr) or not hasattr(attr, "detail") or not hasattr(attr, "mapping"):
                    continue
                if not getattr(attr, "mcp", True):
                    continue

                mcp_description = getattr(attr, "mcp_description", None) or (
                    attr.__doc__.strip().split("\n")[0] if attr.__doc__ else
                    attr_name.replace("_", " ").title()
                )
                tool_name = self._tool_name(basename, attr_name)
                methods = list(attr.mapping.keys())

                self._register_action_tool(
                    tool_name=tool_name,
                    description=mcp_description,
                    viewset=viewset,
                    action_name=attr_name,
                    method=methods[0],
                    detail=attr.detail,
                    prefix=prefix,
                )

    def _register_crud_tool(self, tool_name, description, viewset, action_name, method, detail, prefix):
        """Register a single CRUD tool on the MCP server."""
        _viewset = viewset
        _action_name = action_name
        _method = method
        _detail = detail

        async def tool_fn(**kwargs) -> str:
            return await _execute_viewset_action(
                _viewset, _action_name, _method, _detail, kwargs
            )

        tool_fn.__name__ = tool_name
        tool_fn.__doc__ = description

        # Add type annotations for the tool parameters
        params = _build_tool_params(viewset, action_name, detail)
        _apply_annotations(tool_fn, params)

        self._mcp.add_tool(tool_fn, name=tool_name, description=description)

    def _register_action_tool(self, tool_name, description, viewset, action_name, method, detail, prefix):
        """Register a custom @action tool on the MCP server."""
        _viewset = viewset
        _action_name = action_name
        _method = method
        _detail = detail

        async def tool_fn(**kwargs) -> str:
            return await _execute_viewset_action(
                _viewset, _action_name, _method, _detail, kwargs
            )

        tool_fn.__name__ = tool_name
        tool_fn.__doc__ = description

        params = _build_tool_params(viewset, action_name, detail)
        _apply_annotations(tool_fn, params)

        self._mcp.add_tool(tool_fn, name=tool_name, description=description)


def _apply_annotations(fn, schema: dict) -> None:
    """Apply Python type annotations to a function based on JSON schema."""
    annotations = {}
    properties = schema.get("properties", {})
    json_to_python = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for name, prop in properties.items():
        json_type = prop.get("type", "string")
        py_type = json_to_python.get(json_type, str)
        # Make optional params have None default
        required = schema.get("required", [])
        if name not in required:
            annotations[name] = py_type | None
        else:
            annotations[name] = py_type
    annotations["return"] = str
    fn.__annotations__ = annotations


async def _execute_viewset_action(
    viewset_cls: type, action_name: str, method: str, detail: bool, params: dict
) -> str:
    """Execute a viewset action and return JSON string result.

    Builds a minimal fake request and dispatches through the
    viewset's full pipeline (auth, permissions, throttle, serialization).
    """
    from starlette.testclient import TestClient
    from starlette.requests import Request as StarletteRequest

    # Build action mapping
    actions = {method: action_name}

    # Extract pk/id for detail actions
    pk = params.pop("id", None)
    kwargs = {}
    if detail and pk is not None:
        kwargs["pk"] = pk

    # Build a minimal ASGI scope for the fake request
    query_params = {}
    body_data = None

    if method in ("post", "put", "patch"):
        body_data = params
    else:
        query_params = {k: str(v) for k, v in params.items() if v is not None}

    query_string = "&".join(f"{k}={v}" for k, v in query_params.items())

    # Minimal app-like object for settings resolution
    class _MinimalApp:
        class state:
            pass

    scope = {
        "type": "http",
        "method": method.upper(),
        "path": "/mcp-dispatch",
        "query_string": query_string.encode(),
        "headers": [(b"content-type", b"application/json")],
        "root_path": "",
        "server": ("localhost", 80),
        "app": _MinimalApp(),
    }

    # Create a minimal request
    async def receive():
        body = json.dumps(body_data).encode() if body_data else b""
        return {"type": "http.request", "body": body}

    request = StarletteRequest(scope, receive)

    # Inject body into request data for POST/PUT/PATCH
    if body_data is not None:
        # We pass body data through _body param to skip JSON parsing
        from pydantic import BaseModel

        class DynBody(BaseModel):
            model_config = {"extra": "allow"}

        body_obj = DynBody(**body_data)
        response = await viewset_cls._dispatch_view(actions, {}, request, _body=body_obj, **kwargs)
    else:
        response = await viewset_cls._dispatch_view(actions, {}, request, **kwargs)

    # Convert response to JSON string
    if hasattr(response, "data"):
        return json.dumps(response.data, default=str)
    if hasattr(response, "body"):
        return response.body.decode() if isinstance(response.body, bytes) else str(response.body)
    return json.dumps(response, default=str)


def mount_mcp(app: Any, router: Any, settings: Any = None, path: str | None = None) -> Any:
    """Mount MCP server onto a FastAPI app.

    Args:
        app: FastAPI application instance
        router: FastREST router with registered viewsets
        settings: Optional APISettings instance
        path: Mount path (default: settings.MCP_PREFIX or "/mcp")

    Returns:
        The FastMCP instance
    """
    if settings is None:
        from fastrest.settings import api_settings
        settings = api_settings

    if not settings.MCP_ENABLED:
        return None

    prefix = path or settings.MCP_PREFIX or "/mcp"

    bridge = MCPBridge(router, settings=settings)
    mcp = bridge.build_mcp(name=getattr(settings, "SKILL_NAME", None) or "fastrest")

    # Mount the MCP SSE app as a sub-application
    mcp_app = mcp.sse_app(mount_path=prefix)
    app.mount(prefix, mcp_app)

    return mcp
