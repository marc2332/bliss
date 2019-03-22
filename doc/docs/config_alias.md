# Aliases in Bliss

Aliases in Bliss serves the following main purposes:

* Handle potential duplication of motor names in a beamline-wide
  configuration

* Shorten key names e.g. in the hdf5 files while conserving uniqueness
  of the keys

Aliases are handled at the **session level**. In case they are added
dynamically, they are not propagated to other instances of the
session. If there is a python object in `setup_globals` or the
`env_dict` of the [REPL]() that has a '*name*' or '*fullname*'
property corresponding to the '*original_name*' it will be linked to
this alias if not specified differently.

## Creation of aliases

### Creating aliases through the session yml file

In a session configuration file, a **list of aliases** can be defined
using the `aliases` keyword. An alias requires the two properties:

* `original_name`: (old) name that will be masked by the alias_name
* `alias_name`: (new) name that will be assigned to the alias

The `alias_name` needs to be unique. That means:

* it can not be used by any object in the Beacon config,
* it can not be used as alias name of any other object
* it can not be used by any object exported to `setup_globals`

Further there are three parameters to tune the behavior of the alias
and adopt it to its use-case:

* `export_to_globals` (default:`True`)
    * Alias will be accessible from the command line when set to `True`.

* `hide_controller` (default: `True`)
    * `True` if the controller name should be hidden when in the output
    * Mainly of interest for aliases that are used to modify axes
      names with respect to the beacon config name.
    * For an aliased axis to behave like any other axis, this needs to
      be set `False`

* `remove_original` (default: `False`):
    * The reference with the original name will be removed from the
      scope of the session. Only the reference to the new alias name
      will be kept.
    * Only usable in connection with `export_to_globals`.

Example of a `.yml` session file containing alias configurations:
```yaml
- class: Session
  name: test_alias
  config-objects:
    - simu1
    - roby
    - robz
    - lima_simulator
  aliases:
   - original_name: roby
     alias_name: robyy
     export_to_globals: True
     remove_original: True
   - original_name: robz
     alias_name: robzz
     export_to_globals: True
     hide_controller: False
     remove_original: True
   - original_name: simu1.deadtime_det0
     alias_name: dtime
   - original_name: simu1.realtime_det0
     alias_name: rtime
     export_to_globals: False
   - original_name: simu1.livetime_det0
     alias_name: ltime
     export_to_globals: False
     remove_original: False

```

### Dynamic creation

Inside a session, aliases can be added at runtime. E.g. one can look
at the list of existing counters via `lscnt()` to see valid counter
names available in the session.

```
TEST_ALIAS [1]: lscnt()

Fullname                          Shape    Controller      Name           Alias
--------------------------------  -------  --------------  -------------  -------
lima_simulator.image              2D       lima_simulator  image
...
simu1.realtime_det0               0D       simu1           realtime_det0  rtime
simu1.realtime_det1               0D       simu1           realtime_det1
...

```
in order to assign an alias **rt1** to **simu1.realtime_det1** one can use

```python
ALIASES.create_alias('rt1','simu1.realtime_det1')
```

from now on the counter is accessible as 'rt1' from the command line.

Objects that inherit the *alias* functionality have a `.set_alias()` method. E.g.:

```
TEST_ALIAS [1]: m0 = config.get("m0")

TEST_ALIAS [2]: m0.set_alias("m24", export_to_globals=True, remove_original=True)
Alias 'm24' added for 'm0'

TEST_ALIAS [3]: m24

        Out [1]: <bliss.common.axis.Axis object at 0x7ff086643470>

TEST_ALIAS [4]: m0

        NameError: name 'm0' is not defined
```


## Alias handling

From the BLISS command line all aliases can be managed through
`'ALIASES'` global object and its methods. To list all aliases there
is a `.list_aliases` method:

```
TEST_ALIAS [1]: ALIASES.list_aliases()

Alias    Original name          Linked to py obj
------   -------------------    ------------------
robyy    roby                   True
robzz    robz                   True
dtime    simu1.deadtime_det0    True
rtime    simu1.realtime_det0    True
ltime    simu1.livetime_det0    True
```

### Alias in hdf5 output

Running the following scan in a session with configuration given above
(test_alias session of the test suite):

```python
a2scan(robyy, 0, 5, robzz, 0, 5, 5, 0.001, dtime, simu1.counters.spectrum_det0)
```
results in a hdf5 file with the following dump:
```
+71_a2scan
	+instrument
		+positioners
			<HDF5 dataset "robyy": shape (), type "<f8">
			<HDF5 dataset "robzz": shape (), type "<f8">
		+positioners_dial
			<HDF5 dataset "robyy": shape (), type "<f8">
			<HDF5 dataset "robzz": shape (), type "<f8">
	+measurement
		<HDF5 dataset "axis:robzz": shape (5,), type "<f8">
		<HDF5 dataset "dtime": shape (5,), type "<f8">
		<HDF5 dataset "robyy": shape (5,), type "<f8">
		<HDF5 dataset "simu1:spectrum_det0": shape (5, 1024), type "<u4">
		<HDF5 dataset "timer:elapsed_time": shape (5,), type "<f8">
	<HDF5 dataset "start_time": shape (), type "|O">
	<HDF5 dataset "title": shape (), type "|O">
```

In this example we can discuss the following impacts of aliases:

* The motors are called "robyy" and "robzz" as specified in the
  aliases tag of the configuration
* For "robzz" differences can be noted between `robzz` and `robyy`:
     * 'HDF5 dataset **"axis:robzz"** ' for robzz (`hide_controller: False`)
     * 'HDF5 dataset **"robyy"**' for robyy (`hide_controller: True`)
* The alias `dtime` is used to shorten the counter name in the output
  and also when typing the scan command in the shell.

A more detailed look at the hdf5 reveals attributes on each dataset to
provide the the systematic names in case they are needed.

```
71_a2scan/measurement/axis:robzz
    fullname: axis:robz
    alias: robzz
    has_alias: True
71_a2scan/measurement/simu1:spectrum_det0
    fullname: simu1:spectrum_det0
    alias: None
    has_alias: False
```

## Writing code containing aliases and technical details

There is a `AliasMixin` class that can be inherited to provide alias
functionality to any object in Bliss.

