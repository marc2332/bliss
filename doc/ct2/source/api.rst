.. _ct2-api:

-------------
P201/C208 API
-------------

Device API
~~~~~~~~~~

Device level API. Requires beacon configuration to work

.. autosummary::
   :nosignatures:
   :toctree:

   ct2.device.BaseCT2Device
   ct2.device.CT2Device
   ct2.tango.client.CT2Device
   ct2.device.AcqMode
   ct2.device.AcqStatus



Card API
~~~~~~~~

Low level API. Allows to configure/control the P201/C208 cards at a very low
level.


.. autosummary::
   :nosignatures:
   :toctree:

   ct2.ct2.BaseCard
   ct2.ct2.P201Card
   ct2.ct2.C208Card
   ct2.ct2.CtStatus
   ct2.ct2.CtConfig
   ct2.ct2.FilterOutput
   ct2.ct2.AMCCFIFOStatus
   ct2.ct2.FIFOStatus
   ct2.ct2.TriggerInterrupt
   ct2.ct2.CT2Exception
   ct2.ct2.Clock
   ct2.ct2.Level
   ct2.ct2.FilterClock
   ct2.ct2.OutputSrc
   ct2.ct2.CtClockSrc
   ct2.ct2.CtGateSrc
   ct2.ct2.CtHardStartSrc
   ct2.ct2.CtHardStopSrc




