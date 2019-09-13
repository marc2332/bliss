# MOCO

## Description

This module allows to control ISG MOCO device.

This module provides:

- Raw access to MOCO commands
- Direct access as method or attributes to the main functionnalities of the device
- Access to MOCO values as BLISS counters
- definition of a BLISS motor to control the Voltage output of the module 
  (usually a piezo is connected to this output)

## Configuration

Configuration of a MOCO object is described here: [MOCO Configuration](config_moco.md).

## Usage

In the following session, The Moco object `moco` is running in the `session_moco` BLISS session

### User API

#### status

- Status got from the MOCO device

``` python
SESSION_MOCO [1]: moco
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

- Status of the regulation

``` python
SESSION_MOCO [2]: moco.state()
IDLE
```

#### Parameters

A number of MOCO parameters can set and read:

- amplitude

``` python
SESSION_MOCO [3]: moco.amplitude = 0.00513
SESSION_MOCO [4]: moco.amplitude
         Out [4]: 0.00513
```

- phase
``` python
SESSION_MOCO [5]: moco.phase = 150.0
SESSION_MOCO [6]: moco.phase
         Out [6]: 150.0
```

- slope
``` python
SESSION_MOCO [7]: moco.slope = 1.0
SESSION_MOCO [8]: moco.slope
         Out [8]: 1.0
```

- tau
``` python
SESSION_MOCO [9]: moco.tau = 0.1
SESSION_MOCO [10]: moco.tau
         Out [10]: 0.1
```

- frequency
``` python
SESSION_MOCO [11]: moco.frequency = 166.667
SESSION_MOCO [12]: moco.frequency
         Out [12]: 166.667
```

#### Commands

All commands of a MOCO obejct have silent mode:

```python
    moco.command(par1=val1, par2=val2, ..., silent=False/True)
```

The most important functionnalities of MOCO may be access using the following commands

- mode
```python
SESSION_MOCO [14]: moco.mode("OSCILLATION")
MODE: OSCILLATION       [POSITION | INTENSITY | OSCILLATION]
         Out [14]: 'OSCILLATION'

SESSION_MOCO [15]: moco.mode()
MODE: OSCILLATION       [POSITION | INTENSITY | OSCILLATION]
         Out [15]: 'OSCILLATION'
```

- srange
```python
SESSION_MOCO [16]: moco.srange(0, 3)
SRANGE: [0 - 3]
         Out [116]: [0.0, 3.0]

SESSION_MOCO [17]: moco.srange()
SRANGE: [0 - 3]
         Out [17]: [0.0, 3.0]

```

- outbeam
```python
SESSION_MOCO [18]: moco.outbeam("VOLT", "NORM", "UNIP", 1.25, "autoscale")
OUTBEAM: source    : VOLT       [CURR | VOLT | EXT]
         polarity  : NORM       [NORM | INV]
         channel   : UNIP       [BIP | UNI]
         fullscale : 1.25
         autoscale : NOAUTO     [AUTO | NOAUTO]
SESSION_MOCO [19]: moco.outbeam()
OUTBEAM: source    : VOLT       [CURR | VOLT | EXT]
         polarity  : NORM       [NORM | INV]
         channel   : UNIP       [BIP | UNI]
         fullscale : 1.25
         autoscale : NOAUTO     [AUTO | NOAUTO]
```

- go
```python
SESSION_MOCO [20]: moco.go()
```

- peak
```python
SESSION_MOCO [21]: moco.peak(1, 0.1, 0.0)
SESSION_MOCO [22]: moco.peak()
PEAK: height=1  width=0.1  pos=0
         Out [22]: [1.0, 0.1, 0.0]
```

- tune
```python
SESSION_MOCO [20]: moco.tune()
```

- stop
```python
SESSION_MOCO [20]: moco.stop()
```

- beam
```python
SESSION_MOCO [19]: moco.beam()

Beam IN  [0]
Beam OUT [0.0223569]
```

### Raw commands

- MOCO commands may be call using raw communication system

``` python
SESSION_MOCO [3]: moco.comm("?BEAM")
         Out [3]: '0 0.0217459'
```

- List of commands available using the .comm method

``` python
SESSION_MOCO [2]: moco.help()

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

