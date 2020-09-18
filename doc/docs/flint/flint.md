## What is Flint

Flint is a GUI companion for BLISS.

- It provides a [live display of BLISS scans](flint_scan_plotting.md)

- Helper to configure your BLISS setup:

    - [Lima ROI counter setup](flint_roi_counters.md)

- Few graphic interaction for user scripts:

    - [User data plotting](flint_data_plotting.md)
    - [Interactive selection of region](flint_interaction.md)

Few other basic API are provided bellow.

## Automatic start

When Flint is running, it will automatically display live scans.

If the session is configured for (which is the case for the demo session),
Flint will be started by the invocation of any standard scan command.

It can be enabled this way:
```python
SCAN_DISPLAY.auto = True
```

## Programmatic start and stop

From BLISS shell, few basic interaction with Flint are provided.

To invoke or retrieve a proxy to interact with Flint you can use:

```
flint()
```

!!! note
     If there is a fail to find or to create Flint, this method will raise an
     exception.

The returned object provides few methods to close the application:

```
f = flint()
f.close()    # request a normal close of the application
f.kill()     # kill
f.kill9()    # kill -9
```

## Set the focus

If your window manager provides this feature, you can force the focus on the
application this way:

```
f = flint()
f.focus()
```
