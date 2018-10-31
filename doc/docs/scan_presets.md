

A *preset* (managed by `ChainPreset` class) will be call at the
beginning and at the end of a scan. It's an equivalent of user's hooks
in Spec.


As example, typical usages of this class are:

* to manage the software opening/closing of a shutter
* to test the presence, of an environmental condition device like a cryo-stream flux
* to control a multiplexer to route the signals from/to the scanned devices





