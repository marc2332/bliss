# Cyberstar configuration

Cyberstar is a family of Single Channel Analyser powersupply for Ion-chamber SCA.
This controller supports models X1000, PPU5CH, CS96MCD, X2000 and X20005CH.

Control communication is only via serial-line RS232 and modules can be chained (so-called daisy-chain) on the same serial cable.

The powersupplies provide an SCA output TTL, which is typically integrated via a counter/timer board like the P201 ESRF board.

The BLISS controller provide a SoftAxis to scan the SCA voltage window. 

The 5 channels models accept an additional configuration parameter to specify the module channel. See the example below for more details.


## Example Configuration
```yaml
-   class: Cyberstar
    module: regulation.powersupply.cyberstar
    model: X20005CH
    timeout: 3
    serial:
      url: ser2net://lid221:28000/dev/ttyRP0
    daisy_chain:
      - name: cyber1
        module_address: 0   # <== identify the module in the serial line 
        module_channel: 1   # <== identify the channel on the cyberstar module (for PPU5CH and X20005CH only )
        axis_name: cylow1
      - name: cyber2
        module_address: 0
        module_channel: 2
        axis_name: cylow2
      - name: cyber3
        module_address: 0
        module_channel: 3
        axis_name: cylow3
      - name: cyber4
        module_address: 0
        module_channel: 4
        axis_name: cylow4
      - name: cyber5
        module_address: 0
        module_channel: 5
        axis_name: cylow5

-   class: Cyberstar
    module: regulation.powersupply.cyberstar
    model: X2000
    timeout: 3
    serial:
      url: ser2net://lid221:28000/dev/ttyRP4
    daisy_chain:
      - name: cyber11
        module_address: 10
        axis_name: cylow11
```

## Usage:

Here is an example from ESRF ID22 beamline, where two X20005CH and one X2000 are configured.

```python
CYBERSTAR [26]: cyber1
      Out [26]: name: cyber1
                com:  Serial[ser2net://lid221:28000/dev/ttyRP0]
                module_address: 0
                module_channel: 1
                sca_low         = 3.8800V  (range=[0, 4])
                sca_up          = 4.0000V  (range=[0, 4])
                sca_window_size = 0.1000V
                gain            = 70.0  %  (range=[0, 100])
                peaking_time    = 50    ns (range=[50, 100, 300, 1000])

CYBERSTAR [27]:

CYBERSTAR [25]: wa()
Current Positions: user
                   dial

  cylow1[V]    cylow2[V]    cylow3[V]    cylow4[V]    cylow5[V]    cylow6[V]    cylow7[V]    cylow8[V]    cylow9[V]
-----------  -----------  -----------  -----------  -----------  -----------  -----------  -----------  -----------
    3.88000      1.60000      1.39000      1.60000      1.48000      1.69000      1.08000      1.48000      1.48000
    3.88000      1.60000      1.39000      1.60000      1.48000      1.69000      1.08000      1.48000      1.48000

  cylow10[V]    cylow11[V]
------------  ------------
     1.69000       0.99000
     1.69000       0.99000



CYBERSTAR [2]: cyber1.sc
                         sca_low
                         sca_up
                         sca_window_size

```
