# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy as np
from scipy import signal
from scipy.special import erf

from bliss.scanning.chain import AcquisitionSlave
from bliss.common.counter import Counter, SoftCounter
from bliss.controllers.counter import CounterController
from bliss.common.soft_axis import SoftAxis
from bliss.common.protocols import counter_namespace

# for logging
import logging
from bliss.common.logtools import log_debug, log_debug_data, get_logger

"""
`simulation_counter` allows to define a fake counter.

This fake counter is usable in a `ct` or in a scan.

It returns floats numbers that can be:

* constant
* random
* following a gaussian distribution

If included in a scan (except timescan/loopscan without predefined
number of points), it returns values according to a user defined
distribution:

* FLAT (constant value)
* GAUSSIAN


Parameters:
* <distribution>:  'GAUSSIAN' | 'FLAT'
* <noise_factor>:
    * >= 0.0
    * add a random noise to the distribution
    * 0 means 'no random noise added'
    * noise added is only positive.
* <height_factor>:
    * >= 0.0
    * multiplication factor to adjust height (Y)

Parameters if using GAUSSIAN:
* <mu_offset>: shitfs mean value by <mu_offset> (X-offset)
* <sigma_factor>: standard deviation adjustement factor.
"""

# configuration example:
"""
-
  name: sim_ct_1
  plugin: bliss
  class: simulation_counter
  distribution: GAUSSIAN
  mu_offset: 1.0
  sigma_factor: 1.0
  height_factor: 1.0
  noise_factor: 0.005
-
  name: sim_ct_2
  plugin: bliss
  class: simulation_counter
  distribution: FLAT
  height_factor: 1.0
  noise_factor: 0.005
"""


# tests:
"""

ct(0.1)

debugon(sim_ct_1)

plotselect(sim_ct_1)
ascan(m1,-5,5,35,0.001, sim_ct_1); print(cen())
(0.0, 3.8845999488607355)

plotselect(sim_ct_2)
ascan(m1,-5,5,35,0.001, sim_ct_2);print(cen())
(-1.0121850156448249, 1.6335338706093914)

ct(0.1)        # does not produce a gaussian
timescan(0.1)  # does not produce a gaussian


ascan(m1,-5,5,35,0.001)
loopscan(13, 0.1)
pointscan(m1, [-3 , -2, -1,  0, 0.2,1, 1.1], 0.1)
timescan(0.1, npoints=13)

a2scan(m1,-5,5, m2, 0, 3, 13, 0.01)
cen()


dscan(m1,-1,1, 13, 0.01)

"""


class SimulationCounterAcquisitionSlave(AcquisitionSlave):
    def __init__(
        self,
        controller,
        scan_type=None,
        npoints=1,
        start=0,
        stop=0,
        distribution=None,
        gauss_param=None,
        noise_factor=0,
        ctrl_params=None,
    ):
        # global_map.register(self)
        log_debug(
            self, "SIMULATION_COUNTER_ACQ_DEV -- SimulationCounterAcquisitionSlave()"
        )

        self.distribution = distribution
        self.gauss_param = gauss_param
        self.noise_factor = noise_factor
        self.scan_type = scan_type
        self.scan_start = start
        self.scan_stop = stop

        AcquisitionSlave.__init__(
            self,
            controller,
            npoints=npoints,
            prepare_once=True,  # Do not call prepare at each point.
            start_once=True,  # Do not call start at each point.
            ctrl_params=ctrl_params,
        )

    def is_count_scan(self):
        """
        Return True if the scan involving this acq_device has NOT a
        predefined (timescan) number of points or is just a single count (ct).
        """
        if self.npoints < 2:
            return True
        else:
            return False

    def prepare(self):
        log_debug(self, "SIMULATION_COUNTER_ACQ_DEV -- prepare()")
        self._index = 0

        #### Get scan paramerters
        nbpoints = self.npoints

        # npoints should be 0 only in case of timescan without 'npoints' parameter
        if nbpoints == 0:
            nbpoints = 1

        if self.is_count_scan() or self.scan_type in ["pointscan"]:
            # ct, timescan(without npoints), pointscan
            scan_start = self.scan_start
            scan_stop = self.scan_stop
        elif self.scan_type in ["loopscan", "timescan"]:
            # no user defined start/stop or timescan-with-npoints
            scan_start = 0
            scan_stop = nbpoints
        else:
            # ascan etc.
            scan_start = self.scan_start[0]
            scan_stop = self.scan_stop[0]

        log_debug(
            self,
            "SIMULATION_COUNTER_ACQ_DEV -- prepare() -- type=%s \
        nbpoints=%d start=%s stop=%s",
            self.scan_type,
            nbpoints,
            scan_start,
            scan_stop,
        )

        #### Get gaussian distribution parameters

        mu_offset = self.gauss_param.get("mu_offset", 0.0)
        sigma_factor = self.gauss_param.get("sigma_factor", 1.0)
        self.height_factor = self.gauss_param.get("height_factor", 1.0)

        _dbg_string = f"SIMULATION_COUNTER_ACQ_DEV -- prepare() -- distribution={self.distribution}"
        _dbg_string += f"mu_offset={mu_offset:g} sigma_factor={sigma_factor}"
        _dbg_string += (
            f"height_factor={self.height_factor} noise_factor={self.noise_factor}"
        )
        log_debug(self, _dbg_string)

        #### Generation of the distribution
        # base data
        if self.is_count_scan() or self.distribution == "FLAT":
            log_debug(
                self, "SIMULATION_COUNTER_ACQ_DEV -- prepare() -- is count scan or FLAT"
            )
            self.data = np.ones(nbpoints)
        else:
            log_debug(
                self,
                "SIMULATION_COUNTER_ACQ_DEV -- prepare() -- neither count nor FLAT",
            )
            self.data = np.linspace(scan_start, scan_stop, nbpoints)

        log_debug(self, "SIMULATION_COUNTER_ACQ_DEV -- prepare() -- data(linspace)=")
        log_debug(self, self.data)

        # creates distribution
        if self.is_count_scan() or self.distribution == "FLAT":
            log_debug(self, "SIMULATION_COUNTER_ACQ_DEV -- prepare() -- FLAT")
            pass
        else:
            log_debug(
                self,
                "SIMULATION_COUNTER_ACQ_DEV -- prepare() -- GAUSSIAN -- start=%s stop=%s nbpoints=%d",
                scan_start,
                scan_stop,
                nbpoints,
            )
            self.data = self.gauss(self.data, mu_offset, sigma_factor)

        log_debug_data(
            self, "SIMULATION_COUNTER_ACQ_DEV -- prepare() -- data=", self.data
        )

        # applying Y factor.
        self.data = self.data * self.height_factor
        log_debug_data(self, "self.data with height_factor=", self.data)

        # computing noise.
        if self.is_count_scan():
            noise = (np.random.rand(1)[0] * self.noise_factor) + 1
        else:
            noise = (np.random.rand(nbpoints) * self.noise_factor) + 1
        log_debug_data(self, "noise=", noise)

        # applying noise.
        self.data = self.data * noise
        log_debug_data(self, "self.data with  noise=", self.data)

        next(iter(self._counters.keys())).data = self.data

        log_debug(self, "SIMULATION_COUNTER_ACQ_DEV -- prepare() END")

    def calc_gaussian(self, x, mu, sigma):
        one_over_sqtr = 1.0 / np.sqrt(2.0 * np.pi * np.square(sigma))
        exp = np.exp(-np.square(x - mu) / (2.0 * np.square(sigma)))

        _val = one_over_sqtr * exp

        return _val

    def gauss(self, x, mu_offset, sigma_factor):
        """
        Returns a gaussian distribution of length <x>.

        <x>: initialized array
        <mu_offset>: shift of mean value
        <sigma_factor>: standard deviation adjustement factor

        """

        xmin = min(x)
        xmax = max(x)
        mu = (xmax + xmin) / 2.0
        mu = mu + mu_offset  # negative offset shifts to the left.

        self.mu = mu

        if sigma_factor == 0:
            sigma_factor = 1.0
        else:
            # 6.0 is pifometricly choosen to have a "look-nice" gaussian.
            sigma = sigma_factor * (xmax - xmin) / 6.0

        self.sigma = sigma
        self.fwhm = 2 * np.sqrt(2 * np.log(2)) * sigma  # ~ 2.35 * sigma

        log_debug(
            self,
            "SIMULATION_COUNTER_ACQ_DEV -- xmin=%s xmax=%s mu_offset=%s mu=%s sigma=%s",
            xmin,
            xmax,
            mu_offset,
            mu,
            sigma,
        )

        _val = self.calc_gaussian(x, mu, sigma)

        log_debug(self, "SIMULATION_COUNTER_ACQ_DEV -- gauss() -- returns %s", _val)
        return _val

    def start(self):
        log_debug(self, "SIMULATION_COUNTER_ACQ_DEV -- start()")
        pass

    def stop(self):
        log_debug(self, "SIMULATION_COUNTER_ACQ_DEV -- stop()")
        if self.distribution == "GAUSSIAN" and not self.is_count_scan():
            log_debug(
                self,
                "SIMULATION_COUNTER_ACQ_DEV -- (Theorical values) %s mu=%f sigma=%f fwhm=%f",
                self.name,
                self.mu,
                self.sigma,
                self.fwhm,
            )
        pass

    def trigger(self):
        """
        Called at each point
         * not called during ct()
         * called during timescan()
        """
        log_debug(
            self,
            "SIMULATION_COUNTER_ACQ_DEV -- **************** trigger() **************************",
        )
        if get_logger(self).isEnabledFor(logging.DEBUG):
            print(self.data)
            print("_index=", self._index)

        value = self.data[self._index]

        # publishes the data
        self.channels[0].emit(value)

        if not self.is_count_scan():
            self._index += 1
        log_debug(self, "SIMULATION_COUNTER_ACQ_DEV -- trigger()  END")


class SimulationCounterController(CounterController):
    def __init__(self):
        super().__init__("simulation_counter_controller")

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return SimulationCounterAcquisitionSlave(
            self, ctrl_params=ctrl_params, **acq_params
        )

    def get_default_chain_parameters(self, scan_params, acq_params):
        counter = self.counters[0]

        mu_offset = counter.config.get("mu_offset", 0.0)
        sigma_factor = counter.config.get("sigma_factor", 1.0)
        height_factor = counter.config.get("height_factor", 1.0)

        gauss_param = {
            "mu_offset": mu_offset,
            "sigma_factor": sigma_factor,
            "height_factor": height_factor,
        }

        try:
            scan_type = acq_params["type"]
        except KeyError:
            scan_type = scan_params["type"]

        try:
            npoints = acq_params["npoints"]
        except KeyError:
            npoints = scan_params["npoints"]

        try:
            start = acq_params["start"]
        except KeyError:
            start = scan_params.get("start", [])

        try:
            stop = acq_params["stop"]
        except KeyError:
            stop = scan_params.get("stop", [])

        params = {}
        params["scan_type"] = scan_type
        params["npoints"] = npoints
        params["start"] = start
        params["stop"] = stop
        params["distribution"] = counter.config.get("distribution", "FLAT")
        params["gauss_param"] = gauss_param
        params["noise_factor"] = counter.config.get("noise_factor", 0.0)

        return params


class SimulationCounter(Counter):
    def __init__(self, name, config):
        super().__init__(name, SimulationCounterController())
        self.config = config


class FixedShapeCounter:
    """Counter which generates a signal of predefined shape.
    The predefined shape can be obtained by scanning the
    associated software axis from 0 to 1:

        s = ascan(self.axis, 0, 1, self.npoints, expo, self.counter)
    """

    @staticmethod
    def _missing_edge_of_gaussian_left(npoints, frac_missing):
        p = npoints // 2
        p2 = int(p * frac_missing)
        return np.concatenate(
            (signal.gaussian(p, .1 * npoints)[p2:], np.zeros(p2), np.zeros(npoints - p))
        )

    SIGNALS = {
        "sawtooth": lambda npoints: signal.sawtooth(
            np.arange(0, 2 * np.pi * 1.1, 2 * np.pi * 1.1 / npoints), width=.9
        ),
        "gaussian": lambda npoints: signal.gaussian(npoints, .2 * npoints),
        "flat": lambda npoints: np.ones(npoints),
        "off_center_gaussian": lambda npoints: np.concatenate(
            (
                np.zeros(npoints - npoints // 2),
                signal.gaussian(npoints // 2, .1 * npoints),
            )
        ),
        "missing_edge_of_gaussian_left": lambda npoints: FixedShapeCounter._missing_edge_of_gaussian_left(
            npoints, 0.25
        ),
        "missing_edge_of_gaussian_right": lambda npoints: FixedShapeCounter._missing_edge_of_gaussian_left(
            npoints, 0.25
        )[
            ::-1
        ],
        "half_gaussian_right": lambda npoints: FixedShapeCounter._missing_edge_of_gaussian_left(
            npoints, 0.4
        ),
        "half_gaussian_left": lambda npoints: FixedShapeCounter._missing_edge_of_gaussian_left(
            npoints, 0.4
        )[
            ::-1
        ],
        "triangle": lambda npoints: np.concatenate(
            (
                np.arange(0, 1, 1 / (npoints // 2)),
                np.flip(np.arange(0, 1, 1 / (npoints - npoints // 2))),
            )
        ),
        "square": lambda npoints: np.concatenate(
            (
                np.zeros(npoints // 3),
                np.ones(npoints // 3),
                np.zeros(npoints - 2 * (npoints // 3)),
            )
        ),
        "bimodal": lambda npoints: np.concatenate(
            (
                signal.gaussian(npoints - npoints // 2, .15 * npoints) * 1.5,
                signal.gaussian(npoints // 2, .15 * npoints),
            )
        ),
        "step_down": lambda npoints: np.concatenate(
            (np.ones(npoints // 2), np.zeros(npoints - npoints // 2))
        ),
        "step_up": lambda npoints: np.concatenate(
            (np.zeros(npoints // 2), np.ones(npoints - npoints // 2))
        ),
        "erf_down": lambda npoints: 1 - erf(np.arange(-3, 3, 6 / (npoints))),
        "erf_up": lambda npoints: erf(np.arange(-3, 3, 6 / (npoints))),
        "inverted_gaussian": lambda npoints: 1 - signal.gaussian(npoints, .2 * npoints),
        "expo_gaussian": lambda npoints: np.exp(
            signal.gaussian(npoints, .1 * npoints) * 30
        ),
    }

    def __init__(self, signal="sawtooth", npoints=50):
        self._axis = SoftAxis("TestAxis", self)
        self._counter = SoftCounter(self)
        self._npoints = npoints
        self.signal = signal
        self._position = 0

    @property
    def position(self):
        """The axis position of the associated software counter
        """
        return self._position

    @position.setter
    def position(self, value):
        assert value <= 1
        assert value >= 0
        self._position = value

    def value(self):
        """The counter value for the simulated counter,
        based on the current axis position.
        """
        return self._data[int((self._npoints - 1) * self._position)]

    def init_signal(self):
        """Calculate the values of the simulated counter for an
        ascan of the associated axis between 0 and 1. This ensures
        the predefined signal shape.
        """
        self._data = self.SIGNALS[self._signal](self._npoints)

    @property
    def signal(self):
        return self._signal

    @signal.setter
    def signal(self, value):
        assert value in self.SIGNALS
        self._signal = value
        self.init_signal()

    @property
    def nsteps(self):
        return self._npoints + 1

    @property
    def npoints(self):
        return self._npoints

    @npoints.setter
    def npoints(self, value):
        self._npoints = value
        self.init_signal()

    @property
    def counters(self):
        return counter_namespace([self._counter])

    @property
    def counter(self):
        return self._counter

    @property
    def axis(self):
        return self._axis


class TestFilterCounterAxis:
    """
    Object that produces an axis and a counter to test auto filters
    """

    def __init__(self, name, config):
        self._axis = SoftAxis("TestFilterCounterAxis", self)
        self._counter = SoftCounter(self)
        self._npoints = config.get("npoints", 50)
        self._attn = config.get("attenuator", None)
        self._position = 0
        self.init_signal()

    # for SoftAxis
    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        assert value <= 1
        assert value >= 0
        self._position = value

    # for SoftCounter
    def value(self):
        return (
            self._data[int(round(self._npoints * self._position))]
            * self._attn.transmission
        )

    def init_signal(self):
        self._data = np.exp(
            signal.gaussian(self._npoints + 1, .1 * self._npoints + 1) * 30
        )

    @property
    def npoints(self):
        return self._npoints

    @npoints.setter
    def npoints(self, value):
        self._npoints = value
        self.init_signal()

    @property
    def counters(self):
        return counter_namespace([self._counter])

    @property
    def counter(self):
        return self._counter

    @property
    def axis(self):
        return self._axis
