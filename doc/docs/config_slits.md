# Slits configuration

This chapter presents a typical usage of BLISS to configure and test
standard slits.

The example is based on configuration of secondary slits of ID21.

To ease readability, the configuration of only one pair of blade is
described here, but the example can easily be extended to 2 pairs.

### Real motors

First part of the file is the configuration of **real motors**. In the
case of the slits of ID21, the real motors are driven by Icepap.
[Icepap configuration](config_icepap.md) gives full details of Icepap
motors configuration.

* Note the negative sign to fix cabling choice: user convention is
to be positive when *opening* slits
* NB: `name` field is mandatory for Beacon Web Config tool to
recognize device as a motor.

        -
          controller:
            class: IcePAP
            host: iceid219
            name: secondary_blades
            axes:
                -
                    name: ssf
                    address: 23
                    steps_per_unit: -1000     <--- negative sign.
                    velocity: 1
                    acceleration: 8
                    backlash: 0.05
                -
                    name: ssb
                    address: 24
                    steps_per_unit: -1000
                    velocity: 1
                    acceleration: 8
                    backlash: 0.05


### Virtual axes

Second part is the configuration of new **virtual axes**  based on **real axes**.

* The **role** of each blade is defined using the `tags` keyword
    - `real` means the axis is a real motor, declared elsewhere
    - `front`, `back`, `hgap`, `hoffset` are specifiers for each axis
* The plugin is not specified in `secondary_slits.yml`, because a
  `__init__.yml` with `plugin: emotion` already exists in the directory
* `slit_type`: can be `horizontal` or `vertical` or `both` (default value)

        -
          controller:
            class: slits
            name: secondary_slits
            slit_type: horizontal
            axes:
                -
                    name: $ssf  <----------  The existing 'ssf' axis,
                    tags: real front  <----  has got the role of *real front* axis.
                -
                    name: $ssb
                    tags: real back
                -
                    name: sshg <------------ The (new) virtual axis 'sshg',
                    tags: hgap      <------- is the *horizontal gap* axis.
                    tolerance: 0.04
                -
                    name: ssho <------------ The (new) virtual axis 'ssho',
                    tags: hoffset   <------- is the *horizontal offset* axis.
                    tolerance: 0.04


![Horizontal Slits Example](img/hrz_slits_paths.svg)

