BLISS is primarily a Python library, thus BLISS can be embedded into any Python
program.

## Using BLISS as a library

BLISS modules can be used in any python environment. In order to work correctly
the environment variables `BEACON_HOST` and potentially `TANGO_HOST` must be present.

!!! note
    Have a look at the ["Use Bliss without Hardware"](installation.md#use-bliss-without-hardware)
    section in case you want to have a look at this BLISS feature without
    disturbing beamline operation.
    The examples given below are based on the provided _test_configuration_.

Start a simple python shell e.g. like this:

```bash
$ TANGO_HOST=localhost:20000 BEACON_HOST=localhost python
```

of course the values of `TANGO_HOST` and `BEACON_HOST` have to be changed to the
appropriate values - or not to be set at all if they are available in the
environment already.

The entry-point to work with objects configured in BEACON is:

```python
>>> from bliss.config import static
>>> config = static.get_config()
```

### Using objects provided by BEACON
To work with specific objects they can be imported via `config.get`:

```python
>>> transfocator = config.get('transfocator_simulator')
>>> print(transfocator.__info__())
Transfocator transfocator_simulator:
P0   L1  L2  L3   L4  L5  L6   L7  L8
OUT  IN  IN  OUT  IN  IN  OUT  IN  IN
```

### Using a BLISS session in library mode
To be able to run scans it is best pratice to import a defined BLISS session
and access objects defined in the session via `session.env_dict`

```python
>>> session =  config.get('test_session')
>>> session.setup()
>>> roby = session.env_dict['roby']
>>> roby.position
2.1
```

To run a standard scan the module `bliss.common.scans` can be used:

```python
>>> from bliss.common.scans import loopscan
>>> loopscan(3,.1,session.env_dict['diode'])
Scan(number=32, name=loopscan, path=/tmp/scans/test_session/data.h5)
```

Saving related settings can be configured via `session.scan_saving`:

```python
>>> session.scan_saving.data_filename='my_new_file'
>>> print(session.scan_saving.__info__())
Parameters (default) - 

  .base_path            = '/tmp/scans'
  .data_filename        = 'my_new_file'
  .user_name            = 'pithan'
  .template             = '{session}/'
  .images_path_relative = True
  .images_path_template = 'scan{scan_number}'
  .images_prefix        = '{img_acq_device}_'
  .date_format          = '%Y%m%d'
  .scan_number_format   = '%04d'
  .session              = 'test_session'
  .date                 = '20191211'
  .scan_name            = 'scan name'
  .scan_number          = 'scan number'
  .img_acq_device       = '<images_* only> acquisition device name'
  .writer               = 'hdf5'
  .creation_date        = '2019-11-12-15:32'
  .last_accessed        = '2019-12-11-12:00'
------  ---------  -------------------------------
exists  filename   /tmp/scans/test_session/data.h5
exists  root_path  /tmp/scans/test_session/
------  ---------  -------------------------------
```

## BLISS and IPython

For a BLISS-friendly IPython console can be started like this:

```bash
python -c "import gevent.monkey; gevent.monkey.patch_all(thread=False); import IPython; IPython.start_ipython()"
```

## Using BLISS shell and BLISS in library mode in parallel
It is possible to run e.g. a session in the ["BLISS command line"](shell_cmdline.md)
and access it at the same time in library mode. In this case there are two different
python processes running that don't share the same object instances howver states are
shared via BEACON (wherever implemented) e.g. the position and state of an axis will
be in sync in the two processes.

!!! warning "Concurrent hardware access"
    Each of the two python processes may communicate directly with hardware.
    As for now there is no locking mechanism implented to prevent concurrent
    hardware access.

## Technical details

BLISS is built on top of [gevent](http://www.gevent.org/), a
coroutine-based asynchronous networking library. Under the hood,
gevent works with a very fast control loop based on
[libev](http://software.schmorp.de/pkg/libev.html) (or
[libuv](http://docs.libuv.org/en/v1.x/)).

The loop has to be running in the host program. When BLISS is
imported, gevent monkey-patching is applied automatically (except for
the threading module). In most cases, this is transparent and does not
require anything from the host Python program.

!!! note
    When using BLISS from a command line or from a graphical
    interface, gevent needs to be inserted into the events loop.

The line above launches Python, makes sure Python standard library is
patched, without replacing system threads by gevent greenlets (which
seems like a reasonable option), then starts the IPython interpreter.

From now on it is possible to use BLISS as any Python library:

```python
from bliss.common.axis import Axis

from bliss.controllers.motors import icepap

ice = icepap.Icepap("iceid2322", {"host": "iceid2322"},
                   [("mbv4mot", Axis,
                   {"address":1,"steps_per_unit":817,
                   "velocity": 0.3, "acceleration": 3
                   })], [], [], [])

ice.initialize()

mbv4 = ice.get_axis("mbv4mot")

mbv4.position()
>>>  0.07099143206854346
```

The example above creates an IcePAP motor controller instance,
configured with a `mbv4mot` axis on IcePAP channel 1. Then, the
controller is initialized and the axis object is retrieved to read the
motor position.

!!! note
    This example is meant to demystify BLISS -- the only recommended
    way to use BLISS is to rely on BLISS Beacon to get configuration
    and to use the BLISS shell as the preferred command line
    interface.

