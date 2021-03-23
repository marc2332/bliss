# Alignment functions

This chapter introduces functions usually used for alignment.

Those functions use the **selected counter** data (`plotselect`) of the **last
scan** (`SCANS[-1]`) for calculation.

In case of multi counters, it is possible to specify the counter to use
for the alignment as parameters. i.e:

```python
cen(counter=my_counter)
goto_com(counter=my_counter)
```

In case of multi motors (anscan), all these functions can use a specific
axis either for the calculation or the movement (`goto_` functions).

```python
goto_cen(axis=robz)
peak(axis=robz)
```

If the axis is not specified, `cen`, `com`, `peak`, `trough` functions will return value for
all axes and the `goto_` functions will move all motors.

## Counters selection

The counter selection can be done graphically with *Flint* or with the
`plotselect` user function: `plotselect(<counter_list>)`


!!! example
    ```python
    DEMO [2]: plotselect(sim_ct_2)
    
    Currently plotted counter(s):
    - sim_ct_2
    ```

Without argument, the command will display a help message and the list of
currently selected counters.

!!! example
    ```python
    DEMO [5]: plotselect()
    
    plotselect usage:
        plotselect(<counters>*)
    example:
        plotselect(counter1, counter2)
    
    
    Currently plotted counter(s):
    - sim_ct_1
    - sim_ct_calib_gauss
    - elapsed_time
    ```


!!! note "For Developers"

    `plotselect()` user function is imported from `bliss.common.standard`
    and is built on top of `bliss.common.scans.plotselect()` which can
    be advantageously used in non interactive sequences.
    
    The list of selected counters is stored via a HashSetting using
    `<session_name>:plot_select` as key.

## fwhm()

This function returns th Full Width at Half of the Maximum of data of last scan.

```python
size = fwhm()
```

## cen()

This function returns the motor position corresponding to the center of the fwhm
of the last scan.
```
fwhm_center = cen()
```

## com()

This function returns the motor position of the center of mass.
```
center_of_mass_pos = com()
```

## peak()

This function returns the motor position at the counter maximum value.
```
max_pos = peak()
```

## trough()

This function returns the motor position at the counter minimum value.
```
min_pos = trough()
```

## goto_ functions

* all the previous functions have a corresponding `goto_XXX()` function
to go directly to the calculated position:
    * `goto_cen()`
    * `goto_com()`
    * `goto_peak()`
    * `goto_min()`
* Before the movement, the `goto_XXX` functions will print the **previous position** and
the **future position** of the motor with a `WARNING` message.
* In case of motion abortion, the motor returns to its previous
position.
* At the end of the function the motor position will be displayed in
*Flint* unless the variable `SCAN_DISPLAY.motor_position` is equal
to `False`.  i.e: *goto_cen* will move the motor to the center of
fwhm.


examples:
```python
DEMO [11]: plotselect(simct1)

DEMO [12]: goto_cen()
WARNING  bliss.scans: Motor mm1 will move from 10.000000 to 4.337243

DEMO [13]: goto_peak()
WARNING  bliss.scans: Motor mm1 will move from 4.337243 to 10.000000

DEMO [14]: goto_com()
WARNING  bliss.scans: Motor mm1 will move from 10.000000 to 4.805529

DEMO [15]: goto_min()
WARNING  bliss.scans: Motor mm1 will move from 4.805529 to 0.000000

```

## where()

To display current position of the motor used in the **last scan** use:
```python
where()
```

## Customizable alignment functions: `find_position` and `goto_custom`

In case specific math is needed to treat a special signal form it is
possible to use any python function that calculates an *x-position* based
on an *x-* and *y-array*.

```python
DEMO [11]: def special_com(x, y):
            return numpy.average(x, weights=y)

DEMO [12]: print(find_position(special_com))
DEMO [13]: goto_custom(special_com)
```

The math function and specific helpers can also be defined in the
setup script of the session. Here is an example for the setup script
so that `find_special` and `goto_special` will be available in the shell 
afterwards and can be used without arguments.

```python
import numpy
from bliss.shell.standard import goto_custom,find_position

def special_com(x, y):
    return numpy.average(x, weights=y)

def find_special():
    return find_position(special_com)

def goto_special():
    return goto_custom(special_com)
```


## Use of alignment helpers on a specific scan

Alignment helpers can also be used on any scan object (not necessarily the
last scan that was done). In this case there is **no interaction with flint** 
and **plotselect is not used** to avoid confusion. Here is an example:

```python
TEST_SESSION [1]: s1 = ascan(roby,0,1,20,.1,diode)
TEST_SESSION [2]: s2 = ascan(robz,2,3,20,.1,diode2)
TEST_SESSION [3]: s1.cen(diode)
         Out [3]: 0.46723394864708406
TEST_SESSION [4]: s1.goto_cen(diode)
```

For scans that involve multiple axes it is also possible to operate only
on one specific axis and not on all axes that are involved in the scan:

```python
TEST_SESSION [4]: s = a2scan(roby,0,1,robz,2,3,20,.1,sim_ct_gauss)
TEST_SESSION [5]: s.cen(sim_ct_gauss)
         Out [5]: {roby: 0.5, robz: 2.5}

TEST_SESSION [6]: s.cen(sim_ct_gauss,axis=robz)
         Out [6]: 2.5

TEST_SESSION [7]: s.goto_cen(sim_ct_gauss,axis=robz)
Moving robz from 3 to 2.5
```
