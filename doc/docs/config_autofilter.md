# AutoFilter

## Introduction
### Auto filtering for step-by-step scan
Autof stands for "automatic filter", it provides a way of activating automatically some beam filtering (attenuation) during the step-by-step scans in order to keep the beam intensity in a acceptable range of count rate and to protect the detectors.

During the scan the count (acquisition point) is validated or repeated until the detector count-rate fits with the thresholds (min., max.) of the autofilter controller.

### The AutoFilter controller
The AutoFilter controller requires two input counters, one as the **detector** and one as the **monitor**. Monitor and detector can by of any type, sampling, integrating, 1D roi counter, Lima roi counter and so on.

The AutoFilter controller provides its own `scan` rountines, like ascan, dscan, a2scan, d2scan, a3scan and d3scan. The actual BLISS scan framework cannot be changed to allow repeat of count. So one will need to call <myautof>.dscan() to do a scan with auto-filter activated.

The AutoFilter provides some counters, the `transmission`, the `filter-position`, the `corrected-detector` and the `corrected-counter-to-monitor` ratio counters.
In addition one can configure a list of counters to be corrected with the current transmission. The corrected counters will be named <mycounter><corr_suffix>, the `suffix_for_corr_counter` can be set in the configuration, the default suffix is **_corr**.

### The FilterSet controllers
The AutoFilter controller do not drive any hardware to set the filter but you should configure in its YML file a **FilterSet** object. You can have several FilterSet defined on the beamline, but only will active during a scan. The filterset can be change from the a autofilter setting parameter (`.filterset`).

The filterset is responsible of calculating the effective filter transmissions. The configuration should have the filter definitions (element, thickness or density) and the `energy axis` to read the current beamline energy in keV.

Two types of FilterSet are today supported, the **FilterSet_Wheel** and the **FilterSet_Wago**. 

The Wheel filterset provides N filters and the filter change is made via a motor position. On ESRF ID10 the wheels have 20 different filters.

The Wago filterset is the former ESRF ISG filter box, a pneumatic-driven jacks fo up to to 4 filters. Filters can be all inserted into the beam trajectory, Which makes possible to get up to 16 different transmissions. 

There are some other filterset available at ESRF for instance the Maatel filterset runs on BM28 (XMAS) which can be added easilly to the supported types.

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


