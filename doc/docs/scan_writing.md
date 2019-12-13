#Writing a custom scan

This section will describe how to write your own scan procedure. 

In Bliss, a scanning procedure is managed by the `Scan` object (`bliss.scanning.scan`).
The scan object works on an `AcquisitionChain` object which contains `AcquisitionObject` objects (`bliss.scanning.chain`).

![Screenshot](img/scan_writing/scan.png)

The acquisition chain is a tree of acquisition objects organized in a masters and slaves hierarchy.
There are two kind of objects build on top of the `AcquisitionObject` base class, the `AcquisitionMaster` and the `AcquisitionSlave` objects.
The `AcquisitionMaster` is able to trigger the acquisition slaves below itself.
The `AcquisitionSlave` is always at the end of a branch of the acquisition chain.

![Screenshot](img/scan_writing/acq_chain.png)


The acquisition chain can be conceptually split in two regions. 
On the left, the static part containing the top level masters. This part must be entirely described by the author of the scan procedure. 
On the right, the dynamic part which depends on the list of counters given to this scan procedure. The construction of this part will be partially managed by the `ChainBuilder` object. From the given list of counters, the `ChainBuilder` object will find the `CounterController` on top of each counter.
All counter controllers are able to return the special `AcquisitionObject` associated with themself.
Also, if a counter controller as a master controller on top of it, the chain builder will find it and register the links (like LimaMaster on top of LimaRoi and LimaBPM). 

![Screenshot](img/scan_writing/chain_struct.png)



```python
def scan_demo( motor, start, stop, npoints, count_time, *counters ):

    #---------------------- Initialize required objects -------------------------------

    # the MotorMaster ('left side' of the chain)
    acq_master = LinearStepTriggerMaster(npoints, motor, start, stop)

    chain = AcquisitionChain()
    
    builder = ChainBuilder(counters)

    #----- handle possible controllers introduced by the counters ('right side' of the chain) ------

    #----- here we will only handle the Lima controller and associated counters such as Images, Rois and BPMs -----
    lima_params = {
        "acq_nb_frames": npoints,
        "acq_expo_time": count_time * 0.9,
        "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI",
        "prepare_once": True,
        "start_once": False,
    }

    for node in builder.get_nodes_by_controller_type(Lima):
        # setting the parameters of the LimaMaster is enough 
        # if not specified the children slaves auto-handled)
        node.set_parameters(acq_params=lima_params) 

        # adding the LimaMaster to chain is enough 
        # the slaves (ROI, BPM) are automatically put below
        chain.add(acq_master, node)                 

    #----- finalize the scan construction ----------------------------

    builder.print_tree(not_ready_only=False)
    print(chain._tree)

    #----- finalize the scan construction ----------------------------
    scan_info = {
        "npoints": npoints,
        "count_time": count_time,
        "start": start,
        "stop": stop,
        "type": "continous_scan_demo",
    }

    sc = Scan(
        chain,
        name="scan_demo",
        scan_info=scan_info,
        save=False,
        save_images=False,
        scan_saving=None,
        data_watch_callback=StepScanDataWatch(),
    )

    #----- start the scan ----------------------------
    sc.run()
```




![Screenshot](img/scan_writing/chain_example.png)