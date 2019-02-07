# Energy and Wavelength Calculation Motor

Calculate the energy [keV] and the wavelength [Angstrom] from angle [deg] or
angle [deg] from energy [keV] or wavelength [Angstrom].

Bragg's law based calculation or linear interpolation using a look-up table (LUT) give the result values.

### Example YAML configuration file ###
```yaml
  class: EnergyWavelength
    lut: /users/blissadm/local/beamline_configuration/misc/energy.lut
    axes:
        -
            name: $mono
            tags: real monoang
        -
            name: energy
            tags: energy
            dspace: 3.1356
            low_limit: 7000
            high_limit: 17000
            unit: eV  (or keV)
        -
            name: wl
            description: monochromtor wavelength
            tags: wavelength
```
The plugin for this controller is **emotion**.

The predefined tags correspond to:
*  monoang: alias for the real monochromator motor
*  energy: energy calculated axis alias
*  wavelength: wavelength calculated axis alias

The ***dspace*** is a setting and as such can be changed on the fly. It is only
set when the Brag's law is used for calculations.

If using a look-up table instead, the file should contain two columns. The first
is the energy and the second is the angle, if possible in increasing order.
The energy can only be specified in eV or keV. As there is no calculation involved,
the units of the angle can be any, convenient for the usage.

Example of a file (here energy in eV):
```
...
12000.0 1.0320
12100.0 1.0240
12200.0 1.0160
12300.0 1.0080
12400.0 1.0000
12500.0 0.99200
12600.0 0.98400
...
```