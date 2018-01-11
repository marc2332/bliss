# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
try:
    #this is used only for the b-spline
    from scipy import interpolate
except ImportError:
    interpolate = None

class PointTrajectory(object):
    """
    class helper to build trajectories.
    """
    def __init__(self):
        self._time = None
        self._positions = dict()
        self._velocity = dict()
        self._acceleration = dict()

    def build(self, time_array, positions,
              spline_nb_points=0):
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

    def max_velocity(self):
        """
        Return the maximum velocity.
        """
        max_vel = dict()
        for name, velocities in self._velocity.iteritems():
            max_vel[name] = numpy.absolute(velocities).max()
        return max_vel

    def max_acceleration(self):
        """
        Return the maximum acceleration.
        """
        max_acc = dict()
        for name, accelerations in self._acceleration.iteritems():
            max_acc[name] = numpy.absolute(accelerations).max()
        return max_acc

    def limits(self):
        """
        Return the min and max position for this movement.
        Can be easily compared with the motor limits
        """
        limits = dict()
        for name, positions in self._positions.iteritems():
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

        nb_point = len(self._time) if acceleration_start_end is None \
                   else len(self._time) + 2

        pvt_arrays = dict()

        for name, positions, velocities in zip(self._positions.keys(),
                                               self._positions.values(),
                                               self._velocity.values()):
            dtype = [('time', 'f8'), ('position', positions.dtype),
                     ('velocity', velocities.dtype)]
            pvt_arrays[name] = numpy.zeros(nb_point, dtype)

        if acceleration_start_end is not None:
            max_acc = self.max_acceleration()
            max_acc.update(acceleration_start_end)

            max_acc_time = 0.
            for name, velocities in self._velocity.iteritems():
                velocity = max(abs(velocities[0]), abs(velocities[-1]))
                acc = max_acc[name]
                acc_time = velocity/acc
                if acc_time > max_acc_time:
                    max_acc_time = acc_time

            for name, positions, velocities in zip(self._positions.keys(),
                                                   self._positions.values(),
                                                   self._velocity.values()):
                pvt_array = pvt_arrays[name]
                pvt_array['time'][1:-1] = self._time + max_acc_time
                pvt_array['time'][-1] = pvt_array['time'][-2] + max_acc_time

                pvt_array['velocity'][1:-1] = velocities

                pvt_array['position'][1:-1] = positions
                first_point = positions[0] - (velocities[0] * max_acc_time / 2.)
                last_point = positions[-1] + (velocities[-1] * max_acc_time / 2.)
                pvt_array['position'][0] = first_point
                pvt_array['position'][-1] = last_point
        else:
            for name, positions, velocities in zip(self._positions.keys(),
                                                   self._positions.values(),
                                                   self._velocity.values()):
                pvt_array = pvt_arrays[name]
                pvt_array['time'] = self._time
                pvt_array['position'] = positions
                pvt_array['velocity'] = velocities

        return pvt_arrays
