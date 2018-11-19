
# BLISS configuration start-up guide.


## Configuration example

### YAML files tree

The following tree shows an example of how YAML files can be organized
within the BLISS Beacon `db_path` directory:

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

Each kind of object in the configuration is associated with a
configuration plugin. The configuration plugin interprets
configuration information. Depending on the plugin, different objects
can be instantiated from the same configuration.

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

`controller` is a reserved key for the `emotion` plugin: it indicates
which motor controller to configure.  In this example, the controller
class is set to `icepap`. The IcePAP BLISS controller expects `host`
to be configured, to know to which IcePAP master it corresponds.  The
`iceid2322` IcePAP controller is declared, and two motors `ts2f` and
`ts2b` are configured.

The different fields to be specified under `axes` depends on the controller.
In the case of the IcePAP controller, `address` is one of the specific parameters.
Other parameters are:

* `steps_per_unit`, optional (1), $steps.unit^{-1}$
    - can be negative
* `velocity`, **mandatory**, in $unit.s^{-1}$
* `acceleration`, **mandatory**, in $unit.s^{-2}$
* `backlash`, optional (0), in $unit$
* `tolerance`: optional (0), in $unit$
     - in case of motor in closed loop, tolerance for discrepancy check
       when moving a motor

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
    - `real` means the axis is a real motor, declared elsewhere; the name has
      to be a **reference** to an existing axis (starting with `$`)
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

A session groups objects from configuration under a single name,
associated with a setup file. The setup file is a Python script, that
is executed after session objects are loaded. This can be used to add
small users scripts to the global namespace. A session also defines a
way to call user scripts, stored with the configuration files.

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

`__init__.yml` contains `plugin: session` ; then, all YAML files in
the directory are loaded using the Session plugin.

#### Example session YAML file

```yaml
- class: Session
  name: id23-2
  setup-file: ./id232_setup.py
```

`id232.yml` defines a session called `id23-2`, with a `id232_setup.py` setup file.

By default, **all objects** defined in the configuration will be
loaded in the session.  It is possible to specify which objects must
be included or not by using the `config-objects` keyword with the list
of object names:

```yaml
    - class: Session
      name: eh1
      setup-file: ./eh1_setup.py
      config-objects: [pzth, simul_mca]
```

Conversely, `exclude-objects` can be used to avoid to load unused objects.

#### Measurement groups

A measurement group is an object to wrap counters in it. The
measurement group helps to deal with a coherent set of counters. For
example, a measurement group can represent counters related to a
detector, a hutch or an experiment.

Measurement groups are loaded by the `session` Beacon plugin, thus it
is possible to configure those directly in a session YAML file:

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

All objects from the session are available in the setup script. The
globals defined in the setup script, and all session objects, are
automatically added to the `bliss.setup_globals` namespace, to be used
in user scripts.

#### User scripts

Python files defined under a session `script` directory can be loaded
in the setup file using the `load_script('script_name')` function. In
case of error, the function catches and display exceptions, but do not
prevent the rest of the setup from executing. Each call to
`load_script` reloads the Python script again.  `load_script` is the
equivalent of the `execfile` Python function, but for session scripts.

!!! note
    User scripts in a session should be reserved for small functions and helpers.
    More complex code should be moved to a proper beamline project with revision
    control, tests and documentation.








