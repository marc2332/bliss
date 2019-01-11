# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import datetime
import time
import numpy
import math
import os
import logging
from bliss.common.tango import DeviceProxy
from bliss.common.scans import *
from bliss.common.motor_group import Group
from bliss.common.task import task
from bliss.common.cleanup import cleanup, error_cleanup
from bliss.common.utils import grouped
import copy


class MD2M:
    def __init__(self, name, config):
        self.beamviewer_server = str(config.get("beamviewer_server"))
        self.sample_video_server = str(config.get("sample_video_server"))
        self.shutter_predelay = float(config.get("shutter_predelay"))
        self.shutter_postdelay = float(config.get("shutter_postdelay"))
        self.musst_sampling = int(config.get("musst_sampling"))
        self.diagfile = config.get("diagfile")
        self.diag_n = 0
        self.init_offsets = dict()
        for motor_name, value in config.get("init_offsets").items():
            self.init_offsets[motor_name] = float(value)
        self.zoom_positions = config.get("zoom_positions")
        self.oscil_mprg = config.get("oscil_mprg")
        self.members_state = {"light": None, "cryo": None, "fluodet": None}

    @task
    def _simultaneous_move(self, *args):
        axis_list = []
        for axis, target in grouped(args, 2):
            axis_list.append(axis)
        g = Group(*axis_list)
        g.move(*args)

    @task
    def _simultaneous_rmove(self, *args):
        axis_list = []
        targets = []
        for axis, target in grouped(args, 2):
            axis_list.append(axis)
            targets.append(axis.position + target)
        g = Group(*axis_list)
        g.move(dict(list(zip(axis_list, targets))))

    def _wait_ready(self, *axes, **kwargs):
        timeout = int(kwargs.get("timeout", 3))
        with gevent.Timeout(
            timeout, RuntimeError("Timed out waiting for motors to be READY")
        ):
            for axis in axes:
                axis.wait_move()

    def move_beamstop_out(self):
        self.bstopz.move(-80)

    def move_beamstop_in(self):
        pass

    def full_init(self):
        # add sample changer check?
        print("Please wait while doing full initialization of MD2M...")
        print("Homing fast shutter")
        self.musst.putget("#ABORT")
        self.fshut.home()
        print("  done.")
        self.omega_init()
        self.translation_table_init()
        self.centring_table_init()
        self.zoom_init()
        self.kappa_init()

    def omega_init(self):
        print("Homing omega axis")
        self.omega.apply_config()
        self.omega.home()
        self.omega.dial = float(self.init_offsets["omega"])
        self.omega.position = float(self.init_offsets["omega"])
        time.sleep(1)
        self.musst.putget("#ABORT")  # in case a program is running
        self.omega.move(0)
        self.musst.putget("#CH CH2 0")
        print("  done.")

    def kappa_init(self):
        pass

    def _reset_axes_settings(self, *axes):
        for axis in axes:
            axis.apply_config()

    def translation_table_init(self):
        print("Doing translation table init.")
        table_axes = (self.phix, self.phiy, self.phiz)
        self._reset_axes_settings(*table_axes)
        print(
            "  searching for phix, phiy and phiz negative limits, and setting init pos."
        )
        [axis.hw_limit(-1, wait=False) for axis in table_axes]
        [axis.wait_move() for axis in table_axes]
        for axis in table_axes:
            axis.dial = self.init_offsets[axis.name]
            axis.position = self.init_offsets[axis.name]
        [axis.apply_config() for axis in table_axes]
        # [axis.limits for axis in table_axes]
        self._simultaneous_move(self.phix, 0, self.phiy, 0, self.phiz, 0)
        self.phiy.position = 22
        print("  done.")

    def centring_table_init(self):
        print("Doing centring table init.")
        table_axes = (self.sampx, self.sampy)
        self._reset_axes_settings(*table_axes)
        print("  searching for sampx and sampy positive limits, and setting init pos.")
        [axis.hw_limit(+1) for axis in table_axes]
        [axis.wait_move() for axis in table_axes]
        for axis in table_axes:
            axis.dial = self.init_offsets[axis.name]
            axis.position = self.init_offsets[axis.name]
        [axis.apply_config() for axis in table_axes]
        self._simultaneous_move(self.sampx, 0, self.sampy, 0)
        print("  done.")

    def zoom_init(self):
        print("Homing zoom axis")
        self.zoom.velocity = self.zoom.config_velocity
        self.zoom.acceleration = self.zoom.config_acceleration
        print("  searching for zoom home switch")
        self.zoom.home()
        self.zoom.dial = 6.1
        self.zoom.position = 6.1
        self.zoom.move(1)
        print("  done.")

    def _musst_oscil(self, e1, e2, esh1, esh2, trigger):
        delta = self.musst_sampling

        self.musst.putget("#VAR E1 %d" % e1)
        self.musst.putget("#VAR E2 %d" % e2)
        self.musst.putget("#VAR ESH1 %d" % esh1)
        self.musst.putget("#VAR ESH2 %d" % esh2)
        self.musst.putget("#VAR DE %d" % delta)
        self.musst.putget("#VAR DETTRIG %d" % trigger)
        self.musst.putget("#CH CH3 0")
        print(
            "\ne1=",
            e1,
            "e2=",
            e2,
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

    def _musst_prepare(self, e1, e2, esh1, esh2, pixel_detector_trigger_steps):
        self.musst.putget("#ABORT")
        self.musst.putget("#CHCFG CH2 ENC ALIAS PHI")
        self.musst.putget("#CHCFG CH1 ENC ALIAS SHUTSTATE")
        oscil_program = open(self.oscil_mprg, "r")
        self.musst.upload_program(oscil_program.read())

        self._musst_oscil(e1, e2, esh1, esh2, pixel_detector_trigger_steps)

    def _helical_calc(self, helical_pos, exp_time):
        hp = copy.deepcopy(helical_pos)
        start = hp["1"]
        end = hp["2"]
        logging.info("%r", hp)

        # phiz has to move if chi==90 for example, phiy has to move if chi==0
        helical = {
            "phiy": {
                "trajectory": end.get("phiy", 0) - start.get("phiy", 0),
                "motor": self.phiy,
                "start": start.get("phiy"),
            },
            "sampx": {
                "trajectory": end["sampx"] - start["sampx"],
                "motor": self.sampx,
                "start": start.get("sampx"),
            },
            "sampy": {
                "trajectory": end["sampy"] - start["sampy"],
                "motor": self.sampy,
                "start": start.get("sampy"),
            },
        }
        for motor_name in list(helical.keys()):
            hm = helical[motor_name]
            hm["distance"] = abs(hm["trajectory"])
            if hm["distance"] <= 5E-3:
                del helical[motor_name]
                continue
            hm["d"] = math.copysign(1, hm["trajectory"])
            hm["velocity"] = helical[motor_name]["distance"] / float(exp_time)

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
        def oscil_cleanup(
            omega_v=self.omega.config_velocity,
            omega_a=self.omega.config_acceleration,
            phiy_v=self.phiy.config_velocity,
            phiy_a=self.phiy.config_acceleration,
            sampx_v=self.sampx.config_velocity,
            sampx_a=self.sampx.config_acceleration,
            sampy_v=self.sampy.config_velocity,
            sampy_a=self.sampy.config_acceleration,
        ):
            for motor_name in ("omega", "phiy", "sampx", "sampy"):
                getattr(self, motor_name).velocity = locals([motor_name + "_v"])
                getattr(self, motor_name).acceleration = locals([motor_name + "_a"])

        helical = self._helical_calc(helical_pos, exp_time)
        d, calc_velocity, acc_time, acc_ang = self._oscil_calc(
            start_ang, stop_ang, exp_time
        )

        encoder_step_size = -self.omega.steps_per_unit
        pixel_detector_trigger_steps = encoder_step_size * start_ang
        shutter_predelay_steps = math.fabs(
            float(self.shutter_predelay * calc_velocity * encoder_step_size)
        )
        shutter_postdelay_steps = math.fabs(
            float(self.shutter_postdelay * calc_velocity * encoder_step_size)
        )
        omega_prep_time = self.shutter_predelay * float(calc_velocity)
        oscil_start = start_ang - d * (
            acc_ang + shutter_predelay_steps / encoder_step_size
        )
        oscil_final = stop_ang + d * acc_ang

        with cleanup(oscil_cleanup):
            self.fshut.close()

            moves = []
            for motor_name, helical_info in helical.items():
                motor = helical_info["motor"]
                start = helical_info["start"]
                v = helical_info["velocity"]
                dd = helical_info["d"]
                step_size = abs(motor.steps_per_unit)
                prep_distance = (v * (omega_prep_time - (acc_time / 2.0))) / float(
                    step_size
                )
                deceleration_distance = ((acc_time * v) / 2.0) / float(step_size)
                helical_info["distance"] += prep_distance + deceleration_distance
                # logging.info("relative move for motor %s of: %f, prep_dist=%f", motor_name, start-motor.position-dd*prep_distance, dd*prep_distance)
                moves += [motor, start - dd * prep_distance]

            self._simultaneous_move(self.omega, oscil_start, *moves)

            self.omega.velocity = calc_velocity
            self.omega.acctime = acc_time
            for motor_name, helical_info in helical.items():
                v = helical_info["velocity"]
                m = helical_info["motor"]
                if v > 0:
                    # print 'setting velocity and acctime for motor %s to:' % motor_name, v, acc_time
                    if v > 0.4:
                        raise RuntimeError(
                            "Wrong parameter for helical, velocity is too high; hint: increase number of images or exposure time and reduce transmission."
                        )
                    m.velocity = v
                    m.acctime = acc_time

            e1 = oscil_start * encoder_step_size + 5
            e2 = oscil_final * encoder_step_size - 5
            esh1 = start_ang * encoder_step_size - d * shutter_predelay_steps
            esh2 = stop_ang * encoder_step_size - d * shutter_postdelay_steps

            if (esh1 < esh2 and esh1 < e1) or (esh1 > esh2 and esh1 > e1):
                raise RuntimeError("acc_margin too small")

            if operate_shutter:
                self._musst_prepare(e1, e2, esh1, esh2, pixel_detector_trigger_steps)

            moves = dict()
            for motor_name, helical_info in helical.items():
                m = helical_info["motor"]
                moves[m] = m.position + helical_info["d"] * helical_info["distance"]

            axes_group = Group(self.phiy, self.sampx, self.sampy)

            def abort_all():
                self.omega.stop()
                axes_group.stop()
                self.musst.putget("#ABORT")

            with error_cleanup(abort_all):
                self.omega.move(oscil_final, wait=False)
                axes_group.move(moves)
                self.omega.wait_move()

            if save_diagnostic:
                self.save_diagnostic(wait=False)

    def _oscil_calc(self, start_ang, stop_ang, exp_time):
        abs_ang = math.fabs(stop_ang - start_ang)
        if stop_ang > start_ang:
            d = 1
        else:
            raise RuntimeError("cannot do reverse oscillation")
        osctime = float(exp_time)
        step_size = math.fabs(self.omega.steps_per_unit)
        calc_velocity = float(abs_ang) / osctime
        acc_time = 0.1
        acc_ang = (acc_time * calc_velocity) / 2
        return (
            d,
            calc_velocity,
            acc_time,
            acc_ang,
        )  # oscil_start, oscil_final, calc_velocity, acc_time, acc_ang

    def oscil(
        self,
        start_ang,
        stop_ang,
        exp_time,
        save_diagnostic=True,
        operate_shutter=True,
        helical=False,
    ):
        d, calc_velocity, acc_time, acc_ang = self._oscil_calc(
            start_ang, stop_ang, exp_time
        )

        def oscil_cleanup(
            v=self.omega.config_velocity, a=self.omega.config_acceleration
        ):
            self.omega.velocity = v
            self.omega.acceleration = a

        with cleanup(oscil_cleanup):
            self.fshut.close()

            encoder_step_size = -self.omega.steps_per_unit
            pixel_detector_trigger_steps = encoder_step_size * start_ang
            shutter_predelay_steps = math.fabs(
                float(self.shutter_predelay * calc_velocity * encoder_step_size)
            )
            shutter_postdelay_steps = math.fabs(
                float(self.shutter_postdelay * calc_velocity * encoder_step_size)
            )
            # max_step_ang = max(encoder_step_size * acc_ang + self.acc_margin, shutter_predelay_steps)
            # max_step_ang = max(encoder_step_size * acc_ang, shutter_predelay_steps)
            # max_ang = max_step_ang / encoder_step_size
            oscil_start = start_ang - d * (
                acc_ang + shutter_predelay_steps / encoder_step_size
            )
            oscil_final = stop_ang + d * acc_ang
            # oscil_start = start_ang - d*(max_ang + self.acc_margin/encoder_step_size)
            # oscil_final = stop_ang + d*(max_ang + self.acc_margin/encoder_step_size)

            self.omega.move(oscil_start)
            self.omega.velocity = calc_velocity
            self.omega.acctime = acc_time

            # phi_encoder_pos = self.omega.position*encoder_step_size

            e1 = oscil_start * encoder_step_size + 5
            e2 = oscil_final * encoder_step_size - 5
            # e1 = start_ang*encoder_step_size - d*(max_step_ang + 5)
            # e2 = stop_ang*encoder_step_size + d*(max_step_ang - 5)
            esh1 = start_ang * encoder_step_size - d * shutter_predelay_steps
            esh2 = stop_ang * encoder_step_size - d * shutter_postdelay_steps

            if operate_shutter:
                self._musst_prepare(e1, e2, esh1, esh2, pixel_detector_trigger_steps)

            self.omega.move(oscil_final)

            if save_diagnostic:
                self.save_diagnostic(wait=False)

    def _get_diagnostic(self, phi_encoder_pos):
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
        step_size = math.fabs(self.omega.steps_per_unit)
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
    def save_diagnostic(self, phi_encoder_pos=0):
        diag_data = self._get_diagnostic(phi_encoder_pos)
        self.diag_n += 1
        rows, cols = diag_data.shape
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

    def _set_light(self, set_in):
        set_in = bool(set_in)
        self.wago.set("lightoff", not set_in)
        self.wago.set("lightin", set_in)
        with gevent.Timeout(
            3,
            RuntimeError(
                "Light %s switch is not activated" % ("in" if set_in else "out")
            ),
        ):
            while not self.wago.get("light_is_in" if set_in else "light_is_out"):
                time.sleep(0.1)
            self.members_state["light"] = set_in

    def _get_light(self):
        if self.wago.get("light_is_in"):
            return True
        if self.wago.get("light_is_out"):
            return False
        return None

    def light(self, state=None):
        if state is not None:
            self._set_light(state)
        else:
            return self.members_state["light"]

    def lightin(self):
        return self._set_light(True)

    def lightout(self):
        return self._set_light(False)

    def _set_cryo(self, set_in):
        set_in = bool(set_in)
        self.wago.set("cryoin", set_in)
        with gevent.Timeout(
            3,
            RuntimeError(
                "Cryo %s switch is not activated" % ("in" if set_in else "out")
            ),
        ):
            while not self.wago.get("cryoin" if set_in else "cryobck"):
                time.sleep(0.1)
            self.members_state["cryo"] = set_in

    def cryo(self, state=None):
        if state is not None:
            self._set_cryo(state)
        else:
            return self.members_state["cryo"]

    def cryoin(self):
        return self._set_cryo(True)

    def cryoout(self):
        return self._set_cryo(False)

    def fluodet(self, state=None):
        if state is not None:
            self._set_fluodet(state)
        else:
            return self.members_state["fluodet"]

    def _set_fluodet(self, set_in):
        set_in = bool(set_in)
        self.wago.set("fldin", set_in)
        with gevent.Timeout(
            3,
            RuntimeError(
                "Fluorescense detector %s switch is not activated"
                % ("in" if set_in else "out")
            ),
        ):
            while self.wago.get("fldbck") is not set_in:
                time.sleep(0.1)
            self.members_state["fluodet"] = set_in

    def centrebeam(self):
        self.lightout()
        self._simultaneous_move(self.bstopz, -80)
        self.detcover.set_in()
        self.fshut.open()
        self.i1.autorange(True)

        diode_values = []

        def restore_att(old_transmission=self.transmission.get()):
            self.transmission.set(old_transmission)

        with error_cleanup(restore_att, self.fshut.close):
            for t in (1, 10, 100):
                self.transmission.set(t)
                diode_values.append(self.i1.read())

            if (diode_values[1] / diode_values[0]) <= 12 and (
                diode_values[1] / diode_values[0]
            ) >= 8:
                if (diode_values[2] / diode_values[1]) <= 12 and (
                    diode_values[2] / diode_values[1]
                ) >= 8:
                    pass
                else:
                    raise RuntimeError("Wrong intensity, hint: is there beam?")
            else:
                raise RuntimeError("Wrong intensity, hint: is there beam?")

        def restore_slits(
            saved_pos=(self.hgap, self.hgap.position, self.vgap, self.vgap.position)
        ):
            print("restoring slits to saved positions", saved_pos)
            self._simultaneous_move(*saved_pos)

        self.bv_device = DeviceProxy(self.beamviewer_server)
        self.sample_video_device = DeviceProxy(self.sample_video_server)

        def restore_live():
            self.sample_video_device.video_live = True

        img_width = self.sample_video_device.image_width
        img_height = self.sample_video_device.image_height
        # look for pixels per mm calibration data, depending on zoom level
        zoom_pos = self.zoom.position
        for pos in self.zoom_positions:
            if abs(float(pos.get("offset")) - zoom_pos) < 0.001:
                px_mm_y, px_mm_z = (
                    float(pos.get("pixelsPerMmY")) or 0,
                    float(pos.get("pixelsPerMmZ")) or 0,
                )
                break
        else:
            raise RuntimeError("Could not get pixels/mm calibration")

        def restore_table(
            saved_pos=(
                self.tz1,
                self.tz1.position,
                self.tz2,
                self.tz2.position,
                self.tz3,
                self.tz3.position,
                self.ttrans,
                self.ttrans.position,
            )
        ):
            print("restoring table to saved positions", saved_pos)
            self._simultaneous_move(*saved_pos)

        def do_centrebeam():
            with cleanup(restore_live):
                self.sample_video_device.video_live = False
                res = self.bv_device.GetPosition()

            by = res[2]
            bz = res[3]
            if -1 in (by, bz):
                raise RuntimeError("Could not find beam")

            dy = (by - (img_width / 2)) / px_mm_y
            dz = (bz - (img_height / 2)) / px_mm_z
            if abs(dy) > 0.1 or abs(dz) > 0.1:
                raise RuntimeError("Aborting centrebeam, displacement is too much")

            with error_cleanup(restore_table):
                print("moving ttrans by", -dy)
                print("moving tz1,tz2,tz3 by", -dz)
                self._simultaneous_rmove(
                    self.ttrans, -dy, self.tz1, -dz, self.tz2, -dz, self.tz3, -dz
                )
            return dy, dz

        with cleanup(restore_slits, restore_att, self.fshut.close):
            self.transmission.set(0.5)
            self.detcover.set_in()
            self.move_beamstop_out()
            self.fshut.open()
            self._simultaneous_move(self.hgap, 2, self.vgap, 2)

            for i in range(5):
                dy, dz = do_centrebeam()
                if abs(dy) < 0.001 and abs(dz) < 0.001:
                    break

    def move_to_sample_loading_position(self, holder_length=22):
        move_task = self._simultaneous_move(
            self.phix,
            1.25,
            self.phiy,
            22,
            self.phiz,
            0,
            self.sampx,
            0,
            self.sampy,
            0,
            self.omega,
            0,
            self.zoom,
            1,
            wait=False,
        )
        self.wago.set("swpermit", 0)
        self.wago.set("SCcryoctrl", 0)
        self.wago.set("fldin", 0)
        self.wago.set("scntin", 0)
        self.wago.set("laserin", 0)
        self.wago.set("cryosh", 0)
        self.move_beamstop_out()
        self.lightout()
        self.wago.set("swpermit", 1)
        self.wago.set("SCcryoctrl", 1)
        move_task.get()

        if not self.wago.get("mdpermit"):
            raise RuntimeError("Sample changer: transfer refused")

    def prepare_centring(self):
        self.wago.set("swpermit", 0)
        move_task = self._simultaneous_move(
            self.bstopz,
            -80,
            self.phix,
            0.0,
            self.phiy,
            22,
            self.phiz,
            0,
            self.sampx,
            0,
            self.sampy,
            0,
            self.omega,
            0,
            self.zoom,
            1,
            wait=False,
        )
        try:
            self.lightin()
            self.wago.set("lightctrl", 0.3)
        finally:
            move_task.get()

    def quick_realign(self):
        self.centrebeam()
        self.i1.autorange(True)

        def restore(
            old_transmission=self.transmission.get(),
            old_slits=(self.hgap, self.hgap.position, self.vgap, self.vgap.position),
        ):
            self.transmission.set(old_transmission)
            self._simultaneous_move(*old_slits)
            self.fshut.close()

        with cleanup(restore):
            self._simultaneous_move(self.hgap, 1.6, self.vgap, 0.2)
            self.move_beamstop_in()
            self.transmission.set(10)

            dscan(self.vtrans, -0.2 * 1.5, 0.2 * 1.5, 20, 0, self.i1)
            a = last_scan_data()
            vtrans_max = a[numpy.argmax(a[:, 1]), 0]
            print("moving vert. trans to", vtrans_max)
            self.vtrans.move(vtrans_max)

            dscan(self.htrans, -1.6 * 1.5, 1.6 * 1.5, 20, 0, self.i1)
            a = last_scan_data()
            htrans_max = a[numpy.argmax(a[:, 1]), 0]
            print("moving hor. trans to", htrans_max)
            self.htrans.move(htrans_max)
