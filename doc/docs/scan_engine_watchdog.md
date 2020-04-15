*Watchdog* objects are used to follow wether detectors involved in a scan have
the right behavior.

For this purpose, a callback class inherited from `WatchdogCallback` has to be
registered in a `Scan`.

# WatchdogCallback
This callback has 4 possible methods:

- `.on_scan_new()`: called when the scan starts
- `.on_scan_end()`: called at the end of the scan
- `.on_scan_data()`: called when new data is emitted by the scan
- `.on_timeout()`: called basically when the watchdog timed out

## `.on_scan_data()`

With this method it can be checked whether received data are what is expected.

Ex: to check if detectors received all triggers. In case of a detector's
misbehavior, an exception can be raiseed. All exceptions will bubble-up except
the `StopIteration` which is treated as a normal stop.

## `.on_timeout()`

Timeout callback is called if no other event happens between the **watchdog_timeout**.
i.e: if no more data are received and we reach the **watchdog_timeout**.

To *stop* the scan, an exception like in `.on_scan_data` must be raised.

!!! note
    In the constructor of this class, **watchdog_timeout**, which is the
    minimum calling time of the method `.on_timeout` of this class, can be
    specified.
