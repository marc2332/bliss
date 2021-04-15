# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
from bliss.controllers.motor import CalcController
from bliss.physics import trajectory
from bliss.common import event
from bliss.common.axis import Trajectory
from bliss.common.motor_group import TrajectoryGroup
from bliss.common.utils import all_equal, object_method, grouped


class HKLMotors(CalcController):
    def __init__(self, diffractometer, config, axes):
        super().__init__(config, axes, [], [], [])
        self.diffracto = diffractometer
        self._frozen_angles = dict()

    def initialize(self):
        super().initialize()
        self.update_limits()
        for axis in self.reals:
            if self._axis_tag(axis) != "energy":
                event.connect(axis, "low_limit", self.update_limits)
                event.connect(axis, "high_limit", self.update_limits)

    def close(self):
        for axis in self.reals:
            if self._axis_tag(axis) != "energy":
                event.disconnect(axis, "low_limit", self.update_limits)
                event.disconnect(axis, "high_limit", self.update_limits)
        super().close()

    def update_limits(self, *args):
        geo_limits = self.diffracto.geometry.get_axis_limits()
        for axis in self.reals:
            name = self._axis_tag(axis)
            if name != "energy":
                axis_limits = axis.limits
                if not self.diffracto.geometry.is_axis_limits_initialized(name):
                    geo_limits[name] = axis_limits
                else:
                    geo_limits[name] = (
                        max(axis_limits[0], geo_limits[name][0]),
                        min(axis_limits[1], geo_limits[name][1]),
                    )
        self.diffracto.geometry.set_axis_limits(geo_limits)

    def initialize_axis(self, axis):
        super().initialize_axis(axis)
        axis.no_offset = True

    def get_axis_engine(self, axis):
        return self.diffracto.geometry.get_engine_from_pseudo_tag(self._axis_tag(axis))

    def _get_complementary_pseudos_pos_dict(self, axes):
        """ Find the other pseudos which are not in 'axes' and get their actual position.
            This complementary axes are necessary to compute the reals positions
            via the 'calc_to_real' method. 

            The pseudo axes of other engines are excluded. 

            Args: 
                axes: list of Axis objects
            Return: {axis_tag:dial_pos, ...}
        """

        # get engine of axes and check is unique
        engines = set([self.get_axis_engine(ax) for ax in axes])
        if len(engines) != 1:
            raise ValueError(
                f"cannot mix axes from different engines {[ax.name for ax in axes]}"
            )
        engine = engines.pop()

        # get complementary axes for selected engine
        axis_to_positions = {}
        for axis in self.pseudos:
            if axis not in axes and self.get_axis_engine(axis) == engine:
                axis_to_positions[self._axis_tag(axis)] = axis.user2dial(
                    axis._set_position
                )

        return axis_to_positions

    def _get_motion_pos_dict(self, motion_list):
        """ Get all necessary pseudos with their positions to compute calc_to_real
            Only single 
        """

        positions_dict = dict()
        for motion in motion_list:
            # positions_dict[self._axis_tag(motion.axis)] = motion.target_pos
            positions_dict[self._axis_tag(motion.axis)] = motion.axis.user2dial(
                motion.axis._set_position
            )

        # get complementary pseudos
        axes = [m.axis for m in motion_list]
        cmpl = self._get_complementary_pseudos_pos_dict(axes)
        positions_dict.update(cmpl)

        return positions_dict

    def calc_to_real(self, positions_dict):
        """ computes real pos from pseudo pos.
            positions_dict must provide all pseudo of specific engine.
            do not mix pseudos from different engines.
        """

        # try expecting array of positions per axis
        try:
            k = positions_dict.keys()
            v = positions_dict.values()
            nbr_pos = [len(x) for x in v]
            if not all_equal(nbr_pos):
                raise ValueError(
                    f"all axes must provide same number of positions {positions_dict}"
                )
            n = nbr_pos[0]

        # exception on len(x) => one position per axis
        except TypeError:
            if len(self._frozen_angles):
                self.diffracto.geometry.set_axis_pos(self._frozen_angles, update=False)
            self.diffracto.geometry.set_pseudo_pos(positions_dict)
            return self.diffracto.geometry.get_axis_pos()

        else:
            # transform dict of list to list of dict
            # eg: {pseudo:[pos1, pos2]} into [ {pseudo:pos1}, {pseudo:pos2} ]
            dict_list = [dict(zip(k, [x[i] for x in v])) for i in range(n)]

            # build output {real:[pos1, pos2, ...], ...}
            real_pos = {}
            for d in dict_list:
                if len(self._frozen_angles):
                    self.diffracto.geometry.set_axis_pos(
                        self._frozen_angles, update=False
                    )
                self.diffracto.geometry.set_pseudo_pos(d)
                rp = self.diffracto.geometry.get_axis_pos()
                for x, y in rp.items():
                    real_pos.setdefault(x, []).append(y)

            return real_pos

    def calc_from_real(self, real_positions):
        """ computes pseudo pos from real pos.
            positions_dict must provide positions of all reals.
        """

        energy = real_positions.pop("energy", None)

        # try expecting array of positions per axis
        try:
            k = real_positions.keys()
            v = real_positions.values()
            nbr_pos = [len(x) for x in v]
            assert all_equal(nbr_pos)
            n = nbr_pos[0]
            assert len(energy) == n

        # exception on len(x) => one position per axis
        except TypeError:
            if energy is not None:
                self.diffracto.geometry.set_energy(energy)
            self.diffracto.geometry.set_axis_pos(real_positions)
            return self.diffracto.geometry.get_pseudo_pos()

        else:
            energy = real_positions.pop("energy", None)
            # transform dict of list to list of dict
            # eg: {real:[pos1, pos2]} into [ {real:pos1}, {real:pos2} ]
            dict_list = [dict(zip(k, [x[i] for x in v])) for i in range(n)]

            # build output {pseudo:[pos1, pos2, ...], ...}
            pseudo_pos = {}
            for idx, d in enumerate(dict_list):
                if energy is not None:
                    self.diffracto.geometry.set_energy(energy[idx])
                self.diffracto.geometry.set_axis_pos(d)
                rp = self.diffracto.geometry.get_pseudo_pos()
                for x, y in rp.items():
                    pseudo_pos.setdefault(x, []).append(y)

            return pseudo_pos

    def update(self):
        self._calc_from_real()

    def freeze(self, tag_names):
        for tag in tag_names:
            axis = self._tagged[tag][0]
            self._frozen_angles[tag] = axis.position

    def unfreeze(self):
        self._frozen_angles = dict()
        self._calc_from_real()

    @property
    def frozen_angles(self):
        return self._frozen_angles

    @frozen_angles.setter
    def frozen_angles(self, pos_dict):
        real_tags = [self._axis_tag(axis) for axis in self.reals]
        unknown = [name for name in list(pos_dict.keys()) if name not in real_tags]
        if len(unknown):
            raise ValueError("Unknown frozen axis tags {0}".format(unknown))
        self._frozen_angles = dict(pos_dict)

    @object_method(types_info=(("float", "float", "int", "float"), "object"))
    def scan_on_trajectory(
        self,
        calc_axis,
        start_point,
        end_point,
        nb_points,
        time_per_point,
        interpolation_factor=1,
    ):
        pseudo_name = self._axis_tag(calc_axis)
        return self.calc_trajectory(
            (pseudo_name,),
            (start_point,),
            (end_point,),
            nb_points,
            time_per_point,
            interpolation_factor,
        )

    def calc_trajectory(
        self, pseudos, start, stop, npoints, time_per_point, interpolation_factor=1
    ):

        geometry = self.diffracto.geometry

        # --- check if real motor has trajectory capability
        real_involved = geometry.get_axis_involved(*pseudos)
        real_axes = list()
        for real in self.reals:
            if self._axis_tag(real) in real_involved:
                axis, raxes = self._check_trajectory(real)
                real_axes.append((axis, raxes))

        # --- calculate real axis positions
        calc_pos = dict()
        for name in real_involved:
            calc_pos[name] = numpy.zeros(npoints, numpy.float)

        idx = 0
        for values in zip(*map(numpy.linspace, start, stop, [npoints] * len(pseudos))):
            try:
                pseudo_dict = dict(zip(pseudos, values))
                geometry.set_pseudo_pos(pseudo_dict)
            except:
                raise RuntimeError(
                    "Failed to computes trajectory positions for {0}".format(
                        pseudo_dict
                    )
                )

            axis_pos = geometry.get_axis_pos()
            for name in real_involved:
                calc_pos[name][idx] = axis_pos[name]
            idx += 1

        # --- checking inflexion points
        for (name, pos_arr) in calc_pos.items():
            diffarr = numpy.diff(pos_arr)
            if (
                numpy.alltrue(diffarr <= 0) is False
                and numpy.alltrue(diffarr >= 0) is False
            ):
                raise RuntimeError(
                    "HKl trajectory can not be done.\nInflexion point found on [{0}] geometry axis".format(
                        name
                    )
                )

        # --- get final real positions
        # --- calculate positions of real dependant axis
        # --- and put axis as final_real_pos keys
        final_real_pos = dict()
        self._get_real_position(real_axes, calc_pos, final_real_pos)

        # --- computes trajectory
        time = numpy.linspace(0.0, npoints * time_per_point, npoints)
        spline_nb_points = (
            0 if interpolation_factor == 1 else len(time) * interpolation_factor
        )

        pt = trajectory.PointTrajectory()
        pt.build(
            time,
            {axis.name: position for axis, position in final_real_pos.items()},
            spline_nb_points=spline_nb_points,
        )

        # --- check velocity and acceleration
        error_list = list()
        start_stop_acceleration = dict()
        for axis in final_real_pos:
            axis_vel = axis.velocity
            axis_acc = axis.acceleration
            axis_lim = axis.limits
            traj_vel = pt.max_velocity[axis.name]
            traj_acc = pt.max_acceleration[axis.name]
            traj_lim = pt.limits[axis.name]
            if traj_acc > axis_acc:
                error_list.append(
                    "Axis %s reach %f acceleration on this trajectory,"
                    "max acceleration is %f" % (axis.name, traj_acc, axis_acc)
                )
            if traj_vel > axis_vel:
                error_list.append(
                    "Axis %s reach %f velocity on this trajectory,"
                    "max velocity is %f" % (axis.name, traj_vel, axis_vel)
                )
            for lm in traj_lim:
                if not axis_lim[0] <= lm <= axis_lim[1]:
                    error_list.append(
                        "Axis %s go beyond limits (%f <= %f <= %f)"
                        % (axis.name, axis_lim[0], lm, axis_lim[1])
                    )

            start_stop_acceleration[axis.name] = axis_acc

        if error_list:
            error_message = "HKL Trajectory can not be done.\n"
            error_message += "\n".join(error_list)
            raise ValueError(error_message)

        # --- creates pvt table
        pvt = pt.pvt(acceleration_start_end=start_stop_acceleration)
        trajectories = [Trajectory(axis, pvt[axis.name]) for axis in final_real_pos]

        return TrajectoryGroup(*trajectories)
