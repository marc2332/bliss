# Multiple Positions Object

The MultiplePosition class handles multiple predefined discrete motor positions
equipment. As an example, such equipment can be:

* beamstop holder with IN/OUT positions
* multi filter attenuator
* pinholes holder
* visible light filters

The positions are defined in .yml file, but can also be added/changed/removed
interactively. All the changes are saved in the corresponding .yml file.

The class has axis-like methods: **move**, **stop**, **wait** and properties:
**position**, **state**, but also specific methods: **status**,
**create_position**, **update_position**,
**remove_position** and properties: **motors**, **motor_names**, **motor_objs**.


## Features

MultiplePositions object can be used to represent user defined positions,
e.g. to register points of interest to scan in a microscope view of a sample.


## Configuration

Each **position** is defined by **label**, **target** and optionally a
**description**.

The *label* is an unique string to define the position.

!!! warning "label"
    Label must be a valid python identifier, ie: combination of letters
    in lowercase (a to z) or uppercase (A to Z) or digits (0 to 9) or an underscore _.
    It cannot start with a digit and cannot use space or special symbols like
    !, @, #, $, % etc.


Each *target* consists of one or several **axis** (real motor) and its
**destination** (motor position) and optional **tolerance**.

In case of several motors per *position* it can be specified if the motors move
simultaneously or not - **move_simultaneous** is *True/False*. This is
used if the equipment cannot or should not move the underlying motors
simultaneously. The default value is *True*. In case of non-simultaneous move,
the order of the motors is the one of the *target* configuration.

It is allowed to not always use the same motor(s) for each position and to
have varying number of motors for different positions of the same equipment.


## YAML configuration example
### One motor per position


```yaml
class: MultiplePositions
plugin: bliss
name: att1
positions:
    - label: Al3
      description: Aluminum filter 3 mm
      target:
        - axis: $filt1
          destination: 2.5
          tolerance: 0.01
    - label: Al8
      description: Aluminum filter 8 mm
      target:
        - axis: $filt1
          destination: 7.5
          tolerance: 0.01
```

### Two motors per position
```yaml
class: MultiplePositions
plugin: bliss
name: beamstop
move_simultaneous: True
positions:
    - label: IN
      description: Beamstop position IN the beam
      target:
        - axis: $roby
          destination: 2.5
          tolerance: 0.01
        - axis: $robz
          destination: 1.0
          tolerance: 0.2
    - label: OUT
      description: Beamstop position OUT of the beam
      target:
        - axis: $roby
          destination: 7.5
          tolerance: 0.01
        - axis: $robz
          destination: 4.0
          tolerance: 0.2
    - label: PARK
      description: Beamstop in safe position
      target:
        - axis: $roby
          destination: 25.0
          tolerance: 0.01
        - axis: $robz
          destination: 10.0
          tolerance: 0.2
```

### Different motors per position
```yaml
class: MultiplePositions
plugin: bliss
name: vlight
move_simultaneous: True
positions:
    - label: yellow
      description: Yellow filter
      target:
        - axis: $light1
          destination: 2.5
          tolerance: 0.01
    - label: blue
      description: Blue filter
      target:
        - axis: $light2
          destination: 4.0
          tolerance: 0.2
        - axis: $light1
          destination: 7.5
          tolerance: 0.01
```

## Usage examples:
```python
DEMO [1]: att1
Out [1]: 'READY'

DEMO [2]: att1.move("Al3", wait=False)  # wait is True by default
DEMO [3]: att1
Out [3]: 'MOVING'
att1.wait() # blocking until motor reached the position or timeout RuntimeError

DEMO [4]: att1.status  # display infos
  LABEL    DESCRIPTION             MOTOR POSITION(S)
* Al3      Aluminum filter 3 mm    filt1: 2.500  (± 0.010)
  Al8      Aluminum filter 8 mm    filt1: 7.500  (± 0.010)

filt1 = 2.4590
```

At init, a short-cut function to move to a specific position is created using
the label as name:

```python
DEMO [2]: att1.Al8()
Moving att1 to Al8
DEMO [3]:
```

```python
DEMO [1]: beamstop
   LABEL  DESCRIPTION                         MOTOR POSITION(S)
 * IN     Beamstop position IN the beam       roby:  2.5 (± 0.01)
                                              robz:  1.0 (± 0.2)
   OUT    Beamstop position OFF of the beam   roby:  7.5 (± 0.01)
                                              robz:  4.0 (± 0.2)
   PARK   Beamstop parking position           roby: 25.0 (± 0.01)
                                              robz: 10.0 (± 0.2)
roby = 2.5043
robz = 1.0032
```

example to create a new positison:

```python
DEMO [1]: beamstop.create_position('HALF_IN',
                                   [(roby, 4),(robz, 5)],
                                   "half in half out")

DEMO [2]: beamstop
  LABEL      DESCRIPTION                          MOTOR POSITION(S)
* IN         Beamstop position IN the beam        roby: 2.500  (± 0.010)
                                                  robz: 1.000  (± 0.200)

  OUT        Beamstop position OUT of the beam    roby: 3.500  (± 0.010)
                                                  robz: 2.000  (± 0.200)

  PARK       Beamstop in safe position            roby: 1.500  (± 0.010)
                                                  robz: 0.000  (± 0.200)

  HALF_IN    half in half out                     roby: 4.000  (± 0.000)
                                                  robz: 5.000  (± 0.000)

roby = 2.5000
robz = 1.0000

```
```python
DEMO [1]: beamstop
  LABEL      DESCRIPTION                          MOTOR POSITION(S)
  IN         Beamstop position IN the beam        roby: 2.500  (± 0.010)
                                                  robz: 1.000  (± 0.200)

  OUT        Beamstop position OUT of the beam    roby: 3.500  (± 0.010)
                                                  robz: 2.000  (± 0.200)

  PARK       Beamstop in safe position            roby: 1.500  (± 0.010)
                                                  robz: 0.000  (± 0.200)

  HALF_IN    half in half out                     roby: 4.000  (± 0.000)
                                                  robz: 5.000  (± 0.000)
roby = 2.5500
robz = 1.0000

DEMO [2]: beamstop.update_position('IN')

DEMO [3]: beamstop
  LABEL      DESCRIPTION                          MOTOR POSITION(S)
* IN         Beamstop position IN the beam        roby: 2.550  (± 0.010)
                                                  robz: 1.000  (± 0.200)

  OUT        Beamstop position OUT of the beam    roby: 3.500  (± 0.010)
                                                  robz: 2.000  (± 0.200)

  PARK       Beamstop in safe position            roby: 1.500  (± 0.010)
                                                  robz: 0.000  (± 0.200)

  HALF_IN    half in half out                     roby: 4.000  (± 0.000)
                                                  robz: 5.000  (± 0.000)

roby = 2.55
robz = 1.00
```
