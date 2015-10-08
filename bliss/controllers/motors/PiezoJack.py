import time
from math import cos, radians
from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import AxisState
from bliss.common.task_utils import *

"""
Bliss controller for a piezo jack.

Unite an Icepap Stepper motor with a Physik Instrumente E712 axis.
This will make a PiezoJack, which share one capacitive sensor. The
sensor is read via the PI E712.

Holger Witsch ESRF BLISS
Oct 2014

This config example needs elaborating !!!!

Still in progess, please be patient
"""


#                                      PiezoJack
#    flexor                           /
#    0----------|---------------- \ |/_
#              CC                  \
#                                   \
#
#    dist flexer / captor = 28mm
#    dist flexor / piezo application point = 82mm
#    angle : 26 deg.
#

class PiezoSize():
    """
    Piezo characteristics.
    """
    def __init__(self, length, band):
        self.length = length                        # microns (15)
        self.band = band                            # microns (11)
        self.middle = self.length / 2.0             # microns (7.5)
        self.low = self.middle - (self.band / 2.0)  # microns (2)
        self.high = self.middle + (self.band / 2.0) # microns (13)
        self.middle_voltage = 50                   # Volts


class PiezoJack(Controller):

    def __init__(self, name, config, axes, encoders):
        Controller.__init__(self, name, config, axes, encoders)

        # *Analog* limits of linear use of capacitive sensor.
        self.TADmin = self.config.get("TADmin", int, default = 150000)
        self.TADmax = self.config.get("TADmax", int, default = 700000)

        self.factor = 0  # conversion factor from TNS to microns.

        self._move_task = None

        length = self.config.get("PiezoLength", float, 15)  # microns
        band = self.config.get("PiezoBand", float, 4)       # microns
        self._PiezoSize = PiezoSize(length, band)
        self._piezo_settle_sleep = 1  # seconds
        self._piezo_settle_sleep_CL = 5  # seconds

        self._icepap_retries = 8
        self._piezo_retries = 8

        # Capacitive Sensor's TNS to microns.
        # Measured by Leo Rousset in linear system.
        # 1 TNS = 1.75887 microns
        self.CS_tns2microns = 1.75887

        # leverage arm
        self.leverage_arm = 82.0/28.0   # ~2.93 (theorical value)
        self.leverage_arm = 2.8         # measured

        # A PiezoJack movement (piezo or icepap) produces a
        # <application_angle_factor> times BIGGER movement on the
        # bender.
        self.application_angle_factor = 1/cos(radians(26)) # ~1.11

        # A PJ movement induce a <system_factor> times SMALLER
        # displacement of the capacitive sensor.
        self.system_factor = self.leverage_arm / self.application_angle_factor

        self.piezo_factor  = self.system_factor                       # 1 TNS = 2.64 piezo-microns
        self.icepap_factor = self.CS_tns2microns * self.system_factor # 1 TNS = 4.63 icepap-microns
        self.bender_factor = self.CS_tns2microns * self.leverage_arm  # 1 TNS = 5.15 bender-microns

        # Default factor for TNS to microns conversion
        self.factor = self.config.get("factor", float, default = self.system_factor)

        # setting it to self.factor is setting it to 1 micron tolerance
        self.tns_allowed_divergence = self.config.get("tns_allowed_divergence", float, default = 1)

        self.cname = "PiezoJack"
        self._hw_status = AxisState("READY")


    def initialize(self):
        self.piezo = self._tagged["piezo"][0]
        self.icepap = self._tagged["icepap"][0]
        self._hw_status  =  self.icepap.state()

    def finalize(self):
        pass

    def initialize_axis(self, axis):

        # To get rid of cache coherency problems.
        add_axis_method(axis, self.sync, name = "sync", types_info = (None, None))

    def read_position(self, axis):
        """
        Returns:
            - <position> : float : system position in micron
        """
        try:
            # Capacitive captor value.
            tns = self.piezo.Get_TNS()

            # Conversion TNS to bender-microns
            _pos = tns * self.bender_factor
            elog.debug("--PJ-bender position=%g" % _pos)
            return _pos
        except:
            print "error in reading PJ position"
            sys.excepthook(*sys.exc_info())

    def state(self, axis):
        return self._hw_status

    def prepare_move(self, motion):
        elog.info("--PJ--prepare_move : motion: target_pos=%g  delta=%g " % (motion.target_pos, motion.delta))

        # Check for power cut.
        self.piezo.CheckPowerCut()

        tad = self.piezo.Get_TAD()
        elog.info("TAD : %s, %s, %s" % (tad, self.TADmax, self.TADmin))
        if self.TADmax < tad or tad < self.TADmin:
            #            raise RuntimeError("The capacitive sensor is not in its area of linear function")
            elog.info("""
###########################################################################
##### !! The capacitive sensor is not in its area of linear function  #####
###########################################################################
TAD is %s""" % tad)


    def start_one(self, motion):
        elog.info("--PJ--start_one : motion: target_pos=%g  delta=%g " % (motion.target_pos, motion.delta))

        if self._move_task is None or self._move_task.ready():
            # To be sure state is correct even if movement hasn't started.
            self._hw_status = AxisState("MOVING")

            # Movement greenlet starting point.
            self._move_task = self._do_move(motion, wait = False)

            # At end of the move task, just call _move_done() function.
            self._move_task.link(self._move_done)
        else:
            raise RuntimeError("cannot move, previous task is not finished")

    def _move_done(self, task):
        self._hw_status = self.icepap.state()

        try:
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
        Returns information about controller.
        Helpful to tune the device.
        """
        elog.info("PiezoJack: get_info")
        _info_str = "---------PiezoJack %s : get_info----------\n" % axis.name

        if not self.piezo.controller.name.startswith("mockup"):
            #             elog.info("PiezoJack::get_info: ICEPAP Identifier: " % self.icepap.get_identifier())
            #             elog.info("PiezoJack::get_info: Piezo Info:" % self.piezo.get_info())

            _info_str += "bender position  : %s\n" % self.read_position(axis)
            _info_str += "icepap position  : %s\n" % self.icepap.position()
            _info_str += "piezo closed loop: %s\n" % self.piezo.Get_Closed_Loop_Status()
            _info_str += "piezo tns        : %s\n" % self.piezo.Get_TNS()
            _info_str += "piezo offset     : %s\n" % self.piezo.Get_Offset()
            _info_str += "piezo POS?       : %s\n" % self.piezo.Get_Pos()
            _info_str += "piezo factor     : %g\n" % self.piezo_factor
            _info_str += "icepap factor    : %g\n" % self.icepap_factor
            _info_str += "bender factor    : %g\n" % self.bender_factor
            _info_str += "system factor    : %g\n" % self.system_factor

            _info_str += "piezo MOV?       : %s\n" % self.piezo.Get_MOV()
            _info_str += "piezo SVA?       : %s\n" % self.piezo.Get_SVA()
            _info_str += "piezo VOL?       : %s\n" % self.piezo.Get_VOL()
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
        elog.info("--PJ-------------- starts _do_move loop ----------------- ")
        elog.info("--PJ-- _do_move : motion: target_pos=%g  delta=%g " % (motion.target_pos, motion.delta))

        # Calculates targets positions
        bender_new = motion.target_pos
        bender_delta = motion.delta

        # bender_current = bender_new - bender_delta
        bender_current = self.read_position(motion.axis)

        tns_new = bender_new / self.bender_factor
        tns_delta = motion.delta / self.bender_factor
        tns_current = self.piezo.Get_TNS()

        piezo_delta  = tns_delta * self.piezo_factor
        piezo_current = self.piezo.Get_Pos() * self.system_factor # Sensor corrected by lev.arm+app.angle.
        piezo_target = piezo_current + piezo_delta

        elog.info("--PJ--bender: current=%g  new=%g  delta=%g" % (bender_current, bender_new,   bender_delta))
        elog.info("--PJ--TNS:    current=%g  new=%g  delta=%g" % (tns_current,    tns_new,      tns_delta))
        elog.info("--PJ--piezo:  current=%g  new=%g  delta=%g" % (piezo_current,  piezo_target, piezo_delta))

        elog.info(" ")
        elog.info(" ")

        elog.info("--PJ--piezo:  current=%g  new=%g  delta=%g" % (piezo_current,  piezo_target, piezo_delta))
        return()

        # At the first movement after a restart, the piezo might be
        # way off.
        # If piezo position is outside range [0;15] or if loop is open corrects it.
        if piezo_current <= 0 or piezo_current >= self._PiezoSize.length or not self.piezo.Get_Closed_Loop_Status():
            # Opens the loop, so that the piezo won't break, but move
            # it to zero first and waits a bit to let time to piezo to
            # come back to 0. (to avoid clacs ?)
            elog.info("--PJ--Piezo out of correct range : Moves piezo to zero and opens the loop.")
            self.piezo.move(0)
            time.sleep(self._piezo_settle_sleep)  # ??? e712 does not use ONT? (to be done later if it works)
                                                  # TODO : loop to check how long it takes to be ONT.
            self.piezo.Set_Closed_Loop(False)

            # Changes piezo offset (i.e. 0 reference for capacitive sensor)
            # to compensate icepap movement. (in microns)
            # Offset is set considering that piezo position is 0.
            new_piezo_offset = self.piezo.Get_Offset() - self.piezo.Get_Pos()
            elog.info("--PJ--Puts new PIEZO offset to %g " % new_piezo_offset)
            self.piezo.Put_Offset(new_piezo_offset)

            # Place piezo in middle range. (??? why to do that in open loop ?)
            elog.info("--PJ--Moves piezo to 50 V (half-range)")
            self.piezo.move(self._PiezoSize.middle_voltage)

            self.piezo.Set_Closed_Loop(True)
            time.sleep(self._piezo_settle_sleep_CL) # to stabilise (5s ?)

        elog.info("--PJ--ok, piezo pos is in range and ready to be moved.")
        elog.info(" ")
        elog.info(" ")

        tns_current = self.piezo.Get_TNS()
        piezo_current = self.piezo.Get_Pos() * self.system_factor # Sensor corrected by lev.arm+app.angle.
        piezo_target = piezo_current + piezo_delta

        elog.info("--PJ--New positions should be: bender=%g tns=%g" % (bender_new, tns_new))

        # Checks if new position is within the range of the piezo [2; 13].
        # ie : could be reached with only a piezo movement.
        if (piezo_target >= self._PiezoSize.low) and (piezo_target <= self._PiezoSize.high):
            # #### PIEZO MOVE ONLY  #### #
            elog.info("--PJ--   PIEZO MOVE ONLY ")
            elog.info("--PJ--new bender position (%g=%g+%g) can be reached by piezo: " %
                      (bender_new, bender_current, bender_delta))
            elog.info("--PJ--  piezo_target % is in range [%g, %g] => piezo movement only" %
                      (piezo_target, self._PiezoSize.low, self._PiezoSize.high))

            elog.info("--PJ--Moves bender to %g um (piezo to %g um)" % (bender_new, piezo_target))
            self.piezo.move(piezo_target)  # in um.
            time.sleep(self._piezo_settle_sleep) # needed because E712 is not using "on target" flag.

###            # Why /8 ??? and /100 in final piezo in hybrid movement ?
###            # --->  ok : to be tuned.
###            tns_tolerance = self.tns_allowed_divergence / 8
###            elog.info("--PJ-piezo--TNS tolerance=%g" , tns_tolerance)
###
###            # Piezo approach : Try (many times if needed) to
###            # move piezo to tns_new postion.
###            # ??? why ? in close loop, the controller does that ???
###            self.piezo_approach(tns_new, tns_tolerance)

            tns_current = self.piezo.Get_TNS()
            tns_diff = tns_new - tns_current
            elog.info("--PJ--after piezo move : TNS : current=%g  new=%g  error=%g" % (tns_current, tns_new, tns_diff))
            elog.info("--PJ--New piezo position : %g (updated)" % self.piezo._position())

        else:
            # #### ICEPAP MOVE + PIEZO MOVE  #### #
            elog.info("--PJ--   ICEPAP MOVE  +  PIEZO MOVE ")
            elog.info("--PJ--piezo_target %g OUTSIDE range [%g;%g] => ICEPAP + PIEZO movement" %
                      (piezo_target, self._PiezoSize.low, self._PiezoSize.high))

            ice_pos_before = self.icepap.position()

            # TNS values.
            tns_current = self.piezo.Get_TNS()
            elog.info("--PJ--TNS : current=%g new=%g delta=%g" %(tns_current, tns_new, tns_delta))

            # Piezo to 0 and opens the loop.
            # Icepap movements must be done with piezo loop open to
            #  avoid to clac the piezo when moving icepap.
            elog.info("--PJ--Opens the piezo loop, but move it to zero first")
            self.piezo.move(0)
            self.piezo.Set_Closed_Loop(False)
            time.sleep(self._piezo_settle_sleep)

            # Piezo to middle position (in voltage) to get maximum piezo
            # range of movement after icepap movement.
            self.piezo.move(self._PiezoSize.middle_voltage) # (50 V)
            elog.info("--PJ--Set Piezo voltage to %g" % self._PiezoSize.middle_voltage)
            time.sleep(self._piezo_settle_sleep * 3) # open loop -> voltage mov -> no sync -> wait to stabilise

#            # Correct motion by piezo_current (due to previous piezo.move(0))
#            motion.delta += piezo_current

            # Places icepap just 3um under the requested position, so we can
            # make a positive (i.e. no backlash) movement to get closer.
            motion.delta -= 3

            elog.info("--PJ-ICEPAP-before RMOVE! corrected motion.delta = %g----------" % (motion.delta))
            self.icepap.rmove(motion.delta)
            elog.info("--PJ-ICEPAP-after  RMOVE!<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
            # time.sleep(self._piezo_settle_sleep)

            elog.info("--PJ--Moves ICEPAP to be closest possible to the TNS target .........")
            for ii in range(self._icepap_retries):
                tns_current = self.piezo.Get_TNS()
                tns_diff = abs(tns_new - tns_current)
                bender_diff = tns_diff * self.icepap_factor
                elog.info("--PJ-ICEPAP--%d-- TNS new=%g current=%g diff= %g" % (ii, tns_new, tns_current, tns_diff))
                if tns_diff < self.tns_allowed_divergence:
                    break  # ok we are close enough

                # If overshoot : no icepap move to avoid backlash.
                # -> faire un movement plus petit que voulu ? pour ne pas depasser et donc pour eviter des backlash.
                icepap_move = (tns_new - tns_current) * self.icepap_factor
                if icepap_move < 0:
                    log.info("--PJ-icepap move negatif. tns_diff=%g bender_diff=%g" % tns_diff)

                self.icepap.rmove(icepap_move)

            icepap_after = self.icepap.position()
            elog.info("--PJ- icepap after approach: %s, delta: %s" % (icepap_after, icepap_after - ice_pos_before))

            # Changes piezo offset to compensate icepap movement. (in microns)
            # Piezo was set to middle position before ice movement.
            # And to make piezo controller able to regulate position in closed loop.
            new_piezo_offset = self.piezo.Get_Offset() - self.piezo.Get_Pos() + self._PiezoSize.middle
            self.piezo.Put_Offset(new_piezo_offset)
            elog.info("--PJ- offset changed, close the loop and make final approach")

            self.piezo.Set_Closed_Loop(True)
            time.sleep(self._piezo_settle_sleep_CL) # to stabilise

            # Piezo approach : Try (many times if needed) to
            # move piezo to tns_new postion.
            # In close loop, the controller does that ? (yes if all calculated/measured factors are ideal)
            #   TODO : to test if our factors are so wonderful :)
            tns_tolerance = self.tns_allowed_divergence / 10.0
            if False:
                self.piezo_approach(tns_new, tns_tolerance)
            else:
                _tns_current = self.piezo.Get_TNS()
                _tns_diff = tns_new - _tns_current
                if abs(_tns_diff) > tns_tolerance:
                    _piezo_rmove = _tns_diff * self.piezo_factor
                    elog.info("--PJ-piezo- rmove %g" % (_piezo_rmove))
                    self.piezo.rmove(_piezo_rmove)
                    time.sleep(self._piezo_settle_sleep) # ??? e712 does not use ONT?


    def piezo_approach(self, tns_new, tns_tolerance):
        for pp in range(self._piezo_retries):
            _tns_current = self.piezo.Get_TNS()
            _tns_diff = tns_new - _tns_current
            elog.info("--PJ-piezo--TNS %d:current=%g  new=%g  diff=%g" %
                      (pp, _tns_current, tns_new, _tns_diff))

            if abs(_tns_diff) < tns_tolerance:
                break

            _piezo_rmove = _tns_diff * self.piezo_factor
            elog.info("--PJ-piezo- rmove %g" % (_piezo_rmove))
            self.piezo.rmove(_piezo_rmove)
            time.sleep(self._piezo_settle_sleep) # ??? e712 does not use ONT?


    def sync(self, axis):
        # NB : a _position() is done by E712 when closing/opening the piezo loop.
        axis._position()

