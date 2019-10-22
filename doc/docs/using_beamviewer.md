# Standard Beamviewer (EBV: ESRF Beam Viewer)

Configuration and composition of an EBV is described
here: [ESRF BeamViewer Configuration](config_beamviewer.md).

## Usage

### Global status
```  
BLISS [16]: ebv
  Out [16]: EBV [myebv] (wago: wcid15ab)
                screen : OUT
                led    : OFF
                foil   : NONE
                diode range   : 10uA
                diode current : 0 mA
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

If EBV has no foils, you'll get:
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

You can also access the floating value of gain to convert used to convert reading to **mA**:
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

## Diode as a counter

The diode reading can be used as a sampling counter.
```
BLISS [51]: ct(.1, myebv)
Tue Oct 22 18:17:36 2019

diode = -2.44140625e-07 (-2.44140625e-06/s)
```

Default counter is *diode* but can be changed in configuration.
Counter object is accessible though `myebv.diode`.
So either `myebv` or `myebv.diode` can be added to measurement group (ebv hold only one sampling counter).


