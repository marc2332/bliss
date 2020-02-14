import gevent
import time

from bliss import global_map
from bliss.common.tango import DeviceProxy, DevState
from bliss.common.counter import Counter
from bliss.controllers.counter import CounterController
from bliss.scanning.chain import AcquisitionMaster

"""
Configuration YML:

- class: Elettra
  module: tango_elettra
  name: el2
  uri: //id20ctrl2:20000/id20/elettra/ss1
  counters:
  - counter_name: el2x
    measure: Y
  - counter_name: el2y
    measure: Z
"""

MEASURE_KEYS = {
    "current1": 1,
    "current2": 2,
    "current3": 3,
    "current4": 4,
    "integration_time": 5,
    "samples_number": 6,
    "y": 7,
    "z": 8,
    "current_total": 9,
}


class ElettraCounter(Counter):
    def __init__(self, name, controller, channel, **kwargs):
        super().__init__(name, controller, **kwargs)
        self.channel = channel


class ElettraAcquisitionMaster(AcquisitionMaster):
    def __init__(self, *devices, count_time, ctrl_params=None):

        super().__init__(*devices, ctrl_params=ctrl_params)

        self.count_time = count_time
        self._stop_flag = False

    def _emit_new_data(self, data):
        self.channels.update_from_iterable(data)

    def prepare(self):
        self._stop_flag = False

    def start(self):
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def trigger(self):
        t0 = time.time()
        self.device.start(self.count_time)
        self.trigger_slaves()

        # --- wait count_time -------
        while not self._stop_flag:
            dt = time.time() - t0
            if dt >= self.count_time:
                break
            gevent.idle()

        # --- get and send data --------------
        counters = list(self._counters.keys())
        data = [
            counters[i].conversion_function(x)
            for i, x in enumerate(self.device.get_data(*counters))
        ]

        self._emit_new_data(data)


class Elettra(CounterController):
    def __init__(self, name, config):

        super().__init__(name)

        self._tango_uri = config.get("uri", str)
        self._tango_proxi = DeviceProxy(self._tango_uri)

        global_map.register(self, children_list=[self._tango_proxi], tag=name)
        for cnt in config.get("counters", list()):
            if "measure" in cnt.keys():
                if cnt["measure"].casefold() in MEASURE_KEYS:
                    cnt["channel"] = MEASURE_KEYS[cnt["measure"].casefold()]
                else:
                    print(
                        "WARNING: {0} measure unknown, {1} counter channel will be ignored".format(
                            cnt["measure"], cnt["counter_name"]
                        )
                    )
                    continue

            self.create_counter(
                ElettraCounter, cnt["counter_name"], channel=cnt["channel"]
            )

    def __info__(self):
        _info_str = "ePicea - model {0} - tango server {1}\r\n".format(
            self._tango_proxi.getmodel(), self._tango_uri
        )
        #        _info_str += '         {0} Data stream\r\n'.format('Binary' if self._tango_proxi.putget('BIN ?') is 'ON' else 'Ascii')
        _info_str += "\n"
        _info_str += "         Full scale range: {0:.2g} A\r\n".format(self.range)
        _info_str += "         Measuring offset: {0} A\r\n".format(self.offset)
        _info_str += "\n"
        _meas = self._tango_proxi.measure
        _info_str += "         Last measurements:  \r\n"
        _info_str += "                  current1: {0} A\r\n".format(_meas[0])
        _info_str += "                  current2: {0} A\r\n".format(_meas[1])
        _info_str += "                  current3: {0} A\r\n".format(_meas[2])
        _info_str += "                  current4: {0} A\r\n".format(_meas[3])
        _info_str += "          integration time: {0:.2f} s\r\n".format(_meas[4])
        _info_str += "         number of samples: {0:d} \r\n".format(int(_meas[5]))
        _info_str += "                         X: {0} \r\n".format(_meas[6])
        _info_str += "                         Y: {0} \r\n".format(_meas[7])
        _info_str += "\n"
        _info_str += "         {0}\r\n".format(self._tango_proxi.status())

        return _info_str

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return ElettraAcquisitionMaster(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):
        try:
            count_time = acq_params["count_time"]
        except KeyError:
            count_time = scan_params["count_time"]

        params = {"count_time": count_time}

        return params

    def get_data(self, *counters):
        measure = self._tango_proxi.measure
        #        print ("get_values = measured {0:.1f}".format(measure[4]))
        #        print ("             measured {0:.1f}".format(measure[6]))
        #        print ("             measured {0:.1f}".format(measure[7]))
        return [[measure[cnt.channel - 1]] for cnt in counters]

    #
    # tango DS commands
    #

    def start(self, count_time=0):
        return self._tango_proxi.startcontinuousacq(count_time)

    def stop(self):
        return self._tango_proxi.stopacq()

    @property
    def range(self):
        return self._tango_proxi.getfullscalecurrent()

    @range.setter
    def range(self, value):
        if self._tango_proxi.state() is DevState.ON:
            value = abs(value)
            self._tango_proxi.setfullscalecurrent(value)
        else:
            print(
                "Cannot change measuring range to {0} Amps while the device is {1}".format(
                    value, self._tango_proxi.state()
                )
            )

    @property
    def offset(self):
        return self._tango_proxi.getmeasureoffset()

    def offset_measure(self, integration_time=1):
        timeo = self._tango_proxi.get_timeout_millis()
        itime = timeo / 1005 if integration_time * 1000 >= timeo else integration_time

        return self._tango_proxi.setmeasureoffset(itime)

    def offset_reset(self):
        return self._tango_proxi.resetMeasureOffset()

    #
    # AH401 specific - not tested
    #

    def _getI(self):
        return self._tango_proxi.getitime()

    def _setI(self, value):
        return self._tango_proxi.setitime(value)

    def _getC(self):
        return self._tango_proxi.getrange()

    def _setC(self, value):
        return self._tango_proxi.setrange(value)

    def _getHLF(self):
        return self._tango_proxi.command_inout("PutGet", "HLF ?")

    def _setHLF(self, value):
        return self._tango_proxi.command_inout("PutGet", "HLF {0}".format(value))
