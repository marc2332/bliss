# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""The ESRF_ CT2 (P201/C208) :term:`PCI` counter card

Links to the card manuals:

* `P201 reference manual`_
* `P201 user's manual`_
* `C208 user's manual`_

Quickstart
----------

This documentation provides a concise guide on how to configure and start working
with a CT2 card. Take a look at the BLISS documentation for a complete explanation.

This chapter assumes you already have a ESRF_ CT2 (P201/C208) :term:`PCI`
counter card and driver installed.

The bliss library provides a *CT2* device object which may be local or
remote.

* :class:`~bliss.controllers.ct2.client.CT2` - a remote CT2 device. This
  object is probably the one you will use most of the times. It talks to
  a remote CT2 through bliss rpc. The bliss RPC server runs on the machine
  where the card is physically installed in a PCI/cPCI slot.

* :class:`~bliss.controllers.ct2.device.CT2` - a local CT2 device. This
  object is instantiated by the bliss rpc server

.. note::

   A very low level :class:`~bliss.controllers.ct2.card.CT2Card` is also
   available. It talks directly to CT2 driver and provides a direct map over the
   card configuration (you will only use this API in exceptional cases where you
   need complete control over the card configuration).


You can instantiate the :class:`CT2` from a beacon configured card:

.. code-block:: yaml

   plugin: ct2                      (1)
   class: CT2                       (2)
   name: my_p201                    (3)
   address: tcp://lid312:8005       (4)

#. plugin name (mandatory: ct2)
#. controller name (mandatory)
#. plugin class (mandatory)
#. card address (mandatory). Use `/dev/ct_<card_nb>` for a local card or
   `tcp://<host>:<port>` to connect to a remote bliss rpc CT2 server.

Like this::

    from bliss.config.static import get_config

    config = get_config()
    p201 = config.get('my_p201')


... or without using beacon. In this case your are responsible at runtime
for the card configuration::

    from bliss.controllers.ct2.client import CT2

    p201 = CT2('tcp://lid312:8005')


Accessing the card directly from the PC where the card is installed::

    from bliss.controllers.ct2.card import P201Card, CardInterface
    from bliss.controllers.ct2.device import CT2

    iface = CardInterface('/dev/ct2_0')
    p201_card = P201Card(iface)
    p201_card.request_exclusive_access()
    p201_card.reset_software()

    p201 = CT2(p201_card)


API Reference
-------------

Device API
~~~~~~~~~~

Device level API. Requires beacon configuration to work

.. autosummary::
   :toctree:

   device

Card API
~~~~~~~~

Low level API. Allows to configure/control the P201/C208 cards at a very low
level.


.. autosummary::
   :nosignatures:
   :toctree:

   card

.. _P201 reference manual:
   http://www.esrf.eu/files/live/sites/www/files/Industry/files/p201.pdf
.. _P201 user's manual:
   http://intranet.esrf.fr/ISDD/detector-and-electronics/electronics/DigitalElectronicsLab/Publications/released/p201
.. _C208 user's manual:
   http://intranet.esrf.fr/ISDD/detector-and-electronics/electronics/DigitalElectronicsLab/Publications/released/c208
"""


def create_objects_from_config_node(config, node):
    name = node.get("name")
    klass = node.get("class")
    if klass == "CT2":
        address = node["address"]
        if address.startswith("tcp://"):
            from . import client as module
        else:
            from . import device as module
    else:
        from . import card as module
    return module.create_object_from_config_node(config, node)
