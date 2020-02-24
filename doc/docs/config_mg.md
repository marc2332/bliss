# Measurement groups

A measurement group is a logical container for counters. The idea is to bind a
set of counters together, for a detector, an experiment or an entire
hutch. Measurement groups can be passed to scans, in order to tell which data
acquisition channels will be recorded.

User can enable or disable counters interactively at runtime, in order to select
the active counters within the measurement group.

In addition to enabling or disabling counters, measurement group objects can
also manage **states**: a state corresponds to enabled and disabled counters
associated with a name. The default state is called `default`.

The possibility to define several measurement groups, each with different states
managing lists of enabled and disabled counters gives a lot of flexibility.

An example use case for measurement group states is for diagnostics: it is
possible to disable some counters during an alignment and, in case of problem,
to switch to a state where diagnostic counters are enabled, independently of the
counters selected by the user in the default state.

## Defining measurement groups in Beacon configuration

Measurement groups are loaded by the `session` Beacon plugin, thus it
is possible to configure those:

* directly in a session YAML file
* somewhere else with `plugin: session`

Example:
```yaml
  - class: MeasurementGroup
    plugin: session
    name: align_counters
    counters: [simct1, simct2, simct3]

  - class: MeasurementGroup
    plugin: session
    name: MG1
    counters: [simct2, simct3]
```

!!! note
    Do not forget to associate measurement groups to sessions, by adding
    measurement groups to a session `config-objects` list (like any other
    object)

`counters` must be a list of **names**, corresponding to `Counter` objects or to
**counter container** objects. Valid names include:

- counter fullnames, from the output of `lscnt()`

```
Fullname                       Shape    Controller               Name    Alias
-----------------------------  -------  -----------------------  ------  -------
sim_diode_sampling_ctrl:diode  0D       sim_diode_sampling_ctrl  diode
```

* counter object names, for the counters that exists individually in configuration
* counter container names from configuration, for example a Lima controller name
* counter aliases

Example:
```yaml
- class: MeasurementGroup
  plugin: session
  name: MG_sim
  counters:
  - sim_ct_1
  - simulation_counter_controller:sim_ct_2   <------ full name
```


### Nesting measurement groups

Counters of a measurement group can be included into another measurement group
using `include` keyword in the YML file:

```yaml
- class: MeasurementGroup
  name: MG2
  counters:
  - simct3
  - simct4
  include:
  - MG1
```

## Measurement Group objects

Once a measurement group is added to a session, it can be used from the shell.

```python
DEMO [1]: MG1
 Out [1]: MeasurementGroup: MG1 (state='default')
        - Existing states : 'default'

        Enabled                          Disabled
        -------------------------------  --------------------
        sim_diode_sampling_ctrl:diode
        sim_diode_sampling_ctrl:diode2
        sim_diode_sampling_ctrl:diode3
```

### Properties

* `.name`: measurement group name
* `.active_state_name`: returns the current, active state for this measurement group
* `.state_names`: returns the list of valid states for this measurement group
* `.available`: returns the set of available counter names for the measurement group
* `.enabled`: returns the set of enabled counter names (a subset of
  `.available`) for the current active state
* `.disabled`: returns the set of disabled counter names (a subset of
  `.available`) for the current active state

### Switching states

The `.switch_state(state_name)` method can be used to switch between a state or another.
Switching to a non-existing state creates a new one automatically.

States are persisted across executions as Beacon settings.


At creation, a measurement group is in the `default` state:

```python
DEMO [41]: align_counters
  Out [41]: MeasurementGroup:  align_counters (default) # <-- default state

            Enabled  Disabled
            -------  -------
            simct2   simct1         #   <-- counters simct1 and simct2
                     simct3         #       were previously disabled
```
A new state can be created in a measurement group with the `switch_state(<new_state_name>)`
method:

```python
DEMO [42]: align_counters.switch_state("diag_mono")

DEMO [43]: print align_counters
MeasurementGroup:  align_counters (diag_mono)    #  new "diag_mono" state

Enabled  Disabled
-------  -------
simct1                                           #  with all counters enabled
simct2
simct3
```


To customize the status of each counter within this state:

```python
DEMO [46]: align_counters.disable = "simct3"
```

The `state_names` property returns the list of available states:

```python
DEMO [47]: align_counters.state_names
 Out [47]: ['diag_mono', 'default']
```

Then, it is possible to switch from a state to another:

```python
DEMO [50]: align_counters.switch_state("default")

DEMO [51]: print align_counters
MeasurementGroup:  align_counters (default)

  Enabled  Disabled
  -------  -------
  simct2   simct1
           simct3

DEMO [52]: ct(1)
  Wed Feb 21 15:52:31 2018

     dt(s) = 0.00573420524597 ( 0.00573420524597/s)
    simct2 = 0.499528833799 ( 0.499528833799/s)


DEMO [53]: align_counters.switch_state("diag_mono")

DEMO [55]: print align_counters
MeasurementGroup:  align_counters (diag_mono)

  Enabled  Disabled
  -------  -------
  simct1   simct3
  simct2
```

### Enabling or disabling counters

The `.enable(pattern)` method can be used to enable counters within the current
state of the measurement group:

*pattern* accepts Unix-like wildcard characters:

* `mg.enable("pico1")`
    - enable counter if an existing counter with given name exists
* `mg.enable("lima_simulator")`
    - enable all **default** counters contained within *lima_simulator* controller (see note)
* `mg.enable("lima_simulator:*")`
    - enable **all** counters contained within the *lima_simulator* controller
* `mg.enable("pico*")`
    - match counters whose name or fullname starts with `pico`

!!! note
    Default counters are the ones that are considered more common or the
    more useful for a controller. In the case of Lima controllers, for example,
    BPM counters are not included by default. This is also because the position
    calculation is costly and people do not want it generally.


### edit_mg()

`edit_mg()` command allows to enable/disable counters of the active measurement
group with a simple dialog box.

Use `edit_mg(<mg_name>)` to deal with a specific measurement group.


## Default measurement group

`ACTIVE_MG` is the global variable in the BLISS shell indicating the default measurement group.

```python
DEMO [31]: ACTIVE_MG
  Out [31]: MeasurementGroup:  align_counters (default)

            Enabled  Disabled
            -------  -------
            simct2   simct1
                     simct3
```

This default measurement group is used on a `scan` or a `ct` if nothing is specified:

```python
DEMO [32]: ct(0.1)

Wed Feb 21 15:38:51 2018

   dt(s) = 0.0161161422729 ( 0.161161422729/s)
  simct2 = 0.499050226458 ( 4.99050226458/s)
```

!!! note
    Note that only `simct2` is counting, since the two others are disabled.

The default measurement group can be changed by the use of the `.set_active()` method:

```python
DEMO [33]: ACTIVE_MG
  Out [33]: MeasurementGroup:  align_counters (default)

             Enabled  Disabled
             -------  -------
             simct2   simct1
                      simct3

DEMO [34]: MG2.set_active()

DEMO [35]: ACTIVE_MG
  Out [35]: MeasurementGroup:  MG2 (default)

              Enabled  Disabled
              -------  -------
              simct4
              simct5
```

## lsmg

`lsmg()` can be used to list the defined measurement groups. A star `*`
indicates the active one.

Example:
```python
DEMO [1]: lsmg()
   MG_sim
 * MG_align
   MG_tomo
```


## Usage in scans

One or several measurement groups can be passed as argument to a `scan`
or `ct` procedure to indicate which counters to use:

```python
DEMO [2]: MG1.available
 Out [2]: {'sim_diode_sampling_ctrl:diode',
           'sim_diode_sampling_ctrl:diode3',
           'sim_diode_sampling_ctrl:diode2'}

DEMO [3]: MG2.available
 Out [3]: {'sim_diode_sampling_ctrl:diode4'}

DEMO [4]: timescan(0.1, MG1, MG2, npoints=3)

Scan 15 Wed Feb 21 16:31:48 2018 /tmp/scans/cyril/ cyril user = guilloud
timescan 0.1
          #         dt(s)         diode        diode2        diode3        diode4
          0     0.0347409       0.50349      0.494272      0.501698      0.496145
          1       0.13725       0.49622      0.503753      0.500348      0.500601
          2        0.2391      0.502216      0.500213      0.494356      0.493359

Took 0:00:00.395435
```

## Adding or removing counters

Counters can be added to a measurement group dynamically. It adds the counter in
the set of available counters for the measurement group. By default, the counter
is enabled:

```python
DEMO [4]: MG1
  Out [4]: MeasurementGroup: MG1 (state='default')
             - Existing states : 'default'

             Enabled  Disabled
             -------  -------
             simct1
             simct2

DEMO [5]: MG1.add(emeter2.counters.e1)

DEMO [6]: MG1
  Out [6]: MeasurementGroup: MG1 (state='default')
             - Existing states : 'default'

             Enabled  Disabled
             -------  -------
             simct1
             simct2
             e1
```

Dynamically added counters can be removed with the `.remove(counter)` method:

```
DEMO [7]: MG1.remove(emeter2.counters.e1)

DEMO [8]: MG1
  Out [8]: MeasurementGroup: MG1 (state='default')
             - Existing states : 'default'

             Enabled  Disabled
             -------  -------
             simct1
             simct2
```

!!! note
    Added counters **are not saved in the YML file**. This is runtime only.
    Only **dynamically added counters** can be removed ; it is not possible to
    remove a counter that was made available through the YML configuration.

