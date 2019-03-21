# SoftAxis: creating axes on the fly

BLISS provides a helper which wraps any python object with a `Axis`
interface allowing it to be used in a scan.

Lets say you have a python object:

```python

class Maxipix(object):

    _energy = 12.34

    @property
    def energy_threshold(self):
        return self._energy

    @energy_threshold.setter
    def energy_threshold(self, new_energy):
        self._energy = new_energy

    @property
    def temperature(self):
        return 30 + 10*random.random()

mpx1 = Maxipix()
```

...and you would like to scan the *energy threshold* which is a property of
your object. All you have to do is wrap your object with a bliss `SoftAxis`
(for the sake of the example we also added a temperature counter so we can
count *something*):

```python

from bliss.common.standard import ascan, SoftAxis, SoftCounter

# counter from an object property
mpx1_temp = SoftCounter(mpx1, 'temperature', name='mpx1_temp')

# create an Axis out of the Maxipix energy_threshold
# * read the position means read energy_threshold property
# * move means write the energy_threshold property
mpx1_energy = SoftAxis('mpx1_energy', mpx1, position='energy_threshold',
                       move='energy_threshold')

# You can use it like a "normal" bliss axis
# (although no fancy backlash, acceleration, velocity parameter)
print(mpx1_energy.position())

# now you can scan the energy_threshold like this:
ascan(mpx1_energy, 10, 20, 100, 0.1, mpx1_temp)
```

*position* and *move* are flexible. They can be object property names, object
method names or reference to object methods. Here is an example:

```python

from bliss.common.standard import SoftAxis

class Pilatus(object):

    _energy = 12.34

    def get_energy(self):
        return self._enery

    def set_energy(self, new_energy):
        self._energy = new_energy

pilatus1 = Pilatus()

ptus_energy = SoftAxis('ptus_energy', pilatus1, position='get_energy',
                       move=pilatus1.set_energy)
```

Particularly useful might be tango attributes or commands as axes:

```python

from bliss.common.tango import DeviceProxy

magnet1 = DeviceProxy('id31/magnet/1')
mag1_axis = SoftAxis('mfield', magnet1, position='field',
                     move='SetField')

print(mag_axis.position())
```

!!! note
    Take care of the names you give to axes. If you give a name which
    is already assigned to another bliss object you risk replacing it
    in *setup_globals* with your object
