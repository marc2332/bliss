# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Communication (:class:`~bliss.comm.gpib.Gpib`, :class:`~bliss.comm.tcp.Tcp`, \
:class:`~bliss.comm.serial.Serial`, etc)

This module gathers different communication interfaces

.. autosummary::
   :toctree:

   embl
   gpib
   spec
   exceptions
   Exporter
   modbus
   rpc
   scpi
   serial
   tcp
   tcp_proxy
   udp
   util
"""

from bliss.comm.util import get_comm
