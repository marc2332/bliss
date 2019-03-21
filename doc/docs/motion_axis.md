
# The BLISS Axis object

In most cases a **BLISS Axis** represents a motor driven by a
physical motor controller.

## Configuration

The `Axis` objects need to be declared along their controller
in the BLISS configuration with an unique name, and a set of
configuration parameters.

!!! note
    See the motor controller configuration templates to learn
    about how to configure axes. For example, see [Icepap configuration](config_icepap.md)
    to declare Icepap motor controller axes.

### Default configuration parameters

Configuration parameters from Beacon YAML files are passed to
the `Axis` constructor.

Parameter name |  Required | Setting? | Type   | Description
-------------- |-----------|-----------|--------|------------
name           |  yes      | no        | string | An unique name to identify the `Axis` object
steps_per_unit |  yes      | no        | float  | Number of steps to send to the controller to make a *move of 1 unit* (eg. 1 mm, 1 rad)
velocity       |  yes      | yes        | float  | Nominal axis velocity in *units.s<sup>-1</sup>*
acceleration   |  yes      | yes        | float  | Nominal acceleration value in *units.s<sup>-2</sup>*
sign           |  no       | no         | int    | Accepted values: 1 or -1. User position = (sign * dial_position) + offset ; *defaults to 1*
low_limit      |  no       | yes        | float  | Lower user limit for a move (*None* or not specified means: unlimited) ; *defaults to unlimited*
high_limit     |  no       | yes        | float  | Higher user limit for a move (*None* or not specified means: unlimited) ; *defaults to unlimited*
backlash       |  no       | no         | float  | Axis backlash in user units ; *defaults to 0*
tolerance      |  no       | no         | float  | Accepted discrepancy between controller position and last known axis dial position when starting a move ; *defaults to 1E-4*
encoder        |  no       | no         | string | Name of an existing **Encoder** object linked with this axis
unit           | no        | no         | string | *Informative only* - Unit (for steps per unit), e.g. mm, deg, rad, etc.

!!! note
    Motor controllers with extra features may require more parameters. See the
    documentation of individual motor controllers to known about specific
    parameters.

Some configuration parameters are translated into *settings*, which means
the corresponding value is also stored in redis (see [Settings documentation](beacon_settings.md)).

### Applying configuration changes

To apply a change in YML configuration, use `apply_config` method of `Axis`
objects with `reload=True` keyword argument:

Example: after changing velocity of **ssu** motor in YML file:

    ssu.apply_config(reload=True)

### Custom axis classes

`Axis` is the default class that corresponds to controller motors,
however it is possible to specify *a derived class* with extra features
if needed. Some controllers may return instances of a special class
(for example, the **IcePAP** controller has a special class for linked axes).
User can also force a particular class to be instanciated, by adding
a `class` item within the YAML configuration for the axis.

#### ModuloAxis

An `Axis` whose positions are always between 0 and a modulo value set in the
YAML configuration (`modulo` parameter). For example, a motor for a rotation
can be configured with `class: ModuloAxis` and `modulo: 360`.

#### NoSettingsAxis

An `Axis` which does not store settings in redis -- will always refer to hardware.

## Initialization

Motor controllers follow the following sequence to initialize `Axis` objects:

![Axis initialization logic](img/axis_init.svg)

When the `Axis` object is initialized, settings have prevalence over static
configuration parameters, i.e. the axis velocity will be changed to the
one in redis, not to the nominal value from the configuration.

!!! note
    Axis initialization does not happen when the motor controller is loaded, or when an `Axis` object is retrieved from Beacon. Indeed `Axis` objects implement the *lazy initialization pattern*: the initialization sequence described above only happens the first time the object is accessed.

## Axis properties

Axis properties are built on top of the Python language properties, which provide an elegant way to implement  "getters and setters". Assigning a value to a property sets the value, i.e. an action may be triggered by the object when the descriptor gets written. In the case of the `Axis` object, it can trigger a communication with the motor controller to set the velocity for example.
It is enough to call the property to read the property value. Depending on the property, this can also trigger an action on the motor controller.

Property name | R/W? | Type   | Description
--------------|------|--------|-------------
name          | R    | string | Axis name
velocity      |  R+W | float  | Get or set the axis velocity in *units.s<sup>-1</sup>*
config_velocity | R  | float  | Returns the nominal velocity value from the configuration
acceleration  | R+W  | float  | Get or set the axis acceleration in *units.s<sup>-2</sup>*
config_acceleration | R | float | Returns the nominal acceleration value from the configuration
acctime       | R+W  | float  | Get or set the acceleration time; note: depends on both velocity and acceleration ; *acctime = velocity / acceleration*
config_acctime | R | float | Returns the acceleration time taking into account nominal values for velocity and acceleration
low_limit      | R+W | float or None | Get or set the soft low limit
high_limit     | R+W | float or None | Get or set the soft high limit
limits         | R+W | (float or None, float or None) | Get or set soft limits
config_limits  | R | (float or None, float or None) | Returns (low_limit, high_limit), taking values from the configuration
steps_per_unit | R | float | Number of steps to send to the controller to make a *move of 1 unit* (eg. 1 mm, 1 rad)
backlash       | R | float | Returns the backlash applied to the axis
is_moving      | R | bool | Returns whether the axis is moving
dial           | R+W | float | Get or set the axis *dial* position
offset         | R  | float | Returns the current offset for user position calculation
sign           | R  | int   | Returns the sign for user position calculation
position       | R+W | float | Get or set the axis *user* position ; User position = (sign * dial_position) + offset
_hw_position   | R | float | Returns the controller position for the axis ; *forces a read on the controller*
_set_position  | R+W | float | Last set position for the axis (target of last move, or current position)
tolerance | R | float | Accepted discrepancy between controller position and last known axis dial position when starting a move ; *defaults to 1E-4*
state          | R | AxisState | Returns the state of the axis (*MOVING*, *READY*, *ON_LIMIT*, etc)
encoder        | R | Encoder[None] | Returns the encoder object associated to this axis

### User and Dial positions

`Axis` objects keep track of both a dial and a user position.

The dial position is meant to agree with the readout of the physical dial on the hardware stage. The value and the sign of the *.steps_per_unit* parameter should be chosen so that the dial position and its direction agree with the physical dial reading. Assigning a value to the writable `.dial` property *sets the position on the motor controller register*.

The user position allows to use a logical reference frame, that does not interfere with the motor controller.

```python
    user position = (sign * dial position) + offset
```

Assigning a value to the `.position` property sets the user position. *The offset is determined automatically,
using the above formula.* The offset value can be retrieved with the `.offset` property (read-only).
The sign is read from the configuration. The sign value can be retrieved with the `.sign` property (read-only).

Changing the user position does not change anything on the motor controller. No communication with hardware is involved.

Resetting offset to 0 can be achieved with:

```python
>>> axis.position = axis.dial
>>> axis.offset
0.0
```

### Position change events

Internally, the axis position is kept in a [`Channel` object](beacon_channels.md), which makes it is possible to register a callback function to be called whenever the axis position changes:

```python
>>> from bliss.common import event
>>> def example_callback(new_pos):
      print(f"I moved to {new_pos}")
>>> event.connect(m0, "position", example_callback)
>>> m0.rmove(1)
I moved to 0.0
I moved to 0.241
I moved to 0.486
I moved to 0.691
I moved to 0.880
I moved to 1.0
>>>
```

!!! note
    The same applies for any setting or channel: dial, state, limits, velocity, acceleration

## Axis state

The `.state` property returns the current state of an axis. The returned value is an `AxisState` instance,
which holds *a list of states*, which can be combined to represent more complex situations. Indeed, for example a motor can be both ready to move, and still touching a limit or being at home position.

Standard states are constants:

* MOVING, 'Axis is moving'
* READY, 'Axis is ready to be moved'
* FAULT, 'Error from controller'
* LIMPOS, 'Hardware high limit active'
* LIMNEG, 'Hardware low limit active'
* HOME, 'Home signal active'
* OFF, 'Axis is disabled'

*READY* and *MOVING* are mutually exclusive.

A description is associated to each state. The string representation of the `AxisState` object shows a human-readable description of the state:

```python
TEST_SESSION [1]: m0.state                                                      
         Out [1]: AxisState: READY (Axis is READY)

TEST_SESSION [2]: 'READY' in m0.state                                           
         Out [2]: True

TEST_SESSION [3]: m0.state.MOVING                                               
         Out [3]: False
```

!!! note
    The `in` operator of the Python language can be used to check whether an axis is in a certain state.

Motor controllers assign states to `Axis` objects. It is possible to define custom states (see [how to
  write motor controllers](dev_write_motctrl.md)).

### State change events

Similarly to the `.position` property, it is possible to be notified of state changes by registering to the state change event:

```python
TEST_SESSION [12]: def state_change(new_state):
              ...:     print(f"State changed to {str(new_state)}")              
TEST_SESSION [13]: event.connect(m0, "state", state_change)                     
TEST_SESSION [14]: m0.rmove(1)                                                  
State changed to MOVING (Axis is MOVING)
State changed to MOVING (Axis is MOVING)
State changed to READY (Axis is READY)
```

## Synchronization with hardware

The `Axis` object tries to minimize access to the physical motor controller. In particular, it is assumed
BLISS takes ownership of the hardware devices, i.e. devices are *not* supposed to be driven "externally",
by another software for example. Indeed, all `Axis` settings are cached.

In some cases, though, another application (like **icepapcms** for the **IcePAP** motor controller) can control a BLISS axis. Then any further action on the `Axis` object would end up with an exception being raised,
because of discrepancies between the axis cached state and the hardware state.

In order to solve the problem, and to empty the internal cache, the `.sync_hard()` method can be called.

## Moving

The `Axis` object provides the following methods to start, monitor and stop motion:

* `.move(target_user_position, wait=True, relative=False)`
    - move to target position (absolute, except if relative=True)
* `.rmove(target_user_position, wait=True)`
    - do a relative move to target position
* `.home(switch=1, wait=True)`
    - do a home search
* `.jog(velocity, reset_position=None)`
    - start to move at constant speed ; *velocity* can be negative to indicate the opposite direction
    - if reset position is set to 0, the controller position is set to 0 at the end of the jog move
    - if reset position is a callable, it is called at the end of the jog move, passing the Axis object as first argument
* `.hw_limit(limit, wait=True)`
    - do a limit search
    - a positive limit value means 'limit + switch', whereas a negative value means 'limit - switch'
* `.wait_move()`
    - for motions started with `wait=False`, this allows to join with the end of the move
* `.stop()`
    - send a stop command to the controller
    - the move loop will exit

### Move loop

![Move procedure](img/move_loop.svg)
