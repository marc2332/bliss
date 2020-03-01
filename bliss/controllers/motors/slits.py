# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import CalcController
from bliss.common.logtools import *

"""
example for single VERTICAL slits:

  Λ
  |  |  UP blade |         + 𝝠
  |  |___________|           |         _____
  +        ☉                 |           Λ
      ___________      VOFF  -      VGAP |
  +  |           |           |         __V__
  |  |   DOWN    |           |
  V  |   blade   |

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

"""
example for single HORIZONTAL slits:
 HOFFSET = ( FRONT - BACK ) / 2
 HGAP = BACK + FRONT

              |<--gap--->|       ☉ beam directed to the viewer ⊙
                   +5

                offset= +1.5
            (positif to the hall)
         ----------|------->

         _____           ____
              |         |
 +1 <--- back |         |front  ---> +4
         blade|    ☉    |blade
              |         |
         _____|         |____

         -----|-|-|-|-|-|-->
                ↑  ↑
                0  1.5

"""


class Slits(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

    def initialize_axis(self, axis):
        CalcController.initialize_axis(self, axis)
        axis.no_offset = True

    def calc_from_real(self, positions_dict):
        log_info(self, "[SLITS] calc_from_real()")
        log_info(self, "[SLITS]\treal: %s" % positions_dict)

        calc_dict = dict()
        slit_type = self.config.get("slit_type", default="both")

        if slit_type not in ["vertical"]:
            # OFFSET = ( FRONT - BACK ) / 2
            # GAP = BACK + FRONT
            calc_dict.update(
                {
                    "hoffset": (positions_dict["front"] - positions_dict["back"]) / 2.0,
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

        log_info(self, "[SLITS]\tcalc: %s" % calc_dict)

        return calc_dict

    def calc_to_real(self, positions_dict):
        log_info(self, "[SLITS] calc_to_real()")
        log_info(self, "[SLITS]\tcalc: %s" % positions_dict)

        real_dict = dict()
        slit_type = self.config.get("slit_type", default="both")

        if slit_type not in ["vertical"]:
            real_dict.update(
                {
                    "front": (positions_dict["hgap"] / 2.0) + positions_dict["hoffset"],
                    "back": (positions_dict["hgap"] / 2.0) - positions_dict["hoffset"],
                }
            )

        if slit_type not in ["horizontal"]:
            real_dict.update(
                {
                    "up": (positions_dict["vgap"] / 2.0) + positions_dict["voffset"],
                    "down": (positions_dict["vgap"] / 2.0) - positions_dict["voffset"],
                }
            )

        log_info(self, "[SLITS]\treal: %s" % real_dict)

        return real_dict
