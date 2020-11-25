# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import enum
import gevent
import functools
from tabulate import tabulate

from bliss import global_map
from bliss.config.beacon_object import BeaconObject
from bliss.common.scans import DEFAULT_CHAIN
from bliss.common.user_status_info import status_message
from bliss.common.logtools import user_print

from bliss.common import timedisplay
from bliss.controllers.counter import counter_namespace

from bliss.scanning.scan_meta import get_user_scan_meta
from bliss.scanning.chain import ChainPreset, ChainIterationPreset
from bliss.common import tango
from bliss.controllers.tango_attr_as_counter import (
    TangoCounterController,
    TangoAttrCounter,
)


class MachInfo(BeaconObject):
    """ Access to accelerator information.
    - SR_Current
    - SR_Lifetime
    - SR_Single_Bunch_Current
    - SR_Refill_Countdown
    """

    SRMODE = enum.Enum("SRMODE", "USM MDT Shutdown SafetyTest IdTest")
    name = BeaconObject.config_getter("name")
    extra_checktime = BeaconObject.property_setting("extra_checktime", default=0.)
    waittime = BeaconObject.property_setting("waittime", default=0)
    COUNTERS = (
        ("current", "SR_Current"),
        ("lifetime", "SR_Lifetime"),
        ("sbcurr", "SR_Single_Bunch_Current"),
        ("refill", "SR_Refill_Countdown"),
    )
    KEY_NAME = "MACHINE"

    def __init__(self, name, config):
        super().__init__(config, share_hardware=False)
        global_map.register(self, tag=name)
        self.tango_uri = config["uri"]
        self.__counters = []
        for cnt_name, attr_name in self.COUNTERS:
            counter_config = config.clone()
            counter_config["attr_name"] = attr_name
            counter_config["mode"] = "SINGLE"
            controller = TangoCounterController(
                name, self.proxy, global_map_register=False
            )
            cnt = TangoAttrCounter(cnt_name, counter_config, controller)
            self.__counters.append(cnt)

        self.__counters_groups = dict()
        self.__check = False
        default_counters = config.get("default_counters", list())
        if default_counters:
            # check if allowed (ie: name is in self.COUNTERS)
            allowed_counters = set(c[0] for c in self.COUNTERS)
            not_allowed = [
                name for name in default_counters if name not in allowed_counters
            ]
            if not_allowed:
                raise AttributeError(
                    f"Default counters must be part of {allowed_counters},"
                    f"{not_allowed} are not allowed"
                )
            self._counter_grp = {
                "default": counter_namespace(
                    [
                        counter
                        for counter in self.__counters
                        if counter.name in default_counters
                    ]
                )
            }
        else:
            self._counter_grp = dict()

        self.initialize()

    @property
    @functools.lru_cache(maxsize=1)
    def proxy(self):
        machinfo_dev = tango.DeviceProxy(self.tango_uri)
        machinfo_dev.set_source(tango.DevSource.CACHE_DEV)
        return machinfo_dev

    @property
    @BeaconObject.lazy_init
    def counters(self):
        return counter_namespace(self.__counters)

    @property
    @BeaconObject.lazy_init
    def counter_groups(self):
        return counter_namespace(self._counter_grp)

    @property
    def check(self):
        """
        Install a preset for all common scans to pause
        scans when refill
        """
        return self.__check

    @check.setter
    def check(self, flag):
        if flag:
            preset = WaitForRefillPreset(self)
            DEFAULT_CHAIN.add_preset(preset, name=self.KEY_NAME)
            self.__check = True
            user_print("Activating Wait For Refill on scans")
        else:
            DEFAULT_CHAIN.remove_preset(name=self.KEY_NAME)
            self.__check = False
            user_print("Removing Wait For Refill on scans")

    @BeaconObject.property(default=True)
    def metadata(self):
        """
        Insert machine info metadata's for any scans
        """
        pass

    @metadata.setter
    def metadata(self, flag):
        def get_meta(scan):
            attributes = [
                "SR_Mode",
                "SR_Filling_Mode",
                "SR_Single_Bunch_Current",
                "SR_Current",
                "Automatic_Mode",
                "FE_State",
                "SR_Refill_Countdown",
                "SR_Operator_Mesg",
            ]
            attributes = {
                attr_name: value
                for attr_name, value in zip(
                    attributes, self._read_attributes(attributes)
                )
            }
            # Standard:
            meta_dict = {
                "@NX_class": "NXsource",
                "name": "ESRF",
                "type": "Synchrotron",
                "mode": self.SRMODE(attributes["SR_Mode"]).name,
                "current": attributes["SR_Current"],
                "current@units": "mA",
            }
            # Non-standard:
            if attributes["SR_Filling_Mode"] == "1 bunch":
                meta_dict["single_bunch_current"] = attributes[
                    "SR_Single_Bunch_Current"
                ]
                meta_dict["single_bunch_current@units"] = "mA"
            meta_dict["filling_mode"] = attributes["SR_Filling_Mode"]
            meta_dict["automatic_mode"] = attributes["Automatic_Mode"]
            meta_dict["front_end"] = attributes["FE_State"]
            meta_dict["refill_countdown"] = attributes["SR_Refill_Countdown"]
            meta_dict["refill_countdown@units"] = "s"
            meta_dict["message"] = attributes["SR_Operator_Mesg"]
            return {"machine": meta_dict}

        if flag:
            get_user_scan_meta().instrument.set(self.KEY_NAME, get_meta)
        else:
            get_user_scan_meta().instrument.remove(self.KEY_NAME)

    def iter_wait_for_refill(self, checktime, waittime=0., polling_time=1.):
        """
        Helper for waiting the machine refill.
        It will yield two states "WAIT_INJECTION" and "WAITING_AFTER_BEAM_IS_BACK"
        until the machine refill is finished.

        simple usage will be:
        for status in iter_wait_for_refill(my_check_time,waittime=1.,polling_time=1.):
            if status == "WAIT_INJECTION":
                print("Scan is paused, waiting injection",end='\r')
            else:
                print("Scan will restart in 1 second...",end='\r')
        """
        ok = self.check_for_refill(checktime)
        while not ok:
            yield "WAIT_INJECTION"
            gevent.sleep(polling_time)
            ok = self.check_for_refill(checktime)
            if ok:
                yield "WAITING_AFTER_BEAM_IS_BACK"
                gevent.sleep(waittime)
                ok = self.check_for_refill(checktime)

    def check_for_refill(self, checktime):
        """
        Check if the **checktime** is greater than the **refill countdown**
        """
        attr_to_read = ("SR_Mode", "SR_Refill_Countdown")
        mode, countdown = self._read_attributes(attr_to_read)
        if mode != self.SRMODE.USM.value:
            return True
        return countdown > checktime

    def __info__(self):
        str_info = f"MACHINE INFORMATION   ( {self.tango_uri} )\n\n"
        attributes = (
            "SR_Mode",
            "SR_Current",
            "SR_Lifetime",
            "SR_Single_Bunch_Current",
            "Auto_Mode_Time",
            "Automatic_Mode",
            "SR_Filling_Mode",
            "SR_Refill_Countdown",
            "SR_Operator_Mesg",
        )
        tables = []

        (
            sr_mode,
            sr_curr,
            ltime,
            sb_curr,
            auto_mode_time,
            fe_auto,
            sr_filling_mode,
            refill_time,
            op_message,
        ) = self._read_attributes(attributes)

        # SR_Mode: MDT, USM ...
        tables.append(("SR Mode:", f"{self.SRMODE(sr_mode).name}"))

        # SR_Current is in mA.
        tables.append(("Current:", f"{sr_curr:3.2f} mA"))

        # SR_Lifetime is in seconds with too much decimals.
        ltime = int(ltime)
        tables.append(
            ("Lifetime:", f"{ltime} s = {timedisplay.duration_format(ltime)}")
        )

        # SR_Refill_Countdown is in seconds.
        refill_time
        tables.append(
            (
                "Refill CountDown:",
                f"{int(refill_time)} s = {timedisplay.duration_format(refill_time)}",
            )
        )

        # SR_Filling_Mode value: '7/8 multibunch', '1 bunch'
        tables.append(("Filling Mode:", sr_filling_mode))

        if sr_filling_mode == "1 bunch":
            # SR_Single_Bunch_Current is in mA.
            tables.append(("Single Bunch Cur:", sb_curr))

        if auto_mode_time:
            auto_mode_time_human = timedisplay.duration_format(auto_mode_time)
            tables.append(
                (
                    "AutoMode:",
                    f"{fe_auto} (remaining: {auto_mode_time} s = {auto_mode_time_human})",
                )
            )
        else:
            tables.append(("AutoMode:", fe_auto))
        str_info += tabulate(tables)
        str_info += "\n"
        str_info += f"Operator Message: {op_message}\n"

        return str_info

    def _read_attributes(self, attr_to_read):
        dev_attrs = self.proxy.read_attributes(attr_to_read)

        # Check error
        for attr in dev_attrs:
            error = attr.get_err_stack()
            if error:
                raise tango.DevFailed(*error)
        return (attr.value for attr in dev_attrs)

    @property
    def sr_mode_as_string(self):
        mode, = self._read_attributes(("SR_Mode",))
        return self.SRMODE(mode).name

    @property
    def sr_mode(self):
        mode, = self._read_attributes(("SR_Mode",))
        return mode

    @property
    def automatic_mode(self):
        """
        Return the FE automatic mode status, True or False
        """
        mode, = self._read_attributes(("Automatic_Mode",))
        return mode

    @automatic_mode.setter
    def automatic_mode(self, newmode):
        """
        Set the automatic mode of the FE, True or False
        """
        if newmode is True:
            self.proxy.Automatic()
        else:
            self.proxy.Manual()

    @property
    def all_information(self):
        """
        Return most of all the machine information as a dictionnary
          - 
        """
        attributes = (
            "FE_State",
            "SR_Mode",
            "SR_Current",
            "SR_Lifetime",
            "SR_Single_Bunch_Current",
            "Auto_Mode_Time",
            "Automatic_Mode",
            "SR_Filling_Mode",
            "SR_Refill_Countdown",
            "SR_Operator_Mesg",
            "FE_Itlk_State",
            "PSS_Itlk_State",
            "EXP_Itlk_State",
            "HQPS_Itlk_State",
            "UHV_Valve_State",
        )
        attributes = {
            attr_name: value
            for attr_name, value in zip(attributes, self._read_attributes(attributes))
        }
        attributes["SR_Mode"] = self.SRMODE(attributes["SR_Mode"]).name
        return attributes


class WaitForRefillPreset(ChainPreset):
    """
    This preset will pause a scan during the refill
    and if the **checktime** is greater than the time to refill.
    If **checktime** is set to None then we try to find **count_time**
    on the top master of the chain.

    Do not forget to intialize MachInfo object in session's setup.
    """

    class PresetIter(ChainIterationPreset):
        def __init__(self, machinfo, checktime, waittime, polling_time):
            self.machinfo = machinfo
            self.checktime = checktime
            self.waittime = waittime
            self.polling_time = polling_time

        def start(self):
            ok = self.machinfo.check_for_refill(self.checktime)
            with status_message() as p:
                while not ok:
                    p("Waiting for refill...")
                    gevent.sleep(self.polling_time)
                    ok = self.machinfo.check_for_refill(self.checktime)
                    if ok and self.waittime:
                        p("Waiting {self.waittime} after Beam is back")
                        gevent.sleep(self.waittime)
                        ok = self.check_for_refill(self.checktime)

    def __init__(self, machinfo, checktime=None, waittime=None, polling_time=1.):
        self.machinfo = machinfo
        self.__checktime = checktime
        self.waittime = waittime
        self.polling_time = polling_time

    def get_iterator(self, chain):
        if self.__checktime is None:
            # will look into the chain to find **count_time**
            # on the first softtimer.
            for soft_timer in chain.nodes_list:
                try:
                    count_time = soft_timer.count_time
                except AttributeError:
                    pass
                else:
                    checktime = count_time
                    if self.machinfo.extra_checktime is not None:
                        checktime += self.machinfo.extra_checktime
                    break
            else:
                raise RuntimeError(
                    "Couldn't guess the checktime because didn't "
                    "find any soft timer..."
                    "You need to set checktime for custom scans"
                )
        else:
            checktime = self.__checktime

        while True:
            yield self.PresetIter(
                self.machinfo, checktime, self.waittime, self.polling_time
            )
