# MOCO

## Description



The Monochromator Controller (MoCo) is an electronic module designed to regulate
the position of an optical component in a synchrotron radiation beamline. The
controller corrects the position of the component, typically a mirror or a
monochromator, by monitoring the outgoing beam and actively compensating low
frequency drifts due to thermal load changes or mechanical instability.

Features:

* Active regulation of an optical element on one of its degrees of freedom.
* Keeps constant either the transmission or the position of the beam.
* Primarily designed for double crystal monochromators but it could be
  potentially used with other optics (mirrors, single crystal monochromators).
* Main features:- Time constant from 1 ms to 1 minute- Automatic tuning-
  Autorange- Beam lost detection- Current and voltage inputs- Serial line
  communication
* Can be configured from slave mode to fully automatic mode.
* Built-in current amplifiers (24 gain ranges over 7 decades).



BLISS Moco controller provides:

* Raw access to MOCO commands
* Direct access as method or attributes to the main functionnalities of the
  device
* Access to MOCO values as BLISS counters
* definition of a BLISS motor to control the Voltage output of the module
  (usually a piezo is connected to this output)


## References

* BCU wiki page: http://wikiserv.esrf.fr/bliss/index.php/Moco


## Configuration

### YAML configuration file example


```YAML
- plugin: bliss                     (mandatory)
  class: Moco                       (mandatory)
  name: mocoeh1                     (mandatory)
  serial:                           (mandatory)
    url: rfc2217://ld421-new:28213  (mandatory)

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

* Motor can be removed from the yml file if not needed.
* In the `counters` section add only the needed counters.



## Usage

In the following session, The Moco object `moco` is running in the
`moco` BLISS session

### User API

#### status

* Status got from the MOCO device

```python
DEMO [1]: moco
 Out [1]: MOCO
          Name    : moco
          Comm.   : Serial[rfc2217://lid265:28254]

          MOCO 02.00  -  Current settings:
            NAME "no name"
            ADDR

            OPRANGE -2 5 0
            INBEAM SOFT 1
            OUTBEAM VOLT NORM UNIP 1.25 NOAUTO

            MODE OSCILLATION
            AMPLITUDE 0.0513738
            FREQUENCY 166.667
            PHASE 150
            SLOPE 1
            SETPOINT 0
            TAU 0.1
            SET
            CLEAR  AUTORUN BEAMCHECK NORMALISE AUTORANGE INTERLOCK
            AUTOTUNE OFF
            AUTOPEAK OFF
            BEAMCHECK 0.1 0.1 1.024 0
            SRANGE 0 3
            SPEED 2 50
            INHIBIT OFF LOW
```

* Status of the regulation

```python
DEMO [2]: moco.state()
IDLE
```

#### Parameters

A number of MOCO parameters can set and read:

* `amplitude`
```python
DEMO [3]: moco.amplitude = 0.00513
DEMO [4]: moco.amplitude
 Out [4]: 0.00513
```

* `phase`
```python
DEMO [5]: moco.phase = 150.0
DEMO [6]: moco.phase
 Out [6]: 150.0
```

* `slope`
```python
DEMO [7]: moco.slope = 1.0
DEMO [8]: moco.slope
 Out [8]: 1.0
```

* `tau`
```python
DEMO [9]: moco.tau = 0.1
DEMO [10]: moco.tau
 Out [10]: 0.1
```

* `frequency`
```python
DEMO [11]: moco.frequency = 166.667
DEMO [12]: moco.frequency
 Out [12]: 166.667
```

#### Commands

All commands of a MOCO obejct have silent mode:

```python
moco.command(par1=val1, par2=val2, ..., silent=False/True)
```

The most important functionnalities of MOCO may be access using the following
commands:

* `mode`
```python
DEMO [14]: moco.mode("OSCILLATION")
MODE: OSCILLATION       [POSITION | INTENSITY | OSCILLATION]
 Out [14]: 'OSCILLATION'

DEMO [15]: moco.mode()
MODE: OSCILLATION       [POSITION | INTENSITY | OSCILLATION]
 Out [15]: 'OSCILLATION'
```

* `srange`
```python
DEMO [16]: moco.srange(0, 3)
SRANGE: [0 - 3]
 Out [116]: [0.0, 3.0]

DEMO [17]: moco.srange()
SRANGE: [0 - 3]
 Out [17]: [0.0, 3.0]
```

* `outbeam`
```python
DEMO [18]: moco.outbeam("VOLT", "NORM", "UNIP", 1.25, "autoscale")
OUTBEAM: source    : VOLT       [CURR | VOLT | EXT]
         polarity  : NORM       [NORM | INV]
         channel   : UNIP       [BIP | UNI]
         fullscale : 1.25
         autoscale : NOAUTO     [AUTO | NOAUTO]
DEMO [19]: moco.outbeam()
OUTBEAM: source    : VOLT       [CURR | VOLT | EXT]
         polarity  : NORM       [NORM | INV]
         channel   : UNIP       [BIP | UNI]
         fullscale : 1.25
         autoscale : NOAUTO     [AUTO | NOAUTO]
```

* `go`
```python
DEMO [20]: moco.go()
```

* `peak`
```python
DEMO [21]: moco.peak(1, 0.1, 0.0)
DEMO [22]: moco.peak()
PEAK: height=1  width=0.1  pos=0
 Out [22]: [1.0, 0.1, 0.0]
```

* `tune`
```python
DEMO [20]: moco.tune()
```

* `stop`
```python
DEMO [20]: moco.stop()
```

* `beam`
```python
DEMO [19]: moco.beam()

Beam IN  [0]
Beam OUT [0.0223569]
```

### Raw commands

* MOCO commands may be call using raw communication system

```python
DEMO [3]: moco.comm("?BEAM")
 Out [3]: '0 0.0217459'
```

* List of commands available using the .comm method

```python
DEMO [2]: moco.help()

      RESET
        GO
      STOP
      TUNE
  AUTOTUNE  ?AUTOTUNE
  AUTOPEAK  ?AUTOPEAK
     PIEZO  ?PIEZO
            ?STATE
            ?BEAM
            ?FBEAM
  AUTOBEAM
  SOFTBEAM  ?SOFTBEAM
   OPRANGE  ?OPRANGE
    SRANGE  ?SRANGE
       SET
            ?CLEAR
     CLEAR
            ?SET
     PAUSE  ?PAUSE
   INHIBIT  ?INHIBIT
       TAU  ?TAU
  SETPOINT  ?SETPOINT
      MODE  ?MODE
    INBEAM  ?INBEAM
   OUTBEAM  ?OUTBEAM
      GAIN  ?GAIN
      ZERO  ?ZERO
    OFFSET  ?OFFSET
  ADCCALIB  ?ADCCALIB
 BEAMCHECK  ?BEAMCHECK
     SPEED  ?SPEED
      PEAK  ?PEAK
     SLOPE  ?SLOPE
            ?OSCBEAM
            ?OSCSAT
     OSCIL  ?OSCIL
 AMPLITUDE  ?AMPLITUDE
 FREQUENCY  ?FREQUENCY
     PHASE  ?PHASE
            ?INFO
   ISGTEST  ?ISGTEST
      ECHO
    NOECHO
            ?ERR
      ADDR  ?ADDR
            ?CHAIN
      NAME  ?NAME
            ?VER
            ?HELP
```

