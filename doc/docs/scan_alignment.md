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

In case of multi motors (anscan), all this function can use a specific
axis either for the calculation or the movement (`goto_` functions).

```python
goto_cen(axis=robz)
peak(axis=robz)
```

If the axis is not specify, `cen`, `com`, `peak` functions will return value for
all axis and the `goto_` functions will move all motors.

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


!!! note "For Developpers"

    `plotselect()` user function is imported from `bliss.common.standard`
    and is built on top of `bliss.common.scans.plotselect()` which can
    be advantageously used in non interactive sequences.
    
    The list of selected counters is stored via a HashSetting using
    `<session_name>:plot_select` as key.

## fwhm()

This function return th Full Width at Half of the Maximum of data of last scan.

```python
size = fwhm()
```

## cen()

This function return the motor position corresponding to the center of the fwhm
of the last scan.
```
fwhm_center = cen()
```

## com()

This function return the motor position of the center of mass.
```
center_of_mass_pos = com()
```

## peak()

This function return the motor position at the counter maximum value.
```
max_pos = peak()
```

## goto_ functions

* all the previous functions have a corresponding `goto_XXX()` function
to go directly to the calculated position:
    * `goto_cen()`
    * `goto_com()`
    * `goto_peak()`
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
```

## where()

To display current position of the motor used in the **last scan** use:
```python
where()
```
