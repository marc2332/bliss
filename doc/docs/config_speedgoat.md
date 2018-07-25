# Simulink

Python binding for the Matlab simulink XPC API.

Tested with the Speedgoat box.

## Installation

- login to windows machine
- install python (preferably python >= 3.6, although it should work with 2.7)
- clone this repository (http://gitlab.esrf.fr/bliss/simulink)
- on a the command line, go to the source directory and type: `pip install -e .`

## Run

After installation, run it with:

```bash
$ speedgoat-server 192.168.7.1
Serving XPC speedgoat on tcp://0.0.0.0:8200 ...
```
(replace the IP with your speedgoat box host/IP)

## Tests

To run tests you must first load the tests/BCU_tests.slx simulink model
using Matlab simulink.

Then, since speedgoat only accepts one connection, make sure that:
- you disconnect matlab simulink from the speedgoat and
- no *speedgoat-server* is running

Run tests with:

```bash
$ python setup.py test --speedgoat=192.168.7.1:22222
```
