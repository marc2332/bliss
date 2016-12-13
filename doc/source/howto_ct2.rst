.. currentmodule: bliss.controllers.ct2

.. _bliss-ct2-how-to:

Bliss CT2(P201/C208) how to
===========================

This chapter assumes you have have a running a bliss configuration server
(beacon) available on your system.

The CT2 card has two models:

* *P201*: the :term:`PCI` version of the card

  * 8 input channels
  * 2 input/output channels

* *C208*: the :term:`cPCI` version of the card

  * 10 input channels
  * 2 input/output channels

.. important::
    The CT2 bliss software has only been tested in a limited environment:

    * **one** card.
    * Only the *P201* has been fully tested (*C208* not tested).
    * When card software is initialized, channel 10 is automatically
      configured to generate *output_gate* in :term:`TTL` level
    * Missing external trigger modes

    Please contact the bliss development team if any of these missing
    features is blocking for you.

Supported acquisition types
---------------------------

Before explaining how to configure and run the CT2 card, here is a brief
summary of the current acquisition types supported by the CT2:

Point period
    The time which corresponds to acquisition of one single point.
    This period is sub-divided in exposure time and a dead time.

Exposure time
    The time during which the input channels are enabled to count

.. the following diagrams need wavedrom sphinx extension
.. I used a WYSIWYG editor: www.wavedrom.com/editor.html

.. rubric:: Internal Trigger Single

.. wavedrom::
    {
      signal: [
        { node: ".a...........b", period: 1 },
        { name: "output gate",
          wave: "lH.lh.lh.lh.l", period: 1, },
        { node: ".c..d..."},
        { node: ".e.f"},
      ],

      edge: [ "a<->b Nb. points (N) = 4;",
              "c<->d Point period", "e<->f Exp. time" ],

      head: {
        tick:-1,
      },

      foot: {
        text: "1 soft. start; 0 soft. triggers",
      }
    }

.. pull-quote::
    Start by software. Trigger by internal clock. Internal clock determines
    exposure time and point period.

    Note that in this mode, the acquisition finishes after the last
    *point period*, where in non *single* modes it ends right after *exposure
    time* ends.

.. rubric:: Internal Trigger Multi

.. wavedrom::
    {
      signal: [
        { node: "..a.....................b", period: 0.5 },
        { name: "output gate",
          wave: "l.H...lH...l..H...l.H...l", period: 0.5 },
        { node: "..c...d", period: 0.5 },
      ],

      edge: [ "a<->b Nb. points (N) = 4",
              "c<->d Exp. time" ],

      head: {
        tick:-1,
      },

      foot:{
        text: "1 soft. start; N-1 soft. triggers",
      },
    }

.. pull-quote::
    Start by software. Hardware takes one single point. Each point is
    triggered by software. Internal clock determines exposure time.

.. rubric:: Internal Trigger Readout

.. wavedrom::
    {
      signal: [
        { node: "..a...............b", period: 0.5  },
        { name: "output gate",
          wave: "l.H...h...h...h...l", period: 0.5 },
        { node: "..c...d", period: 0.5 },
      ],

      edge: [ "a<->b Nb. points (N) = 4",
              "c<->d Exp. time" ],

      head: {
        tick:-1,
      },

      foot: {
        text: "1 soft. start; 0 soft. triggers",
      },
    }

.. pull-quote::
    Start by software. Trigger by internal clock which determines exposure time.
    Trigger ends previous acquisition and starts the next with no dead time.

    This mode is similar to *Internal Trigger Single* when *point period*
    equals *exposure time* (ie, no dead time).

.. rubric:: Software Trigger Readout

.. wavedrom::
    {
      signal: [
        { node: "..a...................b", period: 0.5  },
        { name: "output gate",
          wave: "l.H.H......H...H......L", period: 0.5, },
      ],

      edge: [ "a<->b Nb. points (N) = 4" ],

      head: {
        tick:-1,
      },

      foot:{
        text: "1 soft. start; N soft. triggers",
      },
    }

.. pull-quote::
    Start by software; trigger by software. Trigger ends previous acquisition
    and starts next with no dead time.

.. rubric:: External Trigger Single

.. wavedrom::
    {
      signal: [
        { node: ".a...........b" },

        { name: "ext. trigger",
          wave: "lPddd",
        },
        { name: "out. gate",
          wave: "lh.lh.lh.lh.l"},
        { node: ".c..d..."},
        { node: ".e.f"},
      ],

      edge: [ "a<->b Nb. points (N) = 4;",
              "c<->d Point period", "e<->f Exp. time" ],

      head: {
        tick:-1,
      },

      foot: {
        text: "1 external trigger start",
      }
    }

.. pull-quote::
    Start by external trigger. Trigger by internal clock.
    Internal clock determines exposure time and point period.

    Note that in this mode, the acquisition finishes after the last
    *point period*, where in non *single* modes it ends right after *exposure
    time* ends.

    This mode is similar to *Internal Trigger Single* except that the start
    is done by an external trigger instead of software.

.. rubric:: External Trigger Multi


.. _bliss-ct2-driver-how-to:

Driver installation
-------------------

The driver is available as an external project. If you are at ESRF_ you
can install it with blissinstaller tool.

For reference, here is a link to the
`CT2 driver project on gitlab <http://gitlab.esrf.fr/Hardware/P201>`_.

.. _bliss-ct2-yaml-how-to:

YAML_ configuration
-------------------

First, you need a valid CT2 card configuration in beacon:

.. code-block:: yaml

   plugin: ct2           # (1)
   class: P201           # (2)
   name: p201_lid001_0   # (3)
   address: /dev/ct2_0   # (4)

#. plugin name: mandatory, must be the string *ct2*
#. class: mandatory, either *P201* (PCI card) or *C208* (compact PCI card)
#. card name: mandatory, unique name
#. card address: mandatory, */dev/ct2_<N>* where *N* is the card index,
   starting at 0.

After saving the file, we propose to configure the different card channels
using the bliss configuration web GUI. Start a web browser pointing to the
beacon host and web app port (ex: lid001:9030) and you should see your newly
created YAML_ file. Clicking on the *p201_lid001_0* node will show the CT2
configuration panel which you can use to configure the different channels
TTL/NIM level, 50ohm:

.. image:: _static/CT2/config.png

.. important::
    In this preliminary version, by default, the channel 10 is assigned
    to generate gate output in TTL so any YAML_ configuration will be
    overwritten on this channel.


The card is now accessible from a python program/console *on the same
machine the card is installed*::

    from gevent.event import Event

    from bliss.common.event import connect
    from bliss.controllers.ct2 import AcqMode, AcqStatus, StatusSignal
    from bliss.controllers.ct2 import CT2Device

    p201 = CT2Device(name='p201_lid001_0')

    p201.acq_mode = AcqMode.IntTrigReadout
    p201.acq_expo_time = 1E-3               # 1ms acq time
    p201.acq_nb_points = 5000               # 5000 points
    p201.acq_channels = 3, 5                # use channels 3 and 5

    finish_event = Event()

    def on_card_status_changed(status):
        print status
        if status == AcqStatus.Ready:
            finish_event.set()

    connect(p201, StatusSignal, on_card_status_changed)

    p201.prepare_acq()
    p201.start_acq()

    finish_event.wait()

    data = p201.read_data()

This is usually not very useful since you need to be on the same machine were the
card is installed.

.. _bliss-ct2-tango-how-to:

TANGO_ configuration
--------------------

To work around this limitation bliss provides two CT2 TANGO_ components that
help access CT2 as if you were using it locally:

* The server class: :class:`bliss.tango.servers.ct2_ds.CT2`
  (and a CT2 server script to launch a server capable of handling CT2 devices)
* The client class: :class:`bliss.tango.clients.ct2.CT2Device`

To configure a new CT2 server in Jive just go to the menu bar, select
:menuselection:`Edit --> Create server` and type in the following:

.. image:: _static/CT2/tango_create_server.png

You should replace *p201_lid001_0* with a name at your choosing.

The final step in configuring the server is to add a property called
*card_name*. Its value should be the name of the object you gave in the YAML_
configuration:

.. image:: _static/CT2/tango_create_server_property.png

.. versionadded:: 0.2
    If the *server instance name* matches the *card_name* (which is the case in
    the previous example), it is not necessary to specify the *card_name*
    property.

After starting the device server, you can access the CT2 card remotely from
python as if you were using the local
:class:`~bliss.controllers.ct2.device.CT2Device`. The only differences are you
get the :class:`~bliss.tango.clients.ct2.CT2Device` object from
:mod:`bliss.tango.clients.ct2` instead of :mod:`bliss.controllers.ct2` and in
the constructor you pass in the TANGO_ device name::

    from gevent.event import Event

    from bliss.common.event import connect
    from bliss.config.static import get_config
    from bliss.controllers.ct2 import AcqMode, AcqStatus, StatusSignal
    from bliss.tango.clients.ct2 import CT2Device

    p201 = CT2Device('id00/ct2/p201_lid001_0')

    p201.acq_mode = AcqMode.IntTrigReadout
    p201.acq_expo_time = 1E-3               # 1ms acq time
    p201.acq_nb_points = 5000               # 5000 points
    p201.acq_channels = 3, 5                # use channels 3 and 5

    finish_event = Event()

    def on_card_status_changed(status):
        print status
        if status == AcqStatus.Ready:
            finish_event.set()

    connect(p201, StatusSignal, on_card_status_changed)

    p201.prepare_acq()
    p201.start_acq()

    finish_event.wait()

    data = p201.read_data()


SPEC configuration
------------------

bliss also provides a *ct2.mac* macro counter/timer so it can be used from spec.

To configure the CT2 you need to have previously configured TANGO_ CT2 device
(see :ref:`bliss-ct2-tango-how-to`).

Don't forget to add in setup *need ct2*.

Enter **config** and in the *Motor and Counter Device Configuration (Not CAMAC)*
screen, in the SCALERS list add a new item so it looks like this::

    SCALERS        DEVICE                    ADDR  <>MODE  NUM                 <>TYPE
        YES           ct2  id00/ct2/p201_lid001_0           11    Macro Counter/Timer

After, in the *Scaler (Counter) Configuration* screen, add the counters and/or
timer (don't forget that the *Unit* is the nth-1 device in the list of Macro
Counter or Macro Counter/Timer on the previous screen).

If you add a CT2 timer, the *Chan* must be **0**. The CT2 timer is capable of
working in 6 different frequencies: 1.25 KHz, 10 KHz, 125 KHz, 1 MHz, 12.5 MHz
and 100 MHz. The spec *Scale Factor* selects this frequency. The standard
working frequency is 1 MHz which correspondes to a *Scale Factor* of 1E6.
Example::

    Scaler (Counter) Configuration

    Number        Name  Mnemonic  <>Device  Unit  Chan   <>Use As  Scale Factor
         0     Seconds       sec   MAC_CNT     0     0   timebase       1000000
         1      p201_3    p201_3   MAC_CNT     0     3    counter             1
