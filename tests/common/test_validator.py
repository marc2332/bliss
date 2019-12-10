from bliss.common.validator import BlissValidator
from cerberus import errors
import pytest

# tests inspired by tests of cerberus package


def assert_success(document, schema, validator=None, update=False):
    """ Tests whether a validation succeeds. """
    if validator is None:
        validator = BlissValidator(schema)
    result = validator(document, schema, update)
    assert isinstance(result, bool)
    if not result:
        raise AssertionError(validator.errors)


def assert_normalized(document, expected, schema, validator=None):
    if validator is None:
        validator = BlissValidator(schema)
    assert_success(document, schema, validator)
    assert validator.document == expected


def assert_fail(
    document, schema, validator=None, update=False, errors=None, child_errors=None
):
    """ Tests whether a validation fails. """
    if validator is None:
        validator = BlissValidator(schema)
    result = validator(document, schema, update)
    assert isinstance(result, bool)
    assert not result

    actual_errors = validator.errors

    assert actual_errors == errors


def test_oneof_normalization():
    # inserting a default
    schema = {
        "foo": {"type": "string"},
        "bar": {
            "oneof": [
                {"dependencies": {"foo": "B"}, "default": "B"},
                {"dependencies": {"foo": "A"}, "default": "C"},
            ]
        },
    }
    document = {"foo": "A"}
    expected = {"foo": "A", "bar": "C"}
    assert_normalized(document, expected, schema)

    # overwriting None if not nullable
    document = {"foo": "A", "bar": None}
    assert_normalized(document, expected, schema)

    # using a sub-schema inside oneof
    subschema = {
        "field1": {"type": "number"},
        "field2": {"type": "number", "default": 2},
    }
    schema = {
        "foo": {"type": "string"},
        "bar": {
            "type": "dict",
            "oneof": [
                {"dependencies": {"^foo": "B"}, "schema": subschema},
                {"dependencies": {"^foo": "A"}, "default": "C"},
            ],
        },
    }
    document = {"foo": "B", "bar": {"field1": 1}}
    expected = {"foo": "B", "bar": {"field1": 1, "field2": 2}}
    assert_normalized(document, expected, schema)

    # do not normalize if oneof is not fullfilled
    schema = {
        "foo": {"type": "string"},
        "bar": {
            "oneof": [
                {"dependencies": {"foo": "A"}, "default": "B"},
                {"dependencies": {"foo": "A"}, "default": "C"},
            ]
        },
    }
    expected = {"foo": "A", "bar": None}
    document = {"foo": "A", "bar": None}

    validator = BlissValidator(schema)
    assert validator.normalized(document) == expected


def test_value_rule():
    schema = {"foo": {"type": "string", "value": "bar"}}
    document = {"foo": "bar"}
    assert_success(document, schema)

    document = {"foo": "A"}

    assert_fail(document, schema, errors={"foo": [" non expected value"]})


def test_default_setter():
    def my_default_setter(a):
        assert a == {"bar": "1"}
        return "toto"

    schema = {
        "foo": {"type": "string", "default_setter": my_default_setter},
        "bar": {"type": "string"},
    }
    document = {"bar": "1"}
    expected = {"foo": "toto", "bar": "1"}

    schema = {
        "foo": {
            "type": "string",
            "default_setter": "find_default",
            "find_default": "bar",
        },
        "bar": {"type": "string"},
    }
    expected = {"foo": "1", "bar": "1"}
    assert_normalized(document, expected, schema)

    master_schema = {
        "d1": {"type": "dict", "schema": schema},
        "bar": {"type": "string"},
    }
    expected = {"d1": {"foo": "1", "bar": "1"}, "bar": "2"}
    document = {"bar": "2", "d1": {"bar": "1"}}
    assert_normalized(document, expected, master_schema)

    schema = {
        "foo": {
            "type": "string",
            "default_setter": "find_default",
            "find_default": "^bar",
        },
        "bar": {"type": "string"},
    }
    master_schema = {
        "d1": {"type": "dict", "schema": schema},
        "bar": {"type": "string"},
    }
    expected = {"d1": {"foo": "2", "bar": "1"}, "bar": "2"}
    document = {"bar": "2", "d1": {"bar": "1"}}
    assert_normalized(document, expected, master_schema)
