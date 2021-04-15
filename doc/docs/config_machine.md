

BLISS offers some mechanisms to deal with information obtained from the ESRF
accelerator.

`MachInfo` class provides:

* properties to get some machine available information
* counters to access to accelerator information
* helper functions to implement refill pretection in a sequence


## Configuration

Configuration example:

```yaml
- class: MachInfo
  plugin: bliss
  uri: //acs.esrf.fr:10000/fe/master/id42
  name: mama
```


## machinfo properties

* `sr_mode`: operation mode in: [`USM`; `MDT`; `Shutdown`; `SafetyTest`; `IdTest`]
* `automatic_mode`: activation of automatic FE mode: `True` or `False`
* `tango_uri`: address of the Front-End Tango device server
* `counters`:
    - `current`: Ring current of the machine
    - `lifetime`: Remaining Lifetime of the beam
    - `sbcurr`: Ring current of the machine in Single Bunch mode
    - `refill`: Countdown to the Refill


Counters usage in a scan:
```pyton
DEMO [8]: ct(0.1, mama)
Sun Mar 08 13:54:39 2020

 current = 8.830000000000009 ( 88.30000000000008/s)
lifetime =     222633.0 (   2226330.0/s)
  refill =       7523.0 (     75230.0/s)
  sbcurr =          0.0
  Out [8]: Scan(number=2, name=ct, path=)
```

Reading of a particular counter:
```python
DEMO [9]: mama.counters.current
 Out [9]: 'current` Tango attribute counter info:
            device server = //acs.esrf.fr:10000/fe/master/id42
            Tango attribute = SR_Current
            Tango format = "%6.2f"
            Tango unit = "mA"
            scalar
            value: 8.82

DEMO [10]: mama.counters.current.value
 Out [10]: 194.43
```


### `__info__`

`MachInfo` object shell info provides:

* url of the tango device used
* AutoMode timing
* Operator Message

```pyton
DEMO  [5]: mama
  Out [5]: MACHINE INFORMATION   ( //acs.esrf.fr:10000/fe/master/id42 )

           -----------------  ---------------------------------------------
           SR Mode:           USM
           Current:           8.79 mA
           Lifetime:          245231s = 2days 20h 7mn 11s
           Refill CountDown:  6519s = 1h 48mn 39s
           Filling Mode:      7/8 multibunch
           AutoMode:          True (remaining: 498183s = 5days 18h 23mn 3s)
           -----------------  ---------------------------------------------
           Operator Message: Jun  3 12:00 Back to USM
```



### all_information

`all_information` property returns most of all the machine information as a
dictionary:

```python
DEMO [9]: pprint.pprint(mama.all_information)
{'Auto_Mode_Time': 502822,
 'Automatic_Mode': True,
 'EXP_Itlk_State': tango._tango.DevState.ON,
 'FE_Itlk_State': tango._tango.DevState.ON,
 'FE_State': 'FE open',
 'HQPS_Itlk_State': tango._tango.DevState.ON,
 'PSS_Itlk_State': tango._tango.DevState.ON,
 'SR_Current': 195.93514894706684,
 'SR_Filling_Mode': '7/8 multibunch',
 'SR_Lifetime': 66281.93637072828,
 'SR_Mode': 'USM',
 'SR_Operator_Mesg': 'Jun  3 12:00 Back to USM',
 'SR_Refill_Countdown': 2034.0,
 'SR_Single_Bunch_Current': -0.04008001020600001,
 'UHV_Valve_State': tango._tango.DevState.ON}
```


## iter_wait_for_refill

`iter_wait_for_refill(<checktime>, <waittime>=0., <polling_time>=1.)`

Helper for waiting the machine refill.  It will yield two states
"WAIT_INJECTION" and "WAITING_AFTER_BEAM_IS_BACK" until the machine refill is
finished.

simple usage will be:

```python
for status in iter_wait_for_refill(my_check_time,waittime=1.,polling_time=1.):
    if status == "WAIT_INJECTION":
        print("Scan is paused, waiting injection",end='\r')
    else:
        print("Scan will restart in 1 second...",end='\r')
```

## check_for_refill

`check_for_refill(checktime)`: check that `checktime` (in seconds) is *smaller* than `refill`
(the refill countdown).

Example:
```python
DEMO [4]: from bliss.controllers.machinfo import  MachInfo

DEMO [5]: mama.counters.refill
 Out [5]: 'refill` Tango attribute counter info:
             device server = //acs.esrf.fr:10000/fe/master/id42
             Tango attribute = SR_Refill_Countdown
             ...
             value: 6411.0

DEMO [6]: MachInfo.check_for_refill(mama, 6300)
 Out [6]: True

DEMO [7]: MachInfo.check_for_refill(mama, 6500)
 Out [7]: False
```

## WaitForRefillPreset

This preset will pause a scan:

* during the refill
* or if the `checktime` is greater than the **time to refill**.

If `checktime` is set to `None`, `count_time` is used if found on the top
master of the chain.

Insertion of `WaitForRefillPreset` preset is done via `.check` setting:

* Set it to `True` to activate refill check.
* Set it to `False` to de-activate refill check.

Example:
```python

DEMO [6]: mama.check
 Out [6]: False

DEMO [7]: mama.check=True

```
