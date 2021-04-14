# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
from bliss.controllers.demo import lima_tomo_simulation_plugin as TomoSimulationPlugin

sys.modules["Lima.Server.plugins.TomoSimulationPlugin"] = TomoSimulationPlugin

from Lima.Server import plugins

plugins.__all__.append("TomoSimulationPlugin")

from Lima.Server import LimaCCDs


def main():
    result = LimaCCDs.main()
    sys.exit(result)


if __name__ == "__main__":
    main()
