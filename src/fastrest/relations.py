"""Relational fields — stub for Phase 2."""

from __future__ import annotations

from fastrest.fields import Field


class RelatedField(Field):
    pass


class PrimaryKeyRelatedField(RelatedField):
    pass


class HyperlinkedRelatedField(RelatedField):
    pass


class SlugRelatedField(RelatedField):
    pass


class HyperlinkedIdentityField(HyperlinkedRelatedField):
    pass
