# Ace configuration

ACE is an electronic module NIM, two units wide, dedicated to provide all signal and power for an Avalanche photo-diode in X-ray counting. This module includes an easy user interface in local and remote control mode. The unit is based on a micro controller Hitachi and a programmable counter implemented in a Complex Programmable Logic Device from Xilinx. Computer control will communicate to the module through one of the two available serial line ports (RS232 and RS422) or by a parallel GPIB port. The local user interface will be providing by a graphic LCD display with touch panel facility.

The BLISS Ace controller provides:

3 SoftAxis (pseudo-axes):
- low-level threshold of discriminator (tag: `low`)
- window width (high - low) level threshold (tag: `win`)
- head high voltage setpoint (tag: `hhv`)

4 Counters:
- pulse counter (tag: `counts`)
- head temperature (tag: `htemp`)
- high voltage current (tag: `hvcur`)
- high voltage monitor (tag: `hvmon`)


## Example configuration

```yaml
-   class: Ace
    module: sca.ace
    plugin: bliss
    name: ace
    timeout: 3
    serial:
        url: ser2net://lid00limace:28000/dev/ttyS0

    axes:
        - axis_name: ace_axis_low
          tag: low
        
        - axis_name: ace_axis_win
          tag: win

        - axis_name: ace_axis_hhv
          tag: hhv
    
    counters:
        - counter_name: ace_cnt_counts
          tag: counts
          mode: LAST
        
        - counter_name: ace_cnt_htemp
          tag: htemp
          unit: °C
          mode: SINGLE

        - counter_name: ace_cnt_hvcur
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
ACE_TEST [1]: ace
     Out [1]: VERSION:                        ACE 01.04
              SERIAL ADDRESS:
              GPIB ADDRESS:                   14 X10
              HEAD MAX CURRENT:               10.1 mA            (range [0, 25])
              HEAD MAX TEMPERATURE:           40 °C              (range=[0, 50])
              HEAD CURRENT TEMPERATURE:       30.792 °C
              HEAD BIAS VOLTAGE SETPOINT:     310 V (ON)         (range=[0, 600])
              COUNTING SOURCE:                SCA
              SCA MODE:                       WIN
              SCA LOW:                        0.1 V              (range=[-0.2, 5])
              SCA WIN:                        2 V                (range=[0, 5])
              SCA PUSLE SHAPING:              5 ns               (range=[5, 10, 20, 30])
              GATE IN MODE:                   NIM
              TRIGGER IN MODE:                NIM
              SYNC OUTPUT MODE:               GATE POS
              ALARM MODE:                     HEAD CURR
              RATE METER ALARM THRESHOLD:     5e+07              (range=[0, 1e8])
              ALARM THRESHOLD:                8.08 mA            (range=[0, 25])
              BUFFER OPTIONS:                 DOUBLE FULL
              DATA FORMAT:                    DWORD DEC WBSWAP

ACE_TEST [2]: ascan(ace_axis_low ,0,0.1,10,0.1, ace)
     Out [2]: Scan(number=43, name=ascan, path=/tmp/scans/ace_test/data.h5)
```

```python
======================================================= Bliss session 'ace_test': watching scans ====


Scan 43 Fri Mar 06 15:46:57 2020 /tmp/scans/ace_test/data.h5 ace_test user = mauro
ascan ace_axis_low 0 0.1 10 0.1

           #         dt[s]  ace_axis_low[V]  ace_cnt_counts  ace_cnt_htemp[°C]  ace_cnt_hvcur[uA]  ace_cnt_hvmon[V]
           0             0                0          911611             30.743            0.17107            311.81
           1      0.308431             0.01          800857             30.743            0.17107            311.81
           2      0.636019             0.02          538452             30.792             0.1955            311.81
           3      0.962156             0.03          306843             30.792             0.1955            311.81
           4       1.29856             0.04          151126             30.743             0.1955            311.81
           5       1.63566             0.05           68296             30.792            0.17107            311.81
           6       1.97717             0.06           29134             30.694            0.17107            311.81
           7       2.31645             0.07           11744             30.743            0.17107            311.81
           8       2.65045             0.08            4426             30.743             0.1955            311.81
           9       2.99212             0.09            1655             30.743            0.17107            311.81
          10       3.31577              0.1             551             30.743            0.21994            311.81

Took 0:00:04.005052

=================================================== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ====
```