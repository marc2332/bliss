from bliss.controllers.motor import CalcController; from bliss.common import log
from bliss.controllers.motor import add_axis_method

"""
example for single slits:
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
    slit_type: horizontal
    axes:
        -
            name: $rup
            tags: real front
        -
            name: $rdown
            tags: real back
        -
            name: svg
            tags: hgap
        -
            name: svo
            tags: hoffset
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


    def calc_from_real(self, positions_dict):
        log.info("[SLITS] calc_from_real()")
        log.info("[SLITS]\treal: %s" % positions_dict)

        calc_dict = dict()
        slit_type = self.config.get("slit_type", default="both")

        if slit_type not in ['vertical']:
            calc_dict.update(
                { "hoffset":
                  (positions_dict["back"] - positions_dict["front"]) / 2.0,
                  "hgap":
                  positions_dict["back"] + positions_dict["front"]
                  } )

        if slit_type not in ['horizontal']:
            calc_dict.update(
                { "voffset":
                  (positions_dict["up"] - positions_dict["down"]) / 2.0,
                  "vgap":
                  positions_dict["up"] + positions_dict["down"]
                  } )

        log.info("[SLITS]\tcalc: %s" % calc_dict)

        return calc_dict

    def calc_to_real(self, axis_tag, positions_dict):
        if axis_tag in ("hoffset", "hgap"):
            log.info("[SLITS] calc_to_real()")
            log.info("[SLITS]\tcalc: %s" % positions_dict)
            real_dict = {
                "back":
                    (positions_dict["hgap"] / 2.0) + positions_dict["hoffset"],
                "front":
                    (positions_dict["hgap"] / 2.0) - positions_dict["hoffset"]
            }

            log.info("[SLITS]\treal: %s" % real_dict)

            return real_dict

        elif axis_tag in ("voffset", "vgap"):
            return {
                "up":
                    (positions_dict["vgap"] / 2.0) + positions_dict["voffset"],
                "down":
                    (positions_dict["vgap"] / 2.0) - positions_dict["voffset"]
            }
