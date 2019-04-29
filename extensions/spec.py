# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
from setuptools import Command

__all__ = ["InstallSpec"]


class InstallSpec(Command):

    cmd_name = "install_spec"
    description = "install spec macros"

    user_options = [("prefix=", None, "installation prefix")]

    def initialize_options(self):
        self.prefix = None

    def finalize_options(self):
        if self.prefix is None:
            blissadm = os.environ.get("BLISSADM")
            if blissadm:
                self.prefix = os.path.join(blissadm, "spec", "macros")
        if not self.prefix:
            raise RuntimeError("Cannot install spec macros (no prefix defined)")

    def run(self):
        if not os.path.isdir(self.prefix):
            os.makedirs(self.prefix, 0o775)

        this_dir = os.path.dirname(os.path.abspath(__file__))
        src = os.path.join(this_dir, os.path.pardir, "spec")
        os.system("cp -rp {0}/* {1}".format(src, self.prefix))
