

# Creation of a new Calculation Controller


Calculation controller (`CalcController`) are designated to built *virtual* axes over *real* axes.

For example : N-legs tables, energy motor, slits, rotated translations.


## Minimal set of functions to implement

*  `calc_from_real(self, positions_dict)`
    * Must return virtual positions corresponding to <positions_dict> values of real axes.


*  `calc_to_real(self, positions_dict)`
    * Must return real positions corresponding to <positions_dict> values of virtual axes.


!!! note
    For efficiency considerations, real motors can be moved as *grouped axes*


![Screenshot](img/axis_group_calc.svg)

![Screenshot](img/dial_user_ctrl.svg)



