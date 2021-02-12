# Smaract motor controller

The SmarAct BLISS controller is only supporting the MCS model. For the new model MCS2 refer to the
other BLISS controller for MCS2 model [smaract MCS2](config_smaract_mcs2.md)

The only supported protocol is TCP, and the default port is **5000**. If you change the port configuration in the controller box you can change the port in the YML file by adding the port number in the TCP url,  i.e url: \<host\>:\<port\> 

### Supported features

Encoder | Shutter | Trajectories
------- | ------- | ------------
NO	| NO      | NO  

## Yaml sample configuration

```Configuration example
plugin: emotion
class: SmarAct
tcp:
  url: id99smaract1
power: Enabled                 # (1)
axes:
  - name: rot1
    unit: degree               # (2)
    steps_per_unit: 1000000    # (2)
    velocity: 2                # (3)
    acceleration: 0            # (4)
    sensor_type: SR20          # (5)
    hold_time: 60              # (6)
    tolerance: 1e-3

```
1. power: initialization mode of sensors power supply (optional)
   * Disabled  : power is disabled. Almost nothing will work (disadvised)
   * Enabled   : (default) power is always on
   * PowerSave : used to avoid unnecessary heat generation (useful for
                 in-vacuum motors)
2. steps_per_unit:
For rotary sensors, position is given in micro-degree so if you want to work
in degrees you need to put steps_per_unit to 1,000.000.
For linear sensors, position is given in nano-meter so if you want to work
in milimeter you need to put steps_per_unit to 1,000.000.

3. velocity: setting to 0 disables velocity control and implicitly acceleration
control and low vibration mode as well.

4. acceleration: setting to 0 disables acceleration control and low vibration
mode as well.

5. sensor_type: SensorType string (optional, default is to assume the
controller was previously configured and use its value)

6. hold_time after move/home search (optional, default is 60 meanning hold
forever)
   
## Further reading at ESRF
[bliss wiki: Smaract](http://wikiserv.esrf.fr/bliss/index.php/Smaract)
