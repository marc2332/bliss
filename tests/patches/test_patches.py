# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import importlib
import inspect
import difflib
import black
import re
from pprint import pprint


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
    assert len(saved_diff_dump) == len(new_diff_dump)

    for l1, l2 in zip(saved_diff_dump, new_diff_dump):
        assert l1 == l2

    # if these tests fail there are some changes in the source of the installed
    # packages compared to the one that was used for the patch that might be
    # relevant to take into account!

    # to update the dump run
    # pytest tests/patches/test_patches.py --pdb
    # and type "pprint(new_diff_dump)" in the pdb console
    # it is up to you to decide if you need to update the patch or the dump saved here!


def test_ptpython_signature_patch():
    ptpython_signature_patch_diff_dump = [
        "- def signature_toolbar(python_input):\n",
        "+ def NEWsignature_toolbar(python_input):\n",
        "-                 append((Signature, sig.full_name))\n",
        "+                 append((Signature, sig.name))  ### PATCHED HERE\n",
        '-             append((Signature + ",operator", "("))\n',
        '+             append((Signature + ".operator", "("))  ### PATCHED HERE\n',
        '+                 description = description.split("param ")[-1]  ### PATCHED '
        "HERE\n",
        "+                     append(\n",
        '-                     append((Signature + ",current-name", '
        "str(description)))\n",
        '+                         (Signature + ".current-name", str(description))\n',
        "+                     )  ### PATCHED HERE\n",
        '-                 append((Signature + ",operator", ", "))\n',
        '+                 append((Signature + ".operator", ", "))  ### PATCHED '
        "HERE\n",
        '-             append((Signature + ",operator", ")"))\n',
        '+             append((Signature + ".operator", ")"))  ### PATCHED HERE\n',
    ]

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


def test_repl_excecute():
    # diffdump can be generated with pytest --pdb option using
    # >>> import pprint
    # >>> pprint.pprint(diff_dump)
    execute_dump = [
        "-     def _execute(self, line):\n",
        "+     def _execute_line(self, line):\n",
        "-         output = self.app.output\n",
        "- \n",
        "-         # WORKAROUND: Due to a bug in Jedi, the current directory is "
        "removed\n",
        "-         # from sys.path. See: "
        "https://github.com/davidhalter/jedi/issues/1148\n",
        '-         if "" not in sys.path:\n',
        '-             sys.path.insert(0, "")\n',
        "- \n",
        "-         def compile_with_flags(code, mode):\n",
        '-             " Compile code with the right compiler flags. "\n',
        "-             return compile(\n",
        "-                 code,\n",
        '-                 "<stdin>",\n',
        "-                 mode,\n",
        "-                 flags=self.get_compiler_flags(),\n",
        "-                 dont_inherit=True,\n",
        "-             )\n",
        "- \n",
        "- \n",
        "-             # Try eval first\n",
        "+             # First try `eval` and then `exec`\n",
        "+                 self._eval_line(line)\n",
        '-                 code = compile_with_flags(line, "eval")\n',
        "-                 result = eval(code, self.get_globals(), "
        "self.get_locals())\n",
        "- \n",
        "-                 locals = self.get_locals()\n",
        '-                 locals["_"] = locals["_%i" % self.current_statement_index] '
        "= result\n",
        "- \n",
        "-                 if result is not None:\n",
        "-                     out_prompt = self.get_output_prompt()\n",
        "- \n",
        "-                     try:\n",
        "+                 return\n",
        '-                         result_str = "%r\\n" % (result,)\n',
        "-                     except UnicodeDecodeError:\n",
        "-                         # In Python 2: `__repr__` should return a "
        "bytestring,\n",
        "-                         # so to put it in a unicode context could raise "
        "an\n",
        "-                         # exception that the 'ascii' codec can't decode "
        "certain\n",
        "-                         # characters. Decode as utf-8 in that case.\n",
        '-                         result_str = "%s\\n" % '
        'repr(result).decode("utf-8")\n',
        "- \n",
        "-                     # Align every line to the first one.\n",
        '-                     line_sep = "\\n" + " " * '
        "fragment_list_width(out_prompt)\n",
        "-                     result_str = line_sep.join(result_str.splitlines()) + "
        '"\\n"\n',
        "- \n",
        "-                     # Write output tokens.\n",
        "-                     if self.enable_syntax_highlighting:\n",
        "-                         formatted_output = merge_formatted_text(\n",
        "-                             [\n",
        "-                                 out_prompt,\n",
        "-                                 "
        "PygmentsTokens(list(_lex_python_result(result_str))),\n",
        "-                             ]\n",
        "-                         )\n",
        "-                     else:\n",
        "-                         formatted_output = FormattedText(\n",
        '-                             out_prompt + [("", result_str)]\n',
        "-                         )\n",
        "- \n",
        "-                     print_formatted_text(\n",
        "-                         formatted_output,\n",
        "-                         style=self._current_style,\n",
        "-                         style_transformation=self.style_transformation,\n",
        "-                         include_default_pygments_style=False,\n",
        "-                     )\n",
        "- \n",
        "-             # If not a valid `eval` expression, run using `exec` "
        "instead.\n",
        "+                 pass  # SyntaxError should not be in exception chain\n",
        "+             self._exec_line(line)\n",
        '-                 code = compile_with_flags(line, "exec")\n',
        "-                 six.exec_(code, self.get_globals(), self.get_locals())\n",
        "- \n",
        "-             output.flush()\n",
    ]

    from ptpython.repl import PythonRepl
    from bliss.shell.cli.repl import BlissRepl
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    inp1 = create_pipe_input()
    inp2 = create_pipe_input()

    brepl = BlissRepl(input=inp1, output=DummyOutput(), session=None)
    ptrepl = PythonRepl(input=inp2, output=DummyOutput())

    p_source = "class myobj:\n" + inspect.getsource(brepl._execute_line)
    p = black.format_str(p_source, line_length=88)
    o_source = "class myobj:\n" + inspect.getsource(ptrepl._execute)
    o = black.format_str(o_source, line_length=88)

    # strip docstring
    o = re.sub('"""((.|[\n])*)"""', "", o)
    p = re.sub('"""((.|[\n])*)"""', "", p)

    diff_dump = _generate_diff(o, p)

    _compare_dump(execute_dump, diff_dump)


def test_repl_get_compiler_flags():
    # diffdump can be generated with pytest --pdb option using
    # >>> import pprint
    # >>> pprint.pprint(diff_dump)
    execute_dump = [
        "+             try:\n",
        "-             if isinstance(value, __future__._Feature):\n",
        "+                 if isinstance(value, __future__._Feature):\n",
        "-                 flags |= value.compiler_flag\n",
        "+                     f = value.compiler_flag\n",
        "+                     flags |= f\n",
        "+             except:\n",
        "+                 pass\n",
    ]

    from ptpython.repl import PythonRepl
    from bliss.shell.cli.repl import BlissRepl
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    inp1 = create_pipe_input()
    inp2 = create_pipe_input()

    brepl = BlissRepl(input=inp1, output=DummyOutput(), session=None)
    ptrepl = PythonRepl(input=inp2, output=DummyOutput())

    p_source = "class myobj:\n" + inspect.getsource(brepl.get_compiler_flags)
    p = black.format_str(p_source, line_length=88)
    o_source = "class myobj:\n" + inspect.getsource(ptrepl.get_compiler_flags)
    o = black.format_str(o_source, line_length=88)

    # strip docstring
    o = re.sub('"""((.|[\n])*)"""', "", o)
    p = re.sub('"""((.|[\n])*)"""', "", p)

    diff_dump = _generate_diff(o, p)

    _compare_dump(execute_dump, diff_dump)


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
