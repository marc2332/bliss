# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy as np
import pprint

from bliss.scanning.chain import AcquisitionSlave, ChainNode
from bliss.common.counter import Counter
from bliss.controllers.counter import CounterController
from bliss import global_map

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
  name: sim_ct
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

debugon(sim_ct_1.get_acquisition_device())
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
        counter,
        scan_type,
        scan_npoints,
        scan_start,
        scan_stop,
        distribution,
        gauss_param,
        noise_factor,
    ):
        global_map.register(self)
        log_debug(
            self, "SIMULATION_COUNTER_ACQ_DEV -- SimulationCounterAcquisitionSlave()"
        )

        self.distribution = distribution
        self.gauss_param = gauss_param
        self.noise_factor = noise_factor
        self.scan_type = scan_type
        self.scan_start = scan_start
        self.scan_stop = scan_stop

        AcquisitionSlave.__init__(
            self,
            counter,
            npoints=scan_npoints,
            prepare_once=True,  # Do not call prepare at each point.
            start_once=True,  # Do not call start at each point.
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
            f"SIMULATION_COUNTER_ACQ_DEV -- prepare() -- type={self.scan_type} \
        nbpoints={nbpoints} start={scan_start} stop={scan_stop}",
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
            log_debug(self, f"SIMULATION_COUNTER_ACQ_DEV -- prepare() -- FLAT")
            pass
        else:
            log_debug(
                self,
                f"SIMULATION_COUNTER_ACQ_DEV -- prepare() -- GAUSSIAN -- start={scan_start} stop={scan_stop} nbpoints={nbpoints}",
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

        log_debug(self, f"SIMULATION_COUNTER_ACQ_DEV -- prepare() END")

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
            f"SIMULATION_COUNTER_ACQ_DEV -- xmin={xmin} xmax={xmax} mu_offset={mu_offset:g} mu={mu:g} sigma={sigma:g}",
        )

        _val = self.calc_gaussian(x, mu, sigma)

        log_debug(self, f"SIMULATION_COUNTER_ACQ_DEV -- gauss() -- returns {_val}")
        return _val

    def start(self):
        log_debug(self, f"SIMULATION_COUNTER_ACQ_DEV -- start()")
        pass

    def stop(self):
        log_debug(self, "SIMULATION_COUNTER_ACQ_DEV -- stop()")
        if self.distribution == "GAUSSIAN" and not self.is_count_scan():
            print(
                f"SIMULATION_COUNTER_ACQ_DEV -- (Theorical values) {self.name} mu={self.mu:g} sigma={self.sigma:g} fwhm={self.fwhm:g}"
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
            f"SIMULATION_COUNTER_ACQ_DEV -- **************** trigger() **************************",
        )
        if get_logger(self).isEnabledFor(logging.DEBUG):
            print(self.data)
            print("_index=", self._index)

        value = self.data[self._index]

        # publishes the data
        self.channels[0].emit(value)

        if not self.is_count_scan():
            self._index += 1
        log_debug(self, f"SIMULATION_COUNTER_ACQ_DEV -- trigger()  END")


class SimulationCounterControllerChainNode(ChainNode):
    def _get_default_chain_parameters(self, scan_params, acq_params):

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
        except:
            scan_type = scan_params["type"]

        try:
            npoints = acq_params["npoints"]
        except:
            npoints = scan_params["npoints"]

        try:
            start = acq_params["start"]
        except:
            start = scan_params["start"]

        try:
            stop = acq_params["stop"]
        except:
            stop = scan_params["stop"]

        params = {}
        params["type"] = scan_type
        params["npoints"] = npoints
        params["start"] = start
        params["stop"] = stop
        params["distribution"] = counter.config.get("distribution", "FLAT")
        params["gauss_param"] = gauss_param
        params["noise_factor"] = counter.config.get("noise_factor", 0.0)

        return params

    def get_acquisition_object(self, acq_params, ctrl_params=None):

        ################ TO BE CLEANED !!!!!!!!!!!!!!! #############################

        # --- Warn user if an unexpected is found in acq_params
        expected_keys = [
            "type",
            "npoints",
            "start",
            "stop",
            "distribution",
            "gauss_param",
            "noise_factor",
        ]
        for key in acq_params.keys():
            if key not in expected_keys:
                print(
                    f"=== Warning: unexpected key '{key}' found in acquisition parameters for SimulationCounterAcquisitionSlave({self.controller}) ==="
                )

        counter = self.counters[0]

        log_debug(counter, "SIMULATION_COUNTER -- create_acquisition_device")

        # --- MANDATORY PARAMETERS -------------------------------------

        scan_type = acq_params["type"]
        scan_npoints = acq_params["npoints"]
        scan_start = acq_params["start"]
        scan_stop = acq_params["stop"]
        distribution = acq_params["distribution"]
        gauss_param = acq_params["gauss_param"]
        noise_factor = acq_params["noise_factor"]

        acq_dev = SimulationCounterAcquisitionSlave(
            counter,
            scan_type,
            scan_npoints,
            scan_start,
            scan_stop,
            distribution,
            gauss_param,
            noise_factor,
        )

        counter.acq_device = (
            acq_dev
        )  # <= weird stuff to keep SimulationCounter.get_acquisition_device() working !

        log_debug(counter, "SIMULATION_COUNTER -- COUNTER CONFIG")
        if get_logger(counter).isEnabledFor(logging.DEBUG):
            pprint.pprint(counter.config)

        log_debug(counter, "SIMULATION_COUNTER -- SCAN_PARS")

        if get_logger(counter).isEnabledFor(logging.DEBUG):
            pprint.pprint(acq_params)  # .copy().update(acq_params))

        """ SCAN_PARS
        {'type': 'ascan', 'save': True, 'title': 'ascan mm1 0 1 5 0.2', 'sleep_time': None,
         'npoints': 5, 'total_acq_time': 1.0, 'start': [0], 'stop': [1], 'count_time': 0.2,
         'estimation': {'total_motion_time': 2.4644, 'total_count_time': 1.0, 'total_time': 3.46474}
         }
        """

        log_debug(self, "SIMULATION_COUNTER -- create_acquisition_device END")
        return acq_dev


class SimulationCounterController(CounterController):
    def __init__(self):
        super().__init__(
            "simulation_counter_controller",
            chain_node_class=SimulationCounterControllerChainNode,
        )


class SimulationCounter(Counter):
    def __init__(self, name, config):
        super().__init__(name, SimulationCounterController())

        self.config = config
        self.acq_device = None

    def get_acquisition_device(self):
        log_debug(self, "SIMULATION_COUNTER -- get_acquisition_device()")
        return self.acq_device

    def read(self):
        log_debug(self, "SIMULATION_COUNTER -- read()")
        return 33
