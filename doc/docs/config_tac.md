
A Tango attribute can be read as a counter.


Example to read ring current and beam lifetime from machine side:

* `orion:10000/` prefix has to be added if device is defined on another
`TANGO_HOST` than the default one.
* `unit` is optional.

```yaml
- class: tango_attr_as_counter
  uri: orion:10000/fe/id/11
  counters:
    - name: srcur
      attr_name: SR_Current
      unit: mA
    - name: lifetime
      attr_name: SR_Lifetime
```


Example to read a wago thermocouple via a Tango device server attribute.

```yaml
- class: tango_attr_as_counter
  uri: id42/wcid21k/tg
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


