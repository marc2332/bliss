"""
Calculation Bliss controller

real_mot
    real motor axis alias

calc_mot
    calculated axis alias

s_param
    specific_parameter to use for the calculation axis (e.g. gain factor)
    As it can change, we want to treat it as settings parameter as well.
    The parameter can have an initial value in the config file.

Example of the config file:

.. code-block:: yaml

    controller:
        class: calc_motor_mockup
        axes:
            -
                name: $real_motor_name
                tags: real real_mot
            -
                name: calc_mot
                tags: calc_mot
                s_param: 2 #this is optional
"""

from bliss.controllers.motor import CalcController; from bliss.common import event


class calc_motor_mockup(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)
        self._axis = None
        self.axis_settings.add("s_param", float)

    def initialize_axis(self, axis):
        self._axis = axis
        CalcController.initialize_axis(self, axis)
        event.connect(axis, "s_param", self._calc_from_real)

    def close(self):
        if self._axis is not None:
            event.disconnect(self._axis, "s_param", self._calc_from_real)
            self._axis = None
        super(calc_motor_mockup, self).close()

    """
    #Example to use s_param as property instead of settings.
    #s_param is set in the YAML config file.
    @property
    def s_param(self):
        return self.__s_param

    @s_param.setter
    def s_param(self, s_param):
        self.__s_param = s_param
        self._calc_from_real()
    """

    def calc_from_real(self, positions_dict):
        calc_mot_axis = self._tagged["calc_mot"][0]
        s_param = calc_mot_axis.settings.get("s_param")
        # this formula is just an example
        calc_pos = s_param * positions_dict["real_mot"]

        return {"calc_mot": calc_pos}

    def calc_to_real(self, positions_dict):
        calc_mot_axis = self._tagged["calc_mot"][0]
        s_param = calc_mot_axis.settings.get("s_param")
        # this formula is just an example
        real_pos = positions_dict["calc_mot"] / s_param

        return {"real_mot": real_pos}
