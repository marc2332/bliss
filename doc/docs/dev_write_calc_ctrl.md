
# Writing a new Calculation Controller

Calculation controller (`CalcController`) are designed to built
*virtual* axes over *real* axes.

For example: N-legs tables, energy motor, slits, rotated translations.


![Screenshot](img/axis_group_calc.svg)


## Minimal set of functions to implement

*  `calc_from_real(self, positions_dict)`
    * Must return a dictionnary of virtual positions corresponding to
      `<positions_dict>` values of real axes.


*  `calc_to_real(self, positions_dict)`
    * Must return a dictionnary of real positions corresponding to
      `<positions_dict>` values of virtual axes.

!!! note
    Those 2 functions **must** be able to operate on numpy arrays, not only
    scalar values. Indeed, the limits checking feature before move needs to
    execute the calculation functions with numpy arrays.

## Code example

Example of code to create a calculational controller to link 2 axes
with a 3.1415 factor.

```python
def calc_from_real(self, positions_dict):
    calc_mot_axis = self._tagged["calc_mot"][0]
    calc_pos = 3.1415 * positions_dict["real_mot"]

    return {"calc_mot": calc_pos}

def calc_to_real(self, positions_dict):
    calc_mot_axis = self._tagged["calc_mot"][0]
    real_pos = positions_dict["calc_mot"] / 3.1415

    return {"real_mot": real_pos}
```

## Mockup calc controller

`calc_motor_mockup` can be found in `bliss/controllers/motors/mockup.py`


```yaml
controller:
    class: calc_motor_mockup
    module: mockup
    axes:
        -
          name: $m1
          tags: real real_mot
        -
          name: calc_mot
          tags: calc_mot

```

Usage:

```
CYRIL [1]: wa()
Current Positions (user, dial)

  calc_mot       m1
----------  -------
   3.14150  1.00000
   3.14150  1.00000

CYRIL [2]: mv(m1,2)
CYRIL [3]: wa()
Current Positions (user, dial)

  calc_mot       m1
----------  -------
   6.28300  2.00000
   6.28300  2.00000
```


![Screenshot](img/dial_user_ctrl.svg)

!!! note
    During step scans, real axes positions for calculated axes will be emitted as an additional acquisition
    channel of the motor master -- unless "emit_real_position" is set to False in the controller configuration
