"""Content negotiation classes matching DRF's negotiation API."""

from __future__ import annotations

from typing import Any


class BaseContentNegotiation:
    """Base class for content negotiation."""

    def select_renderer(self, request: Any, renderers: list, format_suffix: str | None = None) -> tuple:
        """Select a renderer given the request and list of renderers.

        Returns a (renderer, media_type) tuple.
        """
        raise NotImplementedError


class DefaultContentNegotiation(BaseContentNegotiation):
    """Standard content negotiation based on Accept header.

    Examines the request's Accept header and selects the best
    matching renderer from the available list.
    """

    def select_renderer(self, request: Any, renderers: list, format_suffix: str | None = None) -> tuple:
        if not renderers:
            raise ValueError("No renderers available")

        # If format suffix specified, match on that
        if format_suffix:
            for renderer in renderers:
                if getattr(renderer, 'format', None) == format_suffix:
                    return renderer, renderer.media_type
            # Fall through to accept header matching

        # Parse Accept header
        accept = _get_accept_header(request)
        if not accept or accept == "*/*":
            return renderers[0], renderers[0].media_type

        # Score each renderer against the Accept header
        accepts = _parse_accept_header(accept)
        for media_type, quality in accepts:
            for renderer in renderers:
                if _media_type_matches(media_type, renderer.media_type):
                    return renderer, renderer.media_type

        # No match — return first renderer as fallback
        return renderers[0], renderers[0].media_type


def _get_accept_header(request: Any) -> str:
    """Extract Accept header from request."""
    if hasattr(request, 'headers'):
        return request.headers.get('accept', '*/*')
    if hasattr(request, '_request') and hasattr(request._request, 'headers'):
        return request._request.headers.get('accept', '*/*')
    return '*/*'


def _parse_accept_header(accept: str) -> list[tuple[str, float]]:
    """Parse Accept header into sorted list of (media_type, quality) tuples."""
    result = []
    for part in accept.split(','):
        part = part.strip()
        if not part:
            continue

        params = part.split(';')
        media_type = params[0].strip()
        quality = 1.0

        for param in params[1:]:
            param = param.strip()
            if param.startswith('q='):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 0.0

        result.append((media_type, quality))

    result.sort(key=lambda x: x[1], reverse=True)
    return result


def _media_type_matches(accept_type: str, renderer_type: str) -> bool:
    """Check if an accept media type matches a renderer's media type."""
    if accept_type == '*/*':
        return True
    if accept_type == renderer_type:
        return True
    # Match type/* patterns
    accept_parts = accept_type.split('/')
    renderer_parts = renderer_type.split('/')
    if len(accept_parts) == 2 and len(renderer_parts) == 2:
        if accept_parts[0] == renderer_parts[0] and accept_parts[1] == '*':
            return True
    return False


class BaseRenderer:
    """Base renderer class."""
    media_type: str = 'application/json'
    format: str | None = None
    charset: str = 'utf-8'

    def render(self, data: Any, accepted_media_type: str | None = None, renderer_context: dict | None = None) -> Any:
        raise NotImplementedError


class JSONRenderer(BaseRenderer):
    """Renders data as JSON."""
    media_type = 'application/json'
    format = 'json'

    def render(self, data: Any, accepted_media_type: str | None = None, renderer_context: dict | None = None) -> Any:
        import json
        if data is None:
            return b''
        return json.dumps(data, default=str).encode(self.charset)


class BrowsableAPIRenderer(BaseRenderer):
    """Placeholder for browsable API renderer (HTML)."""
    media_type = 'text/html'
    format = 'html'

    def render(self, data: Any, accepted_media_type: str | None = None, renderer_context: dict | None = None) -> Any:
        import json
        html = f"""<!DOCTYPE html>
<html>
<head><title>API Response</title></head>
<body>
<pre>{json.dumps(data, indent=2, default=str)}</pre>
</body>
</html>"""
        return html.encode(self.charset)
