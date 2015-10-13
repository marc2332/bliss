#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the CT2 project
#
# Copyright 2015 European Synchrotron Radiation Facility, Grenoble, France
#
# Distributed under the terms of the LGPL license.
# See LICENSE.txt for more info.
"""Contain the tests for the CT2 (P201/C208) ESRF counter card."""

# Path
import sys
import os
path = os.path.join(os.path.dirname(__file__), os.pardir)
sys.path.insert(0, os.path.abspath(path))

# Imports
from time import sleep
from mock import MagicMock
from PyTango import DevFailed, DevState
from devicetest import DeviceTestCase, main
from CT2 import CT2

# Note:
#
# Since the device uses an inner thread, it is necessary to
# wait during the tests in order the let the device update itself.
# Hence, the sleep calls have to be secured enough not to produce
# any inconsistent behavior. However, the unittests need to run fast.
# Here, we use a factor 3 between the read period and the sleep calls.
#
# Look at devicetest examples for more advanced testing


# Device test case
class CT2DeviceTestCase(DeviceTestCase):
    """Test case for packet generation."""
    # PROTECTED REGION ID(CT2.test_additionnal_import) ENABLED START #
    # PROTECTED REGION END #    //  CT2.test_additionnal_import
    device = CT2
    properties = {'card_name': 'p201',
                  }
    empty = None  # Should be []

    @classmethod
    def mocking(cls):
        """Mock external libraries."""
        # Example : Mock numpy
        # cls.numpy = CT2.numpy = MagicMock()
        # PROTECTED REGION ID(CT2.test_mocking) ENABLED START #
        # PROTECTED REGION END #    //  CT2.test_mocking

    def test_properties(self):
        # test the properties
        # PROTECTED REGION ID(CT2.test_properties) ENABLED START #
        # PROTECTED REGION END #    //  CT2.test_properties
        pass

    def test_State(self):
        """Test for State"""
        # PROTECTED REGION ID(CT2.test_State) ENABLED START #
        self.device.State()
        # PROTECTED REGION END #    //  CT2.test_State

    def test_Status(self):
        """Test for Status"""
        # PROTECTED REGION ID(CT2.test_Status) ENABLED START #
        self.device.Status()
        # PROTECTED REGION END #    //  CT2.test_Status

    def test_pre_start(self):
        """Test for pre_start"""
        # PROTECTED REGION ID(CT2.test_pre_start) ENABLED START #
        self.device.pre_start()
        # PROTECTED REGION END #    //  CT2.test_pre_start

    def test_start(self):
        """Test for start"""
        # PROTECTED REGION ID(CT2.test_start) ENABLED START #
        self.device.start()
        # PROTECTED REGION END #    //  CT2.test_start

    def test_load_config(self):
        """Test for load_config"""
        # PROTECTED REGION ID(CT2.test_load_config) ENABLED START #
        self.device.load_config()
        # PROTECTED REGION END #    //  CT2.test_load_config

    def test_software_reset(self):
        """Test for software_reset"""
        # PROTECTED REGION ID(CT2.test_software_reset) ENABLED START #
        self.device.software_reset()
        # PROTECTED REGION END #    //  CT2.test_software_reset

    def test_reset(self):
        """Test for reset"""
        # PROTECTED REGION ID(CT2.test_reset) ENABLED START #
        self.device.reset()
        # PROTECTED REGION END #    //  CT2.test_reset

    def test_counters(self):
        """Test for counters"""
        # PROTECTED REGION ID(CT2.test_counters) ENABLED START #
        self.device.counters
        # PROTECTED REGION END #    //  CT2.test_counters

    def test_latches(self):
        """Test for latches"""
        # PROTECTED REGION ID(CT2.test_latches) ENABLED START #
        self.device.latches
        # PROTECTED REGION END #    //  CT2.test_latches


# Main execution
if __name__ == "__main__":
    main()
