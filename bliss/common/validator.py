# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from typing import Mapping, Sequence

from cerberus import Validator, errors
from cerberus.validator import _SchemaRuleTypeError
from cerberus.platform import _str_type


class BlissValidator(Validator):
    """
    A cerberus based validator that can handle normalization also for oneof rule
    """

    _NotProvided = type("_NotProvided", (), {})()

    def __init__(self, *args, **kwargs):
        Validator.__init__(self, *args, **kwargs)
        self._BareValidator__normalize_containers = self.__normalize_containers
        self._BareValidator__normalize_default_fields = self.__normalize_default_fields

    #### ---- Methods that extend the grammar of the validator
    def _normalize_find_default(self, mapping, schema, field):
        """find_default is only used in connection with default_setter=find_default
        The rule's arguments are validated against this schema:
        { 'nullable': True}
        """
        raise RuntimeError

    def _validate_value(self, expected_value, field, value):
        """
        The rule's arguments are validated against this schema:
        { 'nullable': True}
        """
        if not value == expected_value:
            self._error(field, f" non expected value")

    def _normalize_default_setter_find_default(self, mapping, schema, field):

        if not "find_default" in schema[field]:
            return self._NotProvided

        return self._lookup_field(schema[field]["find_default"])[1]

    #### ---- Methods that had to be patched in cerberus

    def _normalize_default_setter(self, mapping, schema, field):
        """ {'oneof': [
                {'type': 'callable'},
                {'type': 'string'}
                ]} """
        if "default_setter" in schema[field]:
            setter = schema[field]["default_setter"]
            if isinstance(setter, str):
                setter = self._BareValidator__get_rule_handler(
                    "normalize_default_setter", setter
                )
                tmp = setter(mapping, schema, field)
            else:
                tmp = setter(mapping)
            if tmp != self._NotProvided:
                mapping[field] = tmp

    def __normalize_containers(self, mapping, schema):
        for field in mapping:
            rules = set(schema.get(field, ()))

            if "oneof" in rules:
                self.__normalize_oneof(mapping, schema, field)

            # TODO: This check conflates validation and normalization
            if isinstance(mapping[field], Mapping):
                if "keysrules" in rules:
                    self._BareValidator__normalize_mapping_per_keysrules(
                        field, mapping, schema[field]["keysrules"]
                    )
                if "valuesrules" in rules:
                    self._BareValidator__normalize_mapping_per_valuesrules(
                        field, mapping, schema[field]["valuesrules"]
                    )
                if rules & set(
                    ("allow_unknown", "purge_unknown", "schema")
                ) or isinstance(self.allow_unknown, Mapping):
                    try:
                        self._BareValidator__normalize_mapping_per_schema(
                            field, mapping, schema
                        )
                    except _SchemaRuleTypeError:
                        pass

            elif isinstance(mapping[field], _str_type):
                continue

            elif isinstance(mapping[field], Sequence):
                if "schema" in rules:
                    self._BareValidator__normalize_sequence_per_schema(
                        field, mapping, schema
                    )
                elif "items" in rules:
                    self._BareValidator__normalize_sequence_per_items(
                        field, mapping, schema
                    )

    def __normalize_oneof(self, mapping, schema, field):

        definitions = schema[field]["oneof"]

        valid_counter = 0
        last_valid_validator = None

        for i, definition in enumerate(definitions):
            schema = {field: definition.copy()}
            for rule in ("allow_unknown", "type"):
                if rule not in schema[field] and rule in self.schema[field]:
                    schema[field][rule] = self.schema[field][rule]
            if "allow_unknown" not in schema[field]:
                schema[field]["allow_unknown"] = self.allow_unknown

            validator = self._get_child_validator(
                schema_crumb=(field, "oneof", i), schema=schema, allow_unknown=True
            )
            if validator(self.document, update=self.update, normalize=True):
                valid_counter += 1
                last_valid_validator = validator
            else:
                self._drop_nodes_from_errorpaths(validator._errors, [], [3])

        if valid_counter == 1:
            if field in mapping:
                norm = last_valid_validator.normalized({field: mapping[field]})[field]
            else:
                norm = last_valid_validator.normalized({})[field]
            mapping[field] = norm

    def _validate_oneof(self, definitions, field, value):
        """ {'type': 'list'} """
        # Sort of hack: remove  'logical': 'oneof'""from docstring above
        valids, _errors = self._BareValidator__validate_logical(
            "oneof", definitions, field, value
        )
        if valids != 1:
            self._error(field, errors.ONEOF, _errors, valids, len(definitions))

    def __normalize_default_fields(self, mapping, schema):
        empty_fields = [
            x
            for x in schema
            if x not in mapping
            or (
                mapping[x] is None  # noqa: W503
                and not schema[x].get("nullable", False)
            )  # noqa: W503
        ]

        try:
            fields_with_default = [x for x in empty_fields if "default" in schema[x]]
            fields_with_oneof = [
                x
                for x in empty_fields
                if not "default" in schema[x] and "oneof" in schema[x]
            ]
        except TypeError:
            raise _SchemaRuleTypeError
        for field in fields_with_default:
            self._normalize_default(mapping, schema, field)

        for field in fields_with_oneof:
            self.__normalize_oneof(mapping, schema, field)

        known_fields_states = set()
        fields_with_default_setter = [
            x for x in empty_fields if "default_setter" in schema[x]
        ]
        while fields_with_default_setter:
            field = fields_with_default_setter.pop(0)
            try:
                self._normalize_default_setter(mapping, schema, field)
            except KeyError:
                fields_with_default_setter.append(field)
            except Exception as e:
                self._error(field, errors.SETTING_DEFAULT_FAILED, str(e))

            fields_processing_state = hash(tuple(fields_with_default_setter))
            if fields_processing_state in known_fields_states:
                for field in fields_with_default_setter:
                    self._error(
                        field,
                        errors.SETTING_DEFAULT_FAILED,
                        "Circular dependencies of default setters.",
                    )
                break
            else:
                known_fields_states.add(fields_processing_state)
