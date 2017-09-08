Handel
=============

A python binding for the [handel](http://support.xia.com/default.asp?W381) library.


System requirements
-------------------

The handel DLL files need to be available in `PATH` (`/usr/local/bin` in Cygwin for instance).

Python compatibility:

- python 2.7
- python 3.6


Python requirements
-------------------

Run requirements:

- cffi
- numpy

Test requirements:

- mock
- pytest
- pytest-cov

Those requirements are automatically handled by `setuptools`.


Installation
------------

Run:

``` console
$ python setup.py install
```

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


Tests
-----

Run:

``` console
$ python setup.py test
```

This also publishes an HTML coverage report in the `htmlcov` directory.


Continuous intergration
-----------------------

This project is automatically tested using Gitlab CI.

The tests are run for python 2.7 and 3.6

The coverage report are published [here](http://bliss.gitlab-pages.esrf.fr/python-handel/).


Scripts
-------

A few scripts are provided:

- `parse_error_header.py` which parses `handel_errors.h` and output a dictionnary of handel errors

- `handel-server` which servers the handel interface over the network using zerorpc. It requires:
  * python3
  * handel
  * zerorpc
  * msgpack_numpy


TODO
----

- Improve `handel-server` using argparse.


Contact
-------

Vincent Michel - vincent.michel@esrf.fr
