*Watchdog* are use to follow if detectors involved in the scan have
the right behavior.  For that you need to register on a `Scan` a
callback class inherited from `WatchdogCallback`.

# WatchdogCallback
This callback has 4 possible methods:

- `.on_scan_new` called we the scan starts
- `.on_scan_end` called at the end of the scan
- `.on_scan_data` called when new data is emitted by the scan.
- `.on_timeout` called basically when the watchdog timed out.

## `.on_scan_data`

In this method you may follow if data received are what you expect.
i.e: check if detectors received all trigger. In case of a detector's
misbehavior, you can raise an exception. All exception will bubble-up
except the `StopIteration` which is treated as a normal stop.

## `.on_timeout`

Timeout callback is called if no other event happen between the **watchdog_timeout**.
i.e: if no more data are received and we reach the **watchdog_timeout**.
If you want to *stop* the scan, you need to raise an exception like in `.on_scan_data`.

!!! note

    In the constructor of this class, you can specify the
    **watchdog_timeout** which is the minimum calling time of the
    method `.on_timeout` of this class.
