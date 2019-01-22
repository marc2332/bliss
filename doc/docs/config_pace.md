# PACE (Pressure Automated Calibration Equipment) Controller
Acessible via tcp sockets, using SCPI protocol instructions.

Models: 5000 (one channel) and 6000 (2 channels).

Manifacturer: General Electric Measurement & Control

### Example YAML configuration file ###
```yaml
  controller:
   class: pace
   url: 'id29pace1:5025' #host:port
   outputs:
     - name: pmbpress
       low_limit: 0
       high_limit: 2.1
       default_unit: 'BAR'
       channel: 1            # for 6000 only
```
The plugin for this controller is temperature.
```yaml
   plugin: temperature
```
should either be in \_\_init__.yml in the same directory or added to the above configuration.

## further reading at ESRF
*  [PACE User Manual](https://www.gemeasurement.com/sites/gemc.dev/files/pace5000_pace6000_user_manual_k0443_rev_b.pdf)
*  PACE SCPI MAnual /segfs/bliss/docs/PACE/PACE_SCPI_Manual_k0472.pdf
