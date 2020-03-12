# Energy and Wavelength Calculation Motor


`EnergyWavelength` is a Calculation Motor to deal with Energy, Wavelength and
Monochromator angle.

It calculates:

* the energy (keV) and the wavelength (Angstrom) from angle (deg)
* angle (deg) from energy (keV) or wavelength (Angstrom)

The conversion can be performed either:

* using Bragg's law.
* or based on a look-up table (LUT) with linear interpolation.


This CalcMotor controller:

* uses existing motor of the angle of the monochromator
    - referenced with `monoang` flag
* creates 2 new kind of motors using flags:
    - `wavelength` (in Angstrom)
    - `energy` (in keV)

The predefined tags correspond to:

* `monoang`: alias for the real monochromator motor
* `energy`: energy calculated axis alias
* `wavelength`: wavelength calculated axis alias    ??????????????? ALIAS ???

The `dspace` is a setting and as such can be changed on the fly. It is only
set when the Brag's law is used for calculations.

If using a look-up table instead, the file should contain two columns. The first
is the energy and the second is the angle, if possible in increasing order.
The energy can only be specified in eV or keV. As there is no calculation involved,
the units of the angle can be any, convenient for the usage.

!!! note
    As `EnergyWavelength` is a `CalcController`, it uses `emotion`
    configuration plugin.

Information about the `EnergyWavelength` CalcController can be obtained with
inline shell info:

* dspace or LUT
* values of related axes

Example:
```python
DEMO [5]: e_mono
 Out [5]: AXIS:
               name (R): e_mono
               unit (R): keV
               offset (R): 0.00000
               backlash (R): 0.00000
               sign (R): 1
               steps_per_unit (R): 1.00
               tolerance (R) (to check pos. before a move): 0.0001
               limits (RW):    Low: -inf High: inf    (config Low: -inf High: inf)
               dial (RW): 10.00235
               position (RW): 10.00235
               state (R): READY (Axis is READY)
               acceleration: None
               velocity: None

          ENERGY-WAVELENGTH CALCULATION MOTOR:
                   energy axis: e_mono (  10.00235 keV)
               wavelength axis: wl_mono (   1.23955 Å)
                        dspace: 3.1356

          ENCODER:
               None
```


### Example YAML configuration file ###

With calculation using Bragg's law:
```yaml
controller:
- class: EnergyWavelength
  axes:
  - name: $mono_oh2
    tags: real monoang
  - name: energy_mono
    tags: energy
    # dspace (= Si111)
    dspace: 3.1356
    unit: keV
  - name: wl_mono
    description: monochromator wavelength
    tags: wavelength
```

With Look-up Table:
```yaml
controller:
- class: EnergyWavelength
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
