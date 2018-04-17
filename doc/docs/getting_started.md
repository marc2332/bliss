# Getting started with BLISS

## Installation at ESRF

At ESRF, it is recommended to follow Beamline Control Unit guidelines for
software installation. In the case of BLISS, a special deployment procedure
has been put in place in order to facilitate the work on beamlines.

Follow instructions [here][1].

## Installation outside ESRF

### Using pip

There is no BLISS package yet, so BLISS has to be installed from the source.
The first step is to clone the [BLISS git repository][2] to get the BLISS project source code:

    $ git clone git://gitlab.esrf.fr/bliss/bliss

The line above creates a `bliss` directory in current directory, containing the
whole project source files. BLISS provides a Python setuptools script, so it
is possible to proceed with installation using `pip`:

    $ cd bliss
    $ pip install .

!!! note
    Recent versions of `setuptools` and `pip` are needed. It may
    be required to upgrade.

BLISS has many dependencies, therefore it is highly recommend to install BLISS
in a virtual environment.

BLISS requires additional, non-Python dependencies:

* redis server

### Using Conda

The use of [Conda][3] is recommended to install all dependencies. BLISS distribution contains a
`requirements-conda.txt` file to help with the installation. Creating a `bliss` Conda environment
can be done like this:

    $ cd bliss
    $ conda env create -n bliss -f ./requirements-conda.txt

Not all packages are available on standard Conda repositories. Remaining packages can then be
installed via `pip` to complete installation:

    $ pip install .

## Beacon configuration server

BLISS relies on its Beacon (BEAmline CONfiguration) server to get access to
beamline configuration. The configuration is a set of [YAML][7] files,
containing all the information needed to build BLISS objects, including user
sessions, beamline devices, scans sequences, etc.
Examples of BLISS YAML configuration files can be found in BLISS distribution
in `tests/test_configuration/`.

[Read more about Beacon and configuration](config.md)

### ESRF installation

At ESRF, the BLISS installation procedure automatically adds Beacon to the set
of daemons started by the system:

* The port number for the Beacon server is set to 25000
* The YAML files directory is set to `/users/blissadm/local/beamline_configuration`
* The configuration web application is available at `http://localhost:9030`
* The Beacon TANGO database service is disabled

### Custom installation

It is required to start Beacon server using `--db_path` to specify the path to the YAML configuration files:

    $ beacon_server --db_path=~/local/beamline_configuration

It is also a good idea to fix the bliss configuration server port number
(otherwise, by default, Beacon will just choose the first free port it finds):

    $ beacon_server --db_path=~/local/beamline_configuration --port=25000

Clients will then need to setup the `BEACON_HOST` environment variable to
point to `<machine>:<port>` (example: `id31:25000`).

The web configuration UI has to be enabled, by specifying the web application port number using `--webapp_port`:

    $ beacon_server --db_path=~/local/beamline_configuration --port=25000 --webapp_port=9030

BLISS Beacon server is also able to provide a full TANGO database server service that integrates nicely with the BLISS configuration. To start this service it is just needed to provide the TANGO port that you want the TANGO database server to serve:

    $ beacon_server --db_path=~/local/beamline_configuration --port=25000 --webapp_port=9030 --tango_port=20000

## Configuration example

### YAML files tree

The following tree shows an example of how YAML files can be organised within the BLISS Beacon `db_path` directory:

    .
    |── bv.yml
    ├── ct2.yml
    ├── musst.yml
    ├── pilatus.yml
    ├── mca
    │   └── falconx.yml
    ├── motors
    │   ├── __init__.yml
    │   ├── ehtable.yml
    └── sessions
        ├── __init__.yml
        └── eh.yml

!!! note
    YAML files are 'transparent', i.e. files and directories can be
    freely organised, and file names are in fact ignored by Beacon.
    The important information is the `name` of each individual object defined
    in the configuration.

Each kind of object in the configuration is associated with a configuration plugin. The configuration plugin interprets
configuration information. Depending on the plugin, different objects can be instantiated from the same configuration.

Beacon supports the following plugins:

* `default`, converts YAML data in a Python dictionary
* `bliss`, general-purpose control objects
* `emotion`, axes, encoders, shutters and motor controllers configuration
* `temperature`, inputs, outputs, loops for temperature controllers
* `session`, to define `Session` objects

It is possible to specify additional configuration information for the files of an entire directory by adding data in a `__init__.yml` file.

When grouping similar configuration information in a directory, it is quite useful to specify the plugin in a `__init__.yml` file, for example for motors:

#### ./motors/\_\_init\_\_.yml

    plugin: emotion

All files in this directory will use the `emotion` plugin by default.

### Icepap controller configuration

(example from ID23-2)

#### slits.yml

```YAML
- controller:
    class: icepap
    host: iceid2322
    axes:
        -   name: ts2f
            address: 4
            steps_per_unit: 1000
            velocity: 0.5
            acceleration: 5
            tolerance: 0.001
            backlash: 0.1
        -   name: ts2b
            address: 5
            steps_per_unit: -1000
            velocity: 0.5
            acceleration: 5
            tolerance: 0.001
            backlash: 0.1
```

The plugin is not specified in `slits.yml`, because a `__init__.yml` with
`plugin: emotion` already exists in the directory.

`controller` is a reserved key for the `emotion` plugin: it indicates which motor controller to configure.
In this example, the controller class is set to `icepap`. The IcePAP BLISS controller expects `host` to be
configured, to know to which IcePAP master it corresponds.
The `iceid2322` IcePAP controller is declared, and two motors `ts2f` and `ts2b` are configured.

The different fields to be specified under `axes` depends on the controller.
In the case of the IcePAP controller, `address` is one of the specific parameters.
Other parameters are:

* `steps_per_unit`, optional (1), $steps.unit^{-1}$
    - can be negative
* `velocity`, **mandatory**, in $unit.s^{-1}$
* `acceleration`, **mandatory**, in $unit.s^{-2}$
* `backlash`, optional (0), in $unit$
* `tolerance`: optional (0), in $unit$
     - in case of motor in closed loop, tolerance for discrepancy check when moving a motor

[Read more about motor controllers configuration](config_motctrl.md)

### Horizontal slits configuration

(example from ID23-2)

#### slits.yml (cont.)

```YAML
- controller:
    class: slits
    slit_type: horizontal
    axes:
    - name: $ts2f
      tags: real front
      tolerance: 0.002
    - name: $ts2b
      tags: real back
      tolerance: 0.002
    - name: ts2hg
      tags: hgap
      tolerance: 0.002
    - name: ts2ho
      tags: hoffset
      tolerance: 0.002
```

* `slit_type` is needed for class `slits`
* axes use the `tag` attribute to know the role of each axis in the declared slits controllers
    - `real` means the axis is a real motor, declared elsewhere; the name has to be a **reference** to an existing axis (starting with `$`)
    - `front`, `back`, `hgap`, `hoffset` are specifiers for each axis
    - non-real axes are considered pseudo axes (calc. motor)

### Pilatus detector configuration

(example from ID15)

#### pilatus.yml file

```YAML
plugin: bliss
name: pilatus
class: Lima
tango_url: id15a/limaccds/pilatus2m
```

[Read more about 2D detectors configuration](config_lima.md)

### Session configuration

A session groups objects from configuration under a single name, associated with a setup file. The setup file is a
Python script, that is executed after session objects are loaded.
This can be used to add small users scripts to the global namespace. A session also defines a way to call user
scripts, stored with the configuration files.

[Read more about Session configuration](config_session.md)

#### Files organisation
    .
    |── ...
    ├── sessions
        ├── id232.yml
        ├── id232_setup.py
        ├── __init__.yml
        └── scripts
            ├── beam_size.py
            |...

`__init__.yml` contains `plugin: session` ; then, all YAML files in the directory are loaded using the Session plugin.

#### Example session YAML file

```yaml
- class: Session
  name: id23-2
  setup-file: ./id232_setup.py
```

`id232.yml` defines a session called `id23-2`, with a `id232_setup.py` setup file.

By default, **all objects** defined in the configuration will be loaded in the session.
It is possible to specify which objects must be included or not by using the `include-objects` keyword with the
list of object names:

```yaml
    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      include-objects: [pzth, simul_mca]
```

Conversely, `exclude-objects` can be used to avoid to load unused objects.

#### Setup file

```python
import os
from bliss.common.standard import * # import all default functions, scans, etc.

SCAN_SAVING.base_path = os.path.join(os.environ["HOME"], "scans")
SCAN_SAVING.template = "{session}/{date}"
print "Setting scanfile to", SCAN_SAVING.get_path()
```

All objects from the session are available in the setup script. The globals defined in the setup script, and all session
objects, are automatically added to the `bliss.setup_globals` namespace, to be used in user scripts.

#### User scripts

Python files defined under a session `script` directory can be loaded in the setup file
using the `load_script('script_name')` function. In case of error, the function catches and
display exceptions, but do not prevent the rest of the setup from executing. Each call to `load_script`
reloads the Python script again.
`load_script` is the equivalent of the `execfile` Python function, but for session scripts.

!!! note
    User scripts in a session should be reserved for small functions and helpers.
    More complex code should be moved to a proper beamline project with revision
    control, tests and documentation.

## BLISS shell

BLISS comes with a command line interface based on [ptpython](8):

    $ bliss -h

    Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>]
           bliss [-v | --version]
           bliss [-h | --help]
           bliss --show-sessions
           bliss --show-sessions-only

    Options:
        -l, --log-level=<log_level>   Log level [default: WARN] (CRITICAL ERROR INFO DEBUG NOTSET)
        -s, --session=<session_name>  Start with the specified session
        -v, --version                 Show version and exit
        -h, --help                    Show help screen and exit
        --show-sessions               Display available sessions and tree of sub-sessions
        --show-sessions-only          Display available sessions names only


The `-s` command line argument loads the specified session at startup, i.e. configuration objects
defined in the session are initialized, then the setup file is executed. Finally the prompt
returns to user:

    $ bliss -s eh1
                           __         __   __
                          |__) |   | /__` /__`
                          |__) |__ | .__/ .__/


    Welcome to BLISS version 0.01 running on pcsht (in bliss Conda environment)
    Copyright (c) ESRF, 2015-2017
    -
    Connected to Beacon server on pcsht (port 3412)
    eh1: Executing setup...
    Initializing 'pzth`
    Initializing 'simul_mca`
    Initializing 'pzth_enc`
    Done.

    EH1 [1]:

[Learn more about BLISS shell](bliss_shell,md)

## BLISS library

BLISS is primarily a Python library, thus BLISS can be embedded into any Python
program.

BLISS is built on top of [gevent][4], a coroutine-based asynchronous networking
library. Under the hood, gevent works with a very fast control loop based on [libev][5] (or [libuv][6]).
The loop has to be running in the host program. When BLISS is imported, gevent monkey-patching is
applied automatically (except for the threading module). In most cases, this is
transparent and does not require anything from the host Python program.

!!! note
    When using BLISS from a command line or from a graphical      
    interface, gevent needs to be inserted into the events loop.

For example a BLISS-friendly IPython console can be started like this:

    $ python -c "import gevent.monkey; gevent.monkey.patch_all(thread=False); import IPython; IPython.start_ipython()"

The line above launches Python, makes sure Python standard library is patched, without replacing system
threads by gevent greenlets (which seems like a reasonable option), then starts the IPython interpreter.

From now on it is possible to use BLISS as any Python library:

```python
    In [1]: from bliss.common.axis import Axis

    In [2]: from bliss.controllers.motors import icepap

    In [3]: iceid2322 = icepap.Icepap("iceid2322", {"host": "iceid2322"},
                                      [("mbv4mot", Axis, { "address":1,"steps_per_unit":817,
                                      "velocity": 0.3, "acceleration": 3
                                      })], [], [], [])

    In [4]: iceid2322.initialize()

    In [5]: mbv4 = iceid2322.get_axis("mbv4mot")

    In [6]: mbv4.position()
    Out[6]: 0.07099143206854346

    In [7]:
```

The example above creates an IcePAP motor controller instance, configured with a `mbv4mot` axis on
IcePAP channel 1. Then, the controller is initialized and the axis object is retrieved to read the
motor position.

!!! note
    This example is meant to demystify BLISS -- the only recommended way to use BLISS is to
    rely on BLISS Beacon to get configuration and to use the BLISS shell as the preferred
    command line interface.




[1]: https://gitlab.esrf.fr/bliss/ansible
[2]: https://gitlab.esrf.fr/bliss/bliss
[3]: https://conda.io/docs/
[4]: http://www.gevent.org
[5]: http://software.schmorp.de/pkg/libev.html
[6]: http://libuv.org/
[7]: https://en.wikipedia.org/wiki/YAML
[8]: https://github.com/jonathanslenders/ptpython
