# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import sys
from bliss.controllers.demo import lima_diff_simulation_plugin as DiffSimulationPlugin

sys.modules["Lima.Server.plugins.DiffSimulationPlugin"] = DiffSimulationPlugin

from Lima.Server import plugins

plugins.__all__.append("DiffSimulationPlugin")

from Lima.Server import LimaCCDs


def main():
    sys.argv[0] = re.sub(r"(-script\.pyw?|\.exe)?$", "", sys.argv[0])
    result = LimaCCDs.main()
    sys.exit(result)


if __name__ == "__main__":
    main()
