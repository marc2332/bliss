All new shutter object should inherited from `Shutter` class located
under `bliss/common/shutter.py`.

Methods to over-load are:

* `_init(self)`: software initialization ie: communication, internal state...
* `_initialize_hardware(self)`: initializes hardware parameters. It is called only
once and only by the first client. The minimum to do in this method is to go
back to the previous **mode** if it has a meaning for your shutter.
* `_set_mode(self, mode)`: changes the opening/closing mode. Modes are:
    * `EXTERNAL`: externally controled i.e: with a TTl signal.
    * `MANUAL`: equals to *software* which means that the opening/closing are done
      with `open()` and `close()` methods.
    * `CONFIGURATION`: mode to tune the shutter. i.e: in case of axis shutter,
    this mode should be use to calibrate the opening and closing position.

!!! note
    Leave this `_set_mode` method unimplemented if **mode** means nothing for your shutter.

* `_state(self)`: returns the current state of the shutter
     * Either `self.OPEN`, `self.CLOSED` or `self.UNKNOWN`
* `_open(self)`: to open the shutter
* `_close(self)`: to close the shutter
* `_measure_open_close_time(self)` (optional): to return the opening plus the closing time for a shutter

