
# MCA


## MCA

Information

```python
DEMO [1]: fx8
 Out [1]: MCA:
              object: <class 'bliss.controllers.mca.xia.FalconX'>
              Detector brand : XIA
              Detector type  : FALCONX
              Acquisition mode : MCA
              Spectrum size    : 2048

          ROIS:
              Name      start    end
              ------  -------  -----
              Aula        888   1234
              NoiSe         3    123

          XIA:
              configuration file:
                - default : falconx8_2ch.ini
                - current : falconx8cyril.ini

          FALCONX:
              address: tcp://wid424:8000
```


* `spectrum_size` /  `spectrum_range`

```python
DEMO [3]: fx8.spectrum_range
 Out [3]: (0, 2047)

DEMO [4]: fx8.spectrum_size
 Out [4]: 2048
```

* `detector_brand` `detector_type`  (in fact brand and type of electronic ???)

```python
DEMO [19]: fx8.detector_brand
 Out [19]: <Brand.XIA: 2>

DEMO [20]: fx8.detector_type
 Out [20]: <DetectorType.FALCONX: 2>
```




## ROIs counters

To see which ROIs are defined:

```python
DEMO [1]: simul_mca.rois
 Out [1]: Name    start  end
          ------  -----  -----
          my_roi  200    800
```

### add/remove a ROI

To add a ROI: `rois.set(<name>, <start>, <stop>)`

* `<name>` (*str*): name of the ROI (must be unique)
* `<start>` (*int*): start channel index
* `<end>` (*int*): end channel index

Example:
```python
DEMO [7]: fx8.rois
 Out [7]: Name      start    end
          ------  -------  -----
          Aula        888   1234
          NoiSe         3    123

DEMO [8]: fx8.rois.set("NiKa", 222, 333)

DEMO [9]: fx8.rois
 Out [9]: Name      start    end
          ------  -------  -----
          Aula        888   1234
          NoiSe         3    123
          NiKa        222    333

DEMO [11]: fx8.rois.remove("NiKa")

DEMO [12]: fx8.rois
 Out [12]: Name      start    end
           ------  -------  -----
           Aula        888   1234
           NoiSe         3    123

```

Each ROI adds several counters:

```python
DEMO [13]: fx8.counters
 Out [13]: Namespace containing:
           .Aula_det0
           .NoiSe_det0
           [...]
           .Aula_detN
           .NoiSe_detN
           .Aula
           .NoiSe
```

To add a roi counter in a measurement group, the *fullname* must be used.

!!!tip
    `lscnt()` command can be used to easily retrieve the full name of a roi counter.



### ROI in config

???



## Acquisition

???



### Acquisition modes

```python
DEMO [22]: fx8.supported_acquisition_modes
 Out [22]: [<AcquisitionMode.MCA: 1>]
```

### Triggering modes

```python

DEMO [24]: fx8.trigger_mode
 Out [24]: <TriggerMode.SOFTWARE: 1>

DEMO [27]: fx8.supported_trigger_modes
 Out [27]: [<TriggerMode.SOFTWARE: 1>,
            <TriggerMode.SYNC: 2>,
            <TriggerMode.GATE: 3>]
```


To set a trigger mode:
```python
DEMO [3]: fx8.trigger_mode = "GATE"

DEMO [4]: fx8.trigger_mode
 Out [4]: <TriggerMode.GATE: 3>
```

or
```python
DEMO [22]: from bliss.controllers.mca import TriggerMode

DEMO [23]: fx8.trigger_mode= TriggerMode.GATE

DEMO [24]: fx8.trigger_mode
  Out [24]: <TriggerMode.GATE: 3>
```

NB: `fx8.trigger_mode = None`  set trigger mode to `"SOFTWARE"`



### preset modes

```python
DEMO [23]: fx8.supported_preset_modes
 Out [23]: [<PresetMode.NONE: 1>,
            <PresetMode.REALTIME: 2>,
            <PresetMode.LIVETIME: 3>,
            <PresetMode.EVENTS: 4>,
            <PresetMode.TRIGGERS: 5>]
```

```python
DEMO [25]: fx8.preset_value
 Out [25]: 300.0
```


### Acquisition commands

* `start_acquisition()`
* `stop_acquisition()`
* `is_acquiring()`
* `get_acquisition_data()`
* `get_acquisition_statistics()`



## Saving

???

## Statistics counters


* `realtime`: total time from start to end of the acquisition
* `trigger_livetime`: 
* `energy_livetime`: 
* `triggers`: 
* `events`: 
* `icr`: Input Count Rate
* `ocr`: Output Count Rate
* `deadtime`: 

### Sums

## Correction


## plotting

via Flint



## debug




## XIA Specific features

### configuration

* `configuration_directory`: PATH to configuration files on windows computer.
* `current_configuration`:
* `default_configuration`: the configuration file defined in YAML config file.

```python
DEMO [6]: fx8.configuration_directory
 Out [6]: 'C:\\\\blissadm\\\\falconx\\\\config\\\\examples'

DEMO [7]: fx8.current_configuration
 Out [7]: 'falconx8cyril.ini'

DEMO [8]: fx8.default_configuration
 Out [8]: 'falconx8_2ch.ini'

```


* `available_configurations`: to be improved... menu ?

sub-directories ?

```python
DEMO [13]: fx8.available_configurations
 Out [13]: ['Cubo_HighRate_20keV_092016.ini', 'falconx4.ini', 'falconx8.ini',
            'falconx8cyril.ini', 'falconx8cyrilPP.ini', 'falconx8_2ch.ini',
            'falconx8_2ch_test.ini', 'falconx8_ch0_MirionXPIPS_Ketek_D2R2.ini',
            'fx82.ini', 'perceval.ini']
```


* `load_configuration`:

```python
DEMO [12]: fx8.load_configuration("falconx8cyril.ini")
DEMO [13]:
```


* `reload_configuration()`: Force a reload of the current configuration.
* `reload_default()`: Load `.default_configuration`




### Mercury specific features

* `set_hardware_scas`

reset_hardware_scas
get_hardware_scas


### XMAP 


### FalconX

```python
DEMO [9]: fx8.url
 Out [9]: 'tcp://wid424:8000'
```


`refresh_rate`: 

```python
DEMO [1]: fx8.refresh_rate
 Out [1]: 0.1
```
