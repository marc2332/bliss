"""
One calculation and two real motors.
The calculation motor has the position of the motor tagged as first.
The real motor tagged as second differs from the first by a fraction.

orientation: label (horizontal | vertical) of the orientation of the motors.
fraction: the difference [mm] between the first and the second motor.

Example yml file:

.. code-block:: yaml

    -
     controller:
       class: Slitbox
       orientation: vertical
       fraction: 0.01
       axes:
           -
            name: s1v
            tags: real first
           -
            name: s2v
            tags: real second
           -
            name: sV
            tags: vertical

    -
     controller:
       class: Slitbox
       orientation: horizontal
       fraction: 0.01
       axes:
           -
            name: $s1h
            tags: real first
           -
            name: $s2h
            tags: real second
           -
            name: sH
            tags: horizontal
"""
from bliss.controllers.motor import CalcController


class Slitbox(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)
        self.orientation = str(self.config.get("orientation"))

    def calc_from_real(self, positions_dict):
        return {self.orientation: positions_dict["first"]}

    def calc_to_real(self, positions_dict):
        fraction = float(self.config.get("fraction"))
        pos = positions_dict[self.orientation]
        return {"first": pos, "second": pos + fraction}
