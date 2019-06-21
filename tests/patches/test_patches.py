# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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


def test_ptpython_signature_patch(clean_gevent):
    clean_gevent["end-check"] = False

    ptpython_signature_patch_diff_dump = [
        "- def signature_toolbar(python_input):\n",
        "+ def NEWsignature_toolbar(python_input):\n",
        "-                 append((Signature, sig.full_name))\n",
        "+                 append((Signature, sig.name))  ### PATCHED HERE\n",
        '-             append((Signature + ",operator", "("))\n',
        '+             append((Signature + ".operator", "("))  ### PATCHED HERE\n',
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


def test_dicttoh5(clean_gevent):
    clean_gevent["end-check"] = False

    # diffdump can be generated with pytest --pdb option using
    # >>> import pprint
    # >>> pprint.pprint(diff_dump)
    dicttoh5_diff_dump = [
        "+     # ... one could think about propagating something similar to the "
        "changes\n",
        "+     # made here back to silx\n",
        "+     import h5py\n",
        "+     from silx.io.dictdump import _SafeH5FileWrite, _prepare_hdf5_dataset\n",
        "+     import warnings\n",
        '+                 if "NX_class" not in h5f[h5path + key].attrs:\n',
        '+                     h5f[h5path + key].attrs["NX_class"] = "NXcollection"\n',
        "+ \n",
        "-                         logger.warning(\n",
        "+                         warnings.warn(\n",
        "+                 # use NXcollection at first, might be overwritten an time "
        "later\n",
        '+                 h5f[h5path + key].attrs["NX_class"] = "NXcollection"\n',
        "+ \n",
        '+             elif key == "NX_class":\n',
        "+                 # assign NX_class\n",
        "+                 try:\n",
        '+                     h5f[h5path].attrs["NX_class"] = treedict[key]\n',
        "+                 except KeyError:\n",
        "+                     h5f.create_group(h5path)\n",
        '+                     h5f[h5path].attrs["NX_class"] = treedict[key]\n',
        "-                             logger.warning(\n",
        "+                             warnings.warn(\n",
        "+ \n",
        "-                             logger.warning(\n",
        "+                             warnings.warn(\n",
    ]

    o, p = _check_patch(
        "silx.io.dictdump", "dicttoh5", "bliss.common.utils", "dicttoh5"
    )

    # strip docstring
    o = re.sub('"""((.|[\n])*)"""', "", o)
    p = re.sub('"""((.|[\n])*)"""', "", p)

    diff_dump = _generate_diff(o, p)

    _compare_dump(dicttoh5_diff_dump, diff_dump)


def test_jedi_signature_patch(clean_gevent):
    clean_gevent["end-check"] = False

    jedi_signature_patch_diff_dump = [
        "+         if self._signature_param.has_default:  #\n",
        "+             val = [c for c in self.infer()][0].get_safe_value()  #\n",
        '+             return self._signature_param.name + "=" + str(val)  #\n',
        "+         else:  #\n",
        "-         return self._signature_param.name\n",
        "+             return self._signature_param.name  #         ^\n",
        "+             #  -------|-----\n",
        "+             #  PATCHED ABOVE\n",
    ]

    o, p = _check_patch(
        "jedi.evaluate.compiled.context",
        "SignatureParamName",
        "bliss.shell.cli.jedi_signature_patch",
        "SignatureParamName",
    )

    diff_dump = _generate_diff(o, p)
    _compare_dump(jedi_signature_patch_diff_dump, diff_dump)

    if "jedi.evaluate.compiled.context" in importlib.sys.modules:
        import bliss.shell.cli.jedi_signature_patch

        importlib.reload(bliss.shell.cli.jedi_signature_patch)
