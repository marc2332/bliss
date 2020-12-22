# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.counter import SamplingCounter
from bliss.common.regulation import Input, Output, Loop, lazy_init


class OxfordInput(Input):
    def _build_counters(self):
        self.create_counter(
            SamplingCounter,
            self.name + "_gas_temp",
            unit=self._config.get("unit", "N/A"),
            mode=self._config.get("sampling-counter-mode", "SINGLE"),
        )

        self.create_counter(
            SamplingCounter,
            self.name + "_evap_temp",
            unit=self._config.get("unit", ""),
            mode=self._config.get("sampling-counter-mode", "SINGLE"),
        )

        self.create_counter(
            SamplingCounter,
            self.name + "_suct_temp",
            unit=self._config.get("unit", ""),
            mode=self._config.get("sampling-counter-mode", "SINGLE"),
        )

        self.create_counter(
            SamplingCounter,
            self.name + "_gas_error",
            unit=self._config.get("unit", ""),
            mode=self._config.get("sampling-counter-mode", "SINGLE"),
        )

    def read_all(self, *counters):
        res = []
        for cnt in counters:
            if cnt.name == f"{self.name}_gas_temp":
                res.append(self.controller.hw_controller.read_gas_temperature())
            elif cnt.name == f"{self.name}_evap_temp":
                res.append(self.controller.hw_controller.read_evap_temperature())
            elif cnt.name == f"{self.name}_suct_temp":
                res.append(self.controller.hw_controller.read_suct_temperature())
            elif cnt.name == f"{self.name}_gas_error":
                res.append(self.controller.hw_controller.read_gas_error())

        return res

    @lazy_init
    def __info__(self):
        lines = ["\n"]
        lines.append(f"=== Input: {self.name} ===")
        lines.append(
            f"controller: {self.controller.name if self.controller.name is not None else self.controller.__class__.__name__}"
        )
        lines.append(f"channel: {self.channel}")
        lines.append("")
        val = self.controller.hw_controller.read_gas_temperature()
        lines.append(f"current gas temperature: {val:.3f} K")
        val = self.controller.hw_controller.read_evap_temperature()
        lines.append(f"current evap temperature: {val:.3f} K")
        val = self.controller.hw_controller.read_suct_temperature()
        lines.append(f"current suct temperature: {val:.3f} K")
        val = self.controller.hw_controller.read_gas_error()
        lines.append(f"current gas error: {val:.3f}")

        return "\n".join(lines)


class OxfordOutput(Output):
    def _build_counters(self):

        self.create_counter(
            SamplingCounter,
            self.name + "_gas_heat",
            unit=self._config.get("unit", "N/A"),
            mode=self._config.get("sampling-counter-mode", "SINGLE"),
        )

        self.create_counter(
            SamplingCounter,
            self.name + "_evap_heat",
            unit=self._config.get("unit", ""),
            mode=self._config.get("sampling-counter-mode", "SINGLE"),
        )

        self.create_counter(
            SamplingCounter,
            self.name + "_suct_heat",
            unit=self._config.get("unit", ""),
            mode=self._config.get("sampling-counter-mode", "SINGLE"),
        )

        self.create_counter(
            SamplingCounter,
            self.name + "_gas_flow",
            unit=self._config.get("unit", ""),
            mode=self._config.get("sampling-counter-mode", "SINGLE"),
        )

    def read_all(self, *counters):
        res = []
        for cnt in counters:
            if cnt.name == f"{self.name}_gas_heat":
                res.append(self.controller.hw_controller.read_gas_heat())
            elif cnt.name == f"{self.name}_evap_heat":
                res.append(self.controller.hw_controller.read_evap_heat())
            elif cnt.name == f"{self.name}_suct_heat":
                res.append(self.controller.hw_controller.read_suct_heat())
            elif cnt.name == f"{self.name}_gas_flow":
                res.append(self.controller.hw_controller.read_gas_flow())

        return res

    @lazy_init
    def __info__(self):
        lines = ["\n"]
        lines.append(f"=== Output: {self.name} ===")
        lines.append(
            f"controller: {self.controller.name if self.controller.name is not None else self.controller.__class__.__name__}"
        )
        lines.append(f"channel: {self.channel}")

        lines.append("")
        val = self.controller.hw_controller.read_gas_heat()
        lines.append(f"current gas heat: {val:.3f}")

        val = self.controller.hw_controller.read_evap_heat()
        lines.append(f"current evap heat: {val:.3f}")

        val = self.controller.hw_controller.read_suct_heat()
        lines.append(f"current suct heat: {val:.3f}")

        val = self.controller.hw_controller.read_gas_flow()
        lines.append(f"current gas flow: {val:.3f}")
        lines.append("")

        lines.append(f"output ramprate: {self.ramprate}")
        lines.append(f"ramping: {self.is_ramping()}")
        lines.append(f"limits: {self._limits}")
        return "\n".join(lines)


class OxfordLoop(Loop):
    def _build_counters(self):

        self.create_counter(
            SamplingCounter,
            self.name + "_gas_setpoint",
            unit=self.input.config.get("unit", "N/A"),
            mode="SINGLE",
        )

        self.create_counter(
            SamplingCounter,
            self.name + "_target_temp",
            unit=self.input.config.get("unit", "N/A"),
            mode="SINGLE",
        )

    def read_all(self, *counters):
        res = []
        for cnt in counters:
            if cnt.name == f"{self.name}_gas_setpoint":
                res.append(self.controller.hw_controller.read_gas_setpoint())
            elif cnt.name == f"{self.name}_target_temp":
                res.append(self.controller.hw_controller.read_target_temperature())
        return res

    @lazy_init
    def __info__(self):
        lines = ["\n"]

        ctrl_name = (
            self.controller.name
            if self.controller.name is not None
            else self.controller.__class__.__name__
        )
        lines.append(f"=== Controller: {ctrl_name} ===")
        lines.append(f"current mode: {self.controller.hw_controller.read_run_mode()}")
        lines.append(f"current phase: {self.controller.hw_controller.read_phase()}")
        lines.append(f"alarm status: {self.controller.hw_controller.read_alarm()}")
        lines.append("")

        lines.append(f"=== Loop: {self.name} ===")
        lines.append(f"gas setpoint: {self.setpoint} K")
        lines.append(f"ramprate: {self.ramprate} K/hour")
        lines.append(f"ramping: {self.is_ramping()}")
        lines.append("")

        lines.append(f"=== Input: {self.input.name} ===")
        val = self.controller.hw_controller.read_gas_temperature()
        lines.append(f"current gas temperature: {val:.3f} K")
        val = self.controller.hw_controller.read_evap_temperature()
        lines.append(f"current evap temperature: {val:.3f} K")
        val = self.controller.hw_controller.read_suct_temperature()
        lines.append(f"current suct temperature: {val:.3f} K")
        val = self.controller.hw_controller.read_gas_error()
        lines.append(f"current gas error: {val:.3f}")
        lines.append("")

        lines.append(f"=== Output: {self.output.name} ===")
        val = self.controller.hw_controller.read_gas_heat()
        lines.append(f"current gas heat: {val:.3f}")
        val = self.controller.hw_controller.read_evap_heat()
        lines.append(f"current evap heat: {val:.3f}")
        val = self.controller.hw_controller.read_suct_heat()
        lines.append(f"current suct heat: {val:.3f}")
        val = self.controller.hw_controller.read_gas_flow()
        lines.append(f"current gas flow: {val:.3f}")

        return "\n".join(lines)
