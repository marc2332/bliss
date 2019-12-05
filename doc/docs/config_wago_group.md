
# Wago groups #

For convenience it's possible to group keys from different wagos to a WagoGroup object in config.

## Configuration ##

```yaml
- name: wago_group
  plugin: bliss
  module: wago.wagogroup
  class: WagoGroup
  wago:
    - name: $wago_simulator
      logical_keys: foh2ctrl, foh2pos, esTr1, esTr2, o10v1
    - name: $wago2
```

In this example you get an `wago_group` object with:

* Keys `foh2ctrl`, `foh2pos`, `esTr1`, `esTr2`, `o10v1` from `wago_simulator`
* All keys from `wago2`

!!! warning
    Duplicate logical key names between wagos are not allowed.

!!! note
    If `logical_keys` is not specified, all keys for the wago are imported.

!!! info
    `logical_keys` defined as counters in the wagos are also `counters` in the wago group.

## Usage ##

```python
TEST_SESSION [1]: wago_simulator
         Out [1]:  logical device     num of channel   module_type           module description
                  ----------------  ----------------  -------------  ----------------------------------
                      foh2ctrl                     4     750-504          4 Channel Digital Output
                      foh2pos                      4     750-408          4 Channel Digital Input
                       sain2                       1     750-408          4 Channel Digital Input
                       sain4                       1     750-408          4 Channel Digital Input
                       sain6                       1     750-408          4 Channel Digital Input
                       sain8                       1     750-408          4 Channel Digital Input
                        pres                       1     750-408          4 Channel Digital Input
                       esTf1                       1     750-469     2 Channel Ktype Thermocouple Input
                       esTf2                       1     750-469     2 Channel Ktype Thermocouple Input
                       esTf3                       1     750-469     2 Channel Ktype Thermocouple Input
                       esTf4                       1     750-469     2 Channel Ktype Thermocouple Input
                       esTr1                       1     750-469     2 Channel Ktype Thermocouple Input
                       esTr2                       1     750-469     2 Channel Ktype Thermocouple Input
                       esTr3                       1     750-469     2 Channel Ktype Thermocouple Input
                       esTr4                       1     750-469     2 Channel Ktype Thermocouple Input
                      intlckf1                     1     750-517         2 Changeover Relay Output
                      intlckf2                     1     750-517         2 Changeover Relay Output
                       o10v1                       1     750-554          2 Channel 4/20mA Output
                       o10v2                       1     750-554          2 Channel 4/20mA Output
                     double_out                    2     750-517         2 Changeover Relay Output

                  Given mapping does match Wago attached modules

TEST_SESSION [2]: wago_group
         Out [2]:  logical device    current value     wago name                description
                  ----------------  ---------------  --------------  ----------------------------------
                      foh2ctrl       [1, 1, 0, 1]    wago_simulator       4 Channel Digital Output
                      foh2pos        [0, 0, 0, 0]    wago_simulator       4 Channel Digital Input
                       esTr1            -496.4       wago_simulator  2 Channel Ktype Thermocouple Input
                       esTr2            -2765.5      wago_simulator  2 Channel Ktype Thermocouple Input
                       o10v1         1.0517578125    wago_simulator       2 Channel 4/20mA Output

TEST_SESSION [3]: wago_group.logical_keys
         Out [3]: ['foh2ctrl', 'foh2pos', 'esTr1', 'esTr2', 'o10v1']

TEST_SESSION [4]: wago_group.cnt_names
         Out [4]: ['esTr1', 'esTr2']

TEST_SESSION [5]: wago_group.counters
         Out [5]: namespace(esTr1=<bliss.controllers.wago.wago.WagoCounter>, esTr2=<bliss.controllers.wago.wago.WagoCounter>)
```

You would then set, get values as you would on the underlying wagos.

```python
TEST_SESSION [8]: wago_group.get('foh2ctrl', 'esTr1', 'o10v1', 'foh2pos')
         Out [8]: [1, 1, 0, 1, -496.4, 1.0517578125, 0, 0, 0, 0]

TEST_SESSION [9]: wago_group.set('foh2ctrl', 1, 1, 1, 1, 'o10v1', 3.14)

TEST_SESSION [10]: wago_group.get('foh2ctrl')
         Out [10]: [1, 1, 1, 1]

TEST_SESSION [11]: wago_group.get('o10v1')
         Out [11]: 3.14013671875

TEST_SESSION [12]: wago_group  
         Out [12]:  logical device    current value     wago name                description
                   ----------------  ---------------  --------------  ----------------------------------
                       foh2ctrl       [1, 1, 1, 1]    wago_simulator       4 Channel Digital Output
                       foh2pos        [0, 0, 0, 0]    wago_simulator       4 Channel Digital Input
                        esTr1            -496.4       wago_simulator  2 Channel Ktype Thermocouple Input
                        esTr2            -2765.5      wago_simulator  2 Channel Ktype Thermocouple Input
                        o10v1         3.14013671875   wago_simulator       2 Channel 4/20mA Output
```