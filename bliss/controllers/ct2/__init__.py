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

The :ref:`CT2 how-to <bliss-ct2-how-to>` provides a concise guide on how to
configure and start working with a CT2 card.

This chapter assumes you already have a ESRF_ CT2 (P201/C208) :term:`PCI`
counter card and driver installed.

The bliss library provides two objects:

* :func:`CT2Card` - low level card. Talks directly to CT2 driver and provides a
  direct map over the card configuration (you will only use this API in
  exceptional cases where you need complete control over the card
  configuration).

* :class:`CT2Device` - an abstraction over the :func:`CT2Card` providing a much
  a much simpler and more intuitive API. It uses the :func:`CT2Card` internally.

You can instantiate the :class:`CT2Device` from a beacon configured card::

    from bliss.controllers.ct2 import CT2Device

    dev = CT2Device(name='my_p201')

... or from without using beacon. In this case your are responsible at runtime
for the card configuration::

    from bliss.controllers.ct2 import P201Card, CT2Device

    p201 = P201Card('/dev/ct2_0')

    p201_card.request_exclusive_access()
    p201_card.reset_software()

    dev = CT2Device(card=p201)


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
   ~bliss.controllers.ct2.ct2.CT2Card
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

