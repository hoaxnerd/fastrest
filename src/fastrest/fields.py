"""Serializer fields matching DRF's field API."""

from __future__ import annotations

import copy
import datetime
import decimal
import re
import uuid
from typing import Any, Callable


class _Empty:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "empty"

    def __bool__(self) -> bool:
        return False

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def __reduce__(self):
        return (_Empty, ())


empty = _Empty()

_MISSING = object()


class SkipField(Exception):
    pass


class Field:
    default_error_messages = {
        "required": "This field is required.",
        "null": "This field may not be null.",
    }
    default_validators: list[Callable] = []
    initial = None

    def __init__(
        self,
        *,
        read_only: bool = False,
        write_only: bool = False,
        required: bool | None = None,
        default: Any = empty,
        source: str | None = None,
        validators: list[Callable] | None = None,
        allow_null: bool = False,
        label: str | None = None,
        help_text: str | None = None,
        error_messages: dict[str, str] | None = None,
    ):
        self.read_only = read_only
        self.write_only = write_only
        self._required = required
        self.default = default
        self.source = source
        self.validators = validators or list(self.default_validators)
        self.allow_null = allow_null
        self.label = label
        self.help_text = help_text

        self.field_name: str | None = None
        self.parent: Any = None

        messages = {}
        for cls in reversed(type(self).__mro__):
            messages.update(getattr(cls, "default_error_messages", {}))
        if error_messages:
            messages.update(error_messages)
        self.error_messages = messages

    @property
    def required(self) -> bool:
        if self._required is not None:
            return self._required
        return self.default is empty and not self.read_only

    @required.setter
    def required(self, value: bool) -> None:
        self._required = value

    def bind(self, field_name: str, parent: Any) -> None:
        self.field_name = field_name
        self.parent = parent
        if self.source is None:
            self.source = field_name

    def get_value(self, data: dict) -> Any:
        if self.field_name not in data:
            return empty
        return data[self.field_name]

    def get_attribute(self, instance: Any) -> Any:
        source = self.source or self.field_name
        attrs = source.split(".")
        val = instance
        for attr in attrs:
            if isinstance(val, dict):
                val = val.get(attr, empty)
            else:
                val = getattr(val, attr, empty)
            if val is empty:
                return None
        return val

    def get_default(self) -> Any:
        if self.default is empty:
            raise SkipField()
        if callable(self.default):
            return self.default()
        return self.default

    def run_validation(self, data: Any = empty) -> Any:
        if data is empty:
            if self.required:
                self.fail("required")
            return self.get_default()

        if data is None:
            if not self.allow_null:
                self.fail("null")
            return None

        value = self.to_internal_value(data)
        self.run_validators(value)
        return value

    def run_validators(self, value: Any) -> None:
        errors = []
        for validator in self.validators:
            try:
                validator(value)
            except Exception as exc:
                if hasattr(exc, "detail"):
                    errors.extend(exc.detail if isinstance(exc.detail, list) else [exc.detail])
                else:
                    errors.append(str(exc))
        if errors:
            from fastrest.exceptions import ValidationError
            raise ValidationError(errors)

    def to_internal_value(self, data: Any) -> Any:
        return data

    def to_representation(self, value: Any) -> Any:
        return value

    def fail(self, key: str, **kwargs: Any) -> None:
        from fastrest.exceptions import ValidationError
        msg = self.error_messages.get(key, key)
        if kwargs:
            msg = msg.format(**kwargs)
        raise ValidationError(msg)


class BooleanField(Field):
    default_error_messages = {
        "invalid": "Must be a valid boolean.",
    }
    TRUE_VALUES = {True, "true", "True", "TRUE", "1", 1, "yes", "Yes"}
    FALSE_VALUES = {False, "false", "False", "FALSE", "0", 0, "no", "No"}

    def to_internal_value(self, data: Any) -> bool:
        if data in self.TRUE_VALUES:
            return True
        if data in self.FALSE_VALUES:
            return False
        self.fail("invalid")

    def to_representation(self, value: Any) -> bool:
        return bool(value)


class CharField(Field):
    default_error_messages = {
        "blank": "This field may not be blank.",
        "max_length": "Ensure this field has no more than {max_length} characters.",
        "min_length": "Ensure this field has at least {min_length} characters.",
    }

    def __init__(self, *, max_length: int | None = None, min_length: int | None = None,
                 allow_blank: bool = False, trim_whitespace: bool = True, **kwargs: Any):
        self.max_length = max_length
        self.min_length = min_length
        self.allow_blank = allow_blank
        self.trim_whitespace = trim_whitespace
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> str:
        value = str(data)
        if self.trim_whitespace:
            value = value.strip()
        if not value and not self.allow_blank:
            self.fail("blank")
        if self.max_length is not None and len(value) > self.max_length:
            self.fail("max_length", max_length=self.max_length)
        if self.min_length is not None and len(value) < self.min_length:
            self.fail("min_length", min_length=self.min_length)
        return value

    def to_representation(self, value: Any) -> str:
        return str(value) if value is not None else ""


class EmailField(CharField):
    default_error_messages = {
        "invalid": "Enter a valid email address.",
    }

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data)
        if value and "@" not in value:
            self.fail("invalid")
        return value


class RegexField(CharField):
    def __init__(self, regex: str, **kwargs: Any):
        self.regex = re.compile(regex)
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data)
        if not self.regex.search(value):
            self.fail("invalid")
        return value


class SlugField(CharField):
    default_error_messages = {
        "invalid": "Enter a valid 'slug' consisting of letters, numbers, underscores or hyphens.",
    }

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data)
        if value and not re.match(r"^[-\w]+$", value):
            self.fail("invalid")
        return value


class URLField(CharField):
    default_error_messages = {
        "invalid": "Enter a valid URL.",
    }

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data)
        if value and not value.startswith(("http://", "https://")):
            self.fail("invalid")
        return value


class UUIDField(Field):
    default_error_messages = {
        "invalid": '"{value}" is not a valid UUID.',
    }

    def to_internal_value(self, data: Any) -> uuid.UUID:
        if isinstance(data, uuid.UUID):
            return data
        try:
            return uuid.UUID(str(data))
        except (ValueError, AttributeError):
            self.fail("invalid", value=data)

    def to_representation(self, value: Any) -> str:
        return str(value)


class IPAddressField(CharField):
    default_error_messages = {
        "invalid": "Enter a valid IPv4 or IPv6 address.",
    }

    def __init__(self, protocol: str = "both", **kwargs: Any):
        self.protocol = protocol
        super().__init__(**kwargs)


class IntegerField(Field):
    default_error_messages = {
        "invalid": "A valid integer is required.",
        "max_value": "Ensure this value is less than or equal to {max_value}.",
        "min_value": "Ensure this value is greater than or equal to {min_value}.",
    }

    def __init__(self, *, max_value: int | None = None, min_value: int | None = None, **kwargs: Any):
        self.max_value = max_value
        self.min_value = min_value
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> int:
        try:
            value = int(data)
        except (ValueError, TypeError):
            self.fail("invalid")
        if self.max_value is not None and value > self.max_value:
            self.fail("max_value", max_value=self.max_value)
        if self.min_value is not None and value < self.min_value:
            self.fail("min_value", min_value=self.min_value)
        return value

    def to_representation(self, value: Any) -> int:
        return int(value) if value is not None else 0


class FloatField(Field):
    default_error_messages = {
        "invalid": "A valid number is required.",
        "max_value": "Ensure this value is less than or equal to {max_value}.",
        "min_value": "Ensure this value is greater than or equal to {min_value}.",
    }

    def __init__(self, *, max_value: float | None = None, min_value: float | None = None, **kwargs: Any):
        self.max_value = max_value
        self.min_value = min_value
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> float:
        try:
            value = float(data)
        except (ValueError, TypeError):
            self.fail("invalid")
        if self.max_value is not None and value > self.max_value:
            self.fail("max_value", max_value=self.max_value)
        if self.min_value is not None and value < self.min_value:
            self.fail("min_value", min_value=self.min_value)
        return value

    def to_representation(self, value: Any) -> float:
        return float(value) if value is not None else 0.0


class DecimalField(Field):
    default_error_messages = {
        "invalid": "A valid number is required.",
        "max_digits": "Ensure that there are no more than {max_digits} digits in total.",
        "max_decimal_places": "Ensure that there are no more than {max_decimal_places} decimal places.",
    }

    def __init__(self, *, max_digits: int | None = None, decimal_places: int | None = None, **kwargs: Any):
        self.max_digits = max_digits
        self.decimal_places = decimal_places
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> decimal.Decimal:
        try:
            return decimal.Decimal(str(data))
        except (decimal.InvalidOperation, ValueError, TypeError):
            self.fail("invalid")

    def to_representation(self, value: Any) -> str:
        if value is None:
            return None
        return str(value)


class DateTimeField(Field):
    default_error_messages = {
        "invalid": "Datetime has wrong format.",
    }

    def __init__(self, *, format: str | None = None, input_formats: list[str] | None = None, **kwargs: Any):
        self.format = format
        self.input_formats = input_formats
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> datetime.datetime:
        if isinstance(data, datetime.datetime):
            return data
        if isinstance(data, str):
            try:
                return datetime.datetime.fromisoformat(data)
            except ValueError:
                pass
        self.fail("invalid")

    def to_representation(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime.datetime):
            return value.isoformat()
        return str(value)


class DateField(Field):
    default_error_messages = {
        "invalid": "Date has wrong format.",
    }

    def to_internal_value(self, data: Any) -> datetime.date:
        if isinstance(data, datetime.date) and not isinstance(data, datetime.datetime):
            return data
        if isinstance(data, str):
            try:
                return datetime.date.fromisoformat(data)
            except ValueError:
                pass
        self.fail("invalid")

    def to_representation(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime.date):
            return value.isoformat()
        return str(value)


class TimeField(Field):
    default_error_messages = {
        "invalid": "Time has wrong format.",
    }

    def to_internal_value(self, data: Any) -> datetime.time:
        if isinstance(data, datetime.time):
            return data
        if isinstance(data, str):
            try:
                return datetime.time.fromisoformat(data)
            except ValueError:
                pass
        self.fail("invalid")

    def to_representation(self, value: Any) -> str | None:
        if value is None:
            return None
        return value.isoformat() if isinstance(value, datetime.time) else str(value)


class DurationField(Field):
    default_error_messages = {
        "invalid": "Duration has wrong format.",
    }

    def to_internal_value(self, data: Any) -> datetime.timedelta:
        if isinstance(data, datetime.timedelta):
            return data
        if isinstance(data, (int, float)):
            return datetime.timedelta(seconds=data)
        self.fail("invalid")

    def to_representation(self, value: Any) -> float | None:
        if value is None:
            return None
        return value.total_seconds()


class ChoiceField(Field):
    default_error_messages = {
        "invalid_choice": '"{input}" is not a valid choice.',
    }

    def __init__(self, choices: list | dict, **kwargs: Any):
        if isinstance(choices, dict):
            self.choices = choices
        else:
            self.choices = {c: c for c in choices}
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> Any:
        if data in self.choices:
            return data
        self.fail("invalid_choice", input=data)


class MultipleChoiceField(ChoiceField):
    def to_internal_value(self, data: Any) -> set:
        if not isinstance(data, (list, set, tuple)):
            self.fail("invalid_choice", input=data)
        result = set()
        for item in data:
            if item not in self.choices:
                self.fail("invalid_choice", input=item)
            result.add(item)
        return result


class FileField(Field):
    default_error_messages = {
        "invalid": "The submitted data was not a file.",
    }

    def to_internal_value(self, data: Any) -> Any:
        return data


class ImageField(FileField):
    default_error_messages = {
        "invalid_image": "Upload a valid image.",
    }


class ListField(Field):
    default_error_messages = {
        "not_a_list": 'Expected a list of items but got type "{input_type}".',
    }

    def __init__(self, *, child: Field | None = None, **kwargs: Any):
        self.child = child
        super().__init__(**kwargs)
        if self.child:
            self.child.bind("", self)

    def to_internal_value(self, data: Any) -> list:
        if not isinstance(data, list):
            self.fail("not_a_list", input_type=type(data).__name__)
        if self.child:
            return [self.child.run_validation(item) for item in data]
        return list(data)

    def to_representation(self, value: Any) -> list:
        if self.child:
            return [self.child.to_representation(item) for item in value]
        return list(value) if value else []


class DictField(Field):
    default_error_messages = {
        "not_a_dict": 'Expected a dictionary but got type "{input_type}".',
    }

    def __init__(self, *, child: Field | None = None, **kwargs: Any):
        self.child = child
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> dict:
        if not isinstance(data, dict):
            self.fail("not_a_dict", input_type=type(data).__name__)
        if self.child:
            return {k: self.child.run_validation(v) for k, v in data.items()}
        return dict(data)


class JSONField(Field):
    def to_internal_value(self, data: Any) -> Any:
        return data

    def to_representation(self, value: Any) -> Any:
        return value


class ReadOnlyField(Field):
    def __init__(self, **kwargs: Any):
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> Any:
        return data


class HiddenField(Field):
    def __init__(self, **kwargs: Any):
        kwargs["write_only"] = True
        assert "default" in kwargs, "HiddenField requires a default value."
        super().__init__(**kwargs)

    def get_value(self, data: dict) -> Any:
        return self.default() if callable(self.default) else self.default


class SerializerMethodField(Field):
    def __init__(self, method_name: str | None = None, **kwargs: Any):
        kwargs["read_only"] = True
        kwargs["source"] = "*"
        self.method_name = method_name
        super().__init__(**kwargs)

    def bind(self, field_name: str, parent: Any) -> None:
        if self.method_name is None:
            self.method_name = f"get_{field_name}"
        super().bind(field_name, parent)

    def to_representation(self, value: Any) -> Any:
        method = getattr(self.parent, self.method_name)
        return method(value)


# Map from ORM field type strings to Field classes
FIELD_TYPE_MAP: dict[str, type[Field]] = {
    "integer": IntegerField,
    "string": CharField,
    "text": CharField,
    "boolean": BooleanField,
    "float": FloatField,
    "decimal": DecimalField,
    "date": DateField,
    "datetime": DateTimeField,
    "time": TimeField,
    "json": JSONField,
    "uuid": UUIDField,
}
