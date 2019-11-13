"""
3-leg table

All distances and motor positions are in mm

* back1, back2: aliases for real back legs axes
* front: alias for real front leg axis
* z: alias for calculated height axis
* xtilt: alias for calculated tilt axis aligned in beam direction
* ytilt: alias for calculated vertical tilt axis
* d1: distance between 2 back legs
* d2: distance between front leg and middle point between back legs
* d3: (depends on geometry) distance between front leg and reference height
  point
* d4: (depends on geometry) distance between back1 leg and reference height
* geometry: number 0 please explain these
                   1 ?
                   2 ?
                   3 ?
                   4 ?
                   5 ?
                   6 ?
                   7 ?
                   8 ?


Example configuration
  controller:
    class: tab3
    d1: 660
    d2: 1600
    d4: 1070
    geometry: 0
    axes:
        -
            name: $BackMotor1
            tags: real back1
        -
            name: $BackMotor2
            tags: real back2
        -
            name: $FrontMotor
            tags: real front
        -
            name: tableheight
            tags: z
            low_limit: -180.0
            high_limit: 180.0
            unit: mm
        -
            name: tabletiltx
            tags: xtilt
            low_limit: -2.0
            high_limit: 2.0
            unit: mrad
        -
            name: tabletilty
            tags: ytilt
            low_limit: -5.0
            high_limit: 0.2
            unit: mrad
"""
from bliss.controllers.motor import CalcController
import numpy


class tab3(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.geometry = self.config.get("geometry", int)
        self.d1 = self.config.get("d1", float)
        self.d2 = self.config.get("d2", float)
        try:
            self.d4 = self.config.get("d4", float)
        except KeyError:
            self.d4 = self.d1 / 2
        if self.geometry in (5, 8):
            self.d3 = self.config.get("d3", float)

        self.no_offset = self.config.get("no_offset", bool, True)

    def initialize_axis(self, axis):
        CalcController.initialize_axis(self, axis)
        axis.no_offset = self.no_offset

    def calc_from_real(self, positions_dict):
        front = positions_dict["front"]

        if self.geometry in (1, 2):
            back = positions_dict["back1"]
        else:
            back = positions_dict["back1"] + (self.d4 / self.d1) * (
                positions_dict["back1"] - positions_dict["back2"]
            )

        xtilt = numpy.arctan(
            (positions_dict["back2"] - positions_dict["back1"]) / self.d1
        )

        ytilt = numpy.arctan((back - positions_dict["front"]) / self.d2)

        if self.geometry in (2, 6):
            xtilt, ytilt = map(numpy.degrees, (xtilt, ytilt))
        else:
            xtilt = 1000 * xtilt
            ytilt = 1000 * ytilt

        if self.geometry == 1:
            back = positions_dict["back2"]
        elif self.geometry in (3, 6):
            front = back

        if self.geometry in (5, 8):
            z = front + ((back - front) * self.d3 / self.d2)
        else:
            z = (front + back) / 2

        return {"z": z, "xtilt": xtilt, "ytilt": ytilt}

    def calc_to_real(self, positions_dict):
        if self.geometry in (2, 6):
            xtan = numpy.tan(numpy.radians(positions_dict["xtilt"]))
            ytan = numpy.tan(numpy.radians(positions_dict["ytilt"]))
        else:
            xtan = numpy.tan(positions_dict["xtilt"] / 1000)
            ytan = numpy.tan(positions_dict["ytilt"] / 1000)

        d1 = self.d1 - self.d4
        if self.geometry in (3, 6):
            d3 = self.d2
            dback = 0
        elif self.geometry in (5, 8):
            d3 = self.d3
            dback = self.d2 - self.d3
        else:
            d3 = self.d2 / 2
            dback = d3

        if self.geometry == 4:
            front = positions_dict["z"] + (d3 * ytan)
        elif self.geometry == 1:
            front = positions_dict["z"] + (d3 * ytan) - (d1 * xtan)
        else:
            front = positions_dict["z"] - (d3 * ytan)

        if self.geometry in (1, 4):
            sign = -1
        else:
            sign = 1
        if self.geometry == 2:
            back1 = positions_dict["z"] + (dback * ytan)
        else:
            back1 = positions_dict["z"] - (self.d4 * xtan) + (sign * dback * ytan)
        back2 = positions_dict["z"] + (d1 * xtan) + (sign * dback * ytan)

        return {"back1": back1, "back2": back2, "front": front}
