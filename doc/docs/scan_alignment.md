# Alignment functions

This chapter introduces functions needed for alignment. Those
functions use the **selected counter** data (`plotselect`) of the **last
scan** (`SCANS[-1]`) for calculation.

## counter selection

The counter selection can be done graphically with *Flint* or with the
*plotselect* function. You can select **only one** counter.
```
plotselect(counter)
```

## `cen()`

This function return the fwhm center motor position and the **fwhm**
( Full Width at Half Maximum) of the last scan.
```
fwhm_center,fwhm = cen()
```

## `com()`

This function return the motor position of the center of mass.
```
center_of_mass_pos = com()
```
## `peak()`

This function return the motor position at the counter maximum.
```
max_pos = peak()
```

## Go to function

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
```
    where()
```
