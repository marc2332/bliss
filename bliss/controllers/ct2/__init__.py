# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""The ESRF_ CT2 (P201/C208) :term:`PCI` counter card

Links to the card manuals:

* `P201 reference manual`_
* `P201 user's manual`_
* `C208 user's manual`_

Quickstart
----------

It assumes you already have an ESRF_ CT2 (P201/C208) :term:`PCI` counter card
and driver installed.

A Minimal Application
~~~~~~~~~~~~~~~~~~~~~

.. rubric:: Beacon pre-configured

A minimal usage looks something like this::

    from bliss.config.static import get_config
    from bliss.controllers.ct2 import AcqMode

    cfg = get_config()

    ct2_device = cfg.get('my_p201')

    ct2_device.acq_mode = AcqMode.IntTrigReadout
    ct2_device.acq_expo_time = 1E-3
    ct2_device.acq_point_period = 0
    ct2_device.acq_nb_points = 5


.. rubric:: Standalone

Minimalistic usage, accesing the low level card API
(you will only use this API in exceptional cases where you need
complete control over the card configuration)::
 
    from bliss.controllers.ct2 import P201Card

    # (CT2 driver must be installed as /dev/ct2_0)
    p201 = P201Card('/dev/ct2_0')

    p201.request_exclusive_access()
    p201.reset_software()

    for i in range(10):
        print(p201.get_test_reg())


API Reference
-------------

Device API
~~~~~~~~~~

Device level API. Requires beacon configuration to work

.. autosummary::
   :toctree:

   ~bliss.controllers.ct2.device.BaseCT2Device
   ~bliss.controllers.ct2.device.CT2Device
   ~bliss.controllers.ct2.device.AcqMode
   ~bliss.controllers.ct2.device.AcqStatus

Card API
~~~~~~~~

Low level API. Allows to configure/control the P201/C208 cards at a very low
level.


.. autosummary::
   :nosignatures:
   :toctree:

   ~bliss.controllers.ct2.ct2.BaseCard
   ~bliss.controllers.ct2.ct2.P201Card
   ~bliss.controllers.ct2.ct2.C208Card
   ~bliss.controllers.ct2.ct2.CtStatus
   ~bliss.controllers.ct2.ct2.CtConfig
   ~bliss.controllers.ct2.ct2.FilterOutput
   ~bliss.controllers.ct2.ct2.AMCCFIFOStatus
   ~bliss.controllers.ct2.ct2.FIFOStatus
   ~bliss.controllers.ct2.ct2.TriggerInterrupt
   ~bliss.controllers.ct2.ct2.CT2Exception
   ~bliss.controllers.ct2.ct2.Clock
   ~bliss.controllers.ct2.ct2.Level
   ~bliss.controllers.ct2.ct2.FilterClock
   ~bliss.controllers.ct2.ct2.OutputSrc
   ~bliss.controllers.ct2.ct2.CtClockSrc
   ~bliss.controllers.ct2.ct2.CtGateSrc
   ~bliss.controllers.ct2.ct2.CtHardStartSrc
   ~bliss.controllers.ct2.ct2.CtHardStopSrc



.. _P201 reference manual:
   http://www.esrf.eu/files/live/sites/www/files/Industry/files/p201.pdf
.. _P201 user's manual:
   http://intranet.esrf.fr/ISDD/detector-and-electronics/electronics/DigitalElectronicsLab/Publications/released/p201
.. _C208 user's manual:
   http://intranet.esrf.fr/ISDD/detector-and-electronics/electronics/DigitalElectronicsLab/Publications/released/c208
"""

from .ct2 import *
from .device import *

