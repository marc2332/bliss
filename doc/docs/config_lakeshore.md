# Lakeshore with **regulation plugin**:

Models (used at ESRF and fow which BLISS controller exists)
have the following possible interfaces:

    * model 331 can use RS232.
    * model 332 can use GPIB or RS232.
    * model 335 can use GPIB or USB.
    * model 336 can use GPIB or Ethernet.
    * model 340 can use GPIB or RS232.

```
Lakeshore 336, acessible via GPIB, USB or Ethernet

yml configuration example:
#controller:
- class: LakeShore336
  module: temperature.lakeshore.lakeshore336
  name: lakeshore336
  timeout: 3
  gpib:
     url: enet://gpibid10f.esrf.fr
     pad: 9
     eol: '\r\n' 
  usb:
     url: ser2net://lid102:28000/dev/ttyUSB0
     baudrate: 57600    # = the only possible value
#ethernet
  tcp:
     #url: idxxlakeshore:7777
     url: lakeshore336se2:7777
  inputs:
    - name: ls336_A
      channel: A 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_336
    - name: ls336_A_c    # input temperature in Celsius
      channel: A
      unit: Celsius
    - name: ls336_A_su  # in sensor units (Ohm or Volt)
      channel: A
      unit: Sensor_unit

    - name: ls336_B
      channel: B 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_336
    - name: ls336_B_c    # input temperature in Celsius
      channel: B
      unit: Celsius
    - name: ls336_B_su  # in sensor units (Ohm or Volt)
      channel: B
      unit: Sensor_unit

    # can add also input channels C and D

  outputs:
    - name: ls336o_1
      channel: 1 
      unit: Kelvin
    - name: ls336o_2
      channel: 2 

  ctrl_loops:
    - name: ls336l_1
      input: $ls336_A
      output: $ls336o_1
      channel: 1
    - name: ls336l_2
      input: $ls336_B
      output: $ls336o_2
      channel: 2

    # can add also output channels 3 and 4

```
