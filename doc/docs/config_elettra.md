## Configuring an Elettra (or ePicea) 4 channels electrometer as a Counter Controller 

This section explains how to configure it to get BPM values as counters

### Example YAML configuration:

```yaml

- class: Elettra
  module: tango_elettra
  name: el2
  uri: //id20ctrl2:20000/id20/elettra/ss1
  counters:
  - counter_name: el2x
    measure: Y
  - counter_name: el2y
    measure: Z
  - counter_name: el2i
    measure: integration_time
  - counter_name: el2n
    measure: samples_number
  - counter_name: c1
    measure: current1
  - counter_name: c2
    measure: current2
  - counter_name: c3
    measure: current3
  - counter_name: c4
    measure: current4
  - counter_name: ctot
    measure: current_total
    
```

### Tango Server

The Tango server package is called elettraAH in blissinstaller.
A conda package will be provided in the next future.

http://wikiserv.esrf.fr/bliss/index.php/CAENels_picoammeter#Tango_Device_Server

### Usage

To setup the measuring range, give maximum current value you expect to measure in Amps:

  el2.range = 0.00025

It is recommended to setup measurement offsets too, for each different measuring range. One can specify the integration time, default is 1 sec. offset_reset command will remove any offset. 

  el2.offset_measure (1)
  
  el2.offset_reset

  el2.offset

### Restrictions

Only AH501 models have been tested so far. AH401 and TetrAMM will come soon.

## TO BE CONTINUED