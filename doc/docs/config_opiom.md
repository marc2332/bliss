# OPIOM card configuration

OPIOM is a multi-purpose digital I/O NIM module built around a programmable
logic device (PLD) and a micro-controller. This architecture provides the user
with the usual programmable logic capabilities combined with the advanced
features available in the micro-controller.

!!! note
    At ESRF, OPIOM board is mainly used:

    * to multiplex signals from and to different devices depending of type of
      acquisistion performed.
         - moving/ready signals comming from motors or detectors
         - trigger/gate signals going to devices (ccd, shutters, etc.)
    * as signal level/duration adaptation
    * as continuous scan master (being replaced by MUSST card)

ISG pages:

* http://www.esrf.fr/Instrumentation/DetectorsAndElectronics/opiom
* http://wikiserv.esrf.fr/esl/index.php/Category:OPIOM
* programs compilation tool: http://pulsar.esrf.fr/opiom/opiomhome.html

![Screenshot](img/opiom_paths.svg)

## Yaml sample configuration

```YAML
- class: Opiom
  name: opiom_eh3
  serial:
    url: tango://id13/Serial_133_232/02
    timeout: 30
  program: /users/blissadm/local/isg/opiom/20180625_152307_multiplexer-eh3
```

## Multiplexer

This object helps to manage an OPIOM board used as a multiplexing board (not as
continuous scan master for example) containing one or many multiplexers.


### BLISS object

In the YAML configuration, can be found:

* the internal multiplexers description
* the program to load into the OPIOM

Multiplexers are typically used in a [scan preset](scan_default.md#using-presets-to-customize-a-scan).



#### Example 1

Simple multiplexer with 1 output and 2 inputs:
```yaml
- class: multiplexer
  name: mpx
  plugin: bliss
  boards:
    - class: opiom
      name: opiom1
      serial:
        url: rfc2217://lid421:28201    # /dev/ttyR1
      program: 20150818_173019_SXM_V0
      opiom_prg_root: /users/blissadm/local/beamline_configuration/
  outputs:
    - label: MUSST_TRIG
      comment: Trig Vscanner
      board: opiom1
      register: IM
      shift: 1
      mask: 0x1
      VSCANNER1: 0
      VSCANNER2: 1
```

This can be represented as:
```
                 0  __
  VSCANNER1------->|  \
                   |   |
                   |   |--------- MUSST_TRIG------->
                 1 |   |
  VSCANNER2------->|__/
                    ^
                    |
                    IM1

     Inputs        Selector          Output
```


#### Usage

To display current state of multiplexer named **mpx**:
```python
DEMO [12]: mpx
 Out [12]: Multiplexer Status:
           Output name                     Output status
           MUSST_TRIG                      VSCANNER1
```

Input `VSCANNER1` is selected.

To change the input:
```python
DEMO [13]: mpx.switch("MUSST_TRIG", "VSCANNER2")
DEMO [14]: mpx
 Out [14]: Multiplexer Status:
           Output name                     Output status
           MUSST_TRIG                      VSCANNER2

```
Input `VSCANNER2` is now selected.

Some other useful commands:
```
DEMO [2]: mpx.getOutputList()
 Out [2]: ['MUSST_TRIG']

DEMO [2]: mpx.getOutputList()
 Out [2]: ['MUSST_TRIG']

DEMO [3]: mpx.getGlobalStat()
 Out [3]: {'MUSST_TRIG': 'VSCANNER2'}

DEMO [4]: mpx.getKeyAndName()
 Out [4]: {'MUSST_TRIG': 'Trig Vscanner'}

DEMO [7]: mpx._boards
 Out [7]: {'opiom1': <bliss.controllers.opiom.Opiom object at 0x7f78d8f85d50>}

DEMO [9]: mpx._boards["opiom1"]
 Out [9]: opiom: Serial[rfc2217://lid213:28201]
```

#### Example 2

More complex example with chained OPIOMs:

```yaml
- class: multiplexer
  name: mult1
  boards:
    - class: opiom
      name: opiom1
      serial: /dev/ttyS0
      program: 220080208_164412_id22NI_opiom_2.8
      opiom_prg_root: /users/blissadm/local/isg/opiom # default
    - class: opiom
      name: opiom2
      serial: /dev/ttyS1
      program: 20100122_143221_id11-laser-1.0.prg
  outputs:
    - label: APD
      comment: APD counter
      board: opiom1
      register: IM
      shift: 0
      mask: 0x3
      APD1: 0
      APD2: 1
      APD3: 2
      chain:
        chained_value: 3
        board: opiom2
        register: IMA
        shift: 2
        mask: 0x3
        APD4: 0
        APD5: 1
        APD6: 2
        APD7: 3
    - label: CR1
      comment: Correlator chan. A
      board: opiom1
      register: IM
      shift: 1
      mask: 0x3
      MON: 0
      DET: 1
      APD1: 2
      APD2: 3
    - label: ITRIG
      comment: ITRIG MUSST
      register: IM
      shift: 1
      mask: 0x7
      sampy: 0
      sampz: 1
      samy: 2
      samz: 3
      cam1: 4
      cam2: 5
```



### Device server

OPIOM multiplexer can also be used with a tango device server (as it was done
with SPEC)

`bliss/tango/servers/multiplexer_ds.py`

