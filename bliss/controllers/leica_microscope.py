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
from bliss.common.cleanup import cleanup
from bliss.common.utils import grouped
import copy


class LeicaMicroscope:
    def __init__(self, name, config):
        self.shutter_predelay = float(config.get("shutter_predelay"))
        self.shutter_postdelay = float(config.get("shutter_postdelay"))
        self.musst_sampling = int(config.get("musst_sampling"))
        self.diagfile = config.get("diagfile")
        self.diag_n = 0
        init_offsets = config.get("init_offsets")
        if init_offsets:
            self.init_offsets = dict()
            for motor_name, value in init_offsets.items():
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

    def phi_init(self):
        print("Homing phi axis")
        self.phi.home()
        self.phi.dial = float(self.init_offsets["phi"])
        self.phi.position = float(self.init_offsets["phi"])
        time.sleep(1)
        self.musst.putget("#ABORT")  # in case a program is running
        self.phi.move(0)
        self.musst.putget("#CH CH2 0")
        print("  done.")

    def kappa_init(self):
        pass

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

    def _oscil_calc(self, start_ang, stop_ang, exp_time):
        abs_ang = math.fabs(stop_ang - start_ang)
        if stop_ang > start_ang:
            d = 1
        else:
            raise RuntimeError("cannot do reverse oscillation")
        osctime = float(exp_time)
        step_size = math.fabs(self.phi.steps_per_unit)
        calc_velocity = float(abs_ang) / osctime
        acc_time = 0.1
        acc_ang = (acc_time * calc_velocity) / 2
        return (
            d,
            calc_velocity,
            acc_time,
            acc_ang,
        )  # oscil_start, oscil_final, calc_velocity, acc_time, acc_ang

    def oscil_prepare(
        self,
        start_ang,
        stop_ang,
        exp_time,
        save_diagnostic=False,
        operate_shutter=False,
    ):
        d, calc_velocity, acc_time, acc_ang = self._oscil_calc(
            start_ang, stop_ang, exp_time
        )

        def oscil_cleanup(v=self.phi.config_velocity, a=self.phi.config_acceleration):
            self.phi.velocity = v
            self.phi.acceleration = a

        with cleanup(oscil_cleanup):
            encoder_step_size = self.phi.steps_per_unit
            pixel_detector_trigger_steps = encoder_step_size * start_ang
            shutter_predelay_steps = math.fabs(
                float(self.shutter_predelay * calc_velocity * encoder_step_size)
            )
            shutter_postdelay_steps = math.fabs(
                float(self.shutter_postdelay * calc_velocity * encoder_step_size)
            )
            oscil_start = start_ang - d * (
                acc_ang + shutter_predelay_steps / encoder_step_size
            )
            oscil_final = stop_ang + d * acc_ang

            self.phi.move(oscil_start)
            self.phi.velocity = calc_velocity
            self.phi.acctime = acc_time

            if operate_shutter:
                e1 = oscil_start * encoder_step_size + 5
                e2 = oscil_final * encoder_step_size - 5
                esh1 = start_ang * encoder_step_size - d * shutter_predelay_steps
                esh2 = stop_ang * encoder_step_size - d * shutter_postdelay_steps

                self._musst_prepare(e1, e2, esh1, esh2, pixel_detector_trigger_steps)
            return oscil_final

    def oscil(
        self,
        start_ang,
        stop_ang,
        exp_time,
        save_diagnostic=False,
        operate_shutter=False,
    ):
        d, calc_velocity, acc_time, acc_ang = self._oscil_calc(
            start_ang, stop_ang, exp_time
        )

        def oscil_cleanup(v=self.phi.config_velocity, a=self.phi.config_acceleration):
            self.phi.velocity = v
            self.phi.acceleration = a

        with cleanup(oscil_cleanup):
            # self.fshut.close()

            # encoder_step_size = -self.phi.steps_per_unit
            encoder_step_size = self.phi.steps_per_unit
            pixel_detector_trigger_steps = encoder_step_size * start_ang
            shutter_predelay_steps = math.fabs(
                float(self.shutter_predelay * calc_velocity * encoder_step_size)
            )
            shutter_postdelay_steps = math.fabs(
                float(self.shutter_postdelay * calc_velocity * encoder_step_size)
            )
            oscil_start = start_ang - d * (
                acc_ang + shutter_predelay_steps / encoder_step_size
            )
            oscil_final = stop_ang + d * acc_ang

            self.phi.move(oscil_start)
            self.phi.velocity = calc_velocity
            self.phi.acctime = acc_time

            if operate_shutter:
                e1 = oscil_start * encoder_step_size + 5
                e2 = oscil_final * encoder_step_size - 5
                esh1 = start_ang * encoder_step_size - d * shutter_predelay_steps
                esh2 = stop_ang * encoder_step_size - d * shutter_postdelay_steps

                self._musst_prepare(e1, e2, esh1, esh2, pixel_detector_trigger_steps)

            self.phi.move(oscil_final)

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
        step_size = math.fabs(self.phi.steps_per_unit)
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
