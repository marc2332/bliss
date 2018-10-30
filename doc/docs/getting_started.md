# Getting started with BLISS

!!! note
    This chapter assumes BLISS is installed, with a running **Beacon** server. See [installation instructions](index.md)
    for more details.

## Configuration example

### YAML files tree

The following tree shows an example of how YAML files can be organized within the BLISS Beacon `db_path` directory:

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
    freely organized, and file names are in fact ignored by Beacon.
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

It is possible to specify additional configuration information for the
files of an entire directory by adding data in a `__init__.yml` file.

#### Default plugin indicator

When grouping similar configuration information in a directory, it is
quite useful to specify the plugin in a `__init__.yml` file:

    plugin: <plugin_name>

Example for a directory containing YML files for motors configuration:

    plugin: emotion


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

[Read more about IcePaP controllers configuration](config_icepap.md)

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

#### Files organization
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
It is possible to specify which objects must be included or not by using the `config-objects` keyword with the
list of object names:

```yaml
    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      config-objects: [pzth, simul_mca]
```

Conversely, `exclude-objects` can be used to avoid to load unused objects.

#### Measurement groups

A measurement group is an object to wrap counters in it. The measurement group helps to deal with a coherent
set of counters. For example, a measurement group can represent counters related to a detector, a hutch or
an experiment.

Measurement groups are loaded by the `session` Beacon plugin, thus it is possible to configure those directly
in a session YAML file:

```yaml
  - class: MeasurementGroup
    name: align_counters
    counters: [simct1, simct2, simct3]

  - class: MeasurementGroup
    name: MG1
    counters: [simct2, simct3]

  - class: MeasurementGroup
    name: MG2
    counters: [simct4, simct5]
```

`counters` must be a list of names, corresponding to `Counter` objects.
[Read more about Counter objects](scan_ctmg.md)

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

## BLISS library

BLISS is primarily a Python library, thus BLISS can be embedded into any Python
program.

BLISS is built on top of [gevent](http://www.gevent.org/), a
coroutine-based asynchronous networking library. Under the hood,
gevent works with a very fast control loop based on
[libev](http://software.schmorp.de/pkg/libev.html) (or
[libuv](http://docs.libuv.org/en/v1.x/)).

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

    In [3]: ice = icepap.Icepap("iceid2322", {"host": "iceid2322"},
                               [("mbv4mot", Axis,
                               {"address":1,"steps_per_unit":817,
                               "velocity": 0.3, "acceleration": 3
                               })], [], [], [])

    In [4]: ice.initialize()

    In [5]: mbv4 = ice.get_axis("mbv4mot")

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

## BLISS shell

BLISS comes with a command line interface based on [ptpython](8):

    % bliss -h
    Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>]
           bliss [-v | --version]
           bliss [-c <name> | --create=<name>]
           bliss [-d <name> | --delete=<name>]
           bliss [-h | --help]
           bliss --show-sessions
           bliss --show-sessions-only
    
    Options:
      -l, --log-level=<log_level>   Log level [default: WARN]
                                    (CRITICAL ERROR INFO DEBUG NOTSET)
      -s, --session=<session_name>  Start with the specified session
      -v, --version                 Show version and exit
      -c, --create=<session_name>   Create a new session with the given name
      -d, --delete=<session_name>   Delete the given session
      -h, --help                    Show help screen and exit
      --show-sessions               Display sessions and tree of sub-sessions
      --show-sessions-only          Display available sessions names only

A specific session can be created using `-c` option:

        % bliss -c eh1
        creating 'eh1' session
        Creating: /blissadm/local/beamline_configuration/sessions/eh1_setup.py
        Creating: /blissadm/local/beamline_configuration/sessions/eh1.yml
        Creating: /blissadm/local/beamline_configuration/sessions/scripts/eh1.py

The `-s` command line option loads the specified session at startup, i.e. configuration objects
defined in the session are initialized, then the setup file is executed. Finally the prompt
returns to user:

        $ bliss -s eh1
                               __         __   __
                              |__) |   | /__` /__`
                              |__) |__ | .__/ .__/


        Welcome to BLISS version 0.01 running on pcsht (in bliss Conda environment)
        Copyright (c) ESRF, 2015-2018
        -
        Connected to Beacon server on pcsht (port 3412)
        eh1: Executing setup...
        Initializing 'pzth`
        Initializing 'simul_mca`
        Initializing 'pzth_enc`
        Done.

        EH1 [1]:

[Learn more about BLISS shell](shell_cmdline.md)

### Examples of standard shell functions

* `wa()` shows a table of all motors in the session, with positions.
* `prdef(func)` displays the source code of a function (if source code is available)
* `lscnt()` shows a table of all counters in the session.

[Learn more about standard shell functions](shell_std_func.md)


## Basic scans

BLISS relies on a powerful scanning engine based on the principle of an **acquisition chain**, i.e. a tree of master and slave devices: master devices trigger acquisition,
whereas slave devices take data. Complex acquisition chains can be built to perform any
kind of data acquisition sequence. [Read more about the BLISS scanning
engine](scan_engine.md)

The acquisition chain for each scan has to be provided by the user. In order to help
with simple scans, BLISS provides a default acquisition chain to perform scans similar
to the default, step-by-step, ones in Spec.

### Default step-by-step scans

BLISS provides functions to perform scans a user would need for usual
step-by-step measurements.

Most common are :

* `ascan(axis, start, stop, n_points, count_time, *counters, **kwargs)`
* `dscan` : same as `ascan`, with `start`, `stop` as relative positions to current axis position
* `a2scan` : same as ascan but with 2 motors
* `mesh` to makes a grid using 2 motors
* `timescan` to count without moving a motor

All scans can take counters in the arguments list. This is to limit the scan to the
provided list of counters.

More about [default scans](scan_default.md).


#### `ascan` example with 2 counters

    TEST_SESSION [1]: ascan(roby, 0, 10, 10, 0.1, diode, diode2)
    Total 10 points, 0:00:03.168758 (motion: 0:00:02.168758, count: 0:00:01)

    Scan 1 Wed Apr 18 08:46:20 2018 /tmp/scans/ test_session user = matias
    ascan roby 0 10 10 0.1

        #         dt(s)          roby        diode2         diode
        0     0.0341308             0       5.88889       7.44444
        1      0.298563        1.1111      -2.88889      -6.88889
        2      0.529942        2.2222           -34       1.33333
        3      0.761447        3.3333      -30.1111      -11.7778
        4       1.00202        4.4444      -6.22222       11.3333
        5       1.23181        5.5556           -17      -5.11111
        6       1.46598        6.6667       12.5556      -8.44444
        7       1.69842        7.7778     -0.777778      -6.55556
        8       1.92679        8.8889      -10.5556            34
        9       2.16557            10            18      -25.5556

    Took 0:00:02.328219 (estimation was for 0:00:03.168758)



### One-shot acquisition with integration time

The `ct(time_in_s, *counters)` function counts for the specified number of seconds. It is equivalent
of a `timescan` with `npoints` set to 1.

### Using measurement groups

An alternative of specifying counters for each scan is to rely on measurement groups
(if configured - see [here](getting_started.md#measurement-groups)).

    CYRIL [1]: align_counters
      Out [1]: MeasurementGroup:  align_counters (default)

               Enabled  Disabled
               -------  -------
               simct1
               simct2
               simct3

The measurement group can be passed to a `scan` or `ct` procedure to
define counters for the scan:

    CYRIL [4]: ascan(simot1, -2, 2, 7, 0.1, align_counters)
    Total 7 points, 0:00:09.500000 (motion: 0:00:08.800000, count: 0:00:00.700000)

    Scan 5 Wed Feb 21 15:26:31 2018 /tmp/scans/cyril/ cyril user = guilloud
    ascan simot1 -2 2 7 0.1

            #         dt(s)        simot1        simct1        simct2        simct3
            0       4.18972            -2      0.501319     0.0165606    0.00511711
            1       5.12933         -1.33      0.728287     0.0236184     0.0073165
            2       6.06347         -0.67      -0.33863      0.257847      0.251785
            3       6.98862             0     -0.608677       1.01518      0.997982
            4       7.92987          0.67      -2.29062      0.261047      0.249959
            5       8.86126          1.33      0.219424      0.023286     0.0137307
            6       9.78928             2     -0.558003    0.00988632     0.0165549

    Took 0:00:09.993863 (estimation was for 0:00:09.500000)

Multiple measurement groups can be passed:

    CYRIL [20]: print MG1.available, MG2.available   #  4 counters defined in 2 MG
    ['simct2', 'simct3'] ['simct4', 'simct5']

    CYRIL [21]: timescan(0.1, MG1, MG2, npoints=3)
    Total 3 points, 0:00:00.300000 (motion: 0:00:00, count: 0:00:00.300000)

    Scan 15 Wed Feb 21 16:31:48 2018 /tmp/scans/cyril/ cyril user = guilloud
    timescan 0.1

            #         dt(s)        simct2        simct3        simct4        simct5
            0     0.0347409       0.50349      0.494272      0.501698      0.496145
            1       0.13725       0.49622      0.503753      0.500348      0.500601
            2        0.2391      0.502216      0.500213      0.494356      0.493359

    Took 0:00:00.395435 (estimation was for 0:00:00.300000)

#### Active measurement group

If no counter and no measurement group is specified to the scan command, a default one is
used: the **active measurement group**. Indeed, there is always only one active measurement
group at a time. `ACTIVE_MG` is a global to know the active measurement group:

     CYRIL [1]: ACTIVE_MG
       Out [1]: MeasurementGroup:  align_counters (default)

                 Enabled  Disabled
                 -------  -------
                 simct2
                 simct3

The active measurement group is the one used by default by a `scan` or a `ct`:

    CYRIL [32]: ct(0.1)

    Wed Feb 21 15:38:51 2018

       dt(s) = 0.016116142272 ( 0.16116142272/s)
      simct2 = 0.499050226458 ( 4.99050226458/s)
      simct3 = 0.591432432452 ( 5.91432432452/s)

The `set_active()` method can be used to change the active measurement group:

    CYRIL [33]: ACTIVE_MG
      Out [33]: MeasurementGroup:  align_counters (default)

                     Enabled  Disabled
                     -------  -------
                     simct1
                     simct2
                     simct3

        CYRIL [34]: MG2.set_active()

        CYRIL [35]: ACTIVE_MG
          Out [35]: MeasurementGroup:  MG2 (default)

                      Enabled  Disabled
                      -------  -------
                      simct4
                      simct5

#### Enabling/disabling counters

Counters can be enabled or disabled in a measurement group, using `.enable(*cnt)` or
`.disable(*cnt)`.

#### Measurement group states

A measurement group can have different **states**, to denote different usages. For example,
it is possible to disable some counters for an alignment procedure, while having a
"diagnostic" state with additional diodes enabled.

The `.switch_state('state_name')` method allows to change state. The state is created if
it does not exist yet. The `default` state corresponds to the initial state, with all
counters enabled.

    CYRIL [41]: align_counters
      Out [41]: MeasurementGroup:  align_counters (default)     #  default state

                Enabled  Disabled
                -------  -------
                simct2   simct1    # <--- assume simct1, simct3 were disabled
                         simct3

Example usage of `switch_state`:

      CYRIL [42]: align_counters.switch_state("diag_mono")

      CYRIL [43]: print align_counters
        Out [43]: MeasurementGroup:  align_counters (diag_mono)
                                                     # new "diag_mono" state
                  Enabled  Disabled
                  -------  -------
                  simct1                  #  with all counters enabled
                  simct2
                  simct3

### Scan saving

The `SCAN_SAVING` global is a structure to tell BLISS where to save scan data:

    ID29 [1]: SCAN_SAVING
     Out [1]: Parameters (default)
                .base_path      = '/users/blissadm/scans'
                .date_format    = '%Y%m%d'
                .template       = '{session}/{date}'
                .user_name      = 'opid29'
                .writer         = 'hdf5'

`base_path` corresponds to the top-level directory where scans are stored. Then, `template`
completes the path. It uses Python's string interpolation syntax to specify how to build the file path from key values. Keys can be freely added. Key values can be numbers or strings, or functions. In case of function key values, the function return value is used.

`SCAN_SAVING.get()` performs template string interpolation and returns a dictionary, whose key `root_path` is the final path to scan files.

#### SCAN_SAVING members

* `base_path`: the highest level directory for the file path, e.g. `/data`
* `user_name`: the current Unix user name
* `session`: current BLISS session name, or `unnamed` if session has no name
* `template`: defaults to `{session}/`
* `.add(key, value)`: add a new key (string) to the SCAN_SAVING structure
    - value can be a scalar or a function
* `.get()`: evaluates template ; produces a dictionary with 2 keys
    - `root_path`: `base_path` + interpolated template
    - `parent`: parent node for publishing data via Redis

    !!! note
        As the ScanSaving object corresponds to a persistent structure in Redis, functions as key values will be serialized. Make sure the functions are serializable.

#### SCAN_SAVING writer

`.writer` is a special member of `SCAN_SAVING`; it indicates which writer to use for saving
data. BLISS only supports the HDF5 file format for scan data, although more writers could
be added to the project later.

### Retrieving scan data

The `get_data()` function takes a scan object and returns scan data in a `numpy` array. Scan data is retrieved from
**redis**. Data references are not resolved, which means 2D data is not returned.

Example:

    TEST_SESSION [4]: myscan = ascan(roby, 0, 1, 10, 0.001, diode,
                                     simu1.counters.spectrum_det0, return_scan=True)
    Total 10 points, 0:00:02.019930 (motion: 0:00:02.009930, count: 0:00:00.010000)
    Activated counters not shown: spectrum_det0

    Scan 3 Fri Apr 20 11:26:55 2018 /tmp/scans/test_session/
                                    test_session user = matias
    ascan roby 0 1 10 0.001

           #         dt(s)          roby         diode
           0      0.337308             0            83
           1      0.759228        0.1111           -10
           2       1.17105        0.2222            57
           3       1.58996        0.3333            43
           4       2.00024        0.4444           -44
           5       2.41497        0.5556           -16
           6       2.83309        0.6667           -74
           7       3.23919        0.7778            18
           8       3.65932        0.8889            74
           9       4.07872             1           -43

    Took 0:00:04.441955 (estimation was for 0:00:02.019930)

    TEST_SESSION [5]: data = get_data(myscan)

The numpy array is built with fields, it is easy to get data for a particular column using the counter name:

    TEST_SESSION [8]: data['diode']
             Out [8]: array([ 83., -10., 57., 43., -44., -16., -74., 18., 74., -43.])


## Online data display

Online data display relies on **Flint**, a graphical application shipped with BLISS and
built on top of [silx](9).

**Flint** can be started automatically when a new scan begins, by configuring `SCAN_DISPLAY`:

    SCAN_DISPLAY.auto = True

Plots are displayed in the **Live** tab. Depending on the scan acquisition chain,
3 types of plots can be shown:

* 1D plots, showing curves from the scan scalar counters
* 1D spectra, showing 1D scan counters (like MCA)
* 2D images, showing 2D data counters (typically, Lima detectors data)

Plots are grouped by the topmost master, i.e. as long as the number of points for a
master corresponds to its parent, the plots are attached to this master (recursively,
up to the root master if possible).
If number of points diverges between 2 masters, then underlying data is represented in
another set of plot windows.
So, there is no limit to the number of windows in the **Live** tab, it depends on the
scan being executed.

    !!! note
    2D images are always represented in their own plot window.

### Live scan data in Flint

    TEST_SESSION [8]: SCAN_DISPLAY.auto=True

    TEST_SESSION [9]: timescan(0.1, lima, diode, diode2, simu1.counters.spectrum_det
             ...: 0, npoints=10)
    Total 10 points, 0:00:01 (motion: 0:00:00, count: 0:00:01)
    Activated counters not shown: spectrum_det0, image

    Scan 145 Wed Apr 18 11:24:06 2018 /tmp/scans/ test_session user = matias
    timescan 0.1

           #         dt(s)        diode2         diode
           0     0.0219111       12.5556      -9.33333
           1      0.348005        30.625         0.125
           2      0.664058       2.88889      -10.2222
           3      0.973582       7.11111       8.44444
           4       1.28277       21.7778       36.3333
           5       1.59305      -15.8889             5
           6       1.90203       43.4444       19.4444
           7       2.21207       20.7778       11.6667
           8       2.52451      -7.88889       24.2222
           9       2.83371        24.125         7.625

    Took 0:00:03.214453 (estimation was for 0:00:01)

    TEST_SESSION [9]:

Flint screenshot:

![Flint screenshot](img/flint_screenshot.png)

[Read more about Online Data Display](flint_scan_plotting.md)

### Interacting with plots

BLISS provides tools to interact with plot windows in **Flint**. Each scan object has a
`.get_plot()` method, that returns a `Plot` object. The argument to pass to `.get_plot` is a counter -- thus, the plot containing this counter data is returned:

    TEST_SESSION [8]: s = loopscan(5, 0.1, lima, return_scan=True)
    Total 5 points, 0:00:00.500000 (motion: 0:00:00, count: 0:00:00.500000)
    Activated counters not shown: image

    Scan 2 Wed Apr 18 11:36:11 2018 /tmp/scans/test_session/
                                    test_session user = matias
    timescan 0.1

           #         dt(s)
           0      0.959486
           1        1.0913
           2       1.23281
           3       1.36573
           4       1.50349

    Took 0:00:01.666654 (estimation was for 0:00:00.500000)

      TEST_SESSION [9]: p = s.get_plot(lima)

     TEST_SESSION [10]: p
              Out [10]: ImagePlot(plot_id=2, flint_pid=13678, name=u'')

Starting from the `ImagePlot` object, it is possible to ask user for making a rectangular
selection for example:

    TEST_SESSION [11]: p.select_shape("rectangle")

BLISS shell is blocked until user makes a rectangular selection:

![Rectangular selection](img/flint_rect_selection.png)

Then, result is returned by the `.select_shape` method:

              Out [11]: ((278.25146, 716.00623), (623.90546, 401.82913)

[Read more about interactions with plots](flint_interaction.md)


[8]: https://github.com/jonathanslenders/ptpython
[9]: http://silx.org
