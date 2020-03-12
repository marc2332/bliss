# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numbers
import numpy
from bliss.common.counter import Counter
from typing import Union, Optional, Tuple, List, Sequence
from bliss.common.protocols import Scannable, CounterContainer
from bliss.common.measurementgroup import MeasurementGroup
from bliss.common.axis import Axis

######### types for typeguard #########
_int = numbers.Integral
_float = numbers.Real
_countable = Counter
_countables = Union[Counter, MeasurementGroup, CounterContainer, Tuple]
_scannable = Union[Axis, Scannable]
# Axis is included explicitly in _scannable as the Scannable protocol evaluates
# all attributes that are part of the protocol during type checking. (py 3.7)
_scannable_or_name = Union[_scannable, str]
_scannable_start_stop_list = List[Tuple[_scannable, _float, _float]]
_position_list = Union[Sequence, numpy.ndarray]
_scannable_position_list = List[Tuple[_scannable, _position_list]]