"""Serializers matching DRF's serializer API."""

from __future__ import annotations

import copy
from collections import OrderedDict
from typing import Any

from fastrest.fields import Field, empty, SkipField, FIELD_TYPE_MAP
from fastrest.exceptions import ValidationError


class SerializerMetaclass(type):
    def __new__(mcs, name: str, bases: tuple, attrs: dict) -> type:
        declared_fields = {}
        for key, val in list(attrs.items()):
            if isinstance(val, Field):
                declared_fields[key] = val
        attrs["_declared_fields"] = declared_fields
        return super().__new__(mcs, name, bases, attrs)


class BaseSerializer(metaclass=SerializerMetaclass):
    def __init__(
        self,
        instance: Any = None,
        data: Any = empty,
        *,
        many: bool = False,
        partial: bool = False,
        context: dict | None = None,
        **kwargs: Any,
    ):
        self.instance = instance
        self.initial_data = data
        self.partial = partial
        self.context = context or {}
        self._validated_data: Any = empty
        self._errors: Any = None
        self._data: Any = None

        if many:
            # Return early; __init_subclass__ or many_init handles this
            pass

    def __new__(cls, *args: Any, **kwargs: Any) -> BaseSerializer:
        if kwargs.pop("many", False):
            return cls.many_init(cls, *args, **kwargs)
        return super().__new__(cls)

    @classmethod
    def many_init(cls, child_cls: type, *args: Any, **kwargs: Any) -> ListSerializer:
        child = child_cls(*args, **kwargs)
        return ListSerializer(child=child, *args, **kwargs)

    def is_valid(self, *, raise_exception: bool = False) -> bool:
        if self.initial_data is empty:
            raise AssertionError("Cannot call `.is_valid()` without passing `data=` to the serializer.")
        if self._validated_data is not empty:
            return not bool(self._errors)
        try:
            self._validated_data = self.run_validation(self.initial_data)
        except ValidationError as exc:
            self._validated_data = {}
            self._errors = exc.detail
        else:
            self._errors = {}
        if self._errors and raise_exception:
            raise ValidationError(self._errors)
        return not bool(self._errors)

    def run_validation(self, data: Any) -> Any:
        return data

    @property
    def validated_data(self) -> Any:
        if self._validated_data is empty:
            raise AssertionError("You must call `.is_valid()` before accessing `.validated_data`.")
        return self._validated_data

    @property
    def errors(self) -> Any:
        if self._errors is None:
            raise AssertionError("You must call `.is_valid()` before accessing `.errors`.")
        return self._errors

    @property
    def data(self) -> Any:
        if self._data is not None:
            return self._data
        if self.instance is not None:
            self._data = self.to_representation(self.instance)
        elif self._validated_data is not empty:
            self._data = self.to_representation(self._validated_data)
        else:
            self._data = self.to_representation(self.initial_data)
        return self._data

    def to_representation(self, instance: Any) -> Any:
        return instance

    def save(self, **kwargs: Any) -> Any:
        validated_data = dict(self.validated_data)
        validated_data.update(kwargs)

        if self.instance is not None:
            self.instance = self.update(self.instance, validated_data)
        else:
            self.instance = self.create(validated_data)
        return self.instance

    def create(self, validated_data: dict) -> Any:
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict) -> Any:
        raise NotImplementedError


class Serializer(BaseSerializer):
    def get_fields(self) -> OrderedDict[str, Field]:
        fields = OrderedDict()
        for key, field in self._declared_fields.items():
            fields[key] = copy.deepcopy(field)
        return fields

    def get_validators(self) -> list:
        return []

    def bind_fields(self, fields: OrderedDict[str, Field]) -> None:
        for field_name, field in fields.items():
            field.bind(field_name, self)

    @property
    def fields(self) -> OrderedDict[str, Field]:
        if not hasattr(self, "_fields"):
            self._fields = self.get_fields()
            self.bind_fields(self._fields)
        return self._fields

    def run_validation(self, data: Any) -> dict:
        if not isinstance(data, dict):
            raise ValidationError("Invalid data. Expected a dictionary.")
        value = self.to_internal_value(data)
        try:
            value = self.validate(value)
        except ValidationError:
            raise
        return value

    def to_internal_value(self, data: dict) -> dict:
        ret = OrderedDict()
        errors = OrderedDict()

        for field_name, field in self.fields.items():
            if field.read_only:
                continue
            value = field.get_value(data)
            if value is empty and self.partial:
                continue
            try:
                validated = field.run_validation(value)
            except SkipField:
                continue
            except ValidationError as exc:
                errors[field_name] = exc.detail
                continue

            # Per-field validate_<name> hook
            validate_method = getattr(self, f"validate_{field_name}", None)
            if validate_method:
                try:
                    validated = validate_method(validated)
                except ValidationError as exc:
                    errors[field_name] = exc.detail
                    continue

            ret[field_name] = validated

        if errors:
            raise ValidationError(errors)
        return ret

    def to_representation(self, instance: Any) -> OrderedDict:
        ret = OrderedDict()
        for field_name, field in self.fields.items():
            if field.write_only:
                continue
            try:
                value = field.get_attribute(instance)
            except SkipField:
                continue
            ret[field_name] = field.to_representation(value)
        return ret

    def validate(self, attrs: dict) -> dict:
        return attrs


class ListSerializer(BaseSerializer):
    child: BaseSerializer | None = None

    def __init__(self, *args: Any, child: BaseSerializer | None = None,
                 allow_empty: bool = True, max_length: int | None = None,
                 min_length: int | None = None, **kwargs: Any):
        self.child = child
        self.allow_empty = allow_empty
        self.max_length = max_length
        self.min_length = min_length
        kwargs.pop("many", None)
        super().__init__(*args, **kwargs)

    def run_validation(self, data: Any) -> list:
        if not isinstance(data, list):
            raise ValidationError("Expected a list of items.")
        ret = []
        errors = []
        for item in data:
            try:
                validated = self.child.run_validation(item)
                ret.append(validated)
                errors.append({})
            except ValidationError as exc:
                ret.append({})
                errors.append(exc.detail)
        if any(errors):
            raise ValidationError(errors)
        return ret

    def to_representation(self, data: list) -> list:
        return [self.child.to_representation(item) for item in data]

    @property
    def data(self) -> list:
        if self._data is not None:
            return self._data
        if self.instance is not None:
            self._data = self.to_representation(self.instance)
        elif self._validated_data is not empty:
            self._data = self.to_representation(self._validated_data)
        return self._data


class ModelSerializer(Serializer):
    class Meta:
        model = None
        fields: str | list = "__all__"
        exclude: list | None = None
        read_only_fields: list | None = None
        extra_kwargs: dict | None = None
        depth: int = 0

    def __init__(self, *args: Any, **kwargs: Any):
        self._adapter = None
        super().__init__(*args, **kwargs)

    @property
    def adapter(self):
        if self._adapter is None:
            from fastrest.compat.orm.sqlalchemy import adapter
            self._adapter = adapter
        return self._adapter

    def get_fields(self) -> OrderedDict[str, Field]:
        declared = OrderedDict()
        for key, field in self._declared_fields.items():
            declared[key] = copy.deepcopy(field)

        meta = self.Meta
        model = meta.model
        if model is None:
            return declared

        orm_fields = self.adapter.get_fields(model)
        field_names = self._get_field_names(meta, orm_fields)

        fields = OrderedDict()
        for name in field_names:
            if name in declared:
                fields[name] = declared[name]
                continue
            orm_field = next((f for f in orm_fields if f.name == name), None)
            if orm_field:
                fields[name] = self._build_field(orm_field, meta)

        return fields

    def _get_field_names(self, meta: type, orm_fields: list) -> list[str]:
        all_names = [f.name for f in orm_fields]
        declared_names = list(self._declared_fields.keys())

        if meta.fields == "__all__":
            names = all_names + [n for n in declared_names if n not in all_names]
        elif isinstance(meta.fields, (list, tuple)):
            names = list(meta.fields)
        else:
            names = all_names

        exclude = getattr(meta, "exclude", None) or []
        names = [n for n in names if n not in exclude]
        return names

    def _build_field(self, orm_field, meta: type) -> Field:
        field_cls = FIELD_TYPE_MAP.get(orm_field.field_type, Field)
        kwargs: dict[str, Any] = {}

        if orm_field.primary_key:
            kwargs["read_only"] = True

        read_only_fields = getattr(meta, "read_only_fields", None) or []
        if orm_field.name in read_only_fields:
            kwargs["read_only"] = True

        if not orm_field.primary_key and not orm_field.nullable and not orm_field.has_default:
            kwargs.setdefault("required", True)
        else:
            kwargs.setdefault("required", False)

        if orm_field.nullable:
            kwargs["allow_null"] = True

        if orm_field.max_length and field_cls in (type(None),) or hasattr(field_cls, "max_length"):
            # CharField and subclasses accept max_length
            if orm_field.max_length:
                kwargs["max_length"] = orm_field.max_length

        extra_kwargs = getattr(meta, "extra_kwargs", None) or {}
        if orm_field.name in extra_kwargs:
            kwargs.update(extra_kwargs[orm_field.name])

        return field_cls(**kwargs)

    async def create(self, validated_data: dict) -> Any:
        session = self.context.get("session")
        return await self.adapter.create(self.Meta.model, session, **validated_data)

    async def update(self, instance: Any, validated_data: dict) -> Any:
        session = self.context.get("session")
        return await self.adapter.update(instance, session, **validated_data)

    async def save(self, **kwargs: Any) -> Any:
        validated_data = dict(self.validated_data)
        validated_data.update(kwargs)

        if self.instance is not None:
            self.instance = await self.update(self.instance, validated_data)
        else:
            self.instance = await self.create(validated_data)
        return self.instance


class HyperlinkedModelSerializer(ModelSerializer):
    pass
