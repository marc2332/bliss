# Standard beamviewer (EBV: ESRF Beam Viewer)

![Screenshot](img/ebv.svg)


**EBV** is an instrument to visualise the various types of x-ray beam (white,
pink and monochromatic) into the visible spectrum, using a scintillator, a
camera and associated software to measure the beam shape and relative power
intensities. The maximum accommodated beam size (or potential beam movement) is
10mm x 10mm for the standard beamviewers.

**EBV** is an assembly of various modules:

* a Control Box (ISG made)
* a fixed giga-ethernet basler camera+lens
    * powered by the Control box
* an extractable head that can be moved in or out of the beam (called *screen*)
    * pneumatic-mounted mirror+scintillator
    * scintillator
        * diamond for white beam
        * YAG for monochromatic beam
        * Energy dependent for pink beam
* a diode read by novelec module providing an output in frequency.
* a LED that can be swiched ON and OFF.
* optionnaly: a foil to attenuate beam (on MX beamlines)

## References

BCU wiki: http://wikiserv.esrf.fr/bliss/index.php/Bvb


## Control

The **EBV** BLISS object controls the wago box (screen, led, foil, diode), the
basler camera and the associated BPM counters computed on images.

## Wagobox modules

Two type of wago box exist:

* 1-EBV wagobox able to control only one EBV :
    - *750-436* : 8-channel digital input; 24VDC
    - *750-530* : 8-channel digital output; 24 VDC; 0.5 A
    - *750-479* : 2-channel analog input module (ADC)

* 2-EBV wagobox able to control up to 2 EBV:
    - *750-436* : 8-channel digital input; 24VDC
    - *750-530* : 8-channel digital output; 24 VDC; 0.5 A
    - *750-530* : 8-channel digital output; 24 VDC; 0.5 A
    - *750-479* : 2-channel analog input module (ADC)

If the EBV has a foil to attenuate beam (MX case), two additionnal wago modules
are added:

- *750-436* : 8-channel digital input; 24VDC
- *750-504* : 4 Channel Digital Output


## Configuration

#### Configuration example
```
plugin: bliss                 (mandatory)
name: myebv                   (mandatory)
class: EBV                    (mandatory)
modbustcp:                    (mandatory)
    url: wcidxxa              (mandatory)

single_model: False
has_foil: False
channel: 0
counter_name: mydiode

camera_tango_url: idxx/limaccds/bv1

```

* `modbustcp / url` defines the wago control box host as in standard wago
  controller.

* `camera_tango_url` defines the `limaccds` Tango device server of associated
  Basler camera.

#### Configuration optionnal parameters

* `single_model`
    - default value : `False`
    - define which model of wago is used : if `single_model` is `True`, the wago
      box is a 1-EBV model otherwise it is 2-EBV model. Note that some 2-EVB
      models can be installed even if it controls only one BVB.

* `has_foil`
    - default value : `False`
    - define if a foil attenuator can be controlled or not

* `channel`
    - default value : `0`
    - in case of a 2-EBV wago box model, defines which EBV is used : 1st one or
      2nd one.

* `counter_name`
    - default value : `diode`
    - counter name of diode current reading when EBV is used in counts/scans

* `camera_tango_url`
    - default value : `None`
    - if provided, the EBV will be extended with the BPM powers (Bpm measurements
      and BeamViewer Live display)




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

If EBV has no foil, `foil_status` returns `None`:
```
BLISS [26]: myebv.foil_status
  Out [26]: 'NONE'
```

Trying to use it will raise error:
```
BLISS [27]: myebv.foil_in()
!!! === RuntimeError: No foil on EBV [myebv] === !!!
BLISS [28]: myebv.foil_out()
!!! === RuntimeError: No foil on EBV [myebv] === !!!
```

EBV with foil:
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

Raw reading of the underlying wago without gain correction is accessible by
`myebv.raw_current`. The value returned is in the 0-10V range.

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

Floating value of gain used to convert reading to **mA** can also be accessed
via:
```
BLISS [44]: myebv.diode_range
  Out [44]: '100uA'

BLISS [45]: myebv.diode_gain
  Out [45]: 10.0

BLISS [46]: myebv.diode_range = "10nA"
BLISS [47]: myebv.diode_gain
  Out [47]: 100000.0
```

Setting the floating gain is possible. Range will be chosen to include the
maximum desired gain given:
```
BLISS [48]: myebv.diode_gain = 500
BLISS [49]: myebv.diode_range
  Out [49]: '1uA'

BLISS [50]: myebv.diode_gain
  Out [50]: 1000.0
```




## EBV and BPM counters

The BPM counter controller is accessible via the EBV object in Bliss.

```python
BLISS [51]: myebv.bpm
  Out [51]: Bpm [id00/limaccds/simulator2]

                exposure : 1.0 s
                size     : [1024, 1024]
                binning  : [1, 1]
                roi      : [0, 0, 1024, 1024]
                flip     : [False, False]
                rotation : NONE
```

The EBV owns all BPM counters and the diode counter.
```python
BLISS [51]: ct(1, myebv)
Tue Mar 31 16:43:52 2020

 acq_time = 1.038032054901123 ( 1.038032054901123/s)
   fwhm_x = 99.04761904761904 ( 99.04761904761904/s)
   fwhm_y = 99.04761904761904 ( 99.04761904761904/s)
intensity =         99.2 (        99.2/s)
        x =        512.0 (       512.0/s)
        y =        512.0 (       512.0/s)
ebv_diode = -0.15674306466872268 (-0.15674306466872268/s)
```



### Bpm measurements reading

Measure and return data (timestamp, intensity, center_x, center_y, fwhm_x, fwhm_y)
```python
BLISS [53]: myebv.bpm.raw_read()
  Out [53]: [array([1.0819428]), array([99.2]), array([512.]),
             array([512.]), array([99.04761905]), array([99.04761905])]
```


## Visualization

The command `myebv.show_beam` will start/raise Flint and display a live preview
from the EBV camera.

To stop the live, just close the tab in Flint.

If a scan is started, the live is automatically stopped first.

A single snapshot can be performed with the command `myebv.bpm.snap()`

Some parameters of the underlying camera can be read or write:

```python
myebv.bpm.exposure = 0.01           # (sec)
myebv.bpm.bin = [2,2]               # (xbin, ybin)
myebv.bpm.roi = [100,200,300,300]   # (xpos, ypos, width, height)
myebv.bpm.flip = [True, False]      # (LR, TB)
myebv.bpm.rotation = 'None'         # in ['None', '90', '180', '270']
```

## BPM Controller (camera only + BPM measurements)

Single cameras which are not part of an EBV set (i.e without the Wago part for
the control of the LED/Foil/Screen) can be used to perform BPM measurements.

A standalone `BpmController` object can be associated to the camera and created
from the configuration files like this:

```
name: mybpm
plugin: bliss
module: ebv
class: BpmController
camera_tango_url: idxx/limaccds/camname
```



## EBV counters

The EBV has 6 sampling counters (1 for the diode and 5 for the Bpm
measurements):

- myebv.diode
- myebv.x
- myebv.y
- myebv.fwhm_x
- myebv.fwhm_y
- myebv.intensity


`myebv` holds all 6 counters wheras `myebv.diode` returns only the diode
counter.

The Bpm measurements will be performed using the current CCD exposure and image
parameters (bin, roi, flip, rotation).

The camera trigger mode is forced to `INTERNAL_TRIGGER` and camera mode to
`SINGLE`.

If the scan count_time is longer than the ccd exposure the Bpm measurements are
sampled as many times as possible.

!!!note
    the default counter name for the diode is *diode* but it can be changed in
    the configuration file.

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

