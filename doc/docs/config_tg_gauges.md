
# Tango Gauges

This chapter describes usage of the `bliss.controllers.vacuum_gauge` class,
designed to interact with `VacGaugeServer` Tango device server.

Targeted gauges are Bazlers' Prani and Penning gauges.


## Gauges API

### Attributes

* `state`: 
* `status`: 
* `pressure`: 

### Functions
* `set_on`: 
* `set_off`: 
* `reset`: 



## Usage examples

```python
RH [1]: pir121.state
Out [1]: 'ON'
```

```python
CYRIL [2]: pen71
  Out [2]:
           ----------------  id42/v-pen/71 ---------------
           State: ON
           Gauge is ON  -  Channel A1 (1)
           Rel. | Lower | Upper | SA | State
             1  | 1.5e-6| 5.0e-6|  1 |  ON
             2  | 4.0e-3| 6.0e-3|  2 |  ON
             3  | 1.0e-6| 3.0e-6|  3 |  ON
             4  | 4.0e-3| 6.0e-3|  4 |  ON
             A  | 4.0e-3| 1.0e-5|  6 |  ON
             B  | 4.0e-3| 1.0e-5|  8 |  ON

           Failed to connect to device sys/hdb-push/id42
           The connection request was delayed.
           The last connection request was done less than 1000 ms ago
           -------------------------------------------------
           PRESSURE: 2.30e-07
           -------------------------------------------------
```

```python
RH [3]: pir121.pressure
Out [3]: 0.0007999999797903001
```


## Configuration example

```yaml
-
  # pirani gauge
  plugin: bliss
  name: pir121
  class: VacuumGauge
  uri: id43/v-pir/121

-
  # penning gauge
  plugin: bliss
  name: pen121
  class: VacuumGauge
  uri: id43/v-balzpen/121
```
