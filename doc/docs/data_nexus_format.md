Currently Bliss supports only one data format: [Nexus compliant](https://www.nexusformat.org/) HDF5 files written by the [Nexus writer](data_nexus_server.md). Here we describe the logic of this Nexus structure.

In the example below we show the file of [one dataset](data_policy.md) which contains the data of three scans:

  1. `ascan(samy, 0, 9, 9, 0.1, diode1, basler1, xmap1)` where diode1 is a diode, basler1 is a camera with one ROI defined and xmap1 an MCA controller with one channel
  2. unspecified scan
  3. a scan with two independent subscans (for example one subscan can be a temperature monitor scan)

```
sample_dataset.h5
 ├ 1.1    # first scan
 |  ├ instrument
 |  |  ├ samy(@NXpositioner)
 |  |  |  └ value (10)   # motor positions during scan
 |  |  ├ diode1(@NXdetector)
 |  |  |  └ data  (10)
 |  |  ├ basler1(@NXdetector)
 |  |  |  ├ data  (10, 2048, 2048)
 |  |  |  ├ acq_parameters   # camera metadata
 |  |  |  |  └ ...
 |  |  |  └ ctrl_parameters  # camera metadata
 |  |  |     └ ...
 |  |  ├ basler1_roi1(@NXdetector)
 |  |  |  ├ data (10)
 |  |  |  ├ avg  (10)
 |  |  |  ├ std  (10)
 |  |  |  ├ min  (10)
 |  |  |  ├ max  (10)
 |  |  |  └ selection   # ROI metadata
 |  |  |     └ ...
 |  |  ├ xmap1_det0(@NXdetector)
 |  |  |  ├ data          (10, 2048)
 |  |  |  ├ elapsed_time  (10)
 |  |  |  ├ live_time     (10)
 |  |  |  ├ dead_time     (10)
 |  |  |  ├ input_counts  (10)
 |  |  |  ├ input_rate    (10)
 |  |  |  ├ output_counts (10)
 |  |  |  └ output_rate   (10)
 |  |  ├ positioners
 |  |  |  ├ samx (1)   # motor position at start
 |  |  |  ├ samy (10)  # motor positions during scan
 |  |  |  └ samz (1)   # motor position at start
 |  |  ├ start_positioners
 |  |  |  ├ samx (1)  # motor position at start
 |  |  |  ├ samy (1)  # motor positions at start
 |  |  |  └ samz (1)  # motor position at start
 |  └ measurement
 |     ├ samy (10)
 |     ├ diode1 (10)
 |     ├ basler1 (10, 2048, 2048)
 |     ├ basler1_roi1 (10)
 |     ├ basler1_roi1_avg (10)
 |     ├ basler1_roi1_std (10)
 |     ├ basler1_roi1_min (10)
 |     ├ basler1_roi1_max (10)
 |     ├ xmap1_det0 (10, 2048)
 |     ├ xmap1_det0_elapsed_time (10)
 |     ├ xmap1_det0_live_time (10)
 |     ├ xmap1_det0_dead_time (10)
 |     ├ xmap1_det0_input_counts (10)
 |     ├ xmap1_det0_input_rate (10)
 |     ├ xmap1_det0_output_counts (10)
 |     └ xmap1_det0_output_rate (10)
 ├ 2.1   # second scan
 ├ 3.1   # third scan
 └ 3.2   # also third scan
```

So each scan contains two groups (plots and application definitions are not shown)

  * *instrument*: 
    * all motors moving during the scan (*NXpositioner*: distance, time, energy, ...)
    * all detectors enabled for the scan (*NXdetector*)
    * *start_positioners*: snapshot of all motors before the scan
    * *positioners*: like start_positioners
  * *measurement*: flat list of all NXpositioner and NXdetector data

Note that each *NXdetector* contains one primary value called *data* and each *NXpositioner* contains one primary value called *value*. Additional datasets and groups represent secondary detector/positioner data or metadata such as detector settings.