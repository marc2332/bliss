bliss: ESRF Motion control library
====================================

EMotion is a Python package developed at the ESRF within the Beamline
Control Unit by Matias Guijarro, Cyril Guilloud and Manuel Perez.

Bliss provides uniform Python objects and a full set of standard
features on top of motor controllers plugins.

Bliss is built around simple concepts:
* Configuration
* Controller
* Axis
* Group

Writing a new motor controller plugin can be done within minutes just
by filling predefined entry points to implement the communication
protocol with the motor controller, leaving more complicated logic to
Bliss base classes. Bliss also brings the possibility to create
pseudo axes, calculated from real ones.

Under the hood Bliss relies on [gevent](http://www.gevent.org), a
coroutine-based Python networking library that uses greenlet to
provide a high-level synchronous API on top of the libev event
loop. On Linux systems, gevent offers maximum performance and minimum
burden to communicate efficiently with Ethernet, Serial or USB motor
controllers.

Bliss is meant to be a building block for automation software or
experiment control sequencers running the gevent loop, which opens a
wide range of possibilities.

To be easy to use, we keep EMotion API simpliest as possible.

Bliss is shipped with a generic Tango device server.
[TANGO](http://www.tango-controls.org)

Controllers supported in EMotion :
*2014-01 : FlexDC.py      Nanomotion flexdc piezo rotation
*2014-01 : IcePAP.py      ESRF IcePap
*2014-01 : PI_E753.py     PI E-753 piezo actuators controller
*2014-02 : PI_E517.py     PI E-517 piezo actuator controller
*2014-04 : PMD206.py      Piezomotor piezo-motors controller
*2014-09 : NF8753.py      Newfocus piezo actuators controller
*2014-11 : GalilDMC213.py Galil stepper motors controller
*2014-11 : VSCANNER.py    ISG voltage controller

Special controllers:
*setpoint.py   Tango attribute as a simple motor (allows scans and ramps)
*mockup.py     Test and demonstration controller
*simpliest.py  Minimal controller example
*PJ31.py       PiezoJack (combination of stepper and pizeo 712)

Calculational controllers
*spectro_eh1_test.py  new ID26 spectrometer prototype
*tab3.py              3 legs table
*tabsup.py            ?
*TangoEMot.py         remote tango motor
*trans4.py            Qsys support for ID22 transfocator
*slits.py             slits
*kb.py                kb support

EMotion features:
*position
*velocity
*acceleration
*acceleration time
*backlash
*errors reporting
*dial / user / controller reference systems
*soft limits
*custom commands
*custom configuration
*configuration management
