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

## Configuration

In this paragraph, a typical session of test and initial configuration
of slits is presented. A more accurate configuration would require
beam.

* Initial situation : Slits are wide open, limit switches activated.
* Set position to 0 in icepapcms
* Move to opposite limits

         CC4 [1]: sshg.move(-100)

         CC4 [2]: sshg.position()
         Out [2]: -44.67

* Define current position as 0 position

         CC4 [3]: sshg.position(0)
         Out [3]: 0.0

        CC4 [6]: ssf.position()
        Out [6]: -0.035000

        CC4 [7]: ssb.position()
        Out [7]: 0.0350000

* Offset are now set

        CC4 [9]: ssb.offset
        Out [9]: 22.335

        CC4 [10]: ssf.offset
        Out [10]: 22.335

        CC4 [11]: ssb.dial()
        Out [11]: 0.045

        CC4 [12]: ssf.dial()
        Out [12]: 0.01

        CC4 [13]: wa()
        Current Positions (user, dial)

                  ssb       ssf        sshg     ssho
             --------  --------    --------  -------
             22.38000  22.34500    46.28200  0.00350
              0.04500   0.01000    46.28200  0.00350
