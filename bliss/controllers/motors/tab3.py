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
  point geometry: number 0..8


Example configuration (from ID30)::

    <config>
      <controller class="IcePAP">
        <host value="iceid305" />
        <libdebug value="1" />
        <axis name="tz1">
          <address value="34" />
          <steps_per_unit value="52500" />
          <backlash value="0.1" />
          <velocity value="6000" />
        </axis>
        <axis name="tz2">
          <address value="35" />
          <steps_per_unit value="52500" />
          <backlash value="0.1" />
          <velocity value="6000" />
        </axis>
        <axis name="tz3">
          <address value="36" />
          <steps_per_unit value="52500" />
          <backlash value="0.1" />
          <velocity value="6000" />
        </axis>
        <axis name="tyf">
          <address value="37" />
          <steps_per_unit value="100000" />
          <backlash value="0.1" />
          <velocity value="8000" />
        </axis>
        <axis name="tyb">
          <address value="38" />
          <steps_per_unit value="100000" />
          <backlash value="0.1" />
          <velocity value="8000" />
        </axis>
      </controller>
      <controller class="tab3">
        <axis name="tz2" tags="real back1" />
        <axis name="tz3" tags="real back2" />
        <axis name="tz1" tags="real front" />
        <axis name="thgt" tags="z"/>
        <axis name="txtilt" tags="xtilt"/>
        <axis name="tytilt" tags="ytilt"/>
        <geometry value="5" />
        <d1 value="1140" />
        <d2 value="1714" />
        <d3 value="675" />
      </controller>
    </config>

Antonia Beteva ESRF BCU
"""
from bliss.controllers.motor import CalcController
import math
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

        self.no_offset = self.config.get('no_offset', bool, True)

    def initialize_axis(self, axis):
        CalcController.initialize_axis(self, axis)
        axis.no_offset = self.no_offset

    def calc_from_real(self, positions_dict):
        front = positions_dict["front"]

        if self.geometry in (1, 2):
            back = positions_dict["back1"]
        else:
            back = positions_dict["back1"] + (self.d4 / self.d1) * \
                (positions_dict["back1"] - positions_dict["back2"])

        xtilt = math.atan(
            (positions_dict["back2"] - positions_dict["back1"]) / self.d1)

        ytilt = math.atan((back - positions_dict["front"]) / self.d2)

        if self.geometry in (2, 6):
            xtilt, ytilt = map(math.degrees, (xtilt, ytilt))
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

        return {"z": z,
                "xtilt": xtilt,
                "ytilt": ytilt}

    def calc_to_real(self, positions_dict):
        if self.geometry in (2, 6):
            xtan = math.tan(math.radians(positions_dict["xtilt"]))
            ytan = math.tan(math.radians(positions_dict["ytilt"]))
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

        return {"back1": back1,
                "back2": back2,
                "front": front}
