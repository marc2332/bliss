# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
from math import cos, radians
from numpy import arange

from bliss.controllers.motor import Controller
from bliss.controllers import motor_settings as settings

from bliss.common.axis import AxisState
from bliss.common.task import task

from bliss.common.utils import object_method

"""
Bliss controller for a piezo jack.

Unite an Icepap Stepper motor with a Physik Instrumente E712 axis.
Sharing one capacitive sensor, they will make the PiezoJack. The
sensor is read via the PI E712.

Holger Witsch ESRF BLISS
Cyril Guilloud ESRF BLISS
2014-2015

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


class PiezoSize:
    """
    Piezo characteristics.
    """

    def __init__(self, length, band):
        self.length = length  # microns (15)
        self.band = band  # microns (11)
        self.middle = self.length / 2.0  # microns (7.5)
        self.low = self.middle - (self.band / 2.0)  # microns (2)
        self.high = self.middle + (self.band / 2.0)  # microns (13)
        self.middle_voltage = 50  # Volts


class PiezoJack(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        # *Analog* limits of linear use of capacitive sensor.
        self.TADmin = self.config.get("TADmin", int, default=150000)
        self.TADmax = self.config.get("TADmax", int, default=700000)

        self.factor = 1  # conversion factor from TNS to microns.

        self._move_task = None

        # set the length of the given piezo,
        # the other needed attributes being calculated in class PiezoSize
        length = self.config.get("PiezoLength", float, 15)  # microns
        band = self.config.get("PiezoBand", float, 4)  # microns
        self._PiezoSize = PiezoSize(length, band)
        self._piezo_settle_sleep = 1  # seconds

        self._icepap_retries = 8

        # Capacitive Sensor's TNS to microns.
        # Measured by Leo Rousset in linear system.
        # 1 TNS = 1.75887 microns
        self.CS_tns2microns = 1.75887

        # leverage arm
        self.system_factor = 82.0 / 28.0  # ~2.93 (theorical value)
        self.system_factor = 2.8  # measured (cos taken into account in measurement...)

        # TNS to bender movement conversion factor
        self.bender_factor = self.CS_tns2microns * self.system_factor  # 4.925

        # Default factor for TNS to microns conversion   # 4.74
        # This value has shown to be different for the two sides of the mirror
        # we used for testing. It needs to be configurable.
        self.bender_factor = self.config.get(
            "factor", float, default=self.bender_factor
        )

        # This value will decide in which distance from the calculated target_tns the icepap position
        # needs to be, before it is acceptable to go on to regulate the position with the piezo.
        self.tns_allowed_divergence = self.config.get(
            "tns_allowed_divergence", float, default=0.5
        )

        # the controllers name. The axes will have names given by the configuration.
        self.cname = "PiezoJack"
        # one has to start somewhere. Be ready for the start.
        self._hw_status = AxisState("READY")
        self.piezo = None
        self.icepap = None

    def initialize(self):
        # velocity and acceleration are not mandatory in config
        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

        # axes used to drive the piezojack, one icepap and one piezo
        self.piezo = self._tagged["piezo"][0]
        self.icepap = self._tagged["icepap"][0]
        # preset the hardware status with the icepap's status.
        self._hw_status = self.icepap.state

    def finalize(self):
        pass

    def initialize_axis(self, axis):
        """

        :type self: object
        """

        # Reads sensors coefficients (previously calibrated...) for the current piezo axis
        # from the PI E712
        self.piezo.coeffs = self.piezo.controller.get_sensor_coeffs(self.piezo)
        if (
            self.bender_factor < 0
            and self.piezo.coeffs[1] > 0
            or self.bender_factor > 0
            and self.piezo.coeffs[1] < 0
        ):
            # Needed, when in the table, when senson works the opposite way
            self.piezo.controller.set_sensor_coeffs(
                self.piezo, 1, -self.piezo.coeffs[1]
            )

    def initialize_encoder(self, encoder):
        """ use the capacitive sensor as encoder"""
        self._logger.debug("initialize_encoder %s" % encoder.name)

    def read_encoder(self, encoder):
        """ read the capacitive sensor over the PI E712 as an encoder """
        _tns = self.piezo.Get_TNS()
        _bender_enc = _tns * self.bender_factor
        return _bender_enc

    def read_position(self, axis):
        """
        Returns:
            - <position> : float : system position in micron
        The current value of the capacitive sensor is read from the PI E712. The multiplication with the
        factor is necessary, because the sensor is mounted much closer to the movement axis, than the piezojack,
        """
        try:
            # Capacitive captor value.
            tns = self.piezo.Get_TNS()

            # Conversion TNS to bender-microns
            _pos = tns * self.bender_factor
            self._logger.debug("--PJ-bender position=%g" % _pos)
            return _pos
        except:
            sys.excepthook(*sys.exc_info())

    def state(self, axis):
        return self._hw_status

    def prepare_move(self, motion):
        self._logger.info(
            "--PJ--prepare_move : motion: target_pos=%g  delta=%g "
            % (motion.target_pos, motion.delta)
        )

        # Check for power cut.
        self.piezo.CheckPowerCut()

        tad = self.piezo.Get_TAD()
        self._logger.info("TAD : %s, %s, %s" % (self.TADmax, tad, self.TADmin))
        if self.TADmax < tad or tad < self.TADmin:
            #            raise RuntimeError("The capacitive sensor is not in its area of linear function")
            self._logger.info(
                "###########################################################################\n"
                + "##### !! The capacitive sensor is not in its area of linear function  #####\n"
                + "###########################################################################\n"
                + "TAD is "
                + str(tad)
            )

    def start_one(self, motion):
        self._logger.info(
            "\n\n\n"
            + "###########################################################################\n"
            + "--PJ--start_one : motion: target_pos={0:g}  delta={1:g}\n".format(
                motion.target_pos, motion.delta
            )
            + "###########################################################################\n\n\n"
        )

        if self._move_task is None or self._move_task.ready():
            # To be sure state is correct even if movement hasn't started.
            self._hw_status = AxisState("MOVING")

            # Movement greenlet starting point.
            self._move_task = self._do_move(motion, wait=False)

            # At end of the move task, just call _move_done() function.
            self._move_task.link(self._move_done)
        else:
            raise RuntimeError("cannot move, previous task is not finished")

    def _move_done(self, task):
        self._hw_status = self.icepap.state

        try:
            task.get()
        except:
            sys.excepthook(*sys.exc_info())

    def move_piezo_smooth(self, pos=0):
        """
        move the piezo voltage to value, but smoothly to avoid
        large changes, which might damage the crystal
        """
        if self.piezo.Get_Closed_Loop_Status():
            # don't do this in closed loop mode
            self._logger.info("move_piezo_smooth : don't do this in closed loop mode")
            return
        _start = self.piezo.position
        _inc = -1 if (pos < _start) else 1
        # print "smooth move to ", target_pos,
        # Uses arange instead of range to be able to have floating point steps.
        for ii in arange(int(_start), int(pos), _inc):
            self.piezo.move(ii)
            time.sleep(0.01)
        self.piezo.move(pos)

        # Loop is open, sleep a bit to stabilise.
        time.sleep(self._piezo_settle_sleep)

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
        self._logger.info("PiezoJack: get_info")
        _info_str = "---------PiezoJack %s : get_info----------\n" % axis.name

        if not self.piezo.controller.name.startswith("mockup"):
            #             self._logger.info("PiezoJack::get_info: ICEPAP Identifier: " % self.icepap.get_identifier())
            #             self._logger.info("PiezoJack::get_info: Piezo Info:" % self.piezo.get_info())

            _info_str += "bender position (set)  : %s\n" % settings.AxisSettings(
                axis
            ).get("_set_position")
            _info_str += "bender position (read) : %s\n" % self.read_position(axis)
            _info_str += "icepap position  : %s\n" % self.icepap.position
            _info_str += "piezo closed loop: %s\n" % self.piezo.Get_Closed_Loop_Status()
            _info_str += "piezo tns        : %s\n" % self.piezo.Get_TNS()
            _info_str += "piezo offset     : %s\n" % self.piezo.Get_Offset()
            _info_str += "piezo POS?       : %s\n" % self.piezo.Get_Pos()
            _info_str += "system factor    : %g\n" % self.system_factor
            _info_str += "bender factor    : %g\n" % self.bender_factor
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
        self._logger.info(
            "--PJ-- _do_move : motion: target_pos=%g  delta=%g "
            % (motion.target_pos, motion.delta)
        )

        bender_current = self.read_position(motion.axis)  # read from TNS

        tns_current = self.piezo.Get_TNS()

        # tns_target = tns_current + ( motion.delta / self.bender_factor )
        tns_target = motion.target_pos / self.bender_factor

        piezo_current = self.piezo.Get_Pos()
        piezo_target = self.calc_poly_value(tns_target, self.piezo.coeffs)

        self._logger.info(
            "--PJ--bender: current=%g  target=%g  "
            % (bender_current, motion.target_pos)
        )
        self._logger.info(
            "--PJ--TNS:    current=%g  target=%g" % (tns_current, tns_target)
        )
        self._logger.info(
            "--PJ--piezo:  current=%g  target=%g" % (piezo_current, piezo_target)
        )

        # At the first movement after a restart, the piezo might be way off.
        # If piezo position is outside range [-1;15] or if loop is open corrects it.
        # -1 : if Volts are 0, position may become -0.XX
        if (
            piezo_current <= -1
            or piezo_current >= self._PiezoSize.length
            or not self.piezo.Get_Closed_Loop_Status()
        ):
            # Opens the loop, so that the piezo won't break, but move
            # it to zero first and waits a bit to let time to piezo to
            # come back to 0. (to avoid clacs ?)
            self._logger.info(
                "--PJ--Piezo problem (C.Loop=%r) : Moves piezo to zero and opens the loop."
                % self.piezo.Get_Closed_Loop_Status()
            )
            self.piezo.Set_Closed_Loop(False)
            # GUILLOUD: do we really need to go to 0 ? this works whereever we are!
            # self.move_piezo_smooth(0)             # moves piezo to 0 Volt per Volt.

            # Changes piezo offset (i.e. 0 reference for capacitive sensor)
            # to compensate icepap movement. (in microns)
            # Offset is set considering that piezo position is 0.
            new_piezo_offset = self.piezo.Get_Offset() - self.piezo.Get_Pos()
            self.piezo.Put_Offset(new_piezo_offset)

            # Need to go to half-range so we can make small movements with piezo only.
            self._logger.info("--PJ--Moves piezo to 50 V (half-range)")
            self.move_piezo_smooth(self._PiezoSize.middle_voltage)

        self._logger.info("--PJ--ok, piezo pos is now in-range and loop is open.")
        self._logger.info(" ")

        piezo_current = self.piezo.Get_Pos()  # um
        piezo_target = self.calc_poly_value(tns_target, self.piezo.coeffs)

        self._logger.info(
            "--PJ--New positions should be: bender=%g tns=%g"
            % (motion.target_pos, tns_target)
        )
        self._logger.info(
            "--PJ--piezo_current=%g piezo_target=%g" % (piezo_current, piezo_target)
        )

        # Checks whether new position is OUTSIDE the piezo's range [2; 13].
        # ie : an icepap movement will be necessary
        if (piezo_target <= self._PiezoSize.low) or (
            piezo_target >= self._PiezoSize.high
        ):
            # #### ICEPAP MOVE #### #
            self._logger.info("--PJ--   ICEPAP MOVE")

            self._logger.info(
                "--PJ--piezo_target %g OUTSIDE range [%g;%g] => ICEPAP movement first"
                % (piezo_target, self._PiezoSize.low, self._PiezoSize.high)
            )

            ice_pos_before = self.icepap.position

            # Places piezo in middle range.
            # Done in open loop to avoid large damaging movements.
            self.piezo.Set_Closed_Loop(False)
            self._logger.info("--PJ--Moves piezo to 50 V (half-range)")
            self.move_piezo_smooth(self._PiezoSize.middle_voltage)

            # TNS values.
            tns_current = self.piezo.Get_TNS()
            tns_delta = tns_target - tns_current

            self._logger.info(
                "--PJ--TNS : current=%g target=%g delta=%g"
                % (tns_current, tns_target, tns_delta)
            )

            # - 3 um : to avoid backlash
            # - self._PiezoSize.middle : piezo should be in middle position.
            ice_delta = (
                (tns_delta * self.bender_factor) - self._PiezoSize.middle - 1
            )  # used to be 3, but
            # provoked unnecessary backlashes with movements of 10 um, where the new initial position was lower
            # than the previous one, i.e. ice_delta became negative.

            self._logger.info(
                "--PJ-ICEPAP-before icepap REL MOVE! ice_delta = %g----------"
                % (ice_delta)
            )
            self.icepap.rmove(ice_delta)
            self._logger.info(
                "--PJ--AFTER initial MOVE. Now moves ICEPAP to be closest possible to the TNS target."
            )
            self._logger.info("")

            for ii in range(self._icepap_retries):
                tns_current = self.piezo.Get_TNS()
                tns_delta = tns_target - tns_current
                self._logger.info(
                    "--PJ-ICEPAP--loop%d-- TNS target=%g current=%g delta= %g"
                    % (ii, tns_target, tns_current, tns_delta)
                )

                # tns_allowed_divergence devided by icepap_factor will be um.
                if abs(tns_delta) < self.tns_allowed_divergence:
                    break  # ok we are close enough

                # If overshoot : no icepap move to avoid backlash.
                # -> faire un movement plus petit que voulu ? pour ne pas depasser et donc pour eviter des backlash.
                # GUILLOUD: pas sure, comme nous allons jamais atteindre le but :-(
                ice_delta = tns_delta * self.bender_factor
                if ice_delta < 0:
                    self._logger.info(
                        "--PJ-icepap move negatif. tns_delta=%g" % tns_delta
                    )

                self._logger.info(
                    "--PJ-ICEPAP- REL MOVE! ice_delta = %g----------" % (ice_delta)
                )
                self.icepap.rmove(ice_delta)

            icepap_after = self.icepap.position
            self._logger.info(
                "--PJ- icepap after approach: %s, delta: %s"
                % (icepap_after, icepap_after - ice_pos_before)
            )

            # Changes piezo offset to compensate icepap movement. (in microns)
            # Piezo was set to middle position before ice movement.
            # And to make piezo controller able to regulate position in closed loop.
            new_piezo_offset = (
                self.piezo.Get_Offset() - self.piezo.Get_Pos() + self._PiezoSize.middle
            )
            self.piezo.Put_Offset(new_piezo_offset)
            self._logger.info(
                "--PJ- offset changed, close the loop and make final approach"
            )

            self.piezo.Set_Closed_Loop(True)

            # END OF ICEPAP MOVEMENT.
        else:
            self._logger.info("--PJ-- NO ICEPAP MOVE")

        # calculate the position to move the piezo to from the calculated TNS value,
        # using the polynomial values stored as "Senson Mech. Corrections 1 to 5.
        # Physik Instrumente manual Software Manual PZ231E, page 81
        #
        # this will lessen the work for the device server AND make the position surely
        # more precise, than an iterative approach.
        #
        # use value in variable tns_target
        #
        piezo_current = self.piezo.Get_Pos()
        piezo_target = self.calc_poly_value(tns_target, self.piezo.coeffs)

        self._logger.info(
            "--PJ--  piezo : current=%g target=%g" % (piezo_current, piezo_target)
        )

        if (piezo_target >= self._PiezoSize.low) and (
            piezo_target <= self._PiezoSize.high
        ):
            # #### PIEZO MOVE  #### #
            self._logger.info("--PJ-- PIEZO MOVE")

            self._logger.info(
                "--PJ--  piezo_target %g is in range [%g, %g] => piezo movement only"
                % (piezo_target, self._PiezoSize.low, self._PiezoSize.high)
            )

            self.piezo.Set_Closed_Loop(True)
            self.piezo.move(piezo_target)  # in um.

            tns_current = self.piezo.Get_TNS()
            tns_delta = tns_target - tns_current
            self._logger.info(
                "--PJ--after piezo move : TNS : current=%g  new=%g  delta=%g"
                % (tns_current, tns_target, tns_delta)
            )
            self._logger.info(
                "--PJ--New piezo position : %g (updated)" % self.piezo._position()
            )

            self._logger.info(
                "--PJ--new Bender pos set:%g read:%g",
                motion.axis._set_position,
                self.read_position(motion.axis),
            )

    def calc_poly_value(self, x, coeffs):
        y = 0
        for ii in range(
            5
        ):  # always go to fourth order, doesn't matter, some coefficients might be zero
            y = y + coeffs[ii] * pow(x, ii)
        return y

    @object_method(types_info=("None", "None"), name="sync")
    def sync(self, axis):
        # NB : a _position() is done by E712 when closing/opening the piezo loop.
        axis._position()
