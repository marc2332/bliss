# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import math
import time
import random
import unittest

import gevent

from bliss.common.measurement import CounterBase
from bliss.common.measurement import SingleMeasurement, FullMeasurement


class RandomCounter(CounterBase):

    def __init__(self, name, range=(0., 1000.), nap=1E-3):
        CounterBase.__init__(self, None, name)
        self.range = range
        self.nb_reads = 0
        self.nap = nap

    def read(self):
        not self.nap or gevent.sleep(self.nap)
        self.nb_reads += 1
        value = self.range[0] + random.random()*self.range[1]
        return value


class TestMeasurements(unittest.TestCase):

    def setUp(self):
        self.longMessage = True
        self.name = 'random'
        self.counter = RandomCounter(self.name, range=(0., 100.), nap=1E-3)

    # called at the end of each individual test
    def tearDown(self):
        del self.counter

    def test_name(self):
        self.assertEquals(self.counter.name, self.name)

    def test_measurement(self):
        for count_time in (0.001, 0.01, 0.1, 1):
            self.counter.nb_reads = 0
            self._test_measurement(count_time)

    def _test_measurement(self, count_time):
        msg="Failed when count_time={0}".format(count_time)
        window = self.counter.range[1] - self.counter.range[0]
        ideal_value = window / 2.
        ideal_nb_points = count_time / self.counter.nap

        start = time.time()
        result = self.counter.count(count_time)
        dt = time.time() - start

        self.assertEqual(result.value, result.average, msg=msg)
        self.assertEqual(result.nb_points, self.counter.nb_reads, msg=msg)
        # allow 25% error. Seems a lot but it is the accumulation of sleep errors
        self.assertAlmostEqual(result.nb_points, ideal_nb_points, 
                               delta=ideal_nb_points*0.25, msg=msg)
        # allow up to 10ms error in time calculation for pure software counter
        self.assertAlmostEqual(dt, count_time, delta=0.01, msg=msg)
        # variable error margin according to number of points
        delta = window*100./ideal_nb_points
        self.assertAlmostEqual(result.value, ideal_value, delta=delta, msg=msg)

    def test_single_measurement(self):
        start = time.time()
        result = self.counter.count(100., measurement=SingleMeasurement())
        dt = time.time() - start

        self.assertEqual(self.counter.nb_reads, 1)
        # should be really fast
        self.assertAlmostEqual(dt, self.counter.nap, delta=1E-3)
        self.assertTrue(result.value >= self.counter.range[0])
        self.assertTrue(result.value < self.counter.range[1])        

    def test_full_measurement(self):
        count_time = .1
        ideal_value = 500
        ideal_nb_points = count_time / self.counter.nap

        start = time.time()
        result = self.counter.count(count_time, measurement=FullMeasurement())
        dt = time.time() - start
        
        self.assertEqual(result.value, result.average)
        self.assertEqual(result.nb_points, self.counter.nb_reads)
        self.assertEqual(len(result.data), result.nb_points)
        self.assertAlmostEqual(result.average, result.data[:,0].mean(), delta=0.1)
