# Oxford 700

## YAML configuration file example

```YAML
plugin: temperature
package: bliss.controllers.temperature.oxfordcryo.oxford700
class: oxford700
serial:
  url: rfc2217://lid032:28008
outputs:
  - name: ox
    tango_server: ox
description: Oxford 700 Cryo from instrument pool
user_tag:
- SAMPLENV.CRYO

```

## Status Information
by calling the controller object (e.g. using aboves configuration ox.controller) the whole device status is shown.


!!! note
    ramping to a setpoint (using ox.ramprate; ox.ramp) instead ox.set seems to be more stable for now.

## further reading at ESRF
   * [Sample env. Wiki: Oxford Cryosystems - Cryostream Controller 700](http://wikiserv.esrf.fr/sample_env/index.php/Oxford_Cryosystems_-_Cryostream_Controller_700)
   * [Bliss Wiki: Oxford700](http://wikiserv.esrf.fr/bliss/index.php/Oxford700)
