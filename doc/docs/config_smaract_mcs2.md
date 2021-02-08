# Smaract MCS2 motor controller

The SmarAct MCS2 BLISS controller is only supporting the MCS2 model. For the old model MCS refer to the other BLISS controller for MCS model [smaract](config_smaract.md)

The SmarAct MCS2 is the follow-up of the MCS controller system. It has several new features and
improvements.

The only supported protocol is TCP, and the default port is **55551**. If you change the port configuration in the controller box you can change the port in the YML file by adding the port number in the TCP url,  i.e url: \<host\>:\<port\> 

When the controller is powered on the position of the axes are lost and the closed-loop are opened.
The CLOOP will be closed once you move the axis.

It is recommended to perform a "home search" to reset the axis to a hardware-known position.

### Supported features

Encoder | Shutter | Trajectories
------- | ------- | ------------
NO	| NO      | NO  

## Configuration example

```yml
plugin: emotion
class: SmarAct_MCS2
name: beutier_polariser
tcp:
   url: smaractid016
 axes:
 - name: pol_y
   channel: 0                 # (1)
   unit: mm               
   steps_per_unit: 1e9        # (2)
   velocity: 0.02             # (3)
   acceleration: 0            # (4)
   positioner_type: SL_S1SS   # (5)
   hold_time: -1              # (6)
   power_mode: Enabled        # (7)
   tolerance: 0.02
 - name: pol_z
   channel: 1
   steps_per_unit: 1000000000 #linear positioner step-size is 1 pico-meter(1e-12)
   unit: mm
   sensor_type: SL_S1SS
   velocity: 0.002 # 2 micro-meter/s
   acceleration: 0
   tolerance: 0.02
 - name: pol_r
   channel: 2
   steps_per_unit: 1000000000 #rotary positioner step-size is 1 nano-degree (1e-9)
   unit: degree
   velocity: 0.001  # 1 mdegree/s
   acceleration: 0
   tolerance: 0.02  
```

1. channel: the channel number of the positioner, starts from 0.

2. steps_per_unit:
For linear positioner the resolution is 1 pico-meter (1e-12). If set to 1e9  the position will 
be in millimeter.
For rotary positioner the resolution is 1 nano-degree (1e-9). If set to 1e9  the position will 
be in degree.
   
3. velocity: setting to 0 disables velocity control and implicitly acceleration
control and low vibration mode as well.
   
4. acceleration: setting to 0 disables acceleration control and low vibration
mode as well.
   
5. positioner_type: PositionerType string (optional, default is to assume the
controller was previously configured and use its value).
Warning: do not change this parameter if you are not sure, it can damage the 
positioner.
   
6. hold_time: This property specifies how long (in ms) the position is actively
held after reaching the target position. After the hold time elapsed the 
channel is stopped and the control-loop is disabled.
A value of 0 deactivates this feature, a value of -1 sets the channel to infinite holding.
   
7. power: initialization mode of the positioner power supply (optional)
   * Disabled  : the positioner power supply is turned off continuously.
   * Enabled   : (default) the positioner is continuously supplied with power.
   * PowerSave : the positioner power supply is pulsed to keep the heat generation low. (useful for
                 in-vacuum motors)

(Tested on ESRF-ID10: Ethernet controller with SL_S1SS (Linear) and  SR_S1S5S (small rotary) positioners)

# Usage

This is a emotion controller, so you just need to get the axis and move/stop/scan ... the motor.

```python
BLISS [1]: config.get('pol_y')                                                                                                                                                         
WARNING 2021-02-08 14:36:42,665 global.controllers.beutier_polariser: pol_y physical position unknown (hint: do a homing to find reference mark)
  Out [1]: AXIS:
                name (R): pol_y
                unit (R): mm
                offset (R): 0.00000
                backlash (R): 0.00000
                sign (R): 1
                steps_per_unit (R): 1000000000.00
                tolerance (R) (to check pos. before a move): 0.02
                limits (RW):    Low: -inf High: inf    (config Low: -inf High: inf)
                dial (RW): -0.00000
                position (RW): -0.00000
                state (R): READY (Axis is READY)
                acceleration: None
                velocity (RW):        0.00200  (config:    0.00200)
                velocity_low_limit (RW):            inf  (config: inf)
                velocity_high_limit (RW):            inf  (config: inf)
           SmarAct MCS2 CONTROLLER:
                controller: 160.103.30.183
                serial #: "MCS2-00003631"
                name: "MCS2-00003631"
                channel: 0 type: SL_S1SS
                status: POWER: Enabled    CLOOP: False    OVERLOAD: False
           ENCODER:
                None

```

If you get the warning message above that means the controller have been power-off/on and you may need to do a homing search to fix the position.

# SmarAct MCS2 specific commands

The axes are working as standard BLISS axes, nevertheless this controller provides some extra functions to perform low level access or to execute special functions like the sensor calibration or a power off.
All the specific commands are accessible by using the **channel** attribute of the bliss axis, e.g `<myaxis>.channel.status` :

 - .channel.status
 - .channel.info_status
 - .channel.power_mode
 - .channel.hold_time
 
 - .channel.find_reference_mark()
 - .channel.calibrate()
 
 - .channel.get_property()
 - .channel.set_property()
 - .channel.command()

## Read hardware status
The Device State, Module State and Channel State properties are used to obtain the current state
of the controller. While the Device State and Module State mainly give information about global
hardware states and available modules, the most prominent state property, the Channel State,
may be used to get feedback for the current movement of a channel.

### Only channel status
``` python
BLISS [4]: pol_y.channel.status                                                                                                                                                        
  Out [4]:  *      ACTIVELY_MOVING = False
            *   CLOSED_LOOP_ACTIVE = True
            *          CALIBRATING = False
            *          REFERENCING = False
            *         MOVE_DELAYED = False
            *       SENSOR_PRESENT = True
            *        IS_CALIBRATED = True
            *        IS_REFERENCED = False
            *     END_STOP_REACHED = False
            *  RANGE_LIMIT_REACHED = False
            * FOLLOWING_LIMIT_REAC = False
            *      MOVEMENT_FAILED = False
            *         IS_STREAMING = False
            *  POSITIONER_OVERLOAD = False
            *     OVER_TEMPERATURE = False
            *       REFERENCE_MARK = False
            *            IS_PHASED = False
            *     POSITIONER_FAULT = False
            *    AMPLIFIER_ENABLED = True
            *          IN_POSITION = True
           

```
### Channel, module and device status
```python
BLISS [2]: pol_y.channel.info_status                                                                                                                                                   
Channel status:
 *      ACTIVELY_MOVING = False
 *   CLOSED_LOOP_ACTIVE = True
 *          CALIBRATING = False
 *          REFERENCING = False
 *         MOVE_DELAYED = False
 *       SENSOR_PRESENT = True
 *        IS_CALIBRATED = True
 *        IS_REFERENCED = False
 *     END_STOP_REACHED = False
 *  RANGE_LIMIT_REACHED = False
 * FOLLOWING_LIMIT_REAC = False
 *      MOVEMENT_FAILED = False
 *         IS_STREAMING = False
 *  POSITIONER_OVERLOAD = False
 *     OVER_TEMPERATURE = False
 *       REFERENCE_MARK = False
 *            IS_PHASED = False
 *     POSITIONER_FAULT = False
 *    AMPLIFIER_ENABLED = True
 *          IN_POSITION = True

Module status:
 *           SM_PRESENT = True
 *      BOOSTER_PRESENT = False
 *   ADJUSTEMENT_PRESET = False
 *           IOM_PRESET = False
 * INTERNAL_COMM_FAILUR = False
 *          FAN_FAILURE = False
 * POWER_SUPPLY_FAILURE = False
 * POWER_SUPPLY_OVERLOA = False
 *     OVER_TEMPERATURE = False

Device status:
 *           HM_PRESENT = False
 *      MOVEMENT_LOCKED = False
 *     AMPLIFIER_LOCKED = False
 * INTERNAL_COMM_FAILUR = False
 *         IS_STREAMING = False
```
## Power mode
In order for a positioner to track its position, its sensor needs to be supplied with power. How-
ever, since this generates heat (causing drift effects), it might be desirable to disable the sensors
in some situations (especially in temperature critical environments). For this, there are three dif-
ferent modes of operation for the sensor, which may be configured individually for each channel
with the Sensor Power Mode property. The following modes are available:
   * Disabled  : the positioner power supply is turned off continuously.
   * Enabled   : (default) the positioner is continuously supplied with power.
   * PowerSave : the positioner power supply is pulsed to keep the heat generation low. (useful for in vacuum setup).

```python
BLISS [4]: pol_y.channel.power_mode                                                                                                                                                    
  Out [4]: <PowerMode.PowerSave: 2>
BLISS [6]: pol_y.channel.power_mode= 'Enabled'
```
## Hold time
This property specifies how long (in ms) the position is actively held after reaching the target
position. After the hold time elapsed the channel is stopped and the control-loop is disabled.

```python
BLISS [2]: pol_y.channel.hold_time                                                                                                                                                     
  Out [2]: -1  
```

## Calibration
Even though every positioner is categorized by its type, each individual positioner
may have slightly different characteristics that require the tuning of some internal parameters for
correct operation and optimal results.
The calibration function is used to adapt to these characteristics and automatically de-
tects parameters for an individual positioner. It must be called once for each channel if the me-
chanical setup changes (different positioners connected to different channels). The calibration
data will be saved to non-volatile memory. If the mechanical setup is unchanged, it is not nec-
essary to run the calibration on each initialization, but newly connected positioners have to be
calibrated in order to ensure proper operation.
CAUTION: As a safety precaution, make sure that the positioner has enough freedom to move
without damaging other equipment.
```python
BLISS [12]: pol_y.channel.calibrate(wait=True, timeout=None)
```
## Homing - Find reference mark
When doing a bliss-axis home search you can only set the direction, calling this function you can set set if you want to reset the position to zero:
```python
BLISS [12]: pol_y.channel.find_reference_mark(1, auto_zero=True)
```

## Low level access 

The MCS2 is "speaking" SCPI protocol language. For the list of functions please refer to the "MCS2 Programming Guide " PDF documentation. You can set/get some axis properties (velocity, position...) or send commands (stop, move, calibrate ....).


### Set or get properties
```python
# Read the position
With set/get_property() functions just passed the property, channel is set automatically.
BLISS [12]: pol_y.channel.get_property(':POS')                                                                                                                                         
  Out [12]: '-479\r'
# Set the acceleration to 1000 steps/s²
BLISS [12]: pol_y.channel.set_property(':ACC 1000')
```

### Send commands
Can only be used to send commands, for instance to stop/move/calibrate/reference commands. There is no return.
```python
BLISS [15]: pol_y.channel.command(':STOP0')
```


