#Continuous Scan Tutorial


This tutorial shows how to use Bliss in 3 steps:

-   configuring data acquisition
-   configuring data storage
-   starting a continuous scan

###First step: data acquisition configuration

A continuous scan in Bliss is the combination of **acquisition
objects**, being either **master** or **slaves**, and **data recorder
objects**.

Master devices are enabled with synchronization superpowers ; their
responsibility is to **start or trigger** slaves to perform data
acquisition at the right moment.

The link between masters and slaves can be either **hardware**, or
**emulated with software**.

A scan can have **multiple masters**, and masters can also be slaves for
other masters. There is no limit to imagination.

The set of masters and slaves acquisition objects is called an
**acquisition chain**, it is the first thing to configure when defining
a new Bliss scan:

```python
from bliss.scanning.chain import AcquisitionChain

chain = AcquisitionChain()
```

Then, masters and slaves objects have to be created and added to the
acquisition chain.

### Master object creation

The `SoftwarePositionTriggerMaster` class is shipped with Bliss. It
takes an **Emotion** `Axis` object, and turns it into a Bliss master,
capable of triggering slaves at evenly spaced points between a start and
an end position.

```python
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster

emotion_master = SoftwarePositionTriggerMaster(m0, 5, 10, 10, time=5)
```

In the example above the `SoftwarePositionTriggerMaster` is configured
to move `m0` from 5 to 10, with 10 points. The optional `time` keyword
argument specifies the time in seconds to go between the start and end
positions (acquisition time). Motor speed is changed accordingly.
Acceleration time is taken into account to ensure constant speed during
acquisition. An extra step is also added after end position in order to
guarantee the last point is exposed identically as the previous ones.

Considering an `m0` Emotion axis with acceleration set to 100 mm.s^-2^,
and time for moving from 5 to 10 set to 5 seconds, velocity will be set
to 1 mm.s^-1^ and the effective move will be from 4.99 to 10.56.

### Slave object creation

Bliss comes with the `LimaAcquisitionMaster` class, encapsulating a
Tango Lima device for use within an acquisition chain:

```python
params = { "acq_nb_frames": 10,
           "acq_expo_time": 0.3,
           "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI" }
lima_acq_dev = LimaAcquisitionMaster(lima_dev, **params)
```

Acquisition is configured to take 10 frames of 300 milliseconds exposure
time, each frame capture being triggered by software.

### Adding master and slave to acquisition chain

The `AcquisitionChain.add()` method is used to associate a master with
slaves or with another master, and to add a node in the chain.

```python
chain.add(emotion_master, lima_acq_dev)
```

Internally, the `AcquisitionChain.add()` method builds a tree
representing the different acquisition devices. Master acquisition
devices are represented as nodes in a tree:

    . chain(AcquisitionChain)
    └── emotion_master(SoftwarePositionTriggerMaster)
        └── lima_dev(LimaAcquisitionMaster)

Second step: data storage configuration
---------------------------------------

Once a continuous scan is started, data is produced from the masters and
slaves devices in the acquisition chain. A `Scan` object has to be
created, in order to specify how data is saved and made accessible for
other programs like Online Data Analysis.

A scan is identified by its name ; the full name is made of a prefix,
plus a run number. The default prefix is *scan*, so the first scan is
called *scan\_1*, the second scan is called *scan\_2* and so on. The
first argument to `Scan` is the scan name prefix.

In the same way the `AcquisitionChain` can be represented as a tree, the
`Scan` saves data in a tree-like structure within the **Redis** cache. A
scan node contains meta-data (`scan_info`), plus a `data` member. If
data is too big, only a reference to the data is saved. For example, in
the case of images, the file name is stored instead of the image bytes.

`Scan` objects can be placed inside a `Container`, in order to match
data acquisition with data analysis logic. A `Container` is only
identified by its name. Typically, a container will have a sample name,
an each scan on this sample can be stored inside the container.
`Container` objects can be nested without limitation.


??? no more data_manager...

```python
from bliss.common.data_manager import Container, Scan

sample = Container('my_sample`')
scan = Scan(name='scan', chain=chain, parent=sample)
```

Launching a scan is done by calling run method :

```python
scan.run()
```
