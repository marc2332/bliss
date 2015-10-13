#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the CT2 project
#
# Copyright 2015 European Synchrotron Radiation Facility, Grenoble, France
#
# Distributed under the terms of the LGPL license.
# See LICENSE.txt for more info.

import os
import sys
from setuptools import setup

setup_dir = os.path.dirname(os.path.abspath(__file__))

# make sure we use latest info from local code
sys.path.insert(0, setup_dir)

with open('README.rst') as file:
    long_description = file.read()

exec(open('CT2/release.py').read())
pack = ['CT2']

setup(name=name,
      version=version,
      description='CT2 (P201/C208) ESRF counter card TANGO device',
      packages=pack,
      scripts=['scripts/CT2'],
      include_package_data=True,
      test_suite="test",
      author='coutinho',
      author_email='coutinho at esrf.fr',
      license='LGPL',
      long_description=long_description,
      url='www.tango-controls.org',
      platforms="Unix Like"
      )
