# Alignment functions

This chapter will introduce function needed for alignment. Those
function will use the **selected counter** data (plotselect) of the
**last scan** (SCANS[-1]) for calculation.

## counter selection

The counter selection can be done graphically with *Flint* or with the
*plotselect* function. You can select **only one** counter.
    plotselect(counter)

## cen function

This function return the fwhm center motor position and the fwhm
(**f**ull **w**idth at **h**alf **m**aximum) of the last scan.
    fwhm_center,fwhm = cen()

## com function

This function return the motor position of the center of mass.
    center_of_mass_pos = com()

## peak function

This function return the motor position at the counter maximum.
    max_pos = peak()

## Go to function

All functions *cen,peak,com* has function to go directly to the
calculated position. Before the movement, the function will print the
previous position and the future position of the motor. In case of
motion abortion, the motor return to it's previous position.  At the
end of the function the motor position will be display in *Flint*
unless the variable **SCAN_DISPLAY.motor_position** is equal to
**False**.
i.e: *goto_cen* will move the motor to the center of fwhm.

## Display current motor

To display current position of the motor used in the **last scan** use:
    where()

