
.. _bliss-motor-controller-how-to:

How to write a new motor controller
===================================


To create a Bliss plugin for a new controller, you have to
provide:

- NewCtrl.py : to implement the NewCtrl  class.
- config_template_NewCtrl.xml : as an example of config file
- template_bliss_NewCtrl.tango : to have an example of tango ressources for your controller.


example : Mockup
----------------


Minimal set of standard functions to implement
----------------------------------------------

- ``__init__(self, name, config, axes)``
- ``start_one(self, motion)``
- ``read_position(self, axis)``
- ``read_velocity(self, axis)``
- ``set_velocity(self, axis, new_velocity)``
- ``state(self, axis)``
- ``stop(self, axis)``


Other standard functions
------------------------
- ``initialize(self)``
- ``initialize_axis(self, axis)``
- ``finalize(self)``
- ``start_all()``
- ``read_acctime()``
- ``set_acctime()``
- ``stop_all(self, *motion_list)``
- ``home_search(self, axis)``
- ``home_state(self, axis)``
- ``get_info(self, axis)``


Example of custom commands
--------------------------

- ``raw_com(self, axis, cmd)``
- ``gate_on(self, axis, state)``
- ``get_id(self, axis)``

