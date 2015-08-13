===================
Getting started
===================

This tutorial shows how to use Juyo in 3 steps:

- configuring data acquisition
- configuring data storage
- starting a continuous scan

First step: data acquisition configuration
------------------------------------------

A continuous scan in Juyo is the combination of **acquisition objects**,
being either **master** or **slaves**, and **data recorder objects**.

Master devices are enabled with synchronization superpowers ; their
responsibility is to **start or trigger** slaves to perform data acquisition
at the right moment.

The link between masters and slaves can be either **hardware**, or **emulated
with software**.

A scan can have **multiple masters**, and masters can also be slaves for
other masters. There is no limit to imagination.

The set of masters and slaves acquisition objects is called an **acquisition
chain**, it is the first thing to configure when defining a new Juyo scan:

.. code-block:: python

   from bliss.common.continuous_scan import AcquisitionChain
     
   chain = AcquisitionChain()

Then, masters and slaves objects have to be created.
Juyo provides 2 base classes:

- ``AcquisitionMaster``
- ``AcquisitionDevice`` 

Those classes are mostly abstract, indeed the idea is to **encapsulate** 
real data acquisition Python objects to turn them into Juyo-compliant
devices. This construct gives a lot of flexibility,
potentially any Python object can become part
of a continuous scan with the appropriate ``AcquisitionMaster`` or
``AcquisitionDevice`` class.

Let's use the standard ``SoftwarePositionTriggerMaster`` class to
make a master triggering slaves on **Emotion axis** positions:

.. code-block:: python

   from bliss.acquisition.motor import SoftwarePositionTriggerMaster

   emotion_master = SoftwarePositionTriggerMaster(m0, 5, 10, 10, time=5)

xxx
