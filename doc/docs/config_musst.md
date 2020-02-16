
MUSST is a board designed by ISG group.

* **M** ultipurpose
* **U** nit for
* **S** ynchronization
* **S** equencing and
* **T** rigering

is an NIM module that produces trigger patterns synchronized with
external events.

It can also be used to:

* read encoder signals
* read ADC values
* read MCA spectrum

The MUSST is controlled via a serial or a GPIB connection. GPIB connection is
faster and must be used to use the MUSST in continuous scans.


## References

* BCU Wiki page: http://wikiserv.esrf.fr/bliss/index.php/Musst
* ISG wiki pages: http://wikiserv.esrf.fr/esl/index.php/Category:MUSST


## Installation

!!! note
    For ESRF users:

    * If using a PCI board, install:
        - gpib drivers
        - gpib Tango device server `GpibController_PCI` (debian8 or redhate4)
        - Configure server startup script

Example of simple YAML configuration file:

```yaml
name: musst_cc1
class: musst
gpib:
  url: tango_gpib_device_server://id42/gpib_1/0   # PCI board
  # url: enet://gpibid156.esrf.fr                 # Enet gpib
  pad: 13                                         # primary address
  timeout: 3.                                     # in seconds
channels:
  - type: CNT                  # encoder/cnt/ssi/adc10/switch
    channel: 2                 # 
    name: enc_sy               # 
    label: "lab_enc_mono"      # ?
    counter_name: enc_mono     # related counter
    counter_mode: SINGLE       # MEAN, LAST,INTEGRATE etc.
counters:
  - name: enc_mono
    channel: CH1
```


It is then possible to use a MUSST counter in a scan or a count:
```python
DEMO [5]: ct(1, musst_sxm.counters.enc_samy)
Mon Feb 10 21:51:44 2020

enc_samy =     393803.0 (    393803.0/s)
  Out [5]: Scan(number=1, name=ct, path=)
```



## Config parameters

Config parameters list:

* **name**: the controller's name
* **config_tree**: controller configuration. In this dictionary we need to have:

* **gpib**:
    - **url**: url of the gpib controller  ex: `enet://gpib42.esrf.fr`
    - **pad**: primary address of the musst controller
    - **timeout**: communication timeout, default is 1s
    - **eos**: end of line termination

* **musst_prg_root**: default path for musst programs
* **block_size**: default is 8k but can be lowered to 512 depend on gpib.
* **one_line_programing**: default is False we send several lines to program the musst
* **channels:**: list of configured channels, in this dictionary we need to have:
    * **label:**: the name alias for the channels
    * **type:**: channel type (`cnt`, `encoder`, `ssi`, `adc5`, `adc10` or `switch`)
        - `CNT`
        - `ENCODER`
        - `SSI`
        - `ADC10`
        - `ADC5`
        - `SWITCH`
    * **channel:**: channel number
    * **name:**: use to reference an external switch
    * **counter_name**:
    * **counter_mode**: [Counter Sampling Mode](dev_ct.md#sampling-counter-modes)

* **counters:**: list of the counters, in this dictionary we need to have:
    * **name:**: counter name
    * **channel:**: musst channel

## Commands

### status

```python
DEMO [1]: musst_sxm.__info__()
====  MUSST info  ===
object name: musst_sxm
version:  MUSST 01.01a
url: tango_gpib_device_server://id42/gpib_lid423/0
address: 13

    CHANNELS:
    CH1 ( RUN):     159982 -  ENC DIR
    CH2 ( RUN):   -8048244 -  ENC DIR
    CH3 ( RUN):      53396 -  ENC DIR
    CH4 ( RUN):     174954 -  ENC DIR
    CH5 ( RUN):  168296384 -  ENC DIR
    CH6 (STOP):          0 -  CNT
```

To set a channel to desired value:
```python
musst_sxm.set_variable("CH3", 123)
```

Direct communication:
```python
DEMO [21]: musst_sxm.putget("?CH CH3")
 Out [21]: '53427 RUN'
```


## Switch

## MUSST MCA

## MUSST MCA

## MUSST Programming

