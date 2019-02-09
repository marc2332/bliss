# Transmission
get/set transmission factor as function of the filters, mounted on a ESRF
standard monochromatic attenuator and the energy (fixed or tunable).
It may not be possible to set the exact factor required.


### Example YAML configuration file ###
```yaml
  controller:
   class: transmission
   name: transmission
   matt: $matt
   energy: $energy (or energy: 12.7)
   datafile: "/users/blissadm/local/beamline_control/configuration/misc/transmission.dat"
```
The plugin for this controller is bliss.

The datafile, required for calculations has first column the energy, next
columns are the corresponding transmission factors for each attenuator blade and
minimum and maximum indexes position.

Example for fixed energy:
```
#MIN_ATT_INDEX = 1
#MAX_ATT_INDEX = 9
#
12.812 100.00 72.00 92.00 3.50 18.00 30.00 42.70 58.18 68.0
```
and for tunable energy:
```
#MIN_ATT_INDEX = 1
#MAX_ATT_INDEX = 13
#
20.0100  100      100      100       94.4431  94.4431  77.7768  66.6651  94.4431
  77.7768  55.5558  38.8872  11.1093  11.1093
19.4979  100      100      100      100       86.3638  77.2724  63.6362  86.3638
  77.2724  50       31.8172   9.0896   9.0896
18.9986  100      100      100       96.1545  92.3073  84.6147  57.6927  88.4618
  84.6147  46.1529  34.6147   7.6911   7.6911
...
```