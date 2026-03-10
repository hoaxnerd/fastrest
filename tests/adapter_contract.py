"""Shared adapter contract tests.

Subclasses must define:
    - self.adapter: ORMAdapter instance
    - self.model: ORM model class
    - self.session: session object (or None for session-less adapters)
    - self.create_kwargs: dict of kwargs to create a test instance
    - self.update_kwargs: dict of kwargs to update a test instance
"""

from fastrest.compat.orm.base import FieldInfo, ORMAdapter


class AdapterContractTests:
    """Mixin that tests the 12-method ORMAdapter contract."""

    async def test_get_fields_returns_field_info_list(self):
        fields = self.adapter.get_fields(self.model)
        assert isinstance(fields, list)
        assert len(fields) > 0
        for f in fields:
            assert isinstance(f, FieldInfo)
            assert isinstance(f.name, str)
            assert isinstance(f.field_type, str)
            assert isinstance(f.primary_key, bool)

    async def test_get_fields_contains_expected_names(self):
        fields = self.adapter.get_fields(self.model)
        names = {f.name for f in fields}
        for expected in self.expected_field_names:
            assert expected in names, f"Expected field '{expected}' not found in {names}"

    async def test_get_field_type(self):
        fields = self.adapter.get_fields(self.model)
        for f in fields:
            result = self.adapter.get_field_type(f)
            assert isinstance(result, str)
            assert result == f.field_type

    async def test_get_pk_field(self):
        pk = self.adapter.get_pk_field(self.model)
        assert isinstance(pk, FieldInfo)
        assert pk.primary_key is True

    async def test_get_relations(self):
        relations = self.adapter.get_relations(self.model)
        assert isinstance(relations, list)

    async def test_create(self):
        obj = await self.adapter.create(self.model, self.session, **self.create_kwargs)
        assert obj is not None

    async def test_get_queryset(self):
        await self.adapter.create(self.model, self.session, **self.create_kwargs)
        items = await self.adapter.get_queryset(self.model, self.session)
        assert isinstance(items, list)
        assert len(items) >= 1

    async def test_get_object(self):
        obj = await self.adapter.create(self.model, self.session, **self.create_kwargs)
        pk_field = self.adapter.get_pk_field(self.model)
        pk_value = getattr(obj, pk_field.name)
        found = await self.adapter.get_object(self.model, self.session, **{pk_field.name: pk_value})
        assert found is not None

    async def test_get_object_not_found(self):
        result = await self.adapter.get_object(self.model, self.session, **self.nonexistent_lookup)
        assert result is None

    async def test_update(self):
        obj = await self.adapter.create(self.model, self.session, **self.create_kwargs)
        updated = await self.adapter.update(obj, self.session, **self.update_kwargs)
        for key, value in self.update_kwargs.items():
            assert getattr(updated, key) == value

    async def test_delete(self):
        obj = await self.adapter.create(self.model, self.session, **self.create_kwargs)
        await self.adapter.delete(obj, self.session)
        pk_field = self.adapter.get_pk_field(self.model)
        pk_value = getattr(obj, pk_field.name)
        found = await self.adapter.get_object(self.model, self.session, **{pk_field.name: pk_value})
        assert found is None

    async def test_count(self):
        initial = await self.adapter.count(self.model, self.session)
        await self.adapter.create(self.model, self.session, **self.create_kwargs)
        after = await self.adapter.count(self.model, self.session)
        assert after == initial + 1

    async def test_exists_true(self):
        obj = await self.adapter.create(self.model, self.session, **self.create_kwargs)
        pk_field = self.adapter.get_pk_field(self.model)
        pk_value = getattr(obj, pk_field.name)
        assert await self.adapter.exists(self.model, self.session, **{pk_field.name: pk_value}) is True

    async def test_exists_false(self):
        assert await self.adapter.exists(self.model, self.session, **self.nonexistent_lookup) is False

    async def test_filter_queryset(self):
        await self.adapter.create(self.model, self.session, **self.create_kwargs)
        results = await self.adapter.filter_queryset(
            self.model, self.session, **self.filter_kwargs,
        )
        assert isinstance(results, list)
