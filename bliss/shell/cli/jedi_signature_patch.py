#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
#
# Patch to modify the behavior of the jedi signature
# The code for def SignatureParamName corresponds to jedi version 0.13.3

from jedi.evaluate.base_context import ContextSet
from jedi.evaluate.filters import AbstractNameDefinition
from jedi.evaluate.compiled.context import create_from_access_path


class SignatureParamName(AbstractNameDefinition):
    api_type = u"param"

    def __init__(self, compiled_obj, signature_param):
        self.parent_context = compiled_obj.parent_context
        self._signature_param = signature_param

    @property
    def string_name(self):
        if self._signature_param.has_default:  #
            val = [c for c in self.infer()][0].get_safe_value()  #
            return self._signature_param.name + "=" + str(val)  #
        else:  #
            return self._signature_param.name  #         ^
            #  -------|-----
            #  PATCHED ABOVE

    def get_kind(self):
        return getattr(Parameter, self._signature_param.kind_name)

    def is_keyword_param(self):
        return self._signature_param

    def infer(self):
        p = self._signature_param
        evaluator = self.parent_context.evaluator
        contexts = ContextSet()
        if p.has_default:
            contexts = ContextSet(create_from_access_path(evaluator, p.default))
        if p.has_annotation:
            annotation = create_from_access_path(evaluator, p.annotation)
            contexts |= annotation.execute_evaluated()
        return contexts


import jedi.evaluate.compiled.context

jedi.evaluate.compiled.context.SignatureParamName = SignatureParamName
