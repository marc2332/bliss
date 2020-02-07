## BLISS as a library

BLISS is primarily a Python library, thus BLISS can be embedded into any Python program.

BLISS is built on top of [gevent](http://www.gevent.org/), a coroutine-based asynchronous networking library. Under the hood, gevent works with a very fast control loop based on [libev](http://software.schmorp.de/pkg/libev.html) (or [libuv](http://docs.libuv.org/en/v1.x/)).

The loop must run in the host program. When BLISS is imported, gevent monkey-patching is applied automatically (except for the threading module). In most cases, this is transparent and does not require anything from the host Python program.

!!! note
    When using BLISS from a command line or from a graphical interface, gevent needs to be inserted into the events loop.

For example a BLISS-friendly IPython console can be started like this:

    python -c "import gevent.monkey; gevent.monkey.patch_all(thread=False); import IPython; IPython.start_ipython()"

The line above launches Python, makes sure the Python standard library is patched, without replacing system threads by gevent greenlets (which seems like a reasonable option), then starts the IPython interpreter.

From hereon it is possible to use BLISS as any Python library:

```python
In [1]: from bliss.common.axis import Axis

In [2]: from bliss.controllers.motors import icepap

In [3]: ice = icepap.Icepap("iceid2322", {"host": "iceid2322"},
                            [("mbv4mot", Axis,
                            {"address":1, "steps_per_unit":817,
                            "velocity": 0.3, "acceleration": 3
                            })], [], [], [])

In [4]: ice.initialize()

In [5]: mbv4 = ice.get_axis("mbv4mot")

In [6]: mbv4.position()
Out[6]: 0.07099143206854346

In [7]:
```

The example above creates an IcePAP motor controller instance, configured with a `mbv4mot` axis on IcePAP channel 1. Then, the
controller is initialized and the axis object is retrieved to read the motor position.

!!! note
    This example is meant to demystify BLISS -- the only recommended
    way to use BLISS is to rely on BLISS Beacon to get configuration
    and to use the BLISS shell as the preferred command line
    interface.

