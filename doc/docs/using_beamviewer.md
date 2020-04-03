# Standard Beamviewer (EBV: ESRF Beam Viewer)

Configuration and composition of an EBV is described
here: [ESRF BeamViewer Configuration](config_beamviewer.md).

## Usage

### Global status
```  
BLISS [16]: myebv
  Out [16]: EBV [myebv] Wago(wcid21bv1)
                screen : IN
                led    : ON
                foil   : NONE
                diode range   : 1mA
                diode current : -0.351451 mA

            Bpm [id21/limaccds/bv1]

                exposure : 1.0 s
                size     : [1024, 1024]
                binning  : [1, 1]
                roi      : [0, 0, 1024, 1024]
                flip     : [False, False]
                rotation : NONE
```

### SCREEN control
```
BLISS [12]: myebv.screen_in()
BLISS [13]: myebv.screen_status
  Out [13]: 'IN'

BLISS [14]: myebv.screen_out()
BLISS [15]: myebv.screen_status
  Out [15]: 'OUT'
```

### LED control
```
BLISS [22]: myebv.led_on()
BLISS [23]: myebv.led_status
  Out [23]: 'ON'

BLISS [24]: myebv.led_off()
BLISS [25]: myebv.led_status
  Out [25]: 'OFF'
```

### FOIL control

If EBV has no foil, you'll get:
```
BLISS [26]: myebv.foil_status
  Out [26]: 'NONE'
```
Trying to use it will raise error:
```
BLISS [27]: myebv.foil_in()
!!! === RuntimeError: No foil on EBV [myebv] === !!! ( for more details type cmd 'last_error' )
BLISS [28]: myebv.foil_out()
!!! === RuntimeError: No foil on EBV [myebv] === !!! ( for more details type cmd 'last_error' )
```

If your EBV has a foil:
```
BLISS [12]: myebv.foil_in()
BLISS [13]: myebv.foil_status
  Out [13]: 'IN'

BLISS [14]: myebv.foil_out()
BLISS [15]: myebv.foil_status
  Out [15]: 'OUT'
```

### DIODE current reading

The current diode value is returned always in **mA**
```
BLISS [39]: myebv.current
  Out [39]: 1.52587890625e-06
```
Raw reading of the underlying wago without gain correction is accessible by `myebv.raw_current`. The value returned is in the 0-10V range.

### DIODE range control

Changing diode range using string format:
```
BLISS [41]: myebv.diode_range_available
  Out [41]: ['1mA', '100uA', '10uA', '1uA', '100nA', '10nA']

BLISS [42]: myebv.diode_range
  Out [42]: '10uA'

BLISS [43]: myebv.diode_range = "100uA"
BLISS [44]: myebv.diode_range
  Out [44]: '100uA'
```

You can also access the floating value of gain used to convert reading to **mA**:
```
BLISS [44]: myebv.diode_range
  Out [44]: '100uA'

BLISS [45]: myebv.diode_gain
  Out [45]: 10.0

BLISS [46]: myebv.diode_range = "10nA"
BLISS [47]: myebv.diode_gain
  Out [47]: 100000.0
```

Setting the floating gain is possible. Range will be chosen to include the maximum desired gain given:
```
BLISS [48]: myebv.diode_gain = 500
BLISS [49]: myebv.diode_range
  Out [49]: '1uA'

BLISS [50]: myebv.diode_gain
  Out [50]: 1000.0
```

### Bpm measurements reading

Measure and return data (timestamp, intensity, center_x, center_y, fwhm_x, fwhm_y)
```python
BLISS [53]: myebv.bpm.raw_read()
  Out [53]: [array([1.0819428]), array([99.2]), array([512.]), array([512.]), array([99.04761905]), array([99.04761905])]
```


## EBV counters

The EBV has 6 sampling counters (1 for the diode and 5 for the Bpm measurements):

- myebv.diode
- myebv.x
- myebv.y
- myebv.fwhm_x
- myebv.fwhm_y
- myebv.intensity


`myebv` holds all 6 counters wheras `myebv.diode` returns only the diode counter.

The Bpm measurements will be performed using the current CCD exposure and image parameters (bin, roi, flip, rotation).
The camera trigger mode is forced to `INTERNAL_TRIGGER` and camera mode to `SINGLE`.

If the scan count_time is longer than the ccd exposure the Bpm measurements are sampled as many time as possible.

Note: the default counter name for the diode is *diode* but it can be changed in the configuration file.

```
BLISS [51]: ct(1, myebv)                                                                                          
Tue Mar 31 16:43:52 2020

 acq_time = 1.038032054901123 ( 1.038032054901123/s)
   fwhm_x = 99.04761904761904 ( 99.04761904761904/s)
   fwhm_y = 99.04761904761904 ( 99.04761904761904/s)
intensity =         99.2 (        99.2/s)
        x =        512.0 (       512.0/s)
        y =        512.0 (       512.0/s)
ebv_diode = -0.15674306466872268 (-0.15674306466872268/s)



BLISS [52]: ct(1, myebv.diode)
Tue Mar 31 16:54:15 2020 

ebv_diode = -0.1567430646687215 (-0.1567430646687215/s)  
```

## EBV Beamviewer

The command `myebv.show_beam` will start/raise Flint and display a live preview from the EBV camera.

To stop the live, just close the tab in Flint.

If a scan is started, the live is automatically stopped first.

A single snapshot can be performed with the command `myebv.bpm.snap()` 

Some parameters of the underlying camera can be read or write:

* `myebv.bpm.exposure`  or `myebv.bpm.exposure = 0.01`          (sec)
* `myebv.bpm.bin`       or `myebv.bpm.bin = [2,2]`              (xbin, ybin)
* `myebv.bpm.roi`       or `myebv.bpm.roi = [100,200,300,300]`  (xpos, ypos, width, height)
* `myebv.bpm.flip`      or `myebv.bpm.flip = [True, False]`     (LR, TB)
* `myebv.bpm.rotation`  or `myebv.bpm.rotation = 'NONE'`        in ['None', '90', '180', '270']


