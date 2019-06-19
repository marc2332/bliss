# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import CalcController

"""
example for single VERTICAL slits:
   |    UP     |
   |___________|           |
                           |           ^
    ___________      VOFF  -     VGAP  |
   |           |           |           V
   |   DOWN    |           |

-
  controller:
    class: mockup
    axes:
      - acceleration: 1
        backlash: 2
        name: rup
        steps_per_unit: 1000
        velocity: 1.1399999999999999
      - acceleration: 1
        backlash: 2
        name: rdown
        steps_per_unit: 1000
        velocity: 1.1399999999999999
-
  controller:
    class: slits
    slit_type: vertical
    axes:
        -
            name: $rup
            tags: real up
        -
            name: $rdown
            tags: real down
        -
            name: vgap
            tags: vgap
        -
            name: voff
            tags: voffset
"""

"""
<slit_type> : [horizontal | vertical | both]
              default value : both
"""


class Slits(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

    def initialize_axis(self, axis):
        CalcController.initialize_axis(self, axis)
        axis.no_offset = True

    def calc_from_real(self, positions_dict):
        self._logger.info("[SLITS] calc_from_real()")
        self._logger.info("[SLITS]\treal: %s" % positions_dict)

        calc_dict = dict()
        slit_type = self.config.get("slit_type", default="both")

        if slit_type not in ["vertical"]:
            calc_dict.update(
                {
                    "hoffset": (positions_dict["back"] - positions_dict["front"]) / 2.0,
                    "hgap": positions_dict["back"] + positions_dict["front"],
                }
            )

        if slit_type not in ["horizontal"]:
            calc_dict.update(
                {
                    "voffset": (positions_dict["up"] - positions_dict["down"]) / 2.0,
                    "vgap": positions_dict["up"] + positions_dict["down"],
                }
            )

        self._logger.info("[SLITS]\tcalc: %s" % calc_dict)

        return calc_dict

    def calc_to_real(self, positions_dict):
        self._logger.info("[SLITS] calc_to_real()")
        self._logger.info("[SLITS]\tcalc: %s" % positions_dict)

        real_dict = dict()
        slit_type = self.config.get("slit_type", default="both")

        if slit_type not in ["vertical"]:
            real_dict.update(
                {
                    "back": (positions_dict["hgap"] / 2.0) + positions_dict["hoffset"],
                    "front": (positions_dict["hgap"] / 2.0) - positions_dict["hoffset"],
                }
            )

        if slit_type not in ["horizontal"]:
            real_dict.update(
                {
                    "up": (positions_dict["vgap"] / 2.0) + positions_dict["voffset"],
                    "down": (positions_dict["vgap"] / 2.0) - positions_dict["voffset"],
                }
            )

        self._logger.info("[SLITS]\treal: %s" % real_dict)

        return real_dict
