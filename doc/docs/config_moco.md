# MOCO

## Description

This module allows to control ISG MOCO device.

This module provides:

* Raw access to MOCO commands
* Direct access as method or attributes to the main functionnalities of the device
* Access to MOCO values as BLISS counters
* definition of a BLISS motor to control the Voltage output of the module
  (usually a piezo is connected to this output)

## Usage

Usage of a MOCO object is described here: [MOCO Usage](using_moco.md).

## Configuration

### YAML configuration file example


```YAML
- plugin: bliss                     (mandatory)
  class: Moco                       (mandatory)
  name: mocoeh1                     (mandatory)
  serial:                           (mandatory)
    url: rfc2217://ld231-new:28213  (mandatory)
      
  counters:
    - counter_name: outm
      role: outbeam
    - counter_name: inm
      role: inbeam
    - counter_name: summ
      role: sum
    - counter_name: diffm
      role: diff
    - counter_name: ndiffm
      role: ndiff
    - counter_name: ratiom
      role: ratio

    - counter_name: foutm
      role: foutbeam
    - counter_name: finm
      role: finbeam
    - counter_name: fsumm
      role: fsum
    - counter_name: fdiffmcamill
      role: fdiff
    - counter_name: fndiffm
      role: fndiff
    - counter_name: fratiom
      role: fratio
      
    - counter_name: oscmainm
      role: oscmain
    - counter_name: oscquadm
      role: oscquad
      
    - counter_name: piezom
      role: piezo

- plugin: emotion
  class: MocoMotorController
  moco: $mocoeh1
  axes:
    - name: qgth2
      class: NoSettingsAxis
      unit: V
      steps_per_unit: 1.0
```

### Configuration options

* If you do not need a motor just remove it from the yml file
* In the `counters` section add only the counters you need

## References

* User Manual: http://www.esrf.fr/Instrumentation/DetectorsAndElectronics/moco
* ISG/ESL page: http://www.esrf.fr/Instrumentation/DetectorsAndElectronics/moco
* BCU wiki page: http://wikiserv.esrf.fr/bliss/index.php/Moco
