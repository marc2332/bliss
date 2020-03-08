# Keithley 428 configuration

Keithley 428 is a amplificator that converts fast, small currents to a voltage,
which can be easily digitized or displayed by an oscilloscope, waveform
analyzer, or data acquisition system.

It cannot measure a current, just change the gain of the amplifier which can be
read via a V2F and a P201.


## Yaml sample configuration

```YAML
- class: keithley428
  plugin: bliss
  name: k_diode1
  gpib:
     url: enet://gpibid42
     pad: 22
```


## Usage

* Read-Write attributes:
    - `filter_rise_time`: 
    - `gain`: 
    - `voltage_bias`: Voltage Bias (-5V ; +5V)
    - `current_suppress`: Current suppress

*Read Only attributes:
    - `state`: 
    - `overloaded`: 
    - `filter_state`: 
    - `zero_check`: 


Shell info example:
```python
DEMO [1]: k1
 Out [1]: KEITHLEY K428
          COMM:
              GPIB type=ENET url='enet://gpibid21a.esrf.fr'
               primary address='11' secondary address='0' tmo='13' timeout(s)='0.5' eol=''
          gain: (3, '1E03V/A')
          filter_rise_time: (0, '10usec')
          voltage_bias: 0.0
          state: K428 - Display:Normal - VBias:off - Zcheck:on - gain:1e03 - rise time:10usec
          overloaded: False
          filter state: Off
          auto_filter_state: On
          zero_check: On
```
