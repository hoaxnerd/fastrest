"""ORM adapter registry and auto-detection."""

from __future__ import annotations

from typing import Any

_default_adapter = None


def get_default_adapter():
    """Return the default ORM adapter, auto-detecting from installed packages.

    Resolution order:
    1. Explicitly set adapter via ``set_default_adapter()``
    2. SQLAlchemy (if installed)
    3. Raise ImportError with guidance
    """
    global _default_adapter
    if _default_adapter is not None:
        return _default_adapter

    # Try SQLAlchemy
    try:
        from fastrest.compat.orm.sqlalchemy import adapter
        _default_adapter = adapter
        return _default_adapter
    except ImportError:
        pass

    raise ImportError(
        "No ORM adapter found. Install an ORM backend:\n"
        "  pip install fastrest[sqlalchemy]\n"
        "Or set a custom adapter via fastrest.compat.orm.set_default_adapter()."
    )


def set_default_adapter(adapter: Any) -> None:
    """Override the default ORM adapter globally."""
    global _default_adapter
    _default_adapter = adapter


def reset_default_adapter() -> None:
    """Reset to auto-detection (useful for testing)."""
    global _default_adapter
    _default_adapter = None
