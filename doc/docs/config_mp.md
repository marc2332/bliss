# Multiple Positions Object

A Multiple Positions is used to represent an object with different discrete
positions.



Examples:

* beamstop holder with IN/OUT positions
* attenuator
* pinholes holder


## Features

Multiple Positions Object can also be used to represent targets specified by
user, e.g. to record points of interest to scan in a microscope view of a
sample.


## Configuration

Each *position* is defined by *label*, *targets* and optionally a *description*.

Each target consists of *axis*, it's *destination*.

Additional *tolerance* of the destination can be defined.

### Single motor configuration example

```yaml
class: MultiplePositions
plugin: bliss
name: att1
positions:
    - label: Al3
      description: Aluminum filter 3 mmm
      target:
        - axis: $filt1
          destination: 2.5
          tolerance: 0.01
    - label: Al8
      description: Aluminum filter 8 mmm
      target:
        - axis: $filt1
          destination: 7.5
          tolerance: 0.01
```

### Multiple motors configuration example
```yaml
class: MultiplePositions
plugin: bliss
name: beamstop
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
      description: Beamstop position OFF of the beam
      target:
        - axis: $roby
          destination: 7.5
          tolerance: 0.01
        - axis: $robz
          destination: 4.0
          tolerance: 0.2
    - label: PARK
      description: Beamstop parking position
      target:
        - axis: $roby
          destination: 25.0
          tolerance: 0.01
        - axis: $robz
          destination: 10.0
          tolerance: 0.2
```

## Usage examples:
```python

att1.move("Al3", wait=False)  # wait is True by default
att1.wait("Al3")

att1.status()  # display infos
  LABEL    DESCRIPTION             MOTOR POSITION(S)
* Al3      Aluminum filter 3 mm    filt1: 2.500  (± 0.010)

  Al8      Aluminum filter 8 mm    filt1: 7.500  (± 0.010)

filt1 = 2.4590
```


```
beamstop.status()
    LABEL    DESCRIPTION                          MOTOR POSITION(S)
 * "IN"     "Beamstop position IN the beam"       roby:  2.5 (± 0.01)
                                                  robz:  1.0 (± 0.2)
   "OUT"    "Beamstop position OFF of the beam"   roby:  7.5 (± 0.01)
                                                  robz:  4.0 (± 0.2)
   "PARK"   "Beamstop parking position"           roby: 25.0 (± 0.01)
                                                  robz: 10.0 (± 0.2)
    roby = 2.5043
    robz = 1.0032
```

example to create a new positison:

```python
DEMO [2]: beamstop.create_position('HALF_IN', [(roby, 4),(robz, 5)], "half in half out")

DEMO [3]: beamstop.status
  LABEL      DESCRIPTION                          MOTOR POSITION(S)
  IN         Beamstop position IN the beam        roby: 2.500  (± 0.010)
                                                  robz: 1.000  (± 0.200)

  OUT        Beamstop position OUT of the beam    roby: 3.500  (± 0.010)
                                                  robz: 2.000  (± 0.200)

  PARK       Beamstop in safe position            roby: 1.500  (± 0.010)
                                                  robz: 0.000  (± 0.200)

  HALF_IN    half in half out                     roby: 4.000  (± 0.000)
                                                  robz: 5.000  (± 0.000)

roby = 0.0000
robz = 0.0000

```
