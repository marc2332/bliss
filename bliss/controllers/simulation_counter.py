# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy as np
import time
import pprint

from bliss.scanning.chain import AcquisitionDevice, AcquisitionChannel
from bliss.scanning.acquisition.counter import SamplingMode
from bliss.common.measurement import GroupedReadMixin, Counter
from bliss.common import session

# for logging
import logging
from bliss.common.logtools import LogMixin

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

sim_ct_1.get_acquisition_device()._logger.debugon()
sim_ct_1._logger.debugon()


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


class SimulationCounter_AcquisitionDevice(AcquisitionDevice, LogMixin):
    def __init__(self, counter, scan_param, distribution, gauss_param, noise_factor):
        session.get_current().map.register(self)
        self._logger.debug(
            "SIMULATION_COUNTER_ACQ_DEV -- SimulationCounter_AcquisitionDevice()"
        )

        self.counter = counter
        self.scan_param = scan_param
        self.distribution = distribution
        self.gauss_param = gauss_param
        self.noise_factor = noise_factor
        self.scan_type = self.scan_param.get("type")

        AcquisitionDevice.__init__(
            self,
            None,
            counter.name,
            npoints=self.scan_param.get("npoints"),
            prepare_once=True,  # Do not call prepare at each point.
            start_once=True,  # Do not call start at each point.
        )

        # add a new channel (data) to the acq dev.
        self.channels.append(AcquisitionChannel(counter, counter.name, np.float, ()))

    def is_count_scan(self):
        """
        Return True if the scan involving this acq_device has NOT a
        predefined (timescan) number of points or is just a single count (ct).
        """
        if self.scan_param.get("npoints") < 2:
            return True
        else:
            return False

    def prepare(self):
        self._logger.debug("SIMULATION_COUNTER_ACQ_DEV -- prepare()")
        self._index = 0

        #### Get scan paramerters
        nbpoints = self.scan_param.get("npoints")

        # npoints should be 0 only in case of timescan without 'npoints' parameter
        if nbpoints == 0:
            nbpoints = 1

        if self.is_count_scan() or self.scan_type in ["pointscan"]:
            # ct, timescan(without npoints), pointscan
            scan_start = self.scan_param.get("start")
            scan_stop = self.scan_param.get("stop")
        elif self.scan_type in ["loopscan", "timescan"]:
            # no user defined start/stop or timescan-with-npoints
            scan_start = 0
            scan_stop = nbpoints
        else:
            # ascan etc.
            scan_start = self.scan_param.get("start")[0]
            scan_stop = self.scan_param.get("stop")[0]

        self._logger.debug(
            f"SIMULATION_COUNTER_ACQ_DEV -- prepare() -- type={self.scan_type} \
        nbpoints={nbpoints} start={scan_start} stop={scan_stop}"
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
        self._logger.debug(_dbg_string)

        #### Generation of the distribution
        # base data
        if self.is_count_scan() or self.distribution == "FLAT":
            self._logger.debug(
                "SIMULATION_COUNTER_ACQ_DEV -- prepare() -- is count scan or FLAT"
            )
            self.data = np.ones(nbpoints)
        else:
            self._logger.debug(
                "SIMULATION_COUNTER_ACQ_DEV -- prepare() -- neither count nor FLAT"
            )
            self.data = np.linspace(scan_start, scan_stop, nbpoints)

        self._logger.debug("SIMULATION_COUNTER_ACQ_DEV -- prepare() -- data(linspace)=")
        self._logger.debug(self.data)

        # creates distribution
        if self.is_count_scan() or self.distribution == "FLAT":
            self._logger.debug(f"SIMULATION_COUNTER_ACQ_DEV -- prepare() -- FLAT")
            pass
        else:
            self._logger.debug(
                f"SIMULATION_COUNTER_ACQ_DEV -- prepare() -- GAUSSIAN -- start={scan_start} stop={scan_stop} nbpoints={nbpoints}"
            )
            self.data = self.gauss(self.data, mu_offset, sigma_factor)

        self._logger.debug("SIMULATION_COUNTER_ACQ_DEV -- prepare() -- data=")
        self._logger.debug(self.data)

        # applying Y factor.
        self.data = self.data * self.height_factor
        self._logger.debug("self.data with height_factor=")
        self._logger.debug(self.data)

        # computing noise.
        if self.is_count_scan():
            noise = (np.random.rand(1)[0] * self.noise_factor) + 1
        else:
            noise = (np.random.rand(nbpoints) * self.noise_factor) + 1
        self._logger.debug("noise=")
        self._logger.debug(noise)

        # applying noise.
        self.data = self.data * noise
        self._logger.debug("self.data with  noise=")
        self._logger.debug(self.data)

        self.counter.data = self.data

        self._logger.debug(f"SIMULATION_COUNTER_ACQ_DEV -- prepare() END")

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

        self._logger.debug(
            f"SIMULATION_COUNTER_ACQ_DEV -- xmin={xmin} xmax={xmax} mu_offset={mu_offset:g} mu={mu:g} sigma={sigma:g}"
        )

        _val = self.calc_gaussian(x, mu, sigma)

        self._logger.debug(f"SIMULATION_COUNTER_ACQ_DEV -- gauss() -- returns {_val}")
        return _val

    def start(self):
        self._logger.debug(f"SIMULATION_COUNTER_ACQ_DEV -- start()")
        pass

    def stop(self):
        self._logger.debug("SIMULATION_COUNTER_ACQ_DEV -- stop()")
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
        self._logger.debug(
            f"SIMULATION_COUNTER_ACQ_DEV -- **************** trigger() **************************"
        )
        if self._logger.isEnabledFor(logging.DEBUG):
            print(self.data)
            print("_index=", self._index)

        value = self.data[self._index]

        # publishes the data
        self.channels[0].emit(value)

        if not self.is_count_scan():
            self._index += 1
        self._logger.debug(f"SIMULATION_COUNTER_ACQ_DEV -- trigger()  END")


class SimulationCounter(Counter, LogMixin):
    def __init__(self, name, config):
        Counter.__init__(self, name)

        self.config = config
        self.acq_device = None
        self.scan_pars = None

    def create_acquisition_device(self, scan_pars):
        self._logger.debug("SIMULATION_COUNTER -- create_acquisition_device")

        mu_offset = self.config.get("mu_offset", 0.0)
        sigma_factor = self.config.get("sigma_factor", 1.0)
        height_factor = self.config.get("height_factor", 1.0)

        gauss_param = {
            "mu_offset": mu_offset,
            "sigma_factor": sigma_factor,
            "height_factor": height_factor,
        }

        self.acq_device = SimulationCounter_AcquisitionDevice(
            self,
            scan_param=scan_pars,
            distribution=self.config.get("distribution", "FLAT"),
            gauss_param=gauss_param,
            noise_factor=self.config.get("noise_factor", 0.0),
        )

        self._logger.debug("SIMULATION_COUNTER -- COUNTER CONFIG")
        if self._logger.isEnabledFor(logging.DEBUG):
            pprint.pprint(self.config)

        self._logger.debug("SIMULATION_COUNTER -- SCAN_PARS")

        if self._logger.isEnabledFor(logging.DEBUG):
            pprint.pprint(scan_pars)
        """ SCAN_PARS
        {'type': 'ascan', 'save': True, 'title': 'ascan mm1 0 1 5 0.2', 'sleep_time': None,
         'npoints': 5, 'total_acq_time': 1.0, 'start': [0], 'stop': [1], 'count_time': 0.2,
         'estimation': {'total_motion_time': 2.4644, 'total_count_time': 1.0, 'total_time': 3.46474}
         }
        """

        self.scan_pars = scan_pars

        self._logger.debug("SIMULATION_COUNTER -- create_acquisition_device END")
        return self.acq_device

    def get_acquisition_device(self):
        self._logger.debug("SIMULATION_COUNTER -- get_acquisition_device()")
        return self.acq_device

    def read(self):
        self._logger.debug("SIMULATION_COUNTER -- read()")
        return 33

    # If no controller, a warning is emited in `master_to_devices_mapping()`
    # def controller(self):
    #     return None
