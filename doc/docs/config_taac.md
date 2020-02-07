
`tango_attr_as_counter` class allows to read a Tango *number* attribute as a
BLISS counter.

## Configuration parameters

* `class`: name of the controller class to use: *tango_attr_as_counter*
* `uri`: address of the Tango device
    -  `<host>:<port>/` prefix has to be added if device is defined on another
       `TANGO_HOST` than the default one.
* `counters`: list of counters wanted
    - `name` (str): name to use for the BLISS counter
    - `attr_name` (str): name of the Tango attribute
    - `unit` (optional) (str): If specified, it will be used by BLISS instead of
       Tango configuration parameter `unit`.
    - `mode` (optional, default:`MEAN`) (str): If specified, sampling mode to use to read this
      counter. The string corresponding to one of the
      [SamplingMode](dev_ct.md#sampling-counter-modes).
    - `format` (optional) (str): string representing the display format to use.
    - `index` (optional) (int): index of the wanted value in case the attribute is an array.

### Tango attribute parameters
If the following parameters are defined in the attribute configuration (in Tango
database), and not overwritten in YAML configuration, they will be used in
BLISS:

* `unit` (string): label used to specify units of the attribute value.
* `display_unit` (float): conversion factor (to change unit of the
  attribute value) by which the raw read value is multiplied.
* `format` (string): string representing the display format to use.


### info

As `tango_attr_as_counter` class provide a `__info__()` method, some info about
the counter and its value can be obtained just by typing the name of the
counter:

```python
DEMO [2]: hpz_off_2
raw_value=167.193531174
  Out [2]: 'hpz_off_2` Tango attribute counter info:
             device server = id16ni:20000/id16ni/hpz/metrology
             Tango attribute = Offsets
             Tango format = "%6.2f"
             Beacon unit = "mm"
             index: 2
             value: 167.19
```


!!! note
    The formated and the raw values can be obtained directly via `.value` and
    `.raw_value` properties:
    ```
    DEMO [5]: hpz_off_2.value
    Out  [5]: 167.19
    DEMO [6]: hpz_off_2.raw_value
    Out  [6]: 167.193531174
    ```


## Examples

Example to read *ring current* and *beam lifetime* from The Machine device
server:

`acs:10000/` prefix is used to access Tango database of The Machine.

```yaml
- class: tango_attr_as_counter
  uri: orion:10000/fe/id/42
  counters:
    - name: srcur
      attr_name: SR_Current
      mode: MEAN
      unit: mA
      format: "3.2f"
    - name: lifetime
      attr_name: SR_Lifetime
```

Example to read a wago thermocouple via a Tango device server attribute:

```yaml
- class: tango_attr_as_counter
  uri: id42/wcid42k/tg
  counters:
    - name: kohztc5
      attr_name: kohztc5
      mode: SINGLE
      unit: deg
    - name: kohztc6
      attr_name: kohztc6
      mode: LAST
      unit: deg
    - name: kohztc7
      attr_name: kohztc7
      unit: deg
```

Example of `ct()` with timing:

* first count : 106 ms
* second count : 65 ms

```python
DEMO [2]: import   time
DEMO [3]: t0=time.time();ct(0.0001, kohztc5, flowBase, flowM2, flowM1,
                            m0m2, pptc1);print("duration=", time.time()-t0)

Tue Jul 23 15:56:13 2019

           dt[s] =          0.0 (         0.0/s)
  flowBase[l/mn] =        0.489 (      4890.0/s)
    flowM1[l/mn] =       0.8865 (      8865.0/s)
    flowM2[l/mn] =       0.7301 ( 7300.999999999999/s)
            m0m2 =      23.3999 ( 233998.99999999997/s)
    kohztc5[Deg] =         20.6 (    206000.0/s)
      pptc1[Deg] =         14.1 (    141000.0/s)

duration= 0.10665655136108398


DEMO [4]: t0=time.time();ct(0.0001, kohztc5, flowBase, flowM2, flowM1,
                            m0m2, pptc1);print("duration=", time.time()-t0)
Tue Jul 23 15:56:15 2019

            dt[s] =          0.0 (         0.0/s)
  flowBase[l/min] =       0.5111 (      5111.0/s)
    flowM1[l/min] =       0.9117 (      9117.0/s)
    flowM2[l/min] =       0.6843 (      6843.0/s)
             m0m2 =      23.3999 ( 233998.99999999997/s)
     kohztc5[Deg] =         20.6 (    206000.0/s)
       pptc1[Deg] =         14.1 (    141000.0/s)

duration= 0.06498312950134277
```


## Tests

Tests files:

* `tests/test_counters.py`
* `tests/test_configuration/tango_attribute_counter.yml`

Tests are using:

* `tests/test_configuration/dummy.yml`
* `tests/dummy_tg_server.py`


```python

pytest tests/test_counters.py -k test_tango_attr_counter

```

