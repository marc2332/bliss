# Aliases in Bliss

Aliases in Bliss serves the following main purposes:

* Handle potential duplication of motor names in a beamline-wide
  configuration

* Shorten counter names e.g. in the hdf5 files while conserving uniqueness
  of the keys

Aliases are handled at the **global map level** within one instance of
BLISS. In case they are added dynamically, they are not propagated to
other instances, e.g when mulitple BLISS shells are running.

## Creation of aliases

### Creating aliases through the session yml file

In a session configuration file, a **list of aliases** can be defined
using the `aliases` keyword. An alias requires the two properties:

* `original_name`: (old) name that will be masked by the alias_name
* `alias_name`: (new) name that will be assigned to the alias

The `alias_name` needs to be unique. That means:

* it can not be used by any object in the configuration,
* it can not be used as alias name of any other object
* it can not be used by any object exported to `setup_globals`

The `original_name` must be either:

* an axis object name
* or a counter fullname
    - counter fullnames are in the form: `[master_controller_name:]controller_name:counter_name`
    - in the case of a Lima ROI counter, a fullname example would be: `pilatus:roi_counters:roi1_std`

Aliases will become accessible to the current session `env_dict`,
`setup_globals` and from the command line, as any other configuration
item.

Aliases **replace** the original object: the original object will be
removed from the global namespaces and dictionaries.

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
   - original_name: simu1:deadtime_det0
     alias_name: dtime
```

### Dynamic creation

Inside a session, aliases can be added at runtime. E.g. one can look
at the list of existing counters via `lscnt()` to see valid counter
names available in the session.

```
TEST_ALIAS [1]: lscnt()

Fullname                          Shape    Controller      Name           Alias
--------------------------------  -------  --------------  -------------  -------
lima_simulator:image              2D       lima_simulator  image
...
simu1:realtime_det0               0D       simu1           realtime_det0  rtime
simu1:realtime_det1               0D       simu1           realtime_det1
...

```
in order to assign an alias **rt1** to **simu1.counters.realtime_det1** one can use

```python
ALIASES.add('rt1',simu1.counters.realtime_det1)
```

from now on the counter is accessible as 'rt1' from the command line.


## Alias handling

From the BLISS command line all aliases can be managed through
`'ALIASES'` global object and its methods.

```
TEST_ALIAS [1]: ALIASES

Alias    Original fullname      
-----   -------------------- 
robyy    roby                
robzz    robz               
dtime    simu1:deadtime_det0
rtime    simu1:realtime_det0
ltime    simu1:livetime_det0
```

* `ALIASES.add(alias_name, object)` adds a new alias dynamically
    - the original object is deleted
    - it is not allowed to make multiple aliases of the same object
    - it is not allowed to make aliases of aliases
* `ALIASES.set(alias_name, object)` replaces an alias with a new one pointing to `object`
* `ALIASES.get(alias_name)` returns the alias object corresponding to an alias name
* `ALIASES.get_alias(object)` returns the alias name corresponding to `object`
* `ALIASES.remove(alias_name)` removes an existing alias
* `ALIASES.names_iter()` returns an iterator over alias names

When adding an alias, the original object gets wrapped into an `Alias` object:

```python
>>> rt1
<CounterAlias at 0x7f64de481630 with factory <bliss.common.alias.CounterWrapper object at 0x7f64e4680588>>
```

It exposes all methods and properties from the underlying original object transparently.
In addition it provides the following properties:

* .original_name: the original object name
* .object_ref: the wrapped original object

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
		<HDF5 dataset "axis:robyy": shape (5,), type "<f8">
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
71_a2scan/measurement/simu1:spectrum_det0
    fullname: simu1:spectrum_det0
```

