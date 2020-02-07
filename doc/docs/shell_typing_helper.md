# BLISS shell typing helper

To serve the demand of a simplified syntax when entering commands in the bliss
shell (without additional parenthesis and commas compared to ‘spec’) a *typing
helper* has been put in place. It is hard to respect both:

* the python code syntax
* enable users to type commands in similar way as they are used to in Spec


## Typing in the shell

!!! info
    Here, ⏎ represents pressing the Enter key and ␣ represents pressing the
    space bar.

Lets look at the `wm` command as an example.
Let us say we want to see the position of two motors m0 and m1.

In order for BLISS to be able to interpret the command we need to do:

```
$ wm(m0,m1)⏎
```

In ‘Spec’ one would have typed
```
$ wm␣m0␣m1⏎
```

The typing helper will map this way of typing the command to the proper python
syntax without having to type `(` , `,` and `)` manually. It replaces ␣ by `(`
or `,` where appropriate. Further it replaces ⏎ by `)`⏎ in case this complets
the input, or `()`⏎ in case a the input reprensts a python callable.
An example:

```
$ wa⏎
```

is transformed into
```
$ wa()⏎
```

The insertion behaviour of ⏎ is also applied to `;`.

## Objects info

In order to ease the acces of BLISS objects, a shell typing short-cut has been
implemented: if a name of a BLISS object is typed and then `⏎` is pressed, the return
value of `__info__()` method (if implemented) is printed.

This method is intented to return a *string* containing information about the
objects: name, class, configuration details etc.

This information can be customized for each type of object.

For example, any `Axis` will display it's name, controller and state. But
additional information can be added case by case.

VSCANNER Example:

```python
DEMO [1]:  sampy⏎
 Out [1]:  axis name: sampy
               state: READY (Axis is READY)
           controller: <bliss.controllers.motors.vscanner.VSCANNER object at 0x7fe0bf0c2fd0>
           ###############################
           Config:
             url=rfc2217://lid213.esrf.fr:28206
             class=VSCANNER
             channel letter:X
           ###############################
           ?ERR: b'OK\r'
           ###############################
           '?INFO' command:
           firmware version   : VSCANNER 01.02
           output voltage     : 0.200001 0.500205
           unit state         : READY
           ###############################
           $
           Max. number of lines: 3276
           Internal time step (microsec.): 50

           Current settings:
              LINE -0.100193 0 1 C
              SCAN 0 0 1 U
              VEL 0.001 0
              LTRIG MASK
              PTRIG MASK
              PIXEL 0 0
              HDELAY 0
           $
           ###############################
```

