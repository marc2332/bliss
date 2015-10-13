# -*- coding: utf-8 -*-
#
# This file is part of the CT2 project
#
# Copyright 2015 European Synchrotron Radiation Facility, Grenoble, France
#
# Distributed under the terms of the LGPL license.
# See LICENSE.txt for more info.

""" CT2 (P201/C208) ESRF counter card

CT2 (P201/C208) ESRF counter card TANGO device
"""

__all__ = ["CT2", "main"]

# PyTango imports
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango.server import class_property, device_property
from PyTango import AttrQuality, AttrWriteType, DispLevel, DevState
# Additional import
# PROTECTED REGION ID(CT2.additionnal_import) ENABLED START #

from beacon.static import get_config

# PROTECTED REGION END #    //  CT2.additionnal_import


class CT2(Device):
    """
    CT2 (P201/C208) ESRF counter card TANGO device
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(CT2.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  CT2.class_variable
    # ----------------
    # Class Properties
    # ----------------

    # -----------------
    # Device Properties
    # -----------------

    card_name = device_property(
        dtype='str', default_value="p201"
    )

    # ----------
    # Attributes
    # ----------

    counters = attribute(
        dtype=('uint',),
        max_dim_x=12,
    )

    latches = attribute(
        dtype=('uint',),
        max_dim_x=12,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(CT2.init_device) ENABLED START #
        config = get_config()
        util = PyTango.Util.instance()
        if not util.is_svr_starting():
            config.reload()
        self.card = config.get(self.card_name)
        # PROTECTED REGION END #    //  CT2.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(CT2.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CT2.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(CT2.delete_device) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CT2.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_counters(self):
        # PROTECTED REGION ID(CT2.counters_read) ENABLED START #
        return self.card.get_counters_values()
        # PROTECTED REGION END #    //  CT2.counters_read

    def read_latches(self):
        # PROTECTED REGION ID(CT2.latches_read) ENABLED START #
        return self.card.get_latches_values()
        # PROTECTED REGION END #    //  CT2.latches_read

    # --------
    # Commands
    # --------

    @command
    @DebugIt()
    def pre_start(self):
        # PROTECTED REGION ID(CT2.pre_start) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CT2.pre_start

    @command
    @DebugIt()
    def start(self):
        # PROTECTED REGION ID(CT2.start) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CT2.start

    @command
    @DebugIt()
    def load_config(self):
        # PROTECTED REGION ID(CT2.load_config) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CT2.load_config

    @command
    @DebugIt()
    def software_reset(self):
        # PROTECTED REGION ID(CT2.software_reset) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CT2.software_reset

    @command
    @DebugIt()
    def reset(self):
        # PROTECTED REGION ID(CT2.reset) ENABLED START #
        pass
        # PROTECTED REGION END #    //  CT2.reset

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    from PyTango.server import run
    return run((CT2,), args=args, **kwargs)

if __name__ == '__main__':
    main()
