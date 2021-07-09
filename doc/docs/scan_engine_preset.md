
# Preset

*Presets* are used to customize a scan by performing extra actions
(eg. open/close a shutter) at special events like `prepare()`, `start()` and
`stop()`.

BLISS standard presets are: `ScanPreset`, `ChainPreset` and
`ChainIterationPreset`.

Typically they allow to control:

* opening/closing of a shutter
* detector cover removing/replacing
* [multiplexer](config_opiom.md#multiplexer)
* pause during a scan
* equipment protection (via data channels hook, see below)
* ...

!!! Note
    In the general case, DO NOT use a `Preset` to modify the acquisition
    parameters (eg. acquisition time) of a device.

    To modify the default acquisition parameters used by a device in
    standard scans, use `DEFAULT_CHAIN.set_settings`, see [Default
    chain](scan_default.md#default-chain).


## Quick overview

A preset is a *hook* introduced in the [acquisition
chain](scan_writing.md#the-acquisition-chain) of a scan thanks to the
`add_preset()` method.

A preset has three methods (`prepare()`, `start()`, `stop()`) that user can
customize.

Bliss provides three kind of presets that act at different levels of the scan
chain: `ScanPreset`, `ChainPreset` and `ChainIterationPreset`.

**ScanPreset:** (hook a whole scan)

   * `.prepare`: called at scan prepare
   * `.start`  : called at scan start
   * `.stop`   : called at scan stop

```python
DEMO [1]: s = loopscan(2, 0.1, diode, run=False)
DEMO [2]: p = MyScanPreset() # a ScanPreset object
DEMO [3]: s.add_preset(p)    # using the scan object method
DEMO [4]: s.run()
```

**ChainPreset:** (hook a top-master)

   * `.prepare`: called at TopMaster.prepare
   * `.start`  : called at TopMaster.start
   * `.stop`   : called at TopMaster.stop

   Similar to `ScanPreset` if the chain has only one top-master (i.e. single
   branch acq_chain)

```python
DEMO [1]: s = loopscan(2, 0.1, diode, run=False)
DEMO [2]: p = MyChainPreset()       # a ChainPreset object
DEMO [3]: s.acq_chain.add_preset(p) # using the chain object method
DEMO [4]: s.run()
```

**ChainIterationPreset:** (hook each iteration of a top-master)

   * `.prepare`: called at prepare of step i (iteration i of a top-master)
   * `.start`  : called at start   of step i (iteration i of a top-master)
   * `.stop`   : called at stop    of step i (iteration i of a top-master)

```python
DEMO [1]: s = loopscan(2, 0.1, diode, run=False)
DEMO [2]: p = MyIteratingChainPreset() # a ChainPreset object with
                                       # a get_iterator method
DEMO [3]: s.acq_chain.add_preset(p)    # using the chain object method
DEMO [4]: s.run()
```

!!! note
    Most of the time the acquisition chain has only one top-master (only
    one acquisition chain branch) and in that case using a `ScanPreset` or a
    `ChainPreset` will produce the same result.

## Add presets to the default chain

It is possible to add a preset to all standard scans of Bliss (i.e: `ct`,
`loopscan`, `ascan`, etc.).

```python
DEMO [1]: p = MyChainPreset()
DEMO [2]: DEFAULT_CHAIN.add_preset(p) # method of the default chain object
...
DEMO [9]: DEFAULT_CHAIN.remove_preset(p)
```


## Multiple top-masters case

Keep in mind that the [acquisition chain](scan_writing.md#the-acquisition-chain)
can have multiple **branches** (one per top-master).

The `ChainPreset` and `ChainIterationPreset` are associated to one top-master
(i.e: one acquisition chain branch).

That is why the `add_preset()` method of the acquisition chain takes an optional
argument `master`.

```python
def add_preset(self, preset, master=None):
    """
    Add a preset on a top-master.

    Args:
        preset: a ChainPreset object
        master: if None, take the first top-master of the chain
    """
```


## ScanPreset
This is the simplest one. It has 3 callback methods:

* `prepare()`: called before all devices preparation
* `start()`: called before all devices starting
* `stop()`: called after all devices are stopped


Example of custom scan preset:
```python
from bliss.scanning.scan import ScanPreset
class Preset(ScanPreset):
    def prepare(self,scan):
        print(f"Preparing scan {scan.name}\n")
    def start(self,scan):
        print(f"Starting scan {scan.name}")
        print(f"Opening the shutter")
    def stop(self,scan):
        print(f"{scan.name} scan is stopped")
        print(f"Closing the shutter")
```

and it's usage:
```python
DEMO [3]: p = Preset()
DEMO [4]: s = loopscan(2, 0.1, diode, run=False)
DEMO [5]: s.add_preset(p)
DEMO [6]: s.run()

Scan 12 Wed Mar 13 11:06:11 2019 /tmp/scans/demo/data.h5 demo user = seb
loopscan 2 0.1

           #         dt[s]         diode
Preparing scan loopscan

Starting scan loopscan
Opening the shutter
           0             0      -40.2222
           1      0.104891      -9.11111
Took 0:00:09.830967
loopscan scan is stopped
Closing the shutter
```

### Data channels hook

The `ScanPreset` has a `connect_data_channels()` method to execute a callback
when data is emitted from channels.

It is useful to protect some equipments. For example, if the value
measured by a diode exceeds some threshold, the scan can be stopped or some
attenuators can be activated.

The basic usage is to call the `.connect_data_channels()` method from the
`.prepare()` of a `ScanPreset`.

The callback will receive the arguments: `counter`, `channel_name` and `data`.

```python
class ScanPreset:
    ...
    def connect_data_channels(self, counters_list, callback):
        """
        Associate a callback to the data emission by the channels
        of a list of counters.

        Args:
        * counters_list: the list of counters to connect data channels to
        * callback: a callback function
        """
        ...

```

Example:

```python
class MyScanPreset(ScanPreset):
   def __init__(self, diode):
       super().__init__()

       self.diode = diode

   def prepare(self, scan):
       self.connect_data_channels([self.diode, ...], self.protect_my_detector)

   def protect_my_detector(self, counter, channel_name, data):
       if counter == diode:
           # assuming the counter has only 1 channel, no need to
           # check for channel name
           if data > threshold:
               # protect the detector...

```

If an exception is raised in the callback function, the scan will stop.


## ChainPreset

ChainPreset hook is linked to a *top-master* of the acquisition chain. So the
callback method will be called during `prepare`, `start` and `stop` phases of
this top-master. It has exactly the same behaviour than the `ScanPreset` if the
chain has **only one** top-master.

Example: In a loopscan, the only top master is a timer. So here it is the same
example as shown above with the ScanPreset, where a shutter is opened at the
beginning of the scan and closed at the end.

The only difference is that the `add_preset()` method is called on the
acquisition chain object instead of the scan object (`s.acq_chain.add_preset`
instead of `s.add_preset`).

In the multiple top-masters case, the `acq_chain.add_preset` method takes an
optional `master` argument to specify the top-master that should be associated
to this preset (see [Multiple top-masters
case](scan_engine_preset.md#multiple-top-masters-case))


```python
from bliss.scanning.chain import ChainPreset
class Preset(ChainPreset):
    def prepare(self,acq_chain):
        print("Preparing")
    def start(self,acq_chain):
        print("Starting, Opening the shutter")
    def stop(self,acq_chain):
        print("Stopped, closing the shutter")
```
```python
DEMO [1]: s = loopscan(2, 0.1, diode, run=False)
DEMO [1]: p = Preset()
DEMO [1]: s.acq_chain.add_preset(p)
DEMO [1]: s.run()

Scan 13 Wed Mar 13 11:54:08 2019 /tmp/scans/demo/data.h5 demo user = seb
loopscan 2 0.1

           #         dt[s]         diode
Preparing
Starting, Opening the shutter
           0             0       24.1111
           1      0.105099       1.22222
Stopped, closing the shutter

Took 0:00:36.189189
```

## ChainIterationPreset

Use ChainIterationPreset to set a hook on each *iteration* of a
top-master. `ChainIterationPreset` is **yield** from `ChainPreset` instance by
the `get_iterator` method.

Example: to open and close the shutter at each iteration of the scan.

```python
class Preset(ChainPreset):

    class Iterator(ChainIterationPreset):
        def __init__(self, iteration_nb):
            self.iteration = iteration_nb
        def prepare(self):
            print(f"Preparing iteration {self.iteration}")
        def start(self):
            print(f"Starting, Opening the shutter iter {self.iteration}")
        def stop(self):
            print(f"Stopped, closing the shutter, iter {self.iteration}")

    def get_iterator(self, acq_chain):
        iteration_nb = 0
        while True:
            yield Preset.Iterator(iteration_nb)
            iteration_nb += 1
```


```python
DEMO [2]: p = Preset()
DEMO [3]: s = loopscan(2,0.1,diode,run=False)
DEMO [4]: s.acq_chain.add_preset(p)
DEMO [5]: s.run()

Scan 18 Wed Mar 13 14:15:40 2019 /tmp/scans/demo/data.h5 demo user = seb
loopscan 2 0.1

           #         dt[s]         diode
Preparing iteration 0
Starting, Opening the shutter iter 0
Stopped, closing the shutter, iter 0
Preparing iteration 1
Starting, Opening the shutter iter 1
           0             0       22.4444
           1       0.10728       13.5556
Stopped, closing the shutter, iter 1

Took 0:00:16.677241
```

!!! warning
    In this example, *data display* and the *chain iteration* are
    executed by two separated greenlets which are not synchronised. This is not
    a problem but can be confusing for the user.


In the multiple top-masters case, the `acq_chain.add_preset` method takes an
optional `master` argument to specify the top-master that should be associated
to this preset (see [Multiple top-masters
case](scan_engine_preset.md#multiple-top-masters-case))

## To pause a scan

As `Preset` callbacks are executed synchronously, they can easily pause a scan,
just by not returning imediatly from `prepare()`, `start()` or `stop()` callback
methods.

For example, to pause a scan in case of beam loss, the condition has to be
checked in a loop.

Example to delay starting a scan until the beam is present.
```python
class Preset(ScanPreset):
    def __init__(self, diode, beam_trigger_value):
        self._diode = diode
        self._beam_trigger_value

    def prepare(self, scan):
        beam_value = self._diode.read()
        while beam_value < self._beam_trigger_value:
            print("Waiting for beam")
            print(f"read {beam_value} expect {self._beam_trigger_value}",end='\r')
            gevent.sleep(1)
            beam_value = self._diode.read()
```
