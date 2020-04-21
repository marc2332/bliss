# Ace configuration

ACE is an electronic module NIM, two units wide, dedicated to provide all signal and power for an Avalanche photo-diode in X-ray counting. This module includes an easy user interface in local and remote control mode. The unit is based on a micro controller Hitachi and a programmable counter implemented in a Complex Programmable Logic Device from Xilinx. Computer control will communicate to the module through one of the two available serial line ports (RS232 and RS422) or by a parallel GPIB port. The local user interface will be providing by a graphic LCD display with touch panel facility.

The BLISS `Ace` controller provides (`bliss.controllers.sca.ace`):

**3 SoftAxis (pseudo-axes)**:


- low-level threshold of discriminator (tag: `low`)

- window width (high - low) level threshold (tag: `win`)

- head high voltage setpoint (tag: `hhv`)

**4 Counters**:

- pulse counter (tag: `counts`)

- head temperature (tag: `htemp`)

- head current (tag: `hvcurr`)

- high voltage monitor (tag: `hvmon`)


## Example configuration

```yaml
-   class: Ace
    module: sca.ace
    plugin: bliss
    name: ace
    timeout: 10
    #serial:
    #    url: ser2net://lid00limace:28000/dev/ttyS0
    gpib:
        url: tango_gpib_device_server://id10/gpib_40/0
        pad: 9
    axes:
        - axis_name: apdthl
          tag: low
        
        - axis_name: apdwin
          tag: win

        - axis_name: apdhv
          tag: hhv
    
    counters:
        - counter_name: apdcnt
          tag: counts
          mode: LAST
        
        - counter_name: apdtemp
          tag: htemp
          unit: °C
          mode: SINGLE

        - counter_name: hvcur
          tag: hvcur
          unit: uA
          mode: SINGLE

        - counter_name: ace_cnt_hvmon
          tag: hvmon
          unit: V
          mode: SINGLE
```

## Usage


```python
    Out [16]: ACE card: acedet, ACE 01.04a
              GPIB type=TANGO_DEVICE_SERVER url='tango_gpib_device_server://id10/gpib_40/0'
                   primary address='9' secondary address='0' tmo='13' timeout(s)='10' eol='
              '
              HEAD MAX CURRENT:               11 mA              (range [0, 25])
              HEAD MAX TEMPERATURE:           40 °C              (range=[0, 50])
              HEAD CURRENT TEMPERATURE:       26.1 °C
              HEAD BIAS VOLTAGE SETPOINT:     420 V (ON)         (range=[0, 600])
              COUNTING SOURCE:                SCA
              SCA MODE:                       WIN
              SCA LOW:                        0.1 V              (range=[-0.2, 5])
              SCA WIN:                        2.6 V              (range=[0, 5])
              SCA PUSLE SHAPING:              20 ns              (range=[5, 10, 20, 30])
              GATE IN MODE:                   NIM
              TRIGGER IN MODE:                NIM
              SYNC OUTPUT MODE:               GATE POS
              ALARM MODE:                     HEAD RATE CURR
              RATE METER ALARM THRESHOLD:     5e+07              (range=[0, 1e8])
              ALARM THRESHOLD:                6 mA               (range=[0, 25])
              BUFFER OPTIONS:                 DOUBLE FULL
              DATA FORMAT:                    DWORD DEC WBSWAP

              Axes
              ----
              low: apdthl
              win: apdwin
              hhv: apdhv

              Counters
              --------
              counts: apdcnt
              htemp: apdtemp
              hvcur: apdcurr
              hvmon: apdhvmon

EH1_EXP [5]: ascan(apdthl, 0, 0.1, 10, 1,ace, save=False)
    Out [5]: Scan(number=9, name=ascan, path=)
```

```python
Scan 9 Wed Mar 18 18:57:30 2020  eh1_exp user = opid10
ascan apdthl 0 0.1 10 1

           #         dt[s]     apdthl[V]        apdcnt   apdcurr[uA]   apdhvmon[V]   apdtemp[°C]
           0             0             0   3.97172e+07             0         421.3          26.1
           1       1.06521          0.01   1.70204e+07             0         421.3          26.1
           2       2.11069          0.02   5.88341e+06             0         421.3          26.1
           3       3.20752          0.03   1.72699e+06             0         421.3          26.1
           4       4.27623          0.04        446087             0         421.3          26.1
           5       5.32162          0.05        106288             0         421.3          26.1
           6       6.36807          0.06         23025             0         421.3          26.1
           7       7.43761          0.07          4793             0         421.3          26.1
           8       8.50213          0.08           901             0         421.3          26.1
           9       9.55439          0.09           174             0         421.3          26.1
          10       10.6151           0.1            39             0         421.3          26.1

Took 0:00:13.145863

================================ >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ================================
```
