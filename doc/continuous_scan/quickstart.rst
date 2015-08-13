===================
Controller tutorial : How to write a new controller ?
===================


To create an EMotion plugin for a new controller, you have to
provide:

- NewCtrl.py : to implement the NewCtrl  class.
- config_template_NewCtrl.xml : as an example of config file
- template_emotion_NewCtrl.tango : to have an example of tango ressources for your controller.


example : Mockup
----------------


Minimal set of standard functions to implement
-------------------------------------
- ``__init__(self, name, config, axes)``

