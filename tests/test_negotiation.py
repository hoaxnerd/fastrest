"""Tests for content negotiation."""

import pytest

from fastrest.negotiation import (
    DefaultContentNegotiation,
    JSONRenderer,
    BrowsableAPIRenderer,
    _parse_accept_header,
    _media_type_matches,
)


class TestParseAcceptHeader:
    def test_simple(self):
        result = _parse_accept_header("application/json")
        assert result == [("application/json", 1.0)]

    def test_multiple(self):
        result = _parse_accept_header("text/html, application/json")
        assert len(result) == 2

    def test_quality(self):
        result = _parse_accept_header("text/html;q=0.9, application/json;q=1.0")
        assert result[0] == ("application/json", 1.0)
        assert result[1] == ("text/html", 0.9)

    def test_wildcard(self):
        result = _parse_accept_header("*/*")
        assert result == [("*/*", 1.0)]

    def test_empty(self):
        result = _parse_accept_header("")
        assert result == []

    def test_complex(self):
        result = _parse_accept_header("text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8")
        assert len(result) == 4
        # q=1.0 items first, then 0.9, then 0.8
        assert result[0][1] == 1.0
        assert result[-1][1] == 0.8


class TestMediaTypeMatches:
    def test_exact_match(self):
        assert _media_type_matches("application/json", "application/json") is True

    def test_no_match(self):
        assert _media_type_matches("text/html", "application/json") is False

    def test_wildcard(self):
        assert _media_type_matches("*/*", "application/json") is True

    def test_type_wildcard(self):
        assert _media_type_matches("application/*", "application/json") is True

    def test_type_wildcard_no_match(self):
        assert _media_type_matches("text/*", "application/json") is False


class TestJSONRenderer:
    def test_render(self):
        renderer = JSONRenderer()
        result = renderer.render({"key": "value"})
        assert b'"key"' in result
        assert b'"value"' in result

    def test_render_none(self):
        renderer = JSONRenderer()
        result = renderer.render(None)
        assert result == b''

    def test_media_type(self):
        assert JSONRenderer.media_type == "application/json"

    def test_format(self):
        assert JSONRenderer.format == "json"


class TestBrowsableAPIRenderer:
    def test_render(self):
        renderer = BrowsableAPIRenderer()
        result = renderer.render({"key": "value"})
        assert b"<html>" in result
        assert b'"key"' in result

    def test_media_type(self):
        assert BrowsableAPIRenderer.media_type == "text/html"

    def test_format(self):
        assert BrowsableAPIRenderer.format == "html"


class TestDefaultContentNegotiation:
    def test_select_json_renderer(self):
        neg = DefaultContentNegotiation()
        renderers = [JSONRenderer(), BrowsableAPIRenderer()]

        class FakeRequest:
            headers = {"accept": "application/json"}

        renderer, media_type = neg.select_renderer(FakeRequest(), renderers)
        assert isinstance(renderer, JSONRenderer)
        assert media_type == "application/json"

    def test_select_html_renderer(self):
        neg = DefaultContentNegotiation()
        renderers = [JSONRenderer(), BrowsableAPIRenderer()]

        class FakeRequest:
            headers = {"accept": "text/html"}

        renderer, media_type = neg.select_renderer(FakeRequest(), renderers)
        assert isinstance(renderer, BrowsableAPIRenderer)
        assert media_type == "text/html"

    def test_default_first_renderer(self):
        neg = DefaultContentNegotiation()
        renderers = [JSONRenderer(), BrowsableAPIRenderer()]

        class FakeRequest:
            headers = {"accept": "*/*"}

        renderer, media_type = neg.select_renderer(FakeRequest(), renderers)
        assert isinstance(renderer, JSONRenderer)

    def test_no_accept_header(self):
        neg = DefaultContentNegotiation()
        renderers = [JSONRenderer()]

        class FakeRequest:
            headers = {}

        renderer, media_type = neg.select_renderer(FakeRequest(), renderers)
        assert isinstance(renderer, JSONRenderer)

    def test_format_suffix(self):
        neg = DefaultContentNegotiation()
        renderers = [JSONRenderer(), BrowsableAPIRenderer()]

        class FakeRequest:
            headers = {"accept": "application/json"}

        renderer, media_type = neg.select_renderer(FakeRequest(), renderers, format_suffix="html")
        assert isinstance(renderer, BrowsableAPIRenderer)

    def test_no_renderers_raises(self):
        neg = DefaultContentNegotiation()

        class FakeRequest:
            headers = {}

        with pytest.raises(ValueError, match="No renderers"):
            neg.select_renderer(FakeRequest(), [])

    def test_quality_preference(self):
        neg = DefaultContentNegotiation()
        renderers = [JSONRenderer(), BrowsableAPIRenderer()]

        class FakeRequest:
            headers = {"accept": "text/html;q=1.0, application/json;q=0.9"}

        renderer, media_type = neg.select_renderer(FakeRequest(), renderers)
        assert isinstance(renderer, BrowsableAPIRenderer)
