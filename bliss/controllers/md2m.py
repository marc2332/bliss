# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Example yml file
class: MD2M
name: minidiff

wago: $wcid29cb
actuators: ["blight", "flight", "cryo", "fluodet"]
motors: {omega: $omega, phix: $phix, phiy: $phiy, phiz: $phiz,
         sampx: $sampx, sampy: $sampy, bstopy: $bstopy, bstopz: $bstopz,
         zoom: $zoom}
init_offsets: {omega: 0,  phix: -3.2, phiy: 6.183, phiz: -3.7,
               sampx: 3.693, sampy: -2.535}
zoom_positions:
  -
    offset: 1
    pixelsPerMmY: 301
    pixelsPerMmZ: 301
  -
    offset: 2
    pixelsPerMmY: 456
    pixelsPerMmZ: 456
  -
    offset: 3
    pixelsPerMmY: 720
    pixelsPerMmZ: 720
  -
    offset: 4
    pixelsPerMmY: 1150
    pixelsPerMmZ: 1150
  -
    offset: 5
    pixelsPerMmY: 1840
    pixelsPerMmZ: 1840
  -
    offset: 6
    pixelsPerMmY: 3040
    pixelsPerMmZ: 3040

beamviewer_server: "id29s/beamviewer/id29s_sample"
sample_video_server: "id29s/limaccd/id29s_sample"
fshut: $fshut
shutter_predelay: 56e-3
shutter_postdelay: 23e-3
acc_margin: 6000
musst: $musst
oscil_mprg: /users/blissadm/local/configuration/misc/oscillPX.mprg
musst_sampling: 80
diagfile: /users/blissadm/oscillation_diag.dat

"""

import datetime
import numpy
import math
import logging
import copy
import gevent

# from bliss.common.tango import DeviceProxy
from bliss.common.motor_group import Group
from bliss.common.task import task
from bliss.common.cleanup import cleanup, error_cleanup
from bliss.common.utils import grouped


class MD2M:
    """Minidiff
    """

    def __init__(self, name, config):
        print(name)
        self.beamviewer_server = str(config.get("beamviewer_server"))
        self.sample_video_server = str(config.get("sample_video_server"))
        # actuators
        self.actuators = {key: None for key in config.get("actuators", [])}
        self.wago = config.get("wago")
        # check the motors
        self.motors = config.get("motors", {})
        # musst
        self.musst = config.get("musst")
        if self.musst:
            self.musst_sampling = int(config.get("musst_sampling"))
        # fast shutter
        self.fshut = config.get("fshut")
        if self.fshut:
            self.shutter_predelay = float(config.get("shutter_predelay"))
            self.shutter_postdelay = float(config.get("shutter_postdelay"))

        self.diagfile = config.get("diagfile")
        self.diag_n = 0
        self.init_offsets = config.get("init_offsets")
        self.zoom_positions = config.get("zoom_positions")
        self.oscil_mprg = config.get("oscil_mprg")

    @task
    def _simultaneous_move(self, *args):
        """ Move simultaneously (absolute) specified motors to the
            requested positions
        Args:
            args (list): list of axis objects and absolute target values [mm].
        Raises:
            RuntimeError: Timeout
        """
        axis_list = []
        for axis, _ in grouped(args, 2):
            axis_list.append(axis)
        g_m = Group(*axis_list)
        g_m.move(*args)

    @task
    def _simultaneous_rmove(self, *args):
        """ Move simultaneously (relative) specified motors to the
            requested positions
        Args:
            args (list): list of axis pbjects and relative target values [mm].
        Raises:
            RuntimeError: Timeout
        """
        axis_list = []
        for axis, _ in grouped(args, 2):
            axis_list.append(axis)
        g_m = Group(*axis_list)
        g_m.rmove(*args)

    def _wait_ready(self, *axes, **kwargs):
        """ Wait until the status is ready
        Args:
            args (list): list of axis objects
        Kwargs:
            timeout (int): timeout [s]
        :type timeout: int
        """
        timeout = int(kwargs.get("timeout", 3))
        with gevent.Timeout(
            timeout, RuntimeError("Timeout waiting for motors to be READY")
        ):
            for axis in axes:
                axis.wait_move()

    def move_beamstop_out(self):
        """Beam stop away from beam
        """
        self.motors["bstopz"].move(-80)

    def move_beamstop_in(self):
        """Beam stop in the beam
        """
        print("Not implemented yet")

    def fshut_init(self):
        print("  Homing fast shutter")
        if self.musst:
            self.musst.putget("#ABORT")
        try:
            self.fshut.init()
        except BaseException:
            print("Non motorised shutter")
        print("  done.")

    def full_init(self):
        """Minidiff complete initialisation
        """
        # add sample changer check?
        print("Please wait while doing full initialisation of MD2M...")
        self.fshut_init()
        self.omega_init()
        self.translation_table_init()
        self.centring_table_init()
        self.zoom_init()
        self.kappa_init()

    def omega_init(self):
        """Initialise the omega axis
        """
        name = self.motors["omega"].name
        print("Homing omega (%s) axis" % name)
        self.motors["omega"].apply_config()
        self.motors["omega"].home()
        try:
            self.motors["omega"].dial(float(self.init_offsets["omega"]))
            self.motors["omega"].position(float(self.init_offsets["omega"]))
        except (TypeError, KeyError):
            print("%s position unchanged" % name)
        gevent.sleep(1)
        self.motors["omega"].move(0)
        if self.musst:
            self.musst.putget("#ABORT")  # in case a program is running
            self.musst.putget("#CH CH2 0")
        print("  done.")

    def kappa_init(self):
        """Initialise the mini kappa
        """
        print("Not implemented yet")

    def _reset_axes_settings(self, *axes):
        """Initialise the axes
        """
        for axis in axes:
            axis.apply_config()

    def translation_table_init(self):
        """Initialise the translation table
        """
        print("Doing translation table initialisation")
        table_axes = (self.motors["phix"], self.motors["phiy"], self.motors["phiz"])
        self._reset_axes_settings(*table_axes)
        print(
            "  Searching for phix, phiy and phiz negative limits\n",
            "  Setting init positions",
        )
        for axis in table_axes:
            axis.hw_limit(-1, wait=False)
            axis.wait_move()
            axis.dial(self.init_offsets[axis.name])
            axis.position(self.init_offsets[axis.name])
            axis.apply_config()
            # axis.limits()
        self._simultaneous_move(
            self.motors["phix"], 0, self.motors["phiy"], 0, self.motors["phiz"], 0
        )
        # set the holderlength position
        self.motors["phiy"].position(22)
        print("  done.")

    def centring_table_init(self):
        """Initialise the centring table
        """
        print("Doing centring table initialisation")
        table_axes = (self.motors["sampx"], self.motors["sampy"])
        self._reset_axes_settings(*table_axes)
        print(
            "  Searching for sampx and sampy positive limits\n",
            "  Setting init positions",
        )
        for axis in table_axes:
            axis.hw_limit(+1)
            axis.wait_move()
            axis.dial(self.init_offsets[axis.name])
            axis.position(self.init_offsets[axis.name])
            axis.apply_config()
        self._simultaneous_move(self.motors["sampx"], 0, self.motors["sampy"], 0)
        print("  done.")

    def zoom_init(self):
        """Initialise the zoom
        """
        print("Homing zoom axis")
        self.motors["zoom"].velocity(self.motors["zoom"].velocity(from_config=True))
        self.motors["zoom"].acceleration(
            self.motors["zoom"].acceleration(from_config=True)
        )
        print("  searching for zoom home switch")
        self.motors["zoom"].home()
        lim = len(self.zoom_positions) + 0.1
        self.motors["zoom"].position(lim)
        self.motors["zoom"].dial(lim)
        self.motors["zoom"].move(1)
        print("  done.")

    def _musst_oscil(self, enc1, enc2, esh1, esh2, trigger):
        delta = self.musst_sampling

        self.musst.putget("#VAR E1 %d" % enc1)
        self.musst.putget("#VAR E2 %d" % enc2)
        self.musst.putget("#VAR ESH1 %d" % esh1)
        self.musst.putget("#VAR ESH2 %d" % esh2)
        self.musst.putget("#VAR DE %d" % delta)
        self.musst.putget("#VAR DETTRIG %d" % trigger)
        self.musst.putget("#CH CH3 0")
        print(
            "\ne1=",
            enc1,
            "e2=",
            enc2,
            "esh1=",
            esh1,
            "esh2=",
            esh2,
            "delta=",
            delta,
            "trigger=",
            trigger,
        )

        self.musst.putget("#RUN OSCILLPX")

    def _musst_prepare(self, enc1, enc2, esh1, esh2, pixel_detector_trigger_steps):
        self.musst.putget("#ABORT")
        self.musst.putget("#CHCFG CH2 ENC ALIAS PHI")
        self.musst.putget("#CHCFG CH1 ENC ALIAS SHUTSTATE")
        oscil_program = open(self.oscil_mprg, "r")
        self.musst.upload_program(oscil_program.read())

        self._musst_oscil(enc1, enc2, esh1, esh2, pixel_detector_trigger_steps)

    def _helical_calc(self, helical_pos, exp_time):
        hpos = copy.deepcopy(helical_pos)
        start = hpos["1"]
        end = hpos["2"]
        logging.info("%r", hpos)

        # phiz has to move if chi==90 for example, phiy has to move if chi==0
        helical = {
            "phiy": {
                "trajectory": end.get("phiy", 0) - start.get("phiy", 0),
                "motor": self.motors["phiy"],
                "start": start.get("phiy"),
            },
            "sampx": {
                "trajectory": end["sampx"] - start["sampx"],
                "motor": self.motors["sampx"],
                "start": start.get("sampx"),
            },
            "sampy": {
                "trajectory": end["sampy"] - start["sampy"],
                "motor": self.motors["sampy"],
                "start": start.get("sampy"),
            },
        }
        for motor_name in helical:
            h_m = helical[motor_name]
            h_m["distance"] = abs(h_m["trajectory"])
            if h_m["distance"] <= 5E-3:
                del helical[motor_name]
                continue
            h_m["d"] = math.copysign(1, h_m["trajectory"])
            h_m["velocity"] = helical[motor_name]["distance"] / float(exp_time)

        return helical

    def helical_oscil(
        self,
        start_ang,
        stop_ang,
        helical_pos,
        exp_time,
        save_diagnostic=True,
        operate_shutter=True,
    ):
        """ Make a helical line scan
        Args:
            start_ang (float): start angle [deg]
            stop_ang (float): end angle [deg]
            helical_pos (dict): start and end helical positions
            exp_time (float): total exposure time [s]
            save_diagnostic (bool): save the diagnostic file
            operate_shutter(bool): open/close fast shutter
        Raises:
            RuntimeError: Wrong helical positions or exposure time
        """

        def oscil_cleanup(
            omega_v=self.motors["omega"].velocity(from_config=True),
            omega_a=self.motors["omega"].acceleration(from_config=True),
            phiy_v=self.motors["phiy"].velocity(from_config=True),
            phiy_a=self.motors["phiy"].acceleration(from_config=True),
            sampx_v=self.motors["sampx"].velocity(from_config=True),
            sampx_a=self.motors["sampx"].acceleration(from_config=True),
            sampy_v=self.motors["sampy"].velocity(from_config=True),
            sampy_a=self.motors["sampy"].acceleration(from_config=True),
        ):
            for motor_name in ("omega", "phiy", "sampx", "sampy"):
                getattr(self, motor_name).velocity(locals()[motor_name + "_v"])
                getattr(self, motor_name).acceleration(locals()[motor_name + "_a"])

        helical = self._helical_calc(helical_pos, exp_time)
        direction, calc_velocity, acc_time, acc_ang = self._oscil_calc(
            start_ang, stop_ang, exp_time
        )

        encoder_step_size = -self.motors["omega"].steps_per_unit
        pixel_detector_trigger_steps = encoder_step_size * start_ang
        shutter_predelay_steps = math.fabs(
            float(self.shutter_predelay * calc_velocity * encoder_step_size)
        )
        shutter_postdelay_steps = math.fabs(
            float(self.shutter_postdelay * calc_velocity * encoder_step_size)
        )
        omega_prep_time = self.shutter_predelay * float(calc_velocity)
        oscil_start = start_ang - direction * (
            acc_ang + shutter_predelay_steps / encoder_step_size
        )
        oscil_final = stop_ang + direction * acc_ang

        with cleanup(oscil_cleanup):
            self.fshut.close()

            moves = []
            for helical_info in helical.values():
                motor = helical_info["motor"]
                start = helical_info["start"]
                vel = helical_info["velocity"]
                direction = helical_info["d"]
                step_size = abs(motor.steps_per_unit)
                prep_distance = (vel * (omega_prep_time - (acc_time / 2.0))) / float(
                    step_size
                )
                deceleration_distance = ((acc_time * vel) / 2.0) / float(step_size)
                helical_info["distance"] += prep_distance + deceleration_distance
                moves += [motor, start - direction * prep_distance]

            self._simultaneous_move(self.motors["omega"], oscil_start, *moves)

            self.motors["omega"].velocity(calc_velocity)
            self.motors["omega"].acctime(acc_time)
            for helical_info in helical.values():
                vel = helical_info["velocity"]
                mot = helical_info["motor"]
                if vel > 0.4:
                    raise RuntimeError(
                        "Wrong parameter for helical, velocity is too high",
                        "hint: increase number of images or exposure time",
                        "reduce transmission.",
                    )
                mot.velocity(vel)
                mot.acctime(acc_time)

            enc1 = oscil_start * encoder_step_size + 5
            enc2 = oscil_final * encoder_step_size - 5
            esh1 = start_ang * encoder_step_size - direction * shutter_predelay_steps
            esh2 = stop_ang * encoder_step_size - direction * shutter_postdelay_steps

            if (esh1 < esh2 and esh1 < enc1) or (esh1 > esh2 and esh1 > enc1):
                raise RuntimeError("acc_margin too small")

            if operate_shutter and self.musst:
                self._musst_prepare(
                    enc1, enc2, esh1, esh2, pixel_detector_trigger_steps
                )

            moves = dict()
            for helical_info in helical.values():
                mot = helical_info["motor"]
                moves[mot] = (
                    mot.position() + helical_info["d"] * helical_info["distance"]
                )

            axes_group = Group(
                self.motors["phiy"], self.motors["sampx"], self.motors["sampy"]
            )

            def abort_all():
                self.motors["omega"].stop()
                axes_group.stop()
                if self.musst:
                    self.musst.putget("#ABORT")

            with error_cleanup(abort_all):
                self.motors["omega"].move(oscil_final, wait=False)
                axes_group.move(moves)
                self.motors["omega"].wait_move()

            if save_diagnostic:
                self.save_diagnostic()

    def _oscil_calc(self, start_ang, stop_ang, exp_time):
        abs_ang = math.fabs(stop_ang - start_ang)
        if stop_ang > start_ang:
            direction = 1
        else:
            raise RuntimeError("cannot do reverse oscillation")
        osctime = float(exp_time)
        # step_size = math.fabs(self.motors["omega"].steps_per_unit)
        calc_velocity = float(abs_ang) / osctime
        acc_time = 0.1
        acc_ang = (acc_time * calc_velocity) / 2
        return (direction, calc_velocity, acc_time, acc_ang)

    def oscil(
        self, start_ang, stop_ang, exp_time, save_diagnostic=True, operate_shutter=True
    ):
        """ Make an oscillation scan
        Args:
            start_ang (float): start angle [deg]
            stop_ang (float): end angle [deg]
            exp_time (float): total exposure time [s]
            save_diagnostic (bool): save the diagnostic file
            operate_shutter(bool): open/close fast shutter
        """
        direction, calc_velocity, acc_time, acc_ang = self._oscil_calc(
            start_ang, stop_ang, exp_time
        )

        def oscil_cleanup(
            vel=self.motors["omega"].velocity(from_config=True),
            acc=self.motors["omega"].acceleration(from_config=True),
        ):
            self.motors["omega"].velocity(vel)
            self.motors["omega"].acceleration(acc)

        with cleanup(oscil_cleanup):
            self.fshut.close()

            encoder_step_size = -self.motors["omega"].steps_per_unit
            pixel_detector_trigger_steps = encoder_step_size * start_ang
            shutter_predelay_steps = math.fabs(
                float(self.shutter_predelay * calc_velocity * encoder_step_size)
            )
            shutter_postdelay_steps = math.fabs(
                float(self.shutter_postdelay * calc_velocity * encoder_step_size)
            )
            oscil_start = start_ang - direction * (
                acc_ang + shutter_predelay_steps / encoder_step_size
            )
            oscil_final = stop_ang + direction * acc_ang

            self.motors["omega"].move(oscil_start)
            self.motors["omega"].velocity(calc_velocity)
            self.motors["omega"].acctime(acc_time)

            if operate_shutter and self.musst:
                enc1 = oscil_start * encoder_step_size + 5
                enc2 = oscil_final * encoder_step_size - 5
                # enc1 = start_ang*encoder_step_size - direction*(max_step_ang + 5)
                # enc2 = stop_ang*encoder_step_size + direction*(max_step_ang - 5)
                esh1 = (
                    start_ang * encoder_step_size - direction * shutter_predelay_steps
                )
                esh2 = (
                    stop_ang * encoder_step_size - direction * shutter_postdelay_steps
                )
                self._musst_prepare(
                    enc1, enc2, esh1, esh2, pixel_detector_trigger_steps
                )

            self.motors["omega"].move(oscil_final)

            if save_diagnostic:
                self.save_diagnostic()

    def _get_diagnostic(self):
        """ Read the diagnostic data from the musst
        """
        if not self.musst:
            return []
        npoints = int(self.musst.putget("?VAR NPOINTS"))
        nlines = npoints  # variable name should be changed in musst program
        diag_data = numpy.zeros((nlines, 9), dtype=numpy.float)
        data = self.musst.get_data(8)

        # first column contains time in microseconds,
        # convert it to milliseconds
        diag_data[:, 0] = data[:, 0] / 1000.0

        # velocity in
        #     v(i) = [ x(i) - x(i-1) ] /  [ t(i) - t(i-1) ]
        # then convert from steps/microsec into deg/sec
        step_size = math.fabs(self.motors["omega"].steps_per_unit)
        diag_data[1:, 1] = [
            xi - prev_xi for xi, prev_xi in zip(data[:, 2][1:], data[:, 2])
        ]
        diag_data[1:, 1] /= [
            float(ti - prev_ti) for ti, prev_ti in zip(data[:, 0][1:], data[:, 0])
        ]
        diag_data[:, 1] *= 1E6 / float(step_size)
        diag_data[0, 1] = diag_data[1, 1]

        # save pos in degrees
        diag_data[:, 2] = data[:, 2] / float(step_size)

        # I0 values
        # diag_data[:,3]=10*(data[:,4]/float(0x7FFFFFFF))
        # diag_data[:,3]=10*(data[:,5]/float(0x7FFFFFFF))
        diag_data[:, 3] = -data[:, 4] / 20000.0

        # I1 values
        # diag_data[:,4]=10*(data[:,5]/float(0x7FFFFFFF))
        diag_data[:, 4] = -10 * (data[:, 6] / float(0x7FFFFFFF))

        # shutter cmd (Btrig)
        # diag_data[:,5]=data[:,6]
        diag_data[:, 5] = data[:, 7]

        # shutter status
        diag_data[:, 6] = data[:, 1]  # & 0x0001)/0x0001

        # detector is acquiring status
        diag_data[:, 7] = data[:, 3]

        # save SAMP step
        diag_data[:, 8] = -data[:, 5] / 20000.0

        return diag_data

    @task
    def save_diagnostic(self):
        """Read the diagnostic data. Save in a file
        """
        diag_data = self._get_diagnostic()
        if diag_data is None:
            return
        self.diag_n += 1
        _, cols = diag_data.shape
        with open(self.diagfile, "a+") as diagfile:
            diagfile.write(
                "\n#S %d\n#D %s\n"
                % (
                    self.diag_n,
                    datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"),
                )
            )
            diagfile.write("#N %d\n" % cols)
            diagfile.write(
                "#L Time(ms)  Speed  Phi  PhiY  I1  Shut Cmd  Shut State  Detector Acquiring  PhiZ\n"
            )
            numpy.savetxt(diagfile, diag_data)
            diagfile.write("\n\n")

    def set_actuator(self, name, set_in, wait=True):
        """Move the actuator to position
        Args:
            name (str): The actuator name
            set_in (boot): True (in), False (out)
            wait (bool): Wait for the position to be reached
        Returns:
            (bool): Actuator position - True (in), False (out), None (unknown)
        """
        set_in = bool(set_in)
        self.wago.set("%s" % name, set_in)
        if wait:
            setin_name = "%s_is_in" % name if set_in else "%s_is_out" % name
            with gevent.Timeout(
                10,
                RuntimeError(
                    "%s %s switch is not activated" % (name, "in" if set_in else "out")
                ),
            ):
                while not self.wago.get(setin_name):
                    gevent.sleep(0.1)
        self.actuators[name] = set_in

    def get_actuator(self, name):
        """Get the actuator position
        Args:
            name (str): The actuator name
        Returns:
            (bool): Actuator position - True (in), False (out), None (unknown)
        """
        if self.wago.get("%s_is_in" % name):
            return True
        if self.wago.get("%s_is_out" % name):
            return False
        return None

    def lightin(self):
        """Move the back light in. Switch it on
        """
        self.set_actuator("blightoff", set_in=False, wait=False)
        self.set_actuator("blight", set_in=True, wait=True)

    def lightout(self):
        """Move the back light out. Switch it off
        """
        self.set_actuator("blightoff", set_in=True, wait=False)
        self.set_actuator("blight", set_in=False, wait=True)

    def light(self, state=None):
        """Move the back light
        Args:
            state (bool): True - in
                          False - out
        Returns:
            (bool): Back light is in/out
        """
        if state is not None:
            if state:
                self.lightin()
            else:
                self.lightout()
        return self.actuators["blight"]

    def cryoin(self):
        """Move the cryostream close to the sample
        """
        self.set_actuator("cryo", set_in=True, wait=True)

    def cryoout(self):
        """Move the cryostream away from the sample
        """
        self.set_actuator("cryo", set_in=False, wait=True)

    def cryo(self, state=None):
        """Move the cryostream
        Args:
            state (bool): True - close to the sample
                          False - away from the sample
        Returns:
            (bool): Cryostream is close to/away from
        """
        if state is not None:
            if state:
                self.cryoin()
            else:
                self.cryoout()
        return self.actuators["cryo"]

    def fluodetin(self):
        """Move the flourescent detector close to the beam
        """
        self.set_actuator("fluodet", set_in=True, wait=True)

    def fluodetout(self):
        """Move the flourescent detector away the beam
        """
        self.set_actuator("fluodet", set_in=False, wait=True)

    def fluodet(self, state=None):
        """Move the flourescent detector
        Args:
            state (bool): True - close to the beam
                          False - away from the beam
        Returns:
            (bool): Fluorescent detector is close to/away from
        """
        if state is not None:
            if state:
                self.fluodetin()
            else:
                self.fluodetout()
        return self.actuators["fluodet"]
