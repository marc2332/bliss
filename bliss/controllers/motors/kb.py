""" Calculational controller for KB rotation motors::

|            X-Ray  <-------
|
|     --o---------o---
|       |         |
|       |<---d--->|
|       |         |
|       | m2      | m1
|     ================== base

"""

from bliss.controllers.motor import CalcController


class kb(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.distance = self.config.get("distance", float)

    def calc_from_real(self, positions_dict):
        calc_dict = {
            "tilt": positions_dict["rot"] + positions_dict["erot"],
            "trans": -1 * positions_dict["erot"] * self.distance / 1000.0,
        }

        return calc_dict

    def calc_to_real(self, positions_dict):
        d = positions_dict["trans"] * 1000.0 / self.distance
        return {"rot": positions_dict["tilt"] + d, "erot": -d}
