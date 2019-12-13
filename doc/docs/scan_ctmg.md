# Creating counters on the fly

Bliss provides a helper which wraps any python object with a bliss counter
interface allowing it to be used as counter in a scan.

Lets say you have a python object:

```python

class Potentiostat:

    def __init__(self, name):
        self.name = name

    @property
    def potential(self):
        return float(self.comm.write_readline('POT?\n'))

    def get_voltage(self):
        return float(self.comm.write_readline('VOL?\n'))

pot = Potentiostat('p1')
```

...and you would like to have its `potential` and `voltage` values in a scan.
The `potential` is implemented as a property and `get_voltage` is a method.
Both techniques can be transformed into counters. All you have to do is wrap
your object with a bliss `SoftCounter`:

```python

from bliss.common.standard import loopscan
from bliss.common.counter import SoftCounter

# counter from an object property
pot_counter = SoftCounter(pot, 'potential')

# counter form an object method. The optional apply parameter
# allows you to apply a transformation function to the value
milivol_counter = SoftCounter(pot, 'get_voltage', name='voltage',
                              apply=lambda v: v*1000)

# now you can use the counters in any scan:

loopscan(10, 0.1, pot_counter, milivol_counter)
```

Functions can also be made counters. Here is how:

```python
from bliss.common.counter import SoftCounter
import random

random_counter = SoftCounter(value=random.random, name='aleat')

```

Particularly useful might be tango attributes or commands as counters:

```python
from bliss.common.counter import SoftCounter
from bliss.common.tango import DeviceProxy

fe = DeviceProxy('orion:10000/fe/id/00')
sr_curr_counter = SoftCounter(fe, value='sr_current')
```

!!! note
    On the fly counters are not necessarily associated with bliss objects. As
    so, they don't have a reserved name in the bliss namespace and therefore
    they cannot be added to a measurement group.
