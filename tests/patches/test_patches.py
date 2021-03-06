# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import importlib
import inspect
import difflib
import black
import re


def _check_patch(orig_module, orig_idn, patched_module, patched_idn):
    if orig_module in importlib.sys.modules:
        importlib.reload(importlib.sys.modules[orig_module])

    om = importlib.import_module(orig_module)
    o_source = inspect.getsource(eval("om." + orig_idn))

    pm = importlib.import_module(patched_module)
    p_source = inspect.getsource(eval("pm." + patched_idn))

    return [
        black.format_str(o_source, line_length=88),
        black.format_str(p_source, line_length=88),
    ]


def _generate_diff(str1, str2):
    d = difflib.Differ()
    return [
        l
        for l in d.compare(
            str1.splitlines(keepends=True), str2.splitlines(keepends=True)
        )
        if l[0] in {"+", "-"}
    ]


def _compare_dump(saved_diff_dump, new_diff_dump):
    # assert len(saved_diff_dump) == len(new_diff_dump)

    for i, (l1, l2) in enumerate(zip(saved_diff_dump, new_diff_dump)):
        assert l1 == l2, f"Patch line nb {i} mismatch"

    # if these tests fail there are some changes in the source of the installed
    # packages compared to the one that was used for the patch that might be
    # relevant to take into account!

    # to update the dump run
    # pytest tests/patches/test_patches.py --pdb
    # and type "pprint(new_diff_dump)" in the pdb console
    # it is up to you to decide if you need to update the patch or the dump saved here!


def test_ptpython_signature_patch():
    diff_dump = """\
- def signature_toolbar(python_input):
+ def NEWsignature_toolbar(python_input):
-             append((Signature + ",operator", "("))
+             append((Signature + ".operator", "("))  ### PATCHED HERE
-                     append((Signature + ",operator", ", "))
+                     append((Signature + ".operator", ", "))  ### PATCHED HERE
-                     append((Signature + ",operator", ", "))
+                     append((Signature + ".operator", ", "))  ### PATCHED HERE
+                 description = p.description.split("param ")[-1]  ### PATCHED HERE
+                     append(
-                     append((Signature + ",current-name", p.description))
+                         (Signature + ".current-name", str(description))
+                     )  ### PATCHED HERE
-                     append((Signature, p.description))
+                     append((Signature, str(description)))  ### PATCHED HERE
-                 append((Signature + ",operator", ", "))
+                 append((Signature + ".operator", ", "))  ### PATCHED HERE
-             append((Signature + ",operator", ")"))
+             append((Signature + ".operator", ")"))  ### PATCHED HERE
"""
    ptpython_signature_patch_diff_dump = [l + "\n" for l in diff_dump.split("\n")]

    o, p = _check_patch(
        "ptpython.layout",
        "signature_toolbar",
        "bliss.shell.cli.ptpython_signature_patch",
        "NEWsignature_toolbar",
    )

    diff_dump = _generate_diff(o, p)
    _compare_dump(ptpython_signature_patch_diff_dump, diff_dump)

    if "ptpython.layout" in importlib.sys.modules:
        import bliss.shell.cli.ptpython_signature_patch

        importlib.reload(bliss.shell.cli.ptpython_signature_patch)


def test_validator_patch_normalize_containers():
    # diffdump can be generated with pytest --pdb option using
    # >>> import pprint
    # >>> pprint.pprint(diff_dump)
    normalize_containers_dump = [
        '+             if "oneof" in rules:\n',
        "+                 self.__normalize_oneof(mapping, schema, field)\n",
        "+ \n",
        "-                     self.__normalize_mapping_per_keysrules(\n",
        "+                     "
        "self._BareValidator__normalize_mapping_per_keysrules(\n",
        "-                     self.__normalize_mapping_per_valuesrules(\n",
        "+                     "
        "self._BareValidator__normalize_mapping_per_valuesrules(\n",
        "-                         self.__normalize_mapping_per_schema(field, "
        "mapping, schema)\n",
        "+                         "
        "self._BareValidator__normalize_mapping_per_schema(\n",
        "+                             field, mapping, schema\n",
        "+                         )\n",
        "-                     self.__normalize_sequence_per_schema(field, mapping, "
        "schema)\n",
        "+                     self._BareValidator__normalize_sequence_per_schema(\n",
        "+                         field, mapping, schema\n",
        "+                     )\n",
        "-                     self.__normalize_sequence_per_items(field, mapping, "
        "schema)\n",
        "+                     self._BareValidator__normalize_sequence_per_items(\n",
        "+                         field, mapping, schema\n",
        "+                     )\n",
    ]

    from bliss.common.validator import BlissValidator
    from cerberus import Validator

    v = Validator()
    bv = BlissValidator()

    p_source = "class myobj:\n" + inspect.getsource(
        bv._BlissValidator__normalize_containers
    )
    p = black.format_str(p_source, line_length=88)
    o_source = "class myobj:\n" + inspect.getsource(
        v._BareValidator__normalize_containers
    )
    o = black.format_str(o_source, line_length=88)

    # strip docstring
    o = re.sub('"""((.|[\n])*)"""', "", o)
    p = re.sub('"""((.|[\n])*)"""', "", p)

    diff_dump = _generate_diff(o, p)

    _compare_dump(normalize_containers_dump, diff_dump)


def test_validator_patch_normalize_default_fields():
    # diffdump can be generated with pytest --pdb option using
    # >>> import pprint
    # >>> pprint.pprint(diff_dump)
    normalize_default_fields_dump = [
        "+             fields_with_oneof = [\n",
        "+                 x\n",
        "+                 for x in empty_fields\n",
        '+                 if not "default" in schema[x] and "oneof" in schema[x]\n',
        "+             ]\n",
        "+ \n",
        "+         for field in fields_with_oneof:\n",
        "+             self.__normalize_oneof(mapping, schema, field)\n",
    ]

    from bliss.common.validator import BlissValidator
    from cerberus import Validator

    v = Validator()
    bv = BlissValidator()

    p_source = "class myobj:\n" + inspect.getsource(
        bv._BlissValidator__normalize_default_fields
    )
    p = black.format_str(p_source, line_length=88)
    o_source = "class myobj:\n" + inspect.getsource(
        v._BareValidator__normalize_default_fields
    )
    o = black.format_str(o_source, line_length=88)

    # strip docstring
    o = re.sub('"""((.|[\n])*)"""', "", o)
    p = re.sub('"""((.|[\n])*)"""', "", p)

    diff_dump = _generate_diff(o, p)

    _compare_dump(normalize_default_fields_dump, diff_dump)


def test_validator_patch_validate_oneof():
    # diffdump can be generated with pytest --pdb option using
    # >>> import pprint
    # >>> pprint.pprint(diff_dump)
    validate_oneof_dump = [
        "-         \"\"\" {'type': 'list', 'logical': 'oneof'} \"\"\"\n",
        '+         """ {\'type\': \'list\'} """\n',
        '-         valids, _errors = self.__validate_logical("oneof", definitions, '
        "field, value)\n",
        "+         # Sort of hack: remove  'logical': 'oneof'\"\"from docstring "
        "above\n",
        "+         valids, _errors = self._BareValidator__validate_logical(\n",
        '+             "oneof", definitions, field, value\n',
        "+         )\n",
    ]

    from bliss.common.validator import BlissValidator
    from cerberus import Validator

    v = Validator()
    bv = BlissValidator()

    p_source = "class myobj:\n" + inspect.getsource(bv._validate_oneof)
    p = black.format_str(p_source, line_length=88)
    o_source = "class myobj:\n" + inspect.getsource(v._validate_oneof)
    o = black.format_str(o_source, line_length=88)

    # doc string matters in this case!

    diff_dump = _generate_diff(o, p)

    _compare_dump(validate_oneof_dump, diff_dump)
