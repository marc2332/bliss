# Getting started with BLISS

This page will present what the **BLISS control system** is and how to start using
it.

## BLISS presentation

The *BLISS control system* provides a global approach to run synchrotron
experiments requiring to synchronously control motors, detectors and
various acquisition devices thanks to hardware integration, Python
sequences and an advanced scanning engine.

As a Python package, BLISS can be easily embedded into any Python
application and data management features enable online data analysis.
In addition, BLISS ships with tools to enhance scientists' user
experience and can easily be integrated into TANGO based environments,
with generic TANGO servers on top of BLISS controllers.

From the user's point of view, BLISS presents different aspects:

* [BLISS shell](shell_cmdline.md): a command line interface to
  interact with devices and to run sequences
* Programming of sequences in order to allow users to adapt the flow of their experiment 
* Configuration of all devices involved in the experiments


## BLISS shell

BLISS comes with a command line interface based on [ptpython][8].

It uses the concept of a *session* to allow users to define a set of procedures
and devices to use in particular circumstances (like alignment, specific hutch
or specific experiment).


```
% bliss -s eh1
```

```python
                       __         __   __          
                      |__) |   | /__` /__`         
                      |__) |__ | .__/ .__/         


Welcome to BLISS version 1.1.0 running on blabla (in bliss Conda environment)
Copyright (c) 2015-2019 Beamline Control Unit, ESRF
-
Connected to Beacon server on blabla (port /tmp/beacon_0lwrjuor.sock)
eh1: Executing setup...

Welcome to your new 'eh1' BLISS session !! 

You can now customize your 'eh1' session by changing files:
   * /eh1_setup.py 
   * /eh1.yml 
   * /scripts/eh1.py 

Initializing 'pzth`
Initializing 'simul_mca`
Initializing 'pzth_enc`
Done.

EH1 [1]:
```

The `-s` command line option loads the specified session at startup,
its configuration objects are initialized,
the setup file is executed. Finally the prompt returns to the user.

The `-h` option gives an overview of the command-line features.

```
(bliss) % bliss -h
Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>] [--no-tmux] [--debug]
       bliss [-v | --version]
       bliss [-c <name> | --create=<name>]
       bliss [-d <name> | --delete=<name>]
       bliss [-h | --help]
       bliss --show-sessions
       bliss --show-sessions-only

Options:
    -l, --log-level=<log_level>   Log level [default: WARN] (CRITICAL ERROR INFO DEBUG NOTSET)
    -s, --session=<session_name>  Start with the specified session
    -v, --version                 Show version and exit
    -c, --create=<session_name>   Create a new session with the given name
    -d, --delete=<session_name>   Delete the given session
    -h, --help                    Show help screen and exit
    --no-tmux                     Deactivate Tmux usage
    --debug                       Allow debugging with full exceptions and keeping tmux alive after Bliss shell exits
    --show-sessions               Display available sessions and tree of sub-sessions
    --show-sessions-only          Display available sessions names only
```

A session can be created using the `-c` option:

```python
(bliss) % bliss -c eh1
Creating 'eh1' BLISS session
Creating sessions/eh1.yml
Creating sessions/eh1_setup.py
Creating sessions/scripts/eh1.py
```
Learn more about [BLISS sessions](config_sessions.md)
Learn more about [BLISS shell](shell_cmdline.md)

### Examples of standard shell functions

Once the BLISS shell is launched, a user can use it as a command line interface in addition to being able to act on configured devices.

Most common devices are *counters* and *motors*.

Most common actions a user would like to perform are *counting* and *scanning*.

Many standard functions are then provided to help the user to perform such
actions on such devices.


* `wa()`: shows a table of all motors in the session and their positions.
* `lscnt()`: shows a table of all counters in the session.
* `ascan(axis, start, stop, intervals, count_time)`: moves an axis from
  *start* to *stop* in *intervals* steps and counts *count_time* at each step.


### Help
Help about BLISS functions can be accessed using `help(<command_name>)`:

```
BLISS [2]: help(wa)
Help on function wa in module bliss.common.standard:

wa(**kwargs)
    Displays all positions (Where All) in both user and dial units
```
Learn more about other [standard shell functions](shell_std_func.md).
Learn more about the [BLISS shell](shell_cmdline.md).


## Counters

The first fundamental objects to consider in BLISS are *counters*. A counter is used to display the reading of a device.

The simplest function to read all defined counters is `ct(<counting_time>)`.

```python
DEMO [1]: ct(0.1)
Fri Jun 7  16:32:17 2018
   dt[s] = 0.0     (    0.0/s)
  simct1 = 0.50109 ( 5.0109/s)
  simct2 = 0.49920 ( 4.9920/s)
  simct3 = 0.50403 ( 5.0403/s)
  simct4 = 0.50311 ( 5.0311/s)

Out [3]: Scan(name=ct_1, run_number=1)
```

To use only a sub-set of counters, they need to be specified as arguments:

```python
DEMO [2]: ct(1, simct1, simct4)

Fri Nov 16 16:37:43 2018

   dt[s] = 0.0    (    0.0/s)
  simct1 = 0.49872 ( 0.49872/s)
  simct4 = 0.50021 ( 0.50021/s)
Out [20]: Scan(name=ct_3, run_number=3)
```

### Using measurement groups

An alternative to specifying counters for each scan is to rely on *measurement groups*.

```python
DEMO [1]: align_counters
Out [1]: MeasurementGroup:  align_counters (default)

            Enabled  Disabled
            -------  -------
            simct1
            simct2
            simct3
```

Passing a measurement group as argument to a `scan` or `ct` procedure will define them for the procedure:

```python
DEMO [2]: ascan(simot1, -2, 2, 7, 0.1, align_counters)
Total 7 points, 0:00:09.500000 (motion: 0:00:08.800000, count: 0:00:00.700000)

Scan 5 Wed Feb 21 15:26:31 2018 /tmp/scans/demo/ demo user = guilloud
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
```

Multiple measurement groups can be used for one procedure:

```python
DEMO [1]: print MG1.available, MG2.available   #  4 counters defined in 2 MG
['simct2', 'simct3'] ['simct4', 'simct5']

DEMO [2]: timescan(0.1, MG1, MG2, npoints=3)
Total 3 points, 0:00:00.300000 (motion: 0:00:00, count: 0:00:00.300000)

Scan 15 Wed Feb 21 16:31:48 2018 /tmp/scans/demo/ demo user = guilloud
timescan 0.1

        #         dt(s)        simct2        simct3        simct4        simct5
        0     0.0347409       0.50349      0.494272      0.501698      0.496145
        1       0.13725       0.49622      0.503753      0.500348      0.500601
        2        0.2391      0.502216      0.500213      0.494356      0.493359

Took 0:00:00.395435 (estimation was for 0:00:00.300000)
```

### Active measurement group

If no counter or measurement group is specified to a scan command, the **active measurement group** is used as default. Indeed, there is always only one active measurement group at a time.

`ACTIVE_MG` is a global variable containing the active measurement group:
```python
DEMO [1]: ACTIVE_MG
Out [1]: MeasurementGroup:  align_counters (default)

            Enabled  Disabled
            -------  -------
            simct2
            simct3
```
The active measurement group is the one used by default by a `scan` or a `ct`:

```python
DEMO [2]: ct(0.1)

Wed Feb 21 15:38:51 2018

    dt(s) = 0.016116142272 ( 0.16116142272/s)
  simct2 = 0.499050226458 ( 4.99050226458/s)
  simct3 = 0.591432432452 ( 5.91432432452/s)
```

The `set_active()` method changes the active measurement group:

```python
DEMO [1]: ACTIVE_MG
Out [1]: MeasurementGroup:  align_counters (default)

            Enabled  Disabled
            -------  -------
            simct1
            simct2
            simct3

DEMO [2]: MG2.set_active()

DEMO [3]: ACTIVE_MG
Out [3]: MeasurementGroup:  MG2 (default)

            Enabled  Disabled
            -------  -------
            simct4
            simct5
```

!!! note
    The default active measurement group is the one last defined in config.

Learn more about [measurement groups](config_mg.md).

## Motors

The second fundamental category of objects to consider in BLISS are **motors**.

Motors are used, where the user can change the  position, i.e. a set-point.

The main parameters for motors are:

* *user* and *dial* positions (potentially influenced by an *offset* and/or *sign*)
* *velocity* and *acceleration*
* *high_limit* and *low_limit*


The `wa()` (where all) standard command is provided to show positions of all motors in the current session.


```python
DEMO [1]: wa()
Current Positions (user, dial)

simot1    simot2    simot3    simot4    simot5
--------  --------  --------  --------  --------
2.00000   4.00000   6.00000   8.00000   9.00000
2.00000   4.00000   6.00000   8.00000   9.00000
```

`wm([motor]+)` (where motor) shows the dial position, limits and offset in addition to positions of one or several motors.

A sub-set of motors to display can be given as an argument to the `wm()` function.

```python
DEMO [2]: wm('simot1', 'simot4')
           simot1    simot4
-------  --------  --------
User
 High     10.00000  10.00000
 Current   2.00000   8.00000
 Low     -10.00000 -10.00000
Offset    -1.00000   4.00000

Dial
 High     11.00000   6.00000
 Current   3.00000   4.00000
 Low      -9.00000 -14.00000
```
Learn more about [IcePap motors configuration](config_icepap.md).
Learn more about [motor usage](motion_axis.md).

## Basic scans

Counters and motors are combined to carry out realistic measurements. This is done with *scans*.

BLISS relies on a powerful scanning engine based on an **acquisition chain**, i.e. a tree of master and slave devices; master devices trigger acquisitions, whereas slave devices take data. Complex acquisition chains can be built to perform any kind of data acquisition sequence.
[Read more about the BLISS scanning engine](scan_engine.md)

The acquisition chain for each scan must be provided by the user. BLISS provides a default acquisition chain to help perform scans similar to the default, step-by-step, ones in Spec.

### Default step-by-step scans

Step-by-step measurements are the simplest form of scans.

Most common are :

* `ascan(axis, start, stop, intervals, count_time, *counters, **kwargs)` as absolute positions scan
* `dscan` : same as `ascan`, with `start`, `stop` as relative positions to current axis position
* `a2scan` : same as ascan but with 2 motors
* `mesh` to makes a grid using 2 motors
* `timescan` just counting time intervals without moving a motor

All scans can take a list of counters as argument, limiting the number of counters to be read out.

More about [default scans](scan_default.md).


#### `ascan`

`ascan` example with 1 motor and 2 counters.

```python
BLISS [1]: ascan(roby, 0, 10, 10, 0.1, diode, diode2)
Total 10 points, 0:00:03.168758 (motion: 0:00:02.168758, count: 0:00:01)

Scan 1 Wed Apr 18 08:46:20 2018 /tmp/scans/ BLISS user = matias
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
```

### One-shot acquisition with integration time

The `ct(time_in_s, *counters)` function counts for the specified number of seconds. It is equivalent of a `timescan` with `npoints` set to 1.

### Scan saving

The `SCAN_SAVING` global is a structure to tell BLISS where to save scan data:

```python
BLISS [1]: SCAN_SAVING
Out [1]: Parameters (default)
        .base_path      = '/users/blissadm/scans'
        .date_format    = '%Y%m%d'
        .template       = '{session}/{date}'
        .user_name      = 'opid29'
        .writer         = 'hdf5'
```

Find more info about how to use it in [SCAN_SAVING section](data_policy_dev_basic.md#scan_saving)


### Retrieving scan data

The `get_data()` function takes a scan object as argument and returns the scan's data in a `numpy` array. Scan data are retrieved from the **redis** data base. Data references are not resolved, which means 2D data are not returned.

Example:

```python
BLISS [4]: myscan = ascan(roby, 0, 1, 10, 0.001, diode,
                                 simu1.counters.spectrum_det0, return_scan=True)
Total 10 points, 0:00:02.019930 (motion: 0:00:02.009930, count: 0:00:00.010000)
Activated counters not shown: spectrum_det0

Scan 3 Fri Apr 20 11:26:55 2018 /tmp/scans/BLISS/
                                BLISS user = matias
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

BLISS [5]: data = get_data(myscan)
```

The numpy array is built of fields, it is easy to get data for a particular column using the counter name:

```python
BLISS [8]: data['diode']
Out [8]: array([ 83., -10., 57., 43., -44., -16., -74., 18., 74., -43.])
```

## Online data display

The BLISS online data display relies on **Flint**, a graphical application installed alongside BLISS and built on top of [silx][9].

**Flint** can be started automatically when a new scan begins, by setting `SCAN_DISPLAY`:

`SCAN_DISPLAY.auto = True`

Plots are displayed in the **Live** tab. Depending on the scan acquisition chain, 3 types of plots can be shown:

* 1D plots, showing curves from the scan scalar counters
* 1D spectra, showing 1D scan counters (like MCA)
* 2D images, showing 2D data counters (typically, Lima detectors data)

Plots are grouped by the topmost master, i.e. as long as the number of points for a master corresponds to its parent, the plots are attached to this master (recursively, up to the root master if possible).
If the number of points diverges between 2 masters, then underlying data are represented in
another set of plot windows.
There is no limit to the number of windows in the **Live** tab, it depends on the
scan being executed.

!!! note
    2D images are always represented in their own plot window.

### Live scan data in Flint

```python
BLISS [1]: SCAN_DISPLAY.auto=True

BLISS [2]: timescan(0.1, lima, diode, diode2, simu1.counters.spectrum_det
         ...: 0, npoints=10)
Total 10 points, 0:00:01 (motion: 0:00:00, count: 0:00:01)
Activated counters not shown: spectrum_det0, image

Scan 145 Wed Apr 18 11:24:06 2018 /tmp/scans/ BLISS user = matias
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

BLISS [3]:
```

Flint screenshot:

![Flint screenshot](img/flint_screenshot.png)

### Interacting with plots

BLISS provides tools to interact with plot windows in **Flint**. Each
scan object has a `.get_plot()` method, that returns a `Plot`
object. The argument to pass to `.get_plot` is a counter -- thus, the
plot containing this counter data is returned:

```python
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
```

Starting from the `ImagePlot` object, it is possible to ask user for
making a rectangular selection for example:

`TEST_SESSION [11]: p.select_shape("rectangle")`

BLISS shell is blocked until user makes a rectangular selection:

![Rectangular selection](img/flint_rect_selection.png)

Then, result is returned by the `.select_shape` method:

` Out [11]: ((278.25146, 716.00623), (623.90546, 401.82913)`

[Read more about interactions with plots](flint_interaction.md)


[8]: https://github.com/prompt-toolkit/ptpython
[9]: http://silx.org
