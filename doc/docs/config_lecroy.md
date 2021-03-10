# Lecroy

## Description

This module allows to control Lecroy Oscilloscopes, it provides access to the 
device commands and allows to use it as a counter during a scan.


## Configuration

### YAML configuration file example


```YAML
    plugin: bliss
    module: oscilloscope.lecroy
    class: LecroyOsc
    name: l1
    host: uwoisgspectro
    counters:
    - counter_name: C1
      channel: 1
    - counter_name: F1
      channel: 1
    measurements:
      - measurement_name: "PNTS_PER_SCREEN"
      - measurement_name: "FIRST_VALID_PNT"
      - measurement_name: "LAST_VALID_PNT"
      - measurement_name: "FIRST_POINT"
      - measurement_name: "SPARSING_FACTOR"
      - measurement_name: "SWEEPS_PER_ACQ"
      - measurement_name: "POINTS_PER_PAIR"
      - measurement_name: "PAIR_OFFSET"
      - measurement_name: "VERTICAL_GAIN"
      - measurement_name: "VERTICAL_OFFSET"
      - measurement_name: "MAX_VALUE"
      - measurement_name: "MIN_VALUE"
      - measurement_name: "NOMINAL_BITS"
      - measurement_name: "HORIZ_INTERVAL"
      - measurement_name: "HORIZ_OFFSET"
      - measurement_name: "PIXEL_OFFSET"
      - measurement_name: "HORIZ_UNCERTAINTY"
      - measurement_name: "ACQ_DURATION"
```

### Python code example
```Python
l1 = config.get(l1)
l1.device.get_tdiv()
#Returns timebase setting

l1.device.set_waveformFormat('WORD')

l1.device.get_waveform('C1')
#Returns a tuple with (header, wave array count, waveform)

scan = amesh(robz, 0, 2, 2, roby, 0, 2, 2, 0.1,l1)
```

## References

* User Manual: http://cdn.teledynelecroy.com/files/manuals/wm-rcm-e_rev_d.pdf
* BCU wiki page: http://wikiserv.esrf.fr/bliss/index.php/Lecroy
