Is a tree which describe the trigger relation between master and
slaves. To define such a relation we insert into the *Acquisition
chain* sub object inherited from [Acquisition
Master](scan_engine_acquisition_master_and_devices.md#Master) or
[Acquisition
Device](scan_engine_acquisition_master_and_devices.md#Device).  With
`add` method the tree is build with the master and a slave passes as
arguments.

Sometime it's needed to control the state of device like shutter,
multiplexeur, detector cover... Those devices should be control with
[Preset](scan_engine_preset.md) objects.

*Acquisition chain*
!!! note
    An *Acquisition chain* can only be run once by a scan

## Add example
 2 points loopscan with 1 counter:

```python
DEMO [1]: from bliss.scanning import chain
DEMO [2]: from bliss.scanning.acquisition.timer import SoftwareTimerMaster
DEMO [3]: from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
DEMO [4]: acq_chain = chain.AcquisitionChain()
DEMO [5]: timer = SoftwareTimerMaster(1, npoints=2)
DEMO [6]: counter_device = SamplingCounterAcquisitionDevice(diode, count_time=1, npoints=2)
DEMO [7]: acq_chain.add(timer, counter_device)
DEMO [8]: print(acq_chain._tree)
acquisition chain
└── timer
    └── diode
```

To execute the `loopsscan`:

```python
DEMO [9]: from bliss.scanning.scan import Scan
DEMO [10]: s = Scan(acq_chain,name='simple loop',scan_info={},save=False)
DEMO [11]: s.run()
DEMO [12]: s.get_data()
 Out [12]: {'elapsed_time': array([0. , 1.0063]), 'diode': array([11.59349, -6.2747])}
```

To transform the loopscan into an `ascan`:
```python
DEMO [9]: from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
DEMO [10]: motor_master = LinearStepTriggerMaster(2,robz,0,1)
DEMO [11]: acq_chain.add(motor_master,timer)
DEMO [12]: print(acq_chain._tree)
acquisition chain
└── axis
    └── timer
        └── diode
```


## Calling sequence

When the *Scan* iterates over the *Acquisition chain*, *Acquisition Master* and
*Acquisition Device* are called in a defined sequence.

For each iteration, the *Acquisition chain* calls are:

* `wait_ready` which should return when the device is ready to have an other trigger.
* `prepare` device preparation.
* `start` starts acquisition on device


All the calling functions of master and device during a scan can be
displayed with the `trace()` method.

```python
DEMO [1]: s = loopscan(2,1,diode,diode2,run=False)
DEMO [2]: s.trace()
DEMO [3]: s.run()
DEBUG 2019-03-06 17:05:29,288 Scan: Start timer.wait_ready
DEBUG 2019-03-06 17:05:29,289 Scan: End timer.wait_ready Took 0.000449s
DEBUG 2019-03-06 17:05:29,289 Scan: Start diode.wait_ready
DEBUG 2019-03-06 17:05:29,289 Scan: Start simulation_diode_controller.wait_ready
DEBUG 2019-03-06 17:05:29,290 Scan: End diode.wait_ready Took 0.000545s
DEBUG 2019-03-06 17:05:29,290 Scan: End simulation_diode_controller.wait_ready Took 0.000495s
Total 2 points, 0:00:02 (motion: 0:00:00, count: 0:00:02)

Scan 11 Wed Mar 06 17:05:24 2019 /tmp/scans/test_session/data.h5 test_session user = seb
loopscan 2 1

           #         dt[s]         diode        diode2
DEBUG 2019-03-06 17:05:29,314 Scan: Start simulation_diode_controller.prepare
DEBUG 2019-03-06 17:05:29,314 Scan: End simulation_diode_controller.prepare Took 0.000120s
DEBUG 2019-03-06 17:05:29,314 Scan: Start diode.prepare
DEBUG 2019-03-06 17:05:29,314 Scan: End diode.prepare Took 0.000040s
DEBUG 2019-03-06 17:05:29,314 Scan: Start timer.prepare
DEBUG 2019-03-06 17:05:29,315 Scan: End timer.prepare Took 0.000033s
DEBUG 2019-03-06 17:05:29,315 Scan: Start simulation_diode_controller.start
DEBUG 2019-03-06 17:05:29,315 Scan: End simulation_diode_controller.start Took 0.000536s
DEBUG 2019-03-06 17:05:29,315 Scan: Start diode.start
DEBUG 2019-03-06 17:05:29,316 Scan: End diode.start Took 0.000395s
DEBUG 2019-03-06 17:05:29,316 Scan: Start timer.start
DEBUG 2019-03-06 17:05:29,316 Scan: Start timer.trigger_slaves
DEBUG 2019-03-06 17:05:29,316 Scan: End timer.trigger_slaves Took 0.000090s
DEBUG 2019-03-06 17:05:29,317 Scan: Start diode.trigger
DEBUG 2019-03-06 17:05:29,317 Scan: End diode.trigger Took 0.000062s
DEBUG 2019-03-06 17:05:29,317 Scan: Start simulation_diode_controller.trigger
DEBUG 2019-03-06 17:05:29,317 Scan: End simulation_diode_controller.trigger Took 0.000037s
DEBUG 2019-03-06 17:05:29,318 Scan: Start timer.wait_slaves
DEBUG 2019-03-06 17:05:29,318 Scan: End timer.wait_slaves Took 0.000249s
DEBUG 2019-03-06 17:05:30,319 Scan: End timer.start Took 1.002655s
DEBUG 2019-03-06 17:05:30,320 Scan: Start timer.wait_ready
DEBUG 2019-03-06 17:05:30,321 Scan: End timer.wait_ready Took 0.000566s
DEBUG 2019-03-06 17:05:30,322 Scan: Start diode.wait_ready
DEBUG 2019-03-06 17:05:30,322 Scan: Start simulation_diode_controller.wait_ready
DEBUG 2019-03-06 17:05:30,323 Scan: End diode.wait_ready Took 0.001143s
DEBUG 2019-03-06 17:05:30,323 Scan: End simulation_diode_controller.wait_ready Took 0.001143s
DEBUG 2019-03-06 17:05:30,324 Scan: Start timer.prepare
DEBUG 2019-03-06 17:05:30,325 Scan: End timer.prepare Took 0.000302s
DEBUG 2019-03-06 17:05:30,326 Scan: Start timer.start
DEBUG 2019-03-06 17:05:30,327 Scan: Start timer.trigger_slaves
DEBUG 2019-03-06 17:05:30,327 Scan: End timer.trigger_slaves Took 0.000420s
DEBUG 2019-03-06 17:05:30,328 Scan: Start diode.trigger
DEBUG 2019-03-06 17:05:30,329 Scan: End diode.trigger Took 0.000344s
DEBUG 2019-03-06 17:05:30,329 Scan: Start simulation_diode_controller.trigger
DEBUG 2019-03-06 17:05:30,329 Scan: End simulation_diode_controller.trigger Took 0.000291s
DEBUG 2019-03-06 17:05:30,332 Scan: Start timer.wait_slaves
DEBUG 2019-03-06 17:05:30,334 Scan: End timer.wait_slaves Took 0.001394s
           0             0       3.52747      -2.57778
DEBUG 2019-03-06 17:05:31,329 Scan: End timer.start Took 1.002674s
DEBUG 2019-03-06 17:05:31,331 Scan: Start timer.wait_ready
DEBUG 2019-03-06 17:05:31,331 Scan: End timer.wait_ready Took 0.000565s
DEBUG 2019-03-06 17:05:31,332 Scan: Start diode.wait_ready
DEBUG 2019-03-06 17:05:31,332 Scan: Start simulation_diode_controller.wait_ready
DEBUG 2019-03-06 17:05:31,339 Scan: End simulation_diode_controller.wait_ready Took 0.006308s
DEBUG 2019-03-06 17:05:31,339 Scan: End diode.wait_ready Took 0.007317s
DEBUG 2019-03-06 17:05:31,340 Scan: Start timer.wait_slaves
DEBUG 2019-03-06 17:05:31,340 Scan: End timer.wait_slaves Took 0.000504s
           1       1.01025      -1.74157       10.4382
DEBUG 2019-03-06 17:05:31,349 Scan: Start timer.stop
DEBUG 2019-03-06 17:05:31,350 Scan: End timer.stop Took 0.000574s
DEBUG 2019-03-06 17:05:31,351 Scan: Start diode.stop
DEBUG 2019-03-06 17:05:31,352 Scan: End diode.stop Took 0.000701s
DEBUG 2019-03-06 17:05:31,352 Scan: Start simulation_diode_controller.stop
DEBUG 2019-03-06 17:05:31,352 Scan: End simulation_diode_controller.stop Took 0.000295s
DEBUG 2019-03-06 17:05:31,353 Scan: Start timer.wait_slaves
DEBUG 2019-03-06 17:05:31,354 Scan: End timer.wait_slaves Took 0.000611s

Took 0:00:06.935785 (estimation was for 0:00:02)
```

## Display the chain tree
A `print()` on the `_tree` attribute of the acquisition chain
displays the acquisition tree.

So from a scan do as follow:

```python
DEMO [1]: s = ascan(robz, 0, 1, 10, 0.1, diode, diode2, diode3, run=False)
DEMO [2]: print(s.acq_chain._tree)
acquisition chain
└── axis
    └── timer
        ├── diode
        └── simulation_diode_controller
```
