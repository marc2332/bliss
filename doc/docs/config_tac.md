
`tango_attr_as_counter` class allows to read a Tango attribute in BLISS as a
counter.

## Configuration parameters

* `class`: name of the controller class to use: *tango_attr_as_counter*
* `uri`: address of the Tango device
    -  `<host>:<port>/` prefix has to be added if device is defined on another
       `TANGO_HOST` than the default one.
* `counters`: list of counters wanted
    - `name` (str): name to use for the BLISS counter
    - `attr_name` (str): name of the Tango attribute
    - `unit` (optional) (str). If specified, it will be used by BLISS instead of
  Tango configuration parameter `unit`.


### Tango attribute parameters
If the following parameters are defined in the attribute configuration (in Tango
database), and not overwritten in YAML configuration, they will be used in
BLISS:

* `unit` (string): label used to specify units of the attribute value.
* `display_unit` (float): conversion factor (to change unit of the
  attribute value) by which the raw read value is multiplied.



## Examples

Example to read *ring current* and *beam lifetime* from The Machine device
server:

`orion:10000/` prefix is used to access Tango database of The Machine.

```yaml
- class: tango_attr_as_counter
  uri: orion:10000/fe/id/42
  counters:
    - name: srcur
      attr_name: SR_Current
      unit: mA
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
      unit: deg
    - name: kohztc6
      attr_name: kohztc6
      unit: deg
    - name: kohztc7
      attr_name: kohztc7
      unit: deg
```

Example of `ct()` with timing:

* first count : 106 ms
* second count : 65 ms

```python
CYRIL [2]: import   time
CYRIL [3]: t0=time.time();ct(0.0001, kohztc5, flowBase, flowM2, flowM1,
                                     m0m2, pptc1);print("duration=", time.time()-t0)

get_proxy -- create dict
get_proxy -- create proxy for id21/wcid21m0/tg
get_proxy -- create proxy for id21/wcid21k/tg
get_proxy -- create proxy for id21/wcid21hpps/tg
Tue Jul 23 15:56:13 2019

           dt[s] =          0.0 (         0.0/s)
  flowBase[l/mn] =        0.489 (      4890.0/s)
    flowM1[l/mn] =       0.8865 (      8865.0/s)
    flowM2[l/mn] =       0.7301 ( 7300.999999999999/s)
            m0m2 =      23.3999 ( 233998.99999999997/s)
    kohztc5[Deg] =         20.6 (    206000.0/s)
      pptc1[Deg] =         14.1 (    141000.0/s)
duration= 0.10665655136108398


CYRIL [4]: t0=time.time();ct(0.0001, kohztc5, flowBase, flowM2, flowM1,
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

Test files:

* `bliss/tests/controllers_sw/test_tango_attr_counters.py`
* `bliss/tests/test_configuration/tango_attribute_counter.yml`

```python
pytest tests/controllers_sw/test_tango_attr_counters.py
```


