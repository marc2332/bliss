# Motion hooks

a *Motion hook* is a piece of code that can be attached to a motor or
a list of motors and executed at particular moments.

!!! note
    For brave old users of SPEC, motion hooks can replace `cdef()`

A new motion hook definition is a python class which inherits from the
base hook class `bliss.common.hook.MotionHook` and implements the
`bliss.common.hook.MotionHook.pre_move` and
`bliss.common.hook.MotionHook.post_move` methods. The base
implementation of both methods does nothing so you may implement only
what you need.

Both methods receive a motion argument. It is a list of
`bliss.common.axis.Motion` objects representing the current motion.

You are free to implement whatever you need in `pre_move` and `post_move`.
However, care has to be taken not to trigger a movement of a motor which
is being moved. Doing so will most likely result in an infinite
recursion error.

You can use `pre_move()` to prevent a motion from occuring if a certain
condition is not satisfied. In this case `pre_move()` should raise an
exception explaining the reason.

A hook is configured using the bliss *YAML* static configuration.

To link an axis with a specific hook you need to add a `motion_hooks`
key to your axis *YAML* configuration. It should be a list of
references to hooks defined somewhere else (see example below).

## Example use case: motor with air-pad

Imagine that in your laboratory there is a motor `m1` that move a heavy
granite table. Before it moves, an air-pad must be filled with air by
triggering a PLC and after the motion ends, the air-pad must be emptied.
Further, since there is no pressure meter, it has been determined
empirically that after the air-pad fill command is sent to the PLC, we
have to wait 1s for the pressure to reach a good value before moving and
wait 2s after the motion is finished.

So the hook implementation will look something like this:

```python
# bliss/controllers/motors/airpad.py
import gevent
from bliss.common.hook import MotionHook

class AirpadHook(MotionHook):
    """air-pad motion hook"""

    def __init__(self, name, config):
        self.config = config
        self.name = name
        self.plc = config['plc']
        self.channel = config['channel']
        super(AirpadHook, self).__init__()

    def pre_move(self, motion_list):
        self.plc.set(self.channel, 1)
        gevent.sleep(1)

    def post_move(self, motion_list):
    self.plc.set(self.channel, 0)
    gevent.sleep(2)
```

And its *YAML* configuration:

```yaml
# motors.yml

plcs:
    - name: plc1
    # here follows PLC configuration

hooks:
  - name: airpad_hook
    plugin: bliss
    package: bliss.controllers.motors.airpad
    plc: $plc1


motors:
  - controller: Mockup
    plugin: emotion
    axes:
  - name: m1
    # here follows motor configuration
    motion_hooks:
      - $airpad_hook
```

Note that in this example only one hook was used for the `m1` motor. You
can define a list of hooks to be executed if you need. The hooks are
executed in the order given in the `motion_hooks` list.

## Example use case: preventing collisions

Hooks can be used to prevent a motion from occuring if certain
conditions are not met.

Lets say that in your laboratory there are two detectors which can move
in the XY plane and you want to prevent collisions between them.

*det1* can only move in the Y axis using motor `det1y` an `det2` can
move in the X and Y axis using motors `det2x` and `det2y`.

Lets say that *det1* is located at *X1=10*, *Y1=200* when `det1y=0`. For
collision purposes it is suficient to approximate the detector geometry
by a sphere of radius *R1=5*.

Lets say that *det2* is located at *X1=10*, *Y1=10* when `det2x = 0`
and `det2y = 0`. For collision purposes it is suficient to approximate
the detector geometry by a sphere of radius *R1=15*.

So, every time that at least one of the three motors `det1y`, `det2x` or
`det2y` moves, a pre-check needs to be made to be sure the motion is not
going to collide the two detectors.

The code should look something like this:

```python
# bliss/controllers/motors/coldet.py
import math
import collections

Point = collections.namedtuple('Point', 'x y')

from bliss.common.hook import MotionHook

class DetectorSafetyHook(MotionHook):
    """Equipment protection of pair of detectors"""

    D1_REF = Point(10, 200)
    D2_REF = Point(10, 10)
    SAFETY_DISTANCE = 5 + 15

    class SafetyError(Exception):
        pass

    def __init__(self, name, config):
        self.axes_roles = {}
        super(DetectorSafetyHook, self).__init__()

    def add_axis(self, axis):
        # overload super add_axis to be able to store which axis has which
        # roles in the system
        tags = axis.config.get('tags')
        if 'd1y' in tags:
            self.axes_roles[axis] = 'd1y'
        elif 'd2x' in tags:
            self.axes_roles[axis] = 'd2x'
        elif 'd2y' in tags:
            self.axes_roles[axis] = 'd2y'
        else:
            raise KeyError('detector motor needs a safety role')
        super(DetectorSafetyHook, self).add_axis(axis)

    def pre_move(self, motion_list):
        # determine desired positions of all detector motors:
    # - if motor in this motion, get its target position
    # - otherwise, get its current position
        target_pos = dict([(axis, axis.position()) for axis in self.axes_roles])
        for motion in motion_list:
            if motion.axis in target_pos:
                target_pos[motion.axis] = motion.target_pos

        # build target positions by detector motor role
        target_pos_role = dict([(self.axes_roles[axis], pos)
                                for axis, pos in target_pos.items()])

        # calculate where detectors will be in space
        d1 = Point(self.D1_REF.x,
                   self.D1_REF.y + target_pos_role['d1y'])
        d2 = Point(self.D2_REF.x + target_pos_role['d2x'],
                   self.D2_REF.y + target_pos_role['d2y'])

        # calculate distance between center of each detector
        distance = math.sqrt((d2.x - d1.x)**2 + (d2.y - d1.y)**2)

        if distance < self.SAFETY_DISTANCE:
            raise self.SafetyError('Cannot move: motion would result ' \
                                   'in detector collision')
```

And its *YAML* configuration:

```yaml
 hooks:
   -   name: det_hook
       class: DetectorSafetyHook
       module: motors.coldet
       plugin: bliss

 controllers:
   -   name: det1y
       acceleration: 10
       velocity: 10
       steps_per_unit: 1
       low_limit: -1000
       high_limit: 1000
       tags: d1y
       unit: mm
       motion_hooks:
         - $det_hook
   -   name: det2x
       acceleration: 10
       velocity: 10
       steps_per_unit: 1
       low_limit: -1000
       high_limit: 1000
       tags: d2x
       unit: mm
       motion_hooks:
         - $det_hook
   -   name: det2y
       acceleration: 10
       velocity: 10
       steps_per_unit: 1
       low_limit: -1000
       high_limit: 1000
       tags: d2y
       unit: mm
       motion_hooks:
         -  $det_hook
```

!!! note
    For demonstration purposes, these examples are minimalistic
    and do no error checking for example. Feel free to use this code
    but please take this into account.

