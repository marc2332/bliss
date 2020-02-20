# Tango Device Servers #

[Tango](https://tango-controls.org) is a toolkit for building distributed control systems.
It is based on the concept of distributed devices.
Tango is used at the ESRF to interface hardware on the accelerator and beamlines.
BLISS can integrate Tango devices easily using the [pytango](https://pytango.readthedocs.io/en/latest/) python binding.

In addition to being a client of Tango BLISS provides a number of Tango device servers to support
the integration of Bliss controllers in existing beamline control systems e.g. via SPEC and Tango tools.

Here is the list of servers provided by Bliss and how to configure them:

- [Axis](config_tango_axis.md)
- [Ct2](config_tango_ct2.md)
- [Gpib](config_tango_gpib.md)
- [Keithley](config_tango_keithley.md)
- [Linkamdsc](config_tango_linkamdsc.md)
- [Fuelcell](config_tango_fuelcell.md)
- [Musst](config_tango_musst.md)
- [Nanobpm](config_tango_nanobpm.md)
- [Nanodac](config_tango_nanodac.md)
- [Wago](config_tango_wago.md)
