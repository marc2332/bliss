# Deprecated controllers

Those controllers are not part of the standard BLISS codebase
anymore. Some of those controllers are Python 2, some others
are not up-to-date with latest API, or those controllers are
obsolete or not in use -- that is why they have been removed
from BLISS.

That said, the code is still available in the project history,
so a link is kept here (just in case !).

## Vaisala HMT330 humidity/temperature controller

### Configuration

```YAML
    plugin: temperature
    module: vaisala
    class: HMT330
    serial:
      url: ser2net://lid312:29000/dev/ttyRP20
    inputs:
      - name: hmtT
        channel: T
      - name: hmtRH
        channel: RH
      - name: hmtA
        channel: A
```

### Code

See commit 11cf383f ; files:

* `bliss/controllers/vaisala.py`
* `bliss/controllers/temperature/vaisala.py`

## Leica microscope

The Leica microscope is a device from ID28, connected via USB.
The communication protocol has been reverse-engineered to be
able to display the microscope image as a video within MXCuBE 2,
and to be able to control the different microscope axes from
BLISS.

### Configuration

```yaml
plugin: bliss
class: LeicaMicroscope
module: leica_microscope
name: leica
shutter_predelay: 56e-3
shutter_postdelay: 23e-3
phi: $phi
oscil_mprg: /users/blissadm/local/HardwareRepository/oscillPX.mprg
musst: $musst
musst_sampling: 80
diagfile: /users/opid28/oscillation_diag.dat
```

Motors:

```yaml
plugin: emotion
controller:
  class: leica
  axes:
    -
      name: zoom
      channel: 60
      steps_per_unit: 100
      low_limit: 5.7
      high_limit: 115
    -
      name: focus_coarse
      channel: 70
      steps_per_unit: 1000
      low_limit: -380
      high_limit: 5.28
    -
      name: focus_fine
      channel: 72
      steps_per_unit: 1000
      low_limit:  0
      high_limit: 10.2
    -
      name: iris
      channel: 62
      steps_per_unit: 10
      low_limit: 20.5
      high_limit: 99.5
    -
      name: light
      channel: 37
      steps_per_unit: 0.1
      low_limit: 10
      high_limit: 100
```

### Code

See commit d631d272 ; files:

* `bliss/controllers/_leica_usb.py`
* `bliss/controllers/leica_microscope.py`
* `bliss/controllers/motors/leica.py`
