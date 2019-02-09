# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import math
import numpy

try:
    # this is used only for the b-spline
    from scipy import interpolate
except ImportError:
    interpolate = None


def find_pvt(pvt, position):
    """
    This function return all matching pvt (position velocity time)
    which intersect the asked **position**
    """
    positions = pvt["position"]
    time = pvt["time"]
    velocities = pvt["velocity"]
    matched_pvt = list()
    match_position = numpy.array([0, 0, position])
    for (
        start_time,
        end_time,
        start_position,
        end_position,
        start_velocity,
        end_velocity,
    ) in zip(time, time[1:], positions, positions[1:], velocities, velocities[1:]):
        # segment match
        if (
            start_position <= end_position and start_position <= position < end_position
        ) or (
            start_position > end_position and end_position < position <= start_position
        ):
            if position == start_position:
                matched_pvt.append((start_position, start_velocity, start_time))
            elif position == end_position:
                matched_pvt.append((end_position, end_velocity, end_time))
            else:
                dt = end_time - start_time
                dv = end_velocity - start_velocity
                acceleration = dv / dt
                # position = (acceleration/2)* t**2 + velocity*t + position_0
                if acceleration >= 0.0:
                    a = (
                        acceleration / 2.0
                        if end_position > start_position
                        else -acceleration / 2.0
                    )
                    position_equ = numpy.array([a, start_velocity, start_position])
                    matched_times = numpy.roots(position_equ - match_position)
                    t = abs(
                        matched_times[abs(matched_times) <= (end_time - start_time)][0]
                    )
                    p = numpy.polyval(position_equ, t)
                    v = start_velocity + acceleration * t
                    t += start_time
                else:
                    a = (
                        acceleration / 2.0
                        if end_position > start_position
                        else -acceleration / 2.0
                    )
                    position_equ = numpy.array([a, start_velocity, end_position])
                    matched_times = numpy.roots(position_equ - match_position)
                    t = abs(
                        matched_times[abs(matched_times) <= (end_time - start_time)][0]
                    )
                    p = numpy.polyval(position_equ, t)
                    t = (end_time - start_time) - t
                    v = start_velocity + acceleration * t
                    t += start_time
                matched_pvt.append((p, v, t))
    return numpy.array(
        matched_pvt, dtype=[("position", "f8"), ("velocity", "f8"), ("time", "f8")]
    )


class PointTrajectory(object):
    """
    class helper to build trajectories.
    """

    def __init__(self):
        self._time = None
        self._positions = dict()
        self._velocity = dict()
        self._acceleration = dict()

    def build(self, time_array, positions, spline_nb_points=0):
        """
        Build trajectory from given positions and time.
        
        This will create the velocity and acceleration array
        according to the positions given.
        if spline_nb_points > 0 the function will use a b-spline
        to interpolate.
        
        Args:
            time_array : is a list or numpy array of the time of each points.
            positions : is a dictionary where the key is a name and the
                        value is a numpy array or a list of values.
        """
        ys = [numpy.array(y) for y in positions.values()]
        xs = [numpy.array(time_array)]
        xs.extend(ys)

        if spline_nb_points > 0:
            tck, _ = interpolate.splprep(xs, k=3, s=0)
            u = numpy.linspace(0, 1, spline_nb_points, endpoint=True)
            out = interpolate.splev(u, tck)
        else:
            out = xs

        self._time = out[0]

        self._positions = dict()
        self._velocity = dict()
        self._acceleration = dict()
        for name, values in zip(positions.keys(), out[1:]):
            self._positions[name] = values
            velocity = numpy.gradient(values, self._time)
            self._acceleration[name] = numpy.gradient(velocity, self._time)
            self._velocity[name] = velocity

    @property
    def max_velocity(self):
        """
        Return the maximum velocity.
        """
        max_vel = dict()
        for name, velocities in self._velocity.items():
            max_vel[name] = numpy.absolute(velocities).max()
        return max_vel

    @property
    def max_acceleration(self):
        """
        Return the maximum acceleration.
        """
        max_acc = dict()
        for name, accelerations in self._acceleration.items():
            max_acc[name] = numpy.absolute(accelerations).max()
        return max_acc

    @property
    def limits(self):
        """
        Return the min and max position for this movement.
        Can be easily compared with the motor limits
        """
        limits = dict()
        for name, positions in self._positions.items():
            limits[name] = (positions.min(), positions.max())
        return limits

    def pvt(self, acceleration_start_end=None):
        """
        Get PVT vectors into named dictionary.

        Each vectors is a numpy struct with 3 columns ('time','position','velocity')

        Keyword arguments::
            acceleration_start_end -- is a dictionary with the maximum acceleration
            if not None will add two points
            to the given trajectories to starts and ends with no velocity.
            if the maximum acceleration is given it will be used it for this
            new points. otherwise maximum acceleration on the trajectory will be
            used.
        """
        if self._time is None or not self._time.size:
            raise RuntimeError("No trajectory built, call build method first")

        nb_point = (
            len(self._time) if acceleration_start_end is None else len(self._time) + 2
        )

        pvt_arrays = dict()

        for name, positions, velocities in zip(
            self._positions.keys(), self._positions.values(), self._velocity.values()
        ):
            dtype = [
                ("time", "f8"),
                ("position", positions.dtype),
                ("velocity", velocities.dtype),
            ]
            pvt_arrays[name] = numpy.zeros(nb_point, dtype)

        if acceleration_start_end is not None:
            max_acc = self.max_acceleration
            max_acc.update(acceleration_start_end)

            max_acc_time = 0.0
            for name, velocities in self._velocity.items():
                velocity = max(abs(velocities[0]), abs(velocities[-1]))
                acc = max_acc[name]
                acc_time = velocity / acc
                if acc_time > max_acc_time:
                    max_acc_time = acc_time

            for name, positions, velocities in zip(
                self._positions.keys(),
                self._positions.values(),
                self._velocity.values(),
            ):
                pvt_array = pvt_arrays[name]
                pvt_array["time"][1:-1] = self._time + max_acc_time
                pvt_array["time"][-1] = pvt_array["time"][-2] + max_acc_time

                pvt_array["velocity"][1:-1] = velocities

                pvt_array["position"][1:-1] = positions
                first_point = positions[0] - (velocities[0] * max_acc_time / 2.0)
                last_point = positions[-1] + (velocities[-1] * max_acc_time / 2.0)
                pvt_array["position"][0] = first_point
                pvt_array["position"][-1] = last_point
        else:
            for name, positions, velocities in zip(
                self._positions.keys(),
                self._positions.values(),
                self._velocity.values(),
            ):
                pvt_array = pvt_arrays[name]
                pvt_array["time"] = self._time
                pvt_array["position"] = positions
                pvt_array["velocity"] = velocities

        return pvt_arrays


class LinearTrajectory(object):
    """
    Trajectory representation for a linear motion

    v|  pa,ta_________pb,tb
     |      //        \\
     |_____//__________\\_______> t
       pi,ti             pf,tf
           <--duration-->
    """

    def __init__(self, pi, pf, velocity, acceleration, ti=None):
        if ti is None:
            ti = time.time()
        self.ti = ti
        self.pi = pi = float(pi)
        self.pf = pf = float(pf)
        self.velocity = velocity = float(velocity)
        self.acceleration = acceleration = float(acceleration)
        self.p = pf - pi
        self.dp = abs(self.p)
        self.positive = pf > pi

        try:
            full_accel_time = velocity / acceleration
        except ZeroDivisionError:
            # piezo motors have 0 acceleration
            full_accel_time = 0
        full_accel_dp = 0.5 * acceleration * full_accel_time ** 2

        full_dp_non_const_vel = 2 * full_accel_dp
        self.reaches_top_vel = self.dp > full_dp_non_const_vel
        if self.reaches_top_vel:
            self.top_vel_dp = self.dp - full_dp_non_const_vel
            self.top_vel_time = self.top_vel_dp / velocity
            self.accel_dp = full_accel_dp
            self.accel_time = full_accel_time
            self.duration = self.top_vel_time + 2 * self.accel_time
            self.ta = self.ti + self.accel_time
            self.tb = self.ta + self.top_vel_time
            if self.positive:
                self.pa = pi + self.accel_dp
                self.pb = self.pa + self.top_vel_dp
            else:
                self.pa = pi - self.accel_dp
                self.pb = self.pa - self.top_vel_dp
        else:
            self.top_vel_dp = 0
            self.top_vel_time = 0
            self.accel_dp = self.dp / 2
            try:
                self.accel_time = math.sqrt(2 * self.accel_dp / acceleration)
            except ZeroDivisionError:
                self.accel_time = 0
            self.duration = 2 * self.accel_time
            self.velocity = acceleration * self.accel_time
            self.ta = self.tb = self.ti + self.accel_time
            if self.positive:
                pa_pb = pi + self.accel_dp
            else:
                pa_pb = pi - self.accel_dp
            self.pa = self.pb = pa_pb
        self.tf = self.ti + self.duration

    def position(self, instant=None):
        """Position at a given instant in time"""
        if instant is None:
            instant = time.time()
        if instant < self.ti:
            raise ValueError("instant cannot be less than start time")
        if instant > self.tf:
            return self.pf
        dt = instant - self.ti
        p = self.pi
        f = 1 if self.positive else -1
        if instant < self.ta:
            accel_dp = 0.5 * self.acceleration * dt ** 2
            return p + f * accel_dp

        p += f * self.accel_dp

        # went through the initial acceleration
        if instant < self.tb:
            t_at_max = dt - self.accel_time
            dp_at_max = self.velocity * t_at_max
            return p + f * dp_at_max
        else:
            dp_at_max = self.top_vel_dp
            decel_time = instant - self.tb
            decel_dp = 0.5 * self.acceleration * decel_time ** 2
            return p + f * dp_at_max + f * decel_dp

    def instant(self, position):
        """Instant when the trajectory passes at the given position"""
        d = position - self.pi
        dp = abs(d)
        if dp > self.dp:
            raise ValueError("position outside trajectory")

        dt = self.ti
        if dp > self.accel_dp:
            dt += self.accel_time
        else:
            return math.sqrt(2 * dp / self.acceleration) + dt

        top_vel_dp = dp - self.accel_dp
        if top_vel_dp > self.top_vel_dp:
            # starts deceleration
            dt += self.top_vel_time
            decel_dp = abs(position - self.pb)
            dt += math.sqrt(2 * decel_dp / self.acceleration)
        else:
            dt += top_vel_dp / self.velocity
        return dt

    def __repr__(self):
        return "{0}({1.pi}, {1.pf}, {1.velocity}, {1.acceleration}, {1.ti})".format(
            type(self).__name__, self
        )
