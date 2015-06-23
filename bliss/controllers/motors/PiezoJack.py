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
        self.length = length                      # microns (15)
        self.band = band                          # microns (4)
        self.middle = self.length / 2             # microns
        self.low = self.middle - (self.band / 2)  # microns
        self.high = self.middle + (self.band / 2) # microns
        self.initial_voltage = 50                 # Volt


class PiezoJack(Controller):

    def __init__(self, name, config, axes, encoders):
        Controller.__init__(self, name, config, axes, encoders)

        self.TADmin = self.config.get("TADmin", int, default = 150000)
        self.TADmax = self.config.get("TADmax", int, default = 700000)

        self.factor = 0
        self.offset = 0
        self.__move_task = None

        length = self.config.get("PiezoLength", float, 15)  # microns
        band = self.config.get("PiezoBand", float, 4)       # microns
        self._PiezoSize = PiezoSize(length, band)
        self._piezo_settle_sleep = 1  # seconds
        self._icepap_retries = 4
        # set default factor and offset for TAD to micron calculation
        # from Leo Rousset
        self.factor = self.config.get("factor", float, default = 1.92782,)
        # dto. but this is depending on the installation
        self.offset = self.config.get("offset", float, default = 0)

        # setting it to self.factor is setting it to 1 micro tolerance
        self.tns_allowed_divergence = self.config.get("tns_allowed_divergence", float, default = self.factor)

        self.cname = "PiezoJack"
        self._hw_status = AxisState("READY")


    def initialize(self):
        self.piezo = self._tagged["piezo"][0]
        self.icepap = self._tagged["icepap"][0]
        self._hw_status  =  self.icepap.state()

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

        add_axis_method(axis, self.read_offset, name = "ReadOffset", types_info = (None, float))
        add_axis_method(axis, self.set_offset, name = "SetOffset", types_info = (float, None))

        add_axis_method(axis, self.read_factor, name = "ReadFactor", types_info = (None, float))
        add_axis_method(axis, self.set_factor, name = "SetFactor", types_info = (float, None))
        add_axis_method(axis, self.sync, name = "sync", types_info = (None, None))

    def read_position(self, axis):
        """
        Returns position

        Args:
            - <axis> : bliss axis.
        Returns:
            - <position> : float : system position in micron
        """

        print ("---------------########### in read_position-------")

        try:
            tns = self.piezo.Get_TNS()

            # conversion to microns (factor=1.75 offset=-400)
            _pos = tns * self.factor + self.offset
            elog.debug("returned position %r" % _pos)
            return _pos
        except:
            print("error in reading PJ position")
            sys.excepthook(*sys.exc_info())

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
        """Set offset (used by position calculation"""

        self.offset = new_offset

        # Force to re-read position
        self.sync(axis)

    def read_factor(self, axis):
        """Returns factor (used by position calculation"""
        return self.factor

    def set_factor(self, axis, new_factor):
        """Set factor (used by position calculation"""

        self.factor = new_factor

        # Force to re-read position to make sure calculated position
        # takes factor into account.
        self.sync(axis)

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
            - RuntimeError('The capacitive sensor is not in its right area of function')
        """
        self.sync(self.piezo)
        self.sync(self.icepap)

        if self.piezo.controller.name.startswith("mockup"):
            self.piezo.custom_get_chapi("titi")
            return

        # check for power cut
        self.piezo.CheckPowerCut()

        tad = self.piezo.Get_TAD()
        elog.debug("TAD : %s, %s, %s" % (tad, self.TADmax, self.TADmin))
        if self.TADmax < tad or tad < self.TADmin:
            #            raise RuntimeError("The capacitive sensor is not in its area of linear function")
            elog.info("""
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
        if self.__move_task is None or self.__move_task.ready():
            self._hw_status = AxisState("MOVING")
            self._move_task = self._do_move(motion, wait = False)
            self._move_task.link(self._move_done)
        else:
            raise RuntimeError("cannot move, previous task is not finished")

    def _move_done(self, task):
        self._hw_status = AxisState("READY")

        try:
            #import pdb; pdb.set_trace()
            task.get()
        except:
            sys.excepthook(*sys.exc_info())

    def stop(self, axis):
        """
        what's to do in case of an interrupt
        """
        self._move_task.kill()

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
        _info_str = "---------PiezoJack: get_info----------\n"

        if not self.piezo.controller.name.startswith("mockup"):
            #             elog.info("PiezoJack::get_info: ICEPAP Identifier: " % self.icepap.get_identifier())
            #             elog.info("PiezoJack::get_info: Piezo Info:" % self.piezo.GetInfo())

            _info_str += "icepap position  : %s\n" % self.icepap.position()
            closed_loop = self.piezo.Get_Closed_Loop_Status()
            _info_str += "piezo closed loop: %s\n" % closed_loop

            _info_str += "piezo tns        : %s\n" % self.piezo.Get_TNS()
            _info_str += "piezo offset     : %s\n" % self.piezo.Get_Offset()

            _info_str += "piezo POS?       : %s\n" % self.piezo.Get_Pos()

            _info_str += "piezo instance   : %s\n" % self.piezo.name

            if closed_loop:
                _info_str += "piezo MOV?       : %s\n" % self.piezo.position()
                self.piezo.Set_Closed_Loop(onoff = False)
                _info_str += "piezo SVA?       : %s\n" % self.piezo.position()
                self.piezo.Set_Closed_Loop(onoff = True)
            else:
                self.piezo.Set_Closed_Loop(onoff = True)
                _info_str += "piezo MOV?       : %s\n" % self.piezo.position()
                self.piezo.Set_Closed_Loop(onoff = False)
                _info_str += "piezo SVA?       : %s\n" % self.piezo.position()
        _info_str += "--------------------------------------\n"

        return _info_str

    @task
    def _do_move(self, motion):
        """
        executive movement method, will be non blocking

        Move piezo/icepap system
        * Check if piezo is within a band of movement for the piezo.

        This has all been built around the fact, that both icepap and
        piezo work in microns.
        """

        """ check if icepap needs moving
            if the new position is outside the piezo's travel range.
            Need to know the POS?
        """
        pos = self.piezo.Get_Pos()   # "POS?"
        elog.debug("real Position is %s" % pos)

        # at the first movement after a ds restart, the POS? might be
        # way off, check if this is outside min and max
        if pos >= self._PiezoSize.high or \
                pos <= self._PiezoSize.low:
            # open the loop, so that the piezo won't break
            self.piezo.Set_Closed_Loop(False)
            # we are out of the controller range, so let's correct the
            # 712 offset.
            # Move is in volt, since loop is opened
            self.piezo.move(50)
            self.piezo.Put_Offset(self.piezo.Get_Offset()-self.piezo.Get_Pos()+ self._PiezoSize.middle)
            self.piezo.Set_Closed_Loop(True)
            time.sleep(self._piezo_settle_sleep)
        
        pos = self.piezo.Get_Pos()
        new_pos = pos + motion.delta
        elog.debug("New position should be %s" % new_pos)

        # Now check if new position is within the range of the piezo.
        if new_pos <= self._PiezoSize.high and \
                 new_pos >= self._PiezoSize.low:
            #### PIEZO ONLY MOVE  ####

            # can't move in open loop.
            self.piezo.Set_Closed_Loop(True)

            self.piezo.move(new_pos)

            time.sleep(self._piezo_settle_sleep)

            elog.debug("New piezo position given by controller: %s" % self.piezo.position())
        else:
            #### ICEPAP MOVE  ####
            elog.debug("ICEPAP needs moving!")
            before = self.icepap.position()

            # new position's TNS value
            current_tns = self.piezo.Get_TNS()

            new_tns = current_tns + motion.delta / self.factor
            elog.debug("self.factor is %r" % self.factor)
            elog.debug("----------------------------> new_tns should be %r" % new_tns)

            # Open the loop
            self.piezo.Set_Closed_Loop(False)

            # place icepap just under the requested position, so we can
            # make a positive (i.e. no backlash) movement to get closer.
            motion.delta -= 3
            elog.debug("ICEPAP before RMOVE! motion.delta = %r" % (motion.delta))
            self.icepap.rmove(motion.delta)  # here we use the common unit, should work!
            elog.debug("ICEPAP after  RMOVE!")

            # time.sleep(self._piezo_settle_sleep)

            # when closed_loop is off, controller set volts
            self.sync(self.piezo)
            self.piezo.move(self._PiezoSize.initial_voltage)
            elog.debug("AFTER Piezo Move")
            time.sleep(self._piezo_settle_sleep * 3)

            # Try to move close to the new calculated TNS.
            for _ in range(self._icepap_retries):
                current_tns = self.piezo.Get_TNS()
                elog.debug("----------------------------     new_tns      ------------------> %r" % (new_tns))
                elog.debug("---------------------------- LOOP current_tns ------------------> %r" % (current_tns))
                if abs(new_tns - current_tns) < self.tns_allowed_divergence:
                    break

                icepap_move = (new_tns - current_tns) * self.factor 
                self.icepap.rmove(icepap_move)

            after = self.icepap.position()
            elog.debug("icepap pos after: %s, delta: %s" % (after, after - before))

            """
            here is where the piezo works

            first set the new offset
            """
            # old offset
            offset = self.piezo.Get_Offset()
            elog.debug("offset: %s" % offset)

            pos = self.piezo.Get_Pos()
            elog.debug("POS? %s" % pos)

            # recalculate offset
            offset -= (pos - self._PiezoSize.middle)  # microns
            self.piezo.Put_Offset(offset)

            # print new values for info.
            offset = self.piezo.Get_Offset()
            pos = self.piezo.Get_Pos()
            elog.debug("new offset : %s with pos: %s" % (offset, pos))

            self.piezo.Set_Closed_Loop(True)

            time.sleep(self._piezo_settle_sleep)

            pos = self.piezo._position()  # "POS?" + cache update.

            for _ in range(self._icepap_retries):
                current_tns = self.piezo.Get_TNS()
                elog.debug("---PIEZO--------------------     new_tns      ------------------> %r" % (new_tns))
                elog.debug("---PIEZO-------------------- LOOP current_tns ------------------> %r" % (current_tns))
                if abs(new_tns - current_tns) < self.tns_allowed_divergence:
                    break

                piezo_move = new_tns * self.factor
                self.piezo.move(piezo_move)
                time.sleep(self._piezo_settle_sleep)


    def sync(self, axis):
        axis._position()

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

