## Configuring an IcePAP motor controller

This chapter explains how to configure an IcePAP motor controller.

### Supported features

Encoder | Shutter | Trajectories | Linked axes
------- | ------- | ------------ | -----------
YES     | YES     |     YES      |     YES

### Specific IcePAP controller parameters

* **host**: controller hostname or IP address

### Specific IcePAP axis parameters

* **address**: int, motor input channel
* **autopower**: bool, automatically switch on/off power on axis

### YAML configuration file example

```YAML
controller:
  class: icepap
  host: iceid2322
  axes:
      - name: mbv4mot
        address: 1
        steps_per_unit: 817
        velocity: 0.3
        acceleration: 3
      - name: camx
        address: 34
        ...
```

!!! note
    Each `controller: ` line can be prepended with `- ` to configure multiple
    controllers in the same YAML file.

!!! note
    Beacon needs the `emotion` configuration plugin for motor controller
    YAML files interpretation.

    It is common to add an **__init__.yml** file with: `plugin: emotion`
    in the top directory of motors configuration YAML files. Another
    possibility is to add `plugin: emotion` directly in each motor controller
    YAML configuration file.

### Encoder configuration

Encoders directly plugged in the IcePAP controller can be configured directly
in the YAML configuration file.

!!! note
    An encoder can be defined on its own (`Encoder` object), or can be associated
    to an axis to add some extra checks when motion is done: for example, an exception
    can be raised if final position does not correspond to encoder position.

#### Specific IcePAP encoder parameters

* **type**: to set which encoder to read.
    * `ENCIN`: rear incremental encoder
    * `ABSENC`: rear SSI interface
    * `INPOS`: front panel encoder
    * `MOTOR`: electrical phase of the motor
    * `AXIS`: nominal axis position
    * `SYNC`: backplance SYNC input register
* **address**: encoder input channel

!!! note
    See icepap documentation for more info.
    http://wikiserv.esrf.fr/bliss/index.php/ICEPAP#Documentation

#### Encoder YAML configuration example

```YAML
controller:
  class: icepap
  host: iceid42
  axes:
      ...
  encoders:
      - name: mbv1enc
        address: 25
        type: ENCIN
        steps_per_unit: 1e5
```

More information about **Encoder** objects [here](motion_encoder.md)

### IcePAP Shutter configuration

The IcePAP controller can be put in shutter control mode (using IcePAP
LIST MODE), to operate opening and closing of a shutter. This is done
by moving back and forth a stepper motor between two pre-defined
positions. The change is trigger by an external signal.

#### Specific IcePAP shutter configuration

* **axis_name**: name of existing IcePAP axis to move as a shutter
* **closed_position**: position of the shutter when it is closed (in user position)
* **opened_position**: position of the shutter when it is open (in user position)

#### Shutter YAML configuration example

```YAML
controller:
   class: icepap
   ...
   axes:
       - name: fshut_mot
         ...
   shutters:
       - name: fshutter
         axis_name: fshut_mot
         closed_position: 0
         opened_position: 1
```

More information about **Shutter** objects [here](using_shutter.md)

### Linked axis configuration

IcePAP controller can link several axes together, creating a new virtual axis
managed directly by the controller itself. A *linked axis* applies motions to
underlying linked motors. Linked motors are considered as *real* (as opposed to
the virtual axis).

!!! note
    **icepapcms** has to be used to create a linked axis in the controller

#### Specific IcePAP linked axis configuration

* **class** for axis has to be `LinkedAxis`
* **address** is the *name* of the linked axis, has defined with **icepapcms**

### Linked axis YAML configuration example

```YAML
controller:
    class: icepap
    host: icebcu21
    axes:
      ...
      - name: linked_axis1
        address: linked_axis_name
        class: LinkedAxis
        steps_per_unit: 200
        velocity: 10
        acceleration: 20
```
