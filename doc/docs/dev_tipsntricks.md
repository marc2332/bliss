

# Tips for BLISS programming


## cleanup

**cleanup context manager** feature allows to restore parameters of a
*motor* or a *lima device* after the execution of code block which
involves them.

*after the execution* means:

* on a Control-C
* at the normal end of the code block

Devices to consider are defined in first parameter of cleanup function.

Parameters to restore are defined in `restore_list`.

Same behaviour but executed only on a `Control-C` is achieved with
`error_cleanup`.


### Motors

For Motors, this context manager would guarantee that they will be
stopped in any case, or even returned to their initial position if
**axis.POS** is in **restore_list**.  You also have the possibility to
restore the velocity (axis.VEL), the acceleration (axis.ACC) or the
limits (axis.LIM).  All motors in the context will be waited.

From `bliss/common/scans.py`:

    axis = enum.Enum("axis", "POS VEL ACC LIM")
    lima = enum.Enum("lima", "VIDEO_LIVE")


Usage examples from `bliss/common/scans.py`


    from bliss.common.cleanup import cleanup, axis as cleanup_axis
    
    ...
    
    with cleanup(motor, restore_list=(cleanup_axis.POS,)):
        scan = ascan(motor, start, stop, npoints, count_time, *counter_args, **kwargs)
    
    return scan

