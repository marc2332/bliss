import time
from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import AxisState
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

    def __init__(self, name, config, axes, encoders):
        Controller.__init__(self, name, config, axes, encoders)

        self.TADmin = self.config.get("TADmin", int, default = 150000)
        self.TADmax = self.config.get("TADmax", int, default = 700000)

        self.factor = 0
        self.offset = 0

        length = self.config.get("PiezoLength", float, 15)
        band = self.config.get("PiezoBand", float, 4)
        self._PiezoSize = PiezoSize(length, band)
        self._piezo_settle_sleep = 1  # seconds
        self._icepap_retries = 4
        # set default factor and offset for TAD to micron calculation
        # from Leo Rousset
        self.factor = self.config.get("factor", float, default = 1.92782,)
        # dto. but this is depending on the installation
        self.offset = self.config.get("offset", float, default = -125.194)

        # setting it to self.factor is setting it to 1 micro tolerance
        self.tns_allowed_divergence = self.config.get("tns_allowed_divergence", float, default = self.factor)

        self.cname = "PiezoJack"
        self._hw_status = AxisState("READY")


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
        add_axis_method(axis, self.get_info, name = "GetInfo", types_info = (None, str))
        add_axis_method(axis, self.selftest, name = "selftest", types_info = (None, None))


    def read_position(self, axis, measured = False):
        """
        Returns position

        Args:
            - <axis> : bliss axis.
        Returns:
            - <position> : float : system position in micron
        """
        tns = self.piezo.Get_TNS()
        _pos = tns * self.factor + self.offset
        return _pos

    def read_encoder(self, encoder):
        """Returns encoder position in encoder units"""
        elog.info("read_encoder() called for encoder %r" % encoder.name)

        return None

    def set_encoder(self, encoder, steps):
        """Set encoder position to a new value given in encoder units"""
        elog.info("set_encoder(%f) called for encoder %r" %
            (steps, encoder.name))
        # No need to return the current encoder position
        return

    def read_velocity(self, axis):
        """ this controller doesn't have a velocity"""
        _velocity = self.icepap.velocity()
        return _velocity

    def set_velocity(self, axis, new_velocity):
        self.icepap.velocity(new_velocity)
        return None

    def read_acceleration(self, axis):
        """Returns axis current acceleration in steps/sec2"""
        return 0

    def set_acceleration(self, axis, new_acc):
        """Set axis acceleration given in steps/sec2"""
        pass

    def read_offset(self, axis):
        """Returns offset (used by position calculation"""
        return self.offset

    def set_offset(self, axis, new_offset):
        """Set axis acceleration given in steps/sec2"""
        self.offset = new_offset

    def state(self, axis):
        if self.piezo.controller.name.startswith("mockup"):
            return AxisState("READY")
        return self._hw_status

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

        if self.piezo.controller.name.startswith("mockup"):
            self.piezo.custom_get_chapi("titi")
            return

        # check for power cut
        self.piezo.CheckPowerCut()

        tad = self.piezo.Get_TAD()
        elog.debug("TAD : %s, %s, %s" % (tad, self.TADmax, self.TADmin))
        if self.TADmax < tad or tad < self.TADmin:
            #            raise RuntimeError("The capacitive sensor is not in its area of linear function")
            elog.error("""
##########################################################################
#####   The capacitive sensor is not in its area of linear function  #####
##########################################################################
TAD is %s""" % tad)

        # elog.debug("icepap position: %s" % self.icepap.position())

    def start_one(self, motion):
        """
        Args:
            - <motion> : Bliss motion object.

        Returns:
            - None
        # TODO: Are we sure the icepap calculates in um, because the
              piezo and this server do. To be checked.
        """
        self._do_move(motion, wait = False)

    def stop(self, axis):
        """
        what's to do in case of an interrupt
        """
        self.icepap.stop()
        self.piezo.stop()
        time.sleep(self._piezo_settle_sleep)
        self.piezo.Set_Closed_Loop(False)

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
        return self.piezo.Get_TAD() * self.factor + self.offset

    @task
    def _do_move(self, motion, wait = False):
        """
        executive movement method, will be non blocking

        Move piezo/icepap system
        * Check if piezo is within a band of movement for the piezo.

        This has all been built around the fact, that both icepap and
        piezo work in microns.
        """

        self._hw_status.set("MOVING")

        """ check if icepap needs moving
            if the new position is outside the piezo's travel range.
            Need to know the POS?
        """
        elog.debug("Read position!")
        measured_pos = self.piezo.measured_position()
        elog.debug("Position is %s" % measured_pos)
        new_pos = measured_pos + motion.delta
        elog.debug("New position should be %s" % new_pos)

        # at the first movement after a ds restart, the POS? might be way off, check it
        # this is outside min and max
        if measured_pos >= self._PiezoSize.high and \
                measured_pos <= self._PiezoSize.low:
            # open the loop, so that the piezo won't break
            self.piezo.Set_Closed_Loop(False)
            elog.debug("Piezo was out of range. Opened loop")

        # now check if new position is within the range of the piezo
        elif new_pos <= self._PiezoSize.high and \
                new_pos >= self._PiezoSize.low:
            # can't move with out loop closed
            self.piezo.Set_Closed_Loop(True)

            self.piezo.rmove(motion.delta)

            time.sleep(self._piezo_settle_sleep)

            elog.debug("New piezo position given by controller: %s" % self.piezo.position())
        else:
            elog.debug("ICEPAP needs moving!")
            before = self.icepap.position()

            # new position's TAD value
            current_tns = self.piezo.Get_TNS()
            new_tns = current_tns + motion.delta / self.factor

            self.piezo.move(self._PiezoSize.middle)
            time.sleep(self._piezo_settle_sleep)

            self.piezo.Set_Closed_Loop(False)

            self.icepap.rmove(motion.delta)  # here we use the common unit, should work!

            time.sleep(self._piezo_settle_sleep)

            # when closed_loop is off, it should set volts
            self.piezo.move(self._PiezoSize.initial_position)
            time.sleep(self._piezo_settle_sleep * 3)

            for _ in range(self._icepap_retries):
                current_tns = self.piezo.Get_TNS()
                newtnsdelta = new_tns - current_tns
                if abs(newtnsdelta) < self.tns_allowed_divergence:
                    break

                icepap_rmove = newtnsdelta * self.factor
                elog.debug("Move icepap by %s" % icepap_rmove)
                self.icepap.rmove(icepap_rmove)

            after = self.icepap.position()
            elog.debug("icepap pos after: %s, delta: %s" % (after, after - before))

            """
            here is where the piezo works

            first set the new offset
            """
            offset = self.piezo.Get_Offset()
            elog.debug("offset: %s" % offset)

            measured_pos = self.piezo.measured_position()
            elog.debug("POS? %s" % measured_pos)

            offset -= measured_pos - self._PiezoSize.middle
            self.piezo.Put_Offset(offset)

            offset = self.piezo.Get_Offset()
            elog.debug("offset: %s" % offset)

            ppos = self.piezo.position()  # with open loop, this is SVA?

            measured_pos = self.piezo.measured_position()  # POS?
            elog.debug("new offset : %s with pos: %s and sva: %s" % (offset, measured_pos, ppos))

            self.piezo.Set_Closed_Loop(True)

            measured_pos = self.piezo.measured_position()  # POS?

            current_position = self.bender_abs_pos()

            elog.debug("bender abs pos: %s" % (current_position))

        self._hw_status.set("READY")

    def selftest(self, axis):
        # testing if in the right zone of the cap sensor
        tad = self.piezo.Get_TAD()
        print("TAD : %s, %s, %s" % (tad, self.TADmax, self.TADmin))
        if self.TADmax < tad or tad < self.TADmin:
            print ("The capacitive sensor is not in its area of linear function: %s" % tad)
        else:
            print("TAD: %s" % tad)

        how_much = 80

        # calculate a vague destination TAD to see if we're in the linear function of the device
        dest_tad = tad + how_much / 7.063955e-04
        if dest_tad > self.TADmax:
            print("Destination TAD would be close to %d" % dest_tad)
            print("better move some in negative direction.")
            return

        preset = icepap_position_before = self.icepap.position()

        ice1 = self.icepap.position()
        tns1 = self.piezo.Get_TNS()
        tsp1 = self.piezo.Get_TSP()
        tad1 = self.piezo.Get_TAD()

        self.icepap.rmove(how_much)
        time.sleep(1)
        tad = self.piezo.Get_TAD()
        print("second TAD : %s" % (tad))

        ice2 = self.icepap.position()
        tns2 = self.piezo.Get_TNS()
        tsp2 = self.piezo.Get_TSP()
        tad2 = self.piezo.Get_TAD()

        self.icepap.rmove(-how_much)
        time.sleep(1)

        print("\n\nICEPAP before: %s" % (icepap_position_before))
        print("ICEPAP there : %s, TAD %s, TNS %s, TSP: %s" % (ice1, tad1, tns1, tsp1))
        print("ICEPAP after : %s, TAD %s, TNS %s, TSP: %s" % (ice2, tad2, tns2, tsp2))

        print("\nTNS positions:\n")
        print("there:  %s" % tns1)
        print("after:  %s" % tns2)

        factor = (ice2 - ice1) / (tns2 - tns1)
        offset = ice1 - (ice2 - ice1) / (tns2 - tns1) * tns1
        print("factor and offset should be: %g, %g \n" % (factor, offset))
        print("the offset could be %f, if tns1 should be zero" % (offset - preset))

        print("factor and offset with TAD: %e, %g" % ((ice2 - ice1) / (tad2 - tad1), ice1 - (ice2 - ice1) / (tad2 - tad1) * tad1))
        print("factor and offset with TSP: %g, %g" % ((ice2 - ice1) / (tsp2 - tsp1), ice1 - (ice2 - ice1) / (tsp2 - tsp1) * tsp1))

        print("\nCalculated positions:\n")
        print("before: %f" % (tns1 * factor + offset))
        print("there:  %f" % (tns1 * factor + offset))
        print("after:  %f" % (tns2 * factor + offset))

