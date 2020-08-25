# AutoFilter

## Introduction
### Auto filtering for step-by-step scan
Autof stands for "automatic filter", it provides a way of activating automatically some beam filtering (attenuation) during the step-by-step scans in order to keep the beam intensity in an acceptable range of count rate and to protect the detectors.

During the scan the count (acquisition point) is validated or repeated until the detector count-rate fits with the specified range for linearity purpose for instance.

### The AutoFilter controller
The AutoFilter controller requires two input counters, one as the **detector** and one as the **monitor**. Monitor and detector can be of any type, sampling, integrating, 1D roi counter, Lima roi counter and so on.

The AutoFilter controller provides its own `scan` rountines, like ascan, dscan, a2scan, d2scan, a3scan and d3scan. The actual BLISS scan framework cannot be changed to allow repeat of count. So one will need to call <myautof>.dscan() to do a scan with auto-filter activated.

The AutoFilter provides some counters, the `transmission`, the `filter-position`, the `corrected-detector` and the `corrected-counter-to-monitor` ratio counters.
In addition one can configure a list of counters to be corrected with the current transmission. The corrected counters will be named <mycounter><corr_suffix>, the `suffix_for_corr_counter` can be set in the configuration, the default suffix is **_corr**.

### The FilterSet controllers
The AutoFilter controller requires a **FilterSet** object to allow filter changes. You can have several FilterSet defined on the beamline, but only one will be active during a scan. The filterset can be change at any time by using the filterset property (`.filterset`).

The filterset is responsible of the effective filter transmission calculation. The filterset configuration should provide the filter definitions (element, thickness or density) and the `energy axis` to read the current beamline energy in keV.

Two types of FilterSet are today supported, the **FilterSet_Wheel** and the **FilterSet_Wago**. 

The Wheel filterset provides N filters and the filter change is made via a motor position. On ESRF ID10 the wheels have 20 different filters.

The Wago filterset is the former ESRF ISG filter box, a pneumatic-driven jacks fo up to to 4 filters. Filters can be all inserted into the beam trajectory, Which makes possible to get up to 16 different transmissions. 

There are some other filterset available at ESRF for instance the Maatel filterset runs on BM28 (XMAS) which will be added.

The FilterSet controller calculate the effective filter tranmsission with the given energy axis and the filter definition


## Example configuration

### AutoFilter
```yaml
- plugin: bliss
  class: AutoFilter
  name: autof_eh1
  package: bliss.common.auto_filter
  detector_counter_name: roi1
  monitor_counter_name: mon
  min_count_rate: 20000
  max_count_rate: 50000
  energy_axis: $eccmono
  filterset: $filtW1

# optionnal parameters
  always_back: True
  counters:
    - counter_name: curratt
      tag: fiteridx
    - counter_name: transm
      tag: transmission
   - counter_name: ratio
     tag: ratio
  suffix_for_corr_counter: "_corr"
  counters_for_correction:
    - det
    - apdcnt
```
### FilterSet

#### Wheel FilterSet
``` yaml
With NO density:
---------------
- name: filtW0
  package: bliss.common.auto_filter.filterset_wheel
  class: FilterSet_Wheel
  rotation_axis: $att1
  filters:
    - position: 0
      material: Cu
      thickness: 0
    - position: 1
      material: Cu
      thickness: 0.04673608
With Density:
-------------
- name: filtW0
  package: bliss.common.auto_filter.filterset_wheel
  class: FilterSet_Wheel
  rotation_axis: $att1
  filters:
    - position: 0
      material: Cu
      thickness: 0
      density: 8.94

    - position: 1
      material: Mo
      thickness: 0.055
      density: 10.22
With pairs transmission/energy:
------------------------------
- name: filtW0
  package: bliss.common.auto_filter.filterset_wheel
  class: FilterSet_Wheel
  rotation_axis: $att1
  filters:
    - position: 0
      material: Ag
      thickness: 0.1
      transmission: 0.173
      energy: 16

    - position: 1
      material: Ag
      thickness: 0.2
      transmission: 0.0412
      energy: 16
```

#### Wago FilterSet
``` yaml
With NO density:
---------------
- name: filtA
  package: bliss.common.auto_filter.filterset_wago
  class: FilterSet_Wago
  wago_controller: $wcid10f
  wago_cmd: filtA
  wago_status: fstatA
  inverted: True
  overlap_time: 0.1
  settle_time: 0.3
  filters:
    - position: 0
      material: Cu
      thickness: 0
    - position: 1
      material: Cu
      thickness: 0.04673608
    - position: 2
      material: Cu
      thickness: 0.09415565
    - position: 3
      material: Cu
      thickness: 0.14524267
With Density:
-------------
- name: filtA
  package: bliss.common.auto_filter.filterset_wago
  class: FilterSet_Wago
  wago_controller: $wcid10f
  wago_cmd: filtA
  wago_status: fstatA
  inverted: True
  overlap_time: 0.1
  settle_time: 0.3
  filters:
    - position: 0
      material: Cu
      thickness: 0
      density: 8.94
    - position: 1
      material: Mo
      thickness: 0.055
      density: 10.22
With pairs transmission/energy:
------------------------------
- name: filtA
  package: bliss.common.auto_filter.filterset_wago
  class: FilterSet_Wago
  wago_controller: $wcid10f
  wago_cmd: filtA
  wago_status: fstatA
  inverted: True
  overlap_time: 0.1
  settle_time: 0.3
  filters:
    - position: 0
      material: Ag
      thickness: 0.1
      transmission: 0.173
      energy: 16

    - position: 1
      material: Ag
      thickness: 0.2
      transmission: 0.0412
      energy: 16

```

## Usage


### Get some filter info

just run the filterset:
```python
BLISS [2]: filtW0
Filter = 5, transm = 1.1684e-32 @ 20 keV
            Out [2]: Filterset Wheel: filtW0
                      - Rotation axis: watt
                      - Idx   Pos. Mat. Thickness    Transm. @ 20 keV:
                      -------------------------------------------------
                        0     0    Cu   0.00000000   1
                        1     1    Cu   0.04673608   6.8728e-07
                        2     2    Cu   0.09415565   3.8383e-13
                        3     3    Cu   0.14524267   7.0393e-20
                        4     4    Cu   0.19116930   6.1858e-26
                        5     5    Cu   0.24215921   1.1684e-32
                        6     6    Cu   0.27220901   1.2737e-36
                        7     7    Cu   0.32278422   2.7287e-43
                        8     8    Cu   0.37046937   1.4058e-49
                        9     9    Cu   0.42335566   1.493e-56
                        10    10   Cu   0.46880012   1.5189e-62
                        11    11   Cu   0.51600567   9.0519e-69
                        12    12   Cu   0.55780431   2.7858e-74
                        13    13   Cu   0.59937871   9.1775e-80
                        14    14   Cu   0.64491601   9.0768e-86
                        15    15   Cu   0.69376533   3.284e-92
                        16    16   Cu   0.73600000   8.8535e-98
                        17    17   Cu   0.78200000   7.6087e-104
                        18    18   Cu   0.82800000   6.5389e-110
                        19    19   Cu   0.87400000   5.6195e-116                                                                                                                                                                                 Active filter is 5, transmission = 1.1684e-32 @ 20 keV 
```

### Get the autof controller info

```python
BLISS [1]: autof_eh1
Filter = 5, transm = 1.1684e-32 @ 20 keV
            Out [1]: Parameter              Value
                     ---------------------  ----------------------------------------------------
                     monitor_counter_name   simulation_diode_sampling_controller:simdiode1_autof
                     detector_counter_name  roi1_sum
                     min_count_rate         20000
                     max_count_rate         50000
                     always_back            True

                     Active filterset: filtW0
                     Energy axis energy: 20 keV

                     Active filter idx 5, transmission 1.16841e-32

                     Table of Effective Filters :
                     Idx    Transm.     Max.cntrate    Opti.cntrate    Min.cntrate
                     -----  ----------  -------------  --------------  -------------
                     0      1           5e+04          0               0
                     1      6.873e-07   7.275e+10      3.976e+04       3.976e+04
                     2      3.838e-13   1.303e+17      5.786e+10       5.786e+10
                     3      7.039e-20   7.103e+23      1.036e+17       1.036e+17
                     4      6.186e-26   8.083e+29      5.649e+23       5.649e+23
                     5      1.168e-32   4.279e+36      6.428e+29       6.428e+29
                     6      1.274e-36   3.926e+40      3.403e+36       3.403e+36
                     7      2.729e-43   1.832e+47      3.122e+40       3.122e+40
                     8      1.406e-49   3.557e+53      1.457e+47       1.457e+47
                     9      1.493e-56   3.349e+60      2.828e+53       2.828e+53
                     10     1.519e-62   3.292e+66      2.663e+60       2.663e+60
                     11     9.052e-69   5.524e+72      2.618e+66       2.618e+66
                     12     2.786e-74   1.795e+78      4.393e+72       4.393e+72
                     13     9.178e-80   5.448e+83      1.427e+78       1.427e+78
                     14     9.077e-86   5.509e+89      4.333e+83       4.333e+83
                     15     3.284e-92   1.523e+96      4.381e+89       4.381e+89
                     16     8.853e-98   5.648e+101     1.211e+96       1.211e+96
                     17     7.609e-104  6.571e+107     4.491e+101      4.491e+101
                     18     6.539e-110  7.647e+113     5.226e+107      5.226e+107
                     19     5.619e-116  8.898e+119     6.081e+113      6.081e+113
```

### Get/set the filter manually

You can either use the a filterset or pass through the autof controller.

```python
BLISS [3]: filtW0.filter
Filter = 5, transm = 1.1684e-32 @ 20 keV
            Out [3]: 5

BLISS [4]: filtW0.filter = 7
Change filter filtW0 from 5 to 7

BLISS [5]: autof_eh1.filter
Filter = 7, transm = 2.7287e-43 @ 20 keV
            Out [5]: 7

BLISS [6]: autof_eh1.filter=5
Change filter filtW0 from 7 to 5

```
### Scan with autof controller

So simple, just use the autof controller scan routines, ascan, dscan, a2scan, d2scan ...

```python
BLISS [7]: autof_eh1.dscan(simot1_autof,-1,1,20,0.1)
```

If you have the autof controller in your measurmement group you will get for free extra counters like the filter position, the transmission, the ratio and the detector corrected value:

```python
BLISS [13]: lscnt()

Fullname                                              Shape    Controller                            Name             Alias
----------------------------------------------------  -------  ------------------------------------  ---------------  -------
...
autof_eh1:curratt                                    0D       autof_eh1                            curratt
autof_eh1:ratio                                      0D       autof_eh1                            ratio
autof_eh1:roi1_sum_corr                              0D       autof_eh1                            roi1_sum_corr
autof_eh1:transm                                     0D       autof_eh1                            transm
...
```

### Change autof filterset

```python
BLISS [9]: autof_eh1.filterset
Filter = 5, transm = 1.1684e-32 @ 20 keV
            Out [9]: Filterset Wheel: filtW0
                      - Rotation axis: watt0
                      - Idx   Pos. Mat. Thickness    Transm. @ 20 keV:
                        -------------------------------------------------
                        0     0    Cu   0.00000000   1
                        1     1    Cu   0.04673608   6.8728e-07
                        2     2    Cu   0.09415565   3.8383e-13
                        3     3    Cu   0.14524267   7.0393e-20
                        4     4    Cu   0.19116930   6.1858e-26
                        5     5    Cu   0.24215921   1.1684e-32
                        6     6    Cu   0.27220901   1.2737e-36
                        7     7    Cu   0.32278422   2.7287e-43
                        8     8    Cu   0.37046937   1.4058e-49
                        9     9    Cu   0.42335566   1.493e-56
                        10    10   Cu   0.46880012   1.5189e-62
                        11    11   Cu   0.51600567   9.0519e-69
                        12    12   Cu   0.55780431   2.7858e-74
                        13    13   Cu   0.59937871   9.1775e-80
                        14    14   Cu   0.64491601   9.0768e-86
                        15    15   Cu   0.69376533   3.284e-92
                        16    16   Cu   0.73600000   8.8535e-98
                        17    17   Cu   0.78200000   7.6087e-104
                        18    18   Cu   0.82800000   6.5389e-110
                        19    19   Cu   0.87400000   5.6195e-116

                     Active filter is 5, transmission = 1.1684e-32 @ 20 keV

BLISS [10]: autof_eh1.filterset=filtW1
BLISS [11]: autof_eh1.filterset
Filter = 0, transm = 1 @ 20 keV
            Out [11]: Filterset Wheel: filtW1
                       - Rotation axis: watt1
                       - Idx   Pos. Mat. Thickness    Transm. @ 20 keV:
                         -------------------------------------------------
                         0     0    Cu   0.00000000   1
                         1     1    Cu   0.04673608   6.8728e-07
                         2     2    Cu   0.09415565   3.8383e-13
                         3     3    Cu   0.14524267   7.0393e-20
                         4     4    Cu   0.19116930   6.1858e-26
                         5     5    Cu   0.24215921   1.1684e-32
                         6     6    Cu   0.27220901   1.2737e-36
                         7     7    Cu   0.32278422   2.7287e-43
                         8     8    Cu   0.37046937   1.4058e-49
                         9     9    Cu   0.42335566   1.493e-56
                         10    10   Cu   0.46880012   1.5189e-62
                         11    11   Cu   0.51600567   9.0519e-69
                         12    12   Cu   0.55780431   2.7858e-74
                         13    13   Cu   0.59937871   9.1775e-80
                         14    14   Cu   0.64491601   9.0768e-86
                         15    15   Cu   0.69376533   3.284e-92
                         16    16   Cu   0.73600000   8.8535e-98
                         17    17   Cu   0.78200000   7.6087e-104
                         18    18   Cu   0.82800000   6.5389e-110
                         19    19   Cu   0.87400000   5.6195e-116

                      Active filter is 0, transmission = 1 @ 20 keV

```

### Change the detector configuration

You can dynamically change the auto-filter configuration to set a new detector and a new count-rate range. In addition the monitor detector can be changed too.


```python
BLISS [19]: autof_eh1.max_count_rate
            Out [19]: 50000

BLISS [20]: autof_eh1.min_count_rate
            Out [20]: 20000

BLISS [21]: autof_eh1.detector_counter
            Out [21]: 'roi1_sum` counter info:
                        counter type = integrating
                        fullname = bcu_simulator2:roi_counters:roi1_sum
                        unit = None


BLISS [22]: autof_eh1.monitor_counter
            Out [22]: 'simdiode1_autof` counter info:
                        counter type = sampling
                        sampling mode = MEAN
                        fullname = simulation_diode_sampling_controller:simdiode1_autof
                        unit = None
                        mode = MEAN (1)

BLISS [19]: autof_eh1.max_count_rate = 60000; autof_eh1.min_count_rate = 10000

BLISS [24]: autof_eh1.detector_counter = bcu_simulator2.roi_counters.counters.roi1_avg

BLISS [25]: autof_eh1.monitor_counter = simdiode2_autof

BLISS [34]: autof_eh1
Filter = 0, transm = 1 @ 20 keV
            Out [34]: Parameter              Value
                      ---------------------  ----------------------------------------------------
                      monitor_counter_name   simulation_diode_sampling_controller:simdiode2_autof
                      detector_counter_name  bcu_simulator2:roi_counters:roi1_avg
                      min_count_rate         10000
                      max_count_rate         60000
                      always_back            True

                      Active filterset: filtW1
                      Energy axis energy: 20 keV

                      Active filter idx 0, transmission 1

                      Table of Effective Filters :
                      Idx    Transm.     Max.cntrate    Opti.cntrate    Min.cntrate
                      -----  ----------  -------------  --------------  -------------
                      0      1           5e+04          0               0
                      1      6.873e-07   7.275e+10      3.976e+04       3.976e+04
                      2      3.838e-13   1.303e+17      5.786e+10       5.786e+10


```