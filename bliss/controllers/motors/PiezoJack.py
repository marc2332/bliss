import time
from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING
from bliss.common.task_utils import *

"""
Bliss controller for a piezo jack.

Unite an Icepap Stepper motor with a Physik Instrumente E712 axis.
This will make a PiezoJack, which share one capacitive sensor. The sensor
is read via the PI E712.


Holger Witsch ESRF BLISS
Oct 2014


This config example needs elaborating !!!!

Still in progess, please be patient
"""

class PiezoSize():

    def __init__(self, length, band):
        self.length = length
        self.band = band
        self.middle = self.length / 2
        self.low = self.middle - (self.band / 2)
        self.high = self.middle + (self.band / 2)
        self.initial_position = 50


class PiezoJack(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        self._state = READY
        self.TADmin = self.config.get("TADmin", int, default = 150000)
        self.TADmax = self.config.get("TADmax", int, default = 700000)

        # these are the factor/offset of a first degree equation, which
        # translates a TNS value to a position.
        # At the time of writing, there was no indication, the values
        # would be the same for each system. But we only had one,
        # so put them here.
        self.factor = self.config.get("factor", float, 1.69609)
        self.offset = self.config.get("offset", float, 197.760)

        length = self.config.get("PiezoLength", float, 15)
        band = self.config.get("PiezoBand", float, 4)
        self._PiezoSize = PiezoSize(length, band)
        self._piezo_settle_sleep = 1  # seconds

        self.cname = "PiezoJack"

    def initialize(self):
        self.piezo = self._tagged["piezo"][0]
        self.icepap = self._tagged["icepap"][0]


    def finalize(self):
        pass

    def initialize_axis(self, axis):
        """
        - Reads specific config
        - Adds specific methods
        - Switches piezo to ONLINE mode so that axis motion can be caused
        by move commands.

        Args:
            - <axis>
        Returns:
            - None
        """
        elog.debug("axis: %s" % axis)
        add_axis_method(axis, self.get_info, name = "GetInfo", types_info = (None, str))
        add_axis_method(axis, self.selftest, name = "selftest", types_info = (None, None))

        elog.debug("axis name %s" % axis.name)
        elog.debug("tagged axes are: %s, %s" % (self.piezo, self.icepap))

    def read_position(self, axis):
        """
        Returns position

        Args:
            - <axis> : bliss axis.
        Returns:
            - <position> : float : system position in (??? to be determined --- ?micrometer?
        """
        _pos = 0
        tns = self.piezo.Get_TNS()
        # Apply calibrated formula
        _pos = tns * self.factor + self.offset
        return _pos

    def read_velocity(self, axis):
        """ this controller doesn't have a velocity"""
        _velocity = 0
        return _velocity

    def set_velocity(self, axis, new_velocity):
        return None

    def state(self, axis):
        if self.piezo.controller.name.startswith("mockup"):
            return READY
        """ disregard the piezo for now. Not sure what to do with it
        """
        return self._state
#         return self.icepap.state()


    def prepare_move(self, motion):
        """
        - TODO for multiple move...

        Args:
            - <motion> : Bliss motion object.

        Returns:
            -

        Raises:
            - RuntimeError("The capacitive sensor is not in its right area of function")
        """

        elog.debug("motion %s" % motion)
        if self.piezo.controller.name.startswith("mockup"):
            self.piezo.custom_get_chapi("titi")
            return

        tad = self.piezo.Get_TAD()

        # check for power cut
        self.piezo.CheckPowerCut()

        elog.debug("TAD : %s, %s, %s" % (tad, self.TADmax, self.TADmin))
        if self.TADmax < tad < self.TADmin:
            raise RuntimeError("The capacitive sensor is not in its area of linear function")

        elog.debug("icepap position: %s" % self.icepap.position())


    def start_one(self, motion):
        """
        Args:
            - <motion> : Bliss motion object.

        Returns:
            - None
        # TODO: Are we sure the icepap calculates in um, because the
              piezo and this server do. To be checked.
        """
        elog.debug("motion %s" % motion)
        self._do_move(motion, wait = False)


    def stop(self, axis):
        """
        what's to do in case of an interrupt
        """
        self.piezo.stop()
        time.sleep(self._piezo_settle_sleep)
        self.piezo.Set_Closed_Loop(False)

        self.icepap.stop()

    def get_info(self, axis):
        """
        Returns a set of useful information about controller.
        Helpful to tune the device.

        Args:
            <axis> : bliss axis
        Returns:
            None
        Raises:
            ?
        """
        elog.info("PiezoJack: get_info")

        if not self.piezo.controller.name.startswith("mockup"):
#             elog.info("PiezoJack::get_info: ICEPAP Identifier: " % self.icepap.get_identifier())
#             elog.info("PiezoJack::get_info: Piezo Info:" % self.piezo.GetInfo())

            elog.info("icepap position  : %s" % self.icepap.position())
            closed_loop = self.piezo.Get_Closed_Loop_Status()
            elog.info("piezo closed loop: %s" % closed_loop)

            elog.info("piezo tns        : %s" % self.piezo.Get_TNS())
            elog.info("piezo offset     : %s" % self.piezo.Get_Offset())
            elog.info("piezo abs pos    : %s" % self.bender_abs_pos())

            elog.info("piezo POS?       : %s" % self.piezo.measured_position())

            elog.info("piezo instance   : %s" % self.piezo)

            if closed_loop:
                elog.info("piezo MOV?       : %s" % self.piezo.position())
                self.piezo.Set_Closed_Loop(onoff = False)
                elog.info("piezo SVA?       : %s" % self.piezo.position())
                self.piezo.Set_Closed_Loop(onoff = True)
            else:
                self.piezo.Set_Closed_Loop(onoff = True)
                elog.info("piezo MOV?       : %s" % self.piezo.position())
                self.piezo.Set_Closed_Loop(onoff = False)
                elog.info("piezo SVA?       : %s" % self.piezo.position())


    def bender_abs_pos(self):
        return self.piezo.Get_TNS() * self.factor + self.offset

#     @task
    def _do_move(self, motion, wait = False):
        """
        executive movement method, will be non blocking

        Move piezo/icepap system
        * Check if piezo is within a band of movement for the piezo.

        """
        self._state = MOVING

        elog.debug("icepap position: %s" % self.icepap.position())
        current_position = self.bender_abs_pos()
        relative_displacement = motion.target_pos - current_position
        position = self.piezo.measured_position()

        # calculate icepap movement
        new_position = relative_displacement + position

        elog.debug("current_position %s relative_displacement %s position %s new_position %s" %
                   (new_position, relative_displacement, position, new_position))

        """ check if icepap needs moving
            if the new position is outside the piezo's travel range.
        """
        if self._PiezoSize.high <= new_position <= self._PiezoSize.low:
            elog.debug("small movement %s" % new_position)

        else:
            elog.debug("ICEPAP needs moving!")
            # self.piezo.move(self._PiezoSize.middle)
            # time.sleep(self._piezo_settle_sleep)

            # self.piezo.Set_Closed_Loop(False)

            # when closed_loop is off, it should set volts
            # self.piezo.move(self._PiezoSize.initial_position)
            # time.sleep(self._piezo_settle_sleep * 3)

            retries = 2
            # current_position = self.bender_abs_pos()
            for _ in range(retries):
                # motion.target_pos - current_position
                elog.debug("icepap move to %s" % motion.target_pos)
                self.icepap.move(motion.target_pos)
                time.sleep(self._piezo_settle_sleep * 3)

                return  # no sensor, no piezo  :-(

            """
            here is where the piezo works

            first set the new offset
            """
            offset = self.piezo._get_offset()
            elog.debug("offset: %s" % offset)
            measured_pos = self.piezo.measured_position()

            offset -= measured_pos - self._PiezoSize.middle
            self._put_offset(offset)

            position = self.piezo.position()
            self.piezo.Set_Closed_Loop(True)

            measured_pos = self.piezo.measured_position()
            elog.debug("new offset : %s with: %s and sva: %s" % (offset, position, measured_pos))

            self.piezo.move(self._PiezoSize.middle)

            current_position = self.piezo.position()
            new_position = motion.target_pos - current_position

        self.piezo.move(new_position)
        elog.debug("New piezo position given by controller: %s" % self.piezo.position())

        self._state = READY


    def selftest(self, axis):
        steps_p_u = self.icepap.steps_per_unit

        how_much = 10

        elog.info("icepap steps per unit %s\n" % steps_p_u)

        """ hoping to be at the right spot :-) """
        icepap_position = self.icepap.position()
        position_before_move = self.piezo.Get_TNS()
        self.icepap.rmove(-how_much)
        position_there = self.piezo.Get_TNS()
        self.icepap.rmove(how_much)
        position_after_move = self.piezo.Get_TNS()

        elog.info("positions\n")
        elog.info("ICEPAP before: %s" % icepap_position)
        elog.info("before: %s" % position_before_move)
        elog.info("there:  %s" % position_there)
        elog.info("after:  %s" % position_after_move)



        factor = (position_there - position_before_move) / how_much
        offset = position_before_move - (self.factor * icepap_position)
        elog.info("factor and offset should be: %s %s \n" % (factor, offset))

        elog.info("piezo says: %s\n" % self.piezo.position())
