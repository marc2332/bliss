All new shutter object should inherited from `Shutter` class located
under *bliss/common/shutter.py*. Methods which should be over-loaded
are:

* `_init(self)` software initialization ie: communication, internal state...
* `_initialize_hardware(self)` initialize hardware parameters. It is call only
once and only by the first client. The minimum to do in this method is to go
back to the previous **mode** if it has a meaning for your shutter.
* `_set_mode(self, mode)` change the opening/closing mode. mode are:
    - **EXTERNAL** externally control i.e: with a TTl signal.
    - **MANUAL** equal to software which mean that the opening/closing are done
    with `open` and `close` methods.
    - **CONFIGURATION** mode to tune the shutter. i.e: in case of axis shutter,
    this mode should be use to calibrate the opening and closing position.

!!! note
    Leave this method unimplemented if **mode** mean noting for your shutter.

* `_state(self)` return the current state of the shutter either **self.OPEN**, **self.CLOSED** or
**self.UNKNOWN**.
* `_open(self)` to open the shutter
* `_close(self)` to close the shutter
* `_measure_open_close_time(self)` *optional* to return the opening and the closing time for a shutter