bliss: ESRF Motion control library
====================================

Bliss is a Python package recently developed at the ESRF within the Beamline Control Unit
by Matias Guijarro, Cyril Guilloud and Manuel Perez.

Bliss provides uniform Python objects and a full set of standard features on top of motor
controllers plugins.

Bliss is built around simple concepts:
* Configuration
* Controller
* Axis
* Group

Writing a new motor controller plugin can be done within minutes just by filling predefined
entry points to implement the communication protocol with the motor controller, leaving more
complicated logic to Bliss base classes. Bliss also brings the possibility to create
pseudo axes, calculated from real ones. 

Under the hood Bliss relies on [gevent](http://www.gevent.org), a coroutine-based Python
networking library that uses greenlet to provide a high-level synchronous API on top of the
libev event loop. On Linux systems, gevent offers maximum performance and minimum burden to
communicate efficiently with Ethernet, Serial or USB motor controllers.

Bliss is meant to be a building block for automation software or experiment control
sequencers running the gevent loop, which opens a wide range of possibilities.

Bliss is shipped with a [TANGO](http://www.tango-controls.org) server. 
