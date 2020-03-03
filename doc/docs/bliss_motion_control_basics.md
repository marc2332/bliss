# Motion control

1. What is a BLISS Axis ?
1. What can be done with an Axis ?
1. Special Axis


## What is a BLISS Axis ?

In most cases a BLISS Axis represents a motor driven by a physical motor
controller.

This page presents main caracteristics of a BLISS Axis object and its
basic usages.

Basicaly it's a position you can change.

In details, it's much more complex ;-)


See [Motion Axis](motion_axis.md) for a detailled Axis description.

Fundamental caracteristics of an Axis are:

* position
* velocity
* acceleration

To match mechanical reality, an Axis also deals with:

* tolerance
* backlash
* limits
* steps_per_unit

And to be usable, another set of notions is present:

* name
* user unit
* sign
* offset
* dial position
* acctime
* state

Each of these notions is implemented as a "**setting**" in BLISS Axis.

A setting is a value that can be changed by user or that evolves as the
Axis moves.

Settings can be defined in the configuration or saved in memory during
the existance of the Axis object. This will be presented in another
section.

## Axis Settings

Settings are implemented as python **attributes**, and not as functions.

This pythonic detail means that they are used without brackets `()`

Example:
```python
DEMO [11]: mot1.velocity       ⏎   # to READ the velocity
 Out [11]: 1.25

DEMO [12]: mot1.velocity = 3.0 ⏎   # to SET a new velocity
DEMO [13]:

DEMO [14]: mot1.velocity ⏎
 Out [14]: 3.0
```

Following sections will briefly present the meaning of these settings.

### name

* string  -  Read Only  -  from config
* unique, but can have an alias in a session.

### state

* AxisState set  -  Read Only  -  computed

```python
DEMO [7]: mot1.state ⏎
 Out [7]: AxisState: READY (Axis is READY)
```


A standard state has a name and a description.

There are 8 standard states:

* `MOVING`  : 'Axis is moving'
* `READY`   : 'Axis is ready to be moved'
* `FAULT`   : 'Error from controller'
* `LIMPOS`  : 'Hardware high limit active'
* `LIMNEG`  : 'Hardware low limit active'
* `HOME`    : 'Home signal active'
* `OFF`     : 'Axis power is off'
* `DISABLED`: 'Axis cannot move'

New states, specific to a controller, can also be created.

`state` attribute is a *set* of one or many standard states.

```python
DEMO [2]: m1.state  ⏎
 Out [2]: AxisState: READY (Axis is READY) | LIMPOS (Hardware high limit active)
```


An axis must be in `READY` state to be moved.


### position / dial / offset / steps_per_unit / sign

`steps_per_unit` is the conversion factor applied to transform
position given by a motor controller (typically "motor steps") into
`dial` value (typically `mm`, `um` or `degrees`)

```user_position = (sign * dial_position) + offset```


```python
DEMO [2]: wa() ⏎
Current Positions: user
                   dial

  mot1[parsec]       mm2      mm3      mm4
-------------  --------  -------  -------
      1.92000  14.75000  2.00000  0.00000
      6.92000  14.75000  2.00000  0.00000
```



### user unit

Read-Only  -  string  -  from config

`unit` is a string read from the configuration as an indication for the
user (typically: "mm", "um", "degrees").

It does not enter in consideration for any calculation.


### velocity / acceleration / acctime

Read-Write  -  float  -  from config and persistant in memory

* velocity is set in user unit per second
* acceleration is given in user unit per second per second
* acctime (acceleration time) is given in seconds

These 3 notions are related.

acceleration = velocity / acctime

Thus:

* when velocity is changed, acctime is updated
* when acceleration is changed, acctime is updated
* when acctime is changed, acceleration is updated.


```python
DEMO [17]: mot1.acceleration  ⏎
 Out [17]: 10.0

DEMO [18]: mot1.acctime  ⏎
 Out [18]: 0.4

DEMO [19]: mot1.acceleration=20  ⏎
DEMO [20]: mot1.acctime  ⏎
 Out [20]: 0.2

DEMO [21]: mot1.acctime=1  ⏎
DEMO [22]: mot1.acceleration  ⏎
 Out [22]: 4.0

```


### limits

Read-Write  -  float  -  from config and persistant in memory

Software limits are defined in user unit.

They can be changed simultaneously or one by one:
```python
DEMO [56]: mot1.limits  ⏎
 Out [56]: (-111.0, 111.0)

DEMO [57]: mot1.limits = (-5, 5)  ⏎

DEMO [58]: mot1.low_limit = -4  ⏎
DEMO [59]: mot1.high_limit = 4  ⏎

```

```python
DEMO [4]: move(mot1, 1122)  ⏎
!!! === ValueError: mot1: move to `1122.000000' (with 0.010000 backlash) would go beyond high limit (4.000000) === !!!
```

### tolerance

Read-Only  -  float  -  from config

At the begining of a movement, the controller position is compared to
the last known axis dial position. If the difference is larger than
the Axis `tolerance`, an exception is raised with a message like:

`discrepancy between dial (0.123) and controller position (0.100), aborting`

This can occur if the axis is moved by another software (*IcepapCMS* for
example)

The axis must be re-synchronized with the BLISS session using:

```python
mot1.sync_hard()
```


###  backlash

Read-Only  -  float  -  from config

Backlash attribute defines a small movement performed at the end of a
movement if this movement's direction is opposed to the sign of the
backlash.

The backlash is defined in the config in user units.

## Encoder

Defined as an object that can be used standalone or linked to an Axis.

After a movement, if:

* an encoder is associated to the axis
* AND `check_encoder` is set to `True` in config

then the encoder position is read and compared to the target position
of the movement. In case of difference outside the limit fixed by
**Encoder tolerance**, an exception is raised with message:

`"didn't reach final position"`

The Axis must then be re-synchronized with:

`mot1.sync_hard()`


## In-line information


To help users to find their way in all these settings, Axis have a
built-in 'info' function called by just typing their name.

Example in a BLISS shell:
```python
DEMO [11]: mot1 ⏎
 Out [11]: AXIS:
               name (R): mot1
               unit (R): um
               offset (R): 0.0000
               backlash (R): 0.01000
               sign (R): 1
               steps_per_unit (R): 52500.00
               tolerance (R) (to check pos. before a move): 0.001
               limits (RW):    Low: -111.00000 High: 111.00000
               dial (RW): 7.50
               position (RW): 7.50
               state (R): READY (Axis is READY)
               acceleration (RW):   10.00000  (config:   10.00000)
               acctime (RW):         0.40000  (config:    0.90000)
               velocity (RW):        4.00000  (config:    9.00000)
          ICEPAP CONTROLLER:
               controller: iceid212
               version: 3.17
          ICEPAP:
               host: iceid212 (ID: 0008.01A1.49C6) (VER: 3.17)
               address: 42
               status: POWER: ON    CLOOP: ON    WARNING: NONE    ALARM: NO
               IcepapEncoders(ENCIN='393759', ABSENC='-1687552', INPOS='0',
                              MOTOR='393744', AXIS='393750', SYNC='388568')
          ENCODER:
               tolerance (to check pos at end of move): 0.001
               dial_measured_position:    7.50017
```


## basic commands

* `on()` / `off()`: dependent on controller. For example for icepap,
  these commads switch the power on/off.
* to know where is your axis and how it feels:
    - `wa()`, `wm(mot1, ..., motN)`: print the dial and user position of all or a list of Axis
    - `sta()`, `stm(mot1, ..., motN)`: print the status of all or a list of Axis
* to move it move it:
    - `mv(mot1, 2.41)`: move motor `mot1` to user position 2.41
    - `umv(mot1, 2.41)`: idem and display intermediate positions to follow the move
    - `mvr(mot1, 0.1)`: move motor `mot1` by 0.1 from current position
    - `umvr(mot1, 0.1)`: idem and display intermediate positions to follow the move



Examples:
```python
DEMO [60]: sta()  ⏎
Axis    Status
------  ---------------------
mot1     READY (Axis is READY)
mot2     READY (Axis is READY)
mot3     READY (Axis is READY)
mot4     READY (Axis is READY)
psf     READY (Axis is READY)
psb     READY (Axis is READY)

DEMO [61]: stm()  ⏎
Axis    Status
------  --------

DEMO [62]: stm(mot1)  ⏎
Axis    Status
------  ---------------------
mot1     READY (Axis is READY)




```python
DEMO [1]: wa()  ⏎
Current Positions: user
                   dial

  mot1[parsec]    mot2     mot3     mot4     mot5      psf      psb
-------------  -------  -------  -------  -------  -------  -------
      0.00000  4.00000  0.00000  0.00000  0.00000  4.00000  1.00000
      5.00000  4.00000  0.00000  0.00000  0.00000  4.00000  1.00000


DEMO [4]: wm(mot1)  ⏎

            mot1[parsec]
--------  -------------
User
 High         111.00000
 Current        0.00000
 Low         -111.00000
Offset         -5.00000

Dial
 High         116.00000
 Current        5.00000
 Low         -106.00000


DEMO [9]: umv(mot1, 1, mot3, 2)  ⏎
Moving mot1 from 2 to 1
Moving mot3 from 4 to 2

  mot1       mot3
   1.000     2.000
```



## Axis-Related features

* Scans will pe presented later.

* See [Motion Axis](motion_axis.md) for a detailled Axis description.
    - [Icepap Configuration](config_icepap.md)

* Standard scans are introduced here: [Default Scans](bliss_standard_scans.md).

* Trajectories

* CalcMotors
    - Calc motor example (slits, tables)
    - calc of calc
    - traj on calcs

* events on change of state, position

* special moves
    - group moves: to move multiple motors in same time
    - jog: to move in velocity rather than in position
    - home / limit search: to recover reference positions

* special motor controller
    - NoSettingsAxis: to avoid caching of settings
    - ModuloAxis: for rotary actuators
    - shutters: for 2-positions actuators

