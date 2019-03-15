# Support of a new motor controller

Motors control in BLISS has been built with an *"easy and fast
integration"* objective in mind. One of the goals of BLISS is to offer
to users an easiest possible way to implement a new controller.

In order to reach this objective, BLISS motors control has been
designed in two parts:

* A generic *motor engine* (`axis.py` module) in charge of driving
  motors with taking care of most of typical motion concepts:
  velocity, acceleration, backlash, limits, etc.
* *Motor plugins* implementing functions used by the *motor engine*
  for each supported motor controller.

To create such a *BLISS motor plugin*, a python module, implementing a
set of standard methods dealing with functionalities offered by the
controller, has to be created. Some of these methods are mandatory,
some of them are needed only if implementation of these
functionalities is wanted. In addition, some *custom commands* can be
defined to implement very specific features of a motor controller.

---

## Example and skeleton of BLISS motor plugin

* `bliss/controllers/motors/mockup.py` is an example of simulated motor

## Minimal set of functions to implement

In order to get a working (but limited) BLISS motor plugin, the
following methods (further detailed) are mandatory:

* `initialize_axis()`
    * NB: If this method in not defined, it create not necessarily an error
    but initialization of axis is not done.
* `start_one(self, motion)`
* `stop(self, axis)`
* `state(self, axis)`


## Controller setup

### Initialization sequence

* **initialize()**: called when an object of that controller class
  is created (called only once, even if many objects are created)
* before first usage of one axis of this controller object (for
  example, read axis state), hardware initialization is performed in
  following order:
    * **initialize_hardware()**: called once for one controller whatever the number of axes.
    * **initialize_axis()**: called once per axis at first use of this axis.
    * **set_velocity()** and **set_acceleration()** with settings values if
      these methods have been implemented.
    * limits application
    * **initialize_hardware_axis()**: called once per axis.


### Initialization methods
* `__init__(self, name, config, axes)`
    * Initialization of internal class attributes

* `initialize(self)`
    * Pure software initialization (like communication channel init). No
    access to physical hardware required at this stage.
    * Called at axes creation (only once, even if many objects are created)

* `initialize_hardware(self)`
    * Must check that controller is responding and initializes the controller.
    * It is executed only once per controller, on first access on any of
    the defined axes.

* `initialize_axis(self, axis)`
    * Software initialization of an axis.
    * Called once per defined axis.

* `initialize_hardware_axis(self, axis)`
    * Hardware initialization of one axis. Typically, power-on the axis,
    activate the closed-loop, set a PID, etc.
    * Called once per defined axis.

* `set_on(self, axis)`
    * Must enable the given axis (ie. activate, power on, ...)
    * Not automatically called ???

* `set_off(self, axis)`
    * Must disable the given axis (power off, breaks ? park ?).
    * Not automatically called ???

### Velocity/Acceleration methods

* `read_velocity(self, axis)`
     * Must return the velocity read from the motor controller
     in *controller unit per second*

* `set_velocity(self, axis, new_velocity)`
     * Must set velocity of `<axis>` in the controller to `<new_velocity>`.
     * `<new_velocity>` is given in *controller unit per second* (ie: user
     units per second multiplied by `steps_per_units` value).
     * If `set_velocity()` method is defined, then *velocity* parameter is
     mandatory in config.

* `read_acceleration(self, axis)`
     * Must return acceleration read from the motor controller
     in *controller unit per second\*\*2*

* `set_acceleration(self, axis, new_acc)`
    * Must set acceleration of `<axis>` in the controller to `<new_acc>`.
    * `<new_acc>` is given in *controller unit per second\*\*2* (ie:
    user unit per second\*\*2 multiplied by `steps_per_units` value).
    * If `set_acceleration()` function is defined, then *acceleration*
    parameter is mandatory in config.

## Motion commands

### Status and position methods
* `state(self, axis)`
    * Must return an `AxisState()` object. `AxisState()` has the following standard states
        * **MOVING**: Axis is moving
        * **READY**:  Axis is ready to be moved (not moving ?)
        * **FAULT**:  Error from controller
        * **LIMPOS**: Hardware high limit active
        * **LIMNEG**: Hardware low limit active
        * **HOME**:   Home signal active
        * **OFF**:    Axis is disabled (must be enabled to move (not ready ?))

    * To allow a motion, the axis must be in **READY** state and not
      have one of **LIMPOS** or **LIMNEG** states. Once a motion is
      started, state is switched to **MOVING**. Motion will be
      considered finished when the **MOVING** state disappear.

    * Any controller can add its own state to inform user of current
      controller state. For example:

            from bliss.common.axis import AxisState
            state = AxisState()
            state.create_state("CLOSED_LOOP_ERROR", "Error on axis closed loop")
            state.create_state("HOMING_DONE", "Homing has been performed")

    * To activate one of those new states:

            state.set("CLOSED_LOOP_ERROR")

* `read_position(self, axis)`
    * Must return the current position (read from the controller) of the axis in *controller units*
    * Called before and after a movement.

* `set_position(self, axis, new_position)`
    * Must set controller position to &lt;`new_position`&gt;
    * Must return the current position of the axis in *controller units*
    * Called when changing the dial position of the controller.

### single axis motion
* `prepare_move(self, motion)`
    * Must prepare a movement
    * Can be used to arm a movement
    * Called just before `start_one()`.

* `start_one(self, motion)`
    * Must send to controller a start on one axis.
    * Called in commands like `mymot.move(10.0)`
    * NOT called in commands `move(axis, pos)`

* `stop(self, axis)`
    * Must send a command to the controller to halt this axis movement
    * Called on a `ctrl-c`

!!! note

    Motion object: this object holds requested motion parameters:
    
        * motion.axis:       axis to be moved
        * motion.target_pos: absolute motion target position (in controller units)
        * motion.delta:      corresponding relative motion delta (in controller units)
        * motion.backlash:   backlash (in controller units ?)

### Group motion
* `start_all(self, *motions)`
    * Must start all movements for all axes defined in `motions`
    * Multiple starts can be optimized on controllers allowing multi-axes commands
    * `motions` is a tuple of `motion`
    * Called in a group move
        * `move(m1, 3, m2, 1)` is a group move
        * `move(m1, 3)` is a group move as well as `umvr()` `mvr()`
        * `m1.move(3)` is a single move

* `stop_all(self, *motions)`
    * Must stop all movements defined in `motions`
    * Called on a `ctrl-c` during a group move

### jog motion
* `start_jog(self, axis, velocity, direction)`
    * Must start a "jog" movement: an unfinished movement at `velocity` speed.
      Movement will be finished when user calls `stop_jog()`.
    * Called by `axis.jog()` function.

* `stop_jog(self, axis)`
    * Must stops a jog motion.
    * Called by `axis.stop()` or `axis.stop_jog()`

### trajectory motion
The trajectory methods are used by the `TrajectoryGroup` class.

In Bliss two type of trajectories can be send to a controller:

  - `Trajectory` define **one continous movement**.
  This movement is given by a numpy **p** osition,**v** elocity and **t** ime array.
  This object has two argument:
    - **axis** instance
    - **pvt** a numpy **pvt** array ( *"position","velocity","time"* ).
    - **events_positions** list of triplet **pvt** where the controller should send event when axes
    reach this triplet during trajectory motion.

  - and `CyclicTrajectory` define **trajectory pattern** with a **number of cycle**.
  This object has this arguments:
    - **origin** the absolute starting position
    - **pvt_pattern** a numpy **pvt** array relative to the **origin** position.
    - **nb_cycles** number of iteration for the **pvt_pattern**.
    - **is_closed** return True if first point == to last point.
    - **events_pattern_positions** list of event for this trajectory pattern.
    - *pvt* full trajectory, this one is **calculated** to help controller which
    doesn't managed trajectory pattern.
    - *events_positions* list of all event on the full trajectory,
    same as above, it's **calculated**.
    
####Methods involved:

* `has_trajectory(self)`
    * Must return true if motor controller supports trajectory
* `prepare_trajectory(self, *trajectories)`
    * Musst prepare controller to perform given trajectories
* `move_to_trajectory(self, *trajectories)`
    * Must to the first (or starting) point of the trajectories
* `start_trajectory(self, *trajectories)`
    * Must move motor(s) along trajectories to the final position(s)
* `stop_trajectory(self, *trajectories)`
    * Must interrupt running trajectory motion

```python
def prepare_trajectory(self, *trajectories):
    for traj in trajectories:
        axis = traj.axis #get the axis for that trajectory
        pvt = traj.pvt # get the trajectory array
        times = pvt['time'] # the timing array (absciss)
        positions = pvt['position'] # all the axis positions
        velocities = pvt['velocity'] # all axis velocity (trajectory slope)
```

When the Bliss core ask a controller to move his axis in trajectory, the calling sequence is fixed to:

  - first call `prepare_trajectory`
  - secondly call `move_to_trajectory`
  - then `start_trajectory`
  - and eventually `stop_trajectory` in case of movement interruption.

#### event on trajectory

  - `has_trajectory_event` should return True if capable.
  - `set_trajectory_events` register events on the trajectory given has argument.
  Use **events_positions** or **events_pattern_positions** of `Trajectory` object.
  
### Calibration methods
* `home_search(self, axis, direction)`
    * Must start a home search in the positive direction if `direction`>0, negative otherwise
    * Called by `axis.home(direction)`
* `home_state(self, axis)`
    * Must return a MOVING state when still performing home search, and a READY state when homing is finished
    * Called by axis when polling to wait end of home search
* `limit_search(self, axis, limit)`
    * Must move to one hardware limit (positive if `limit`>0, negative otherwise)
    * Called by `axis.hw_limit(limit)`

### Encoder methods
* `initialize_encoder(self, encoder)`
    * Must perform init task related to encoder.
    * Called at first usage of the encoder
        * ``read()`` or ``measured_position()`` of related axis if linked to an axis.

* `read_encoder(self, encoder)`
    * Must return the encoder position in *encoder_steps*
    * Called by `encoder.read()` method by exported Encoder object or by `axis.measured_position()` of related axis
    * `encoder.read()` is called at the end of a motion to check if final position has been reached.

* `set_encoder(self, encoder, new_value)`
    * Must set the encoder position to ``new_value``
    * ``new_value`` is in encoder_steps
    * Called by `encoder.set(new_value)` 

### Information methods
* `get_id(self, axis)`
* `get_info(self, axis)`
    * Musst return printable infos for axis
    * Called by `axis.get_info()`

### Direct communication methods
These methods allow to send arbitrary commands and read responses from the controller.

They can be useful to test, to debug or to tune a controller.

* `raw_write(self, com)`
    * Must send the `<com>` command.
    * Called by user.

* `raw_write_read(self, com)`
    * Must send the `<com>` command and return the answer of the controller.
    * Called by user.

### Position triggers
* `set_event_positions(self, axis_or_encoder, positions)`
    * This method is use to load into the controller a list of positions for
        event/trigger.  The controller should generate an event
        (mainly electrical pulses) when the axis or the encoder pass
        through one of this position.

* `get_event_positions(self, axis_or_encoder)`


### Custom commands ###

The `object_method` decorator is used to create custom commands.

Example of custom command:

    @object_method(types_info=("None","int"))
    def get_user_mode(self,axis):
        return int(self._query("UM"))

`types_info` parameter of this decorator allows to define types of parameters used
by the created controller command.


## NOTES

* Steps per unit is in *unit-1* (1 per default)
* Backlash is in *user_unit*
* *user_unit* can be millimeter, micron, degree etc..
* *encoder_steps*
* developer of the plugin and units management
    * On the user point of view, motors are driven in *user units*,
      whatever unit is used in the controller API
    * On the programmer point of view, the BLISS plugin is dealing with
      controller units (steps, microns, ...)
    * The programmer should not have to deal with units conversions.


*`move(m1, 3)`: uses `Group.move()`
*`m1.move(3)`: uses `Axis.move()`


