Handel
=============

A python binding for the [handel](http://support.xia.com/default.asp?W381) library.


System requirements
-------------------

The handel DLL files need to be available in `PATH` (`/usr/local/bin` in Cygwin for instance).

Python compatibility:

- python 3.7

Usage
-----

Example usage:

``` python
>>> from bliss.controllers.mca.handel.interface import *
>>> init('xmap.ini')
>>> start_system()
>>> get_detectors()
['detector1']
>>> get_modules()
['module1']
>>> get_module_type('module1')
'mercury'
>>> get_channels()
(0,)
>>> start_run(0)
>>> stop_run(0)
>>> get_run_data(0)
array([13260, 52275,   256, ...,     0,     0,     0], dtype=uint32)
```

Gevent mode
-----------

Make the interface gevent-compatible using:

``` python
>>> from handel.gevent import patch
>>> patch()
```



Scripts
-------

A few scripts are provided:

- `parse_error_header.py` which parses `handel_errors.h` and output a python dictionnary of handel errors

Entry points
------------

- `bliss-handel-server` which serves the handel interface over the network using bliss rpc.

Contact
-------

Vincent Michel - vincent.michel@esrf.fr
