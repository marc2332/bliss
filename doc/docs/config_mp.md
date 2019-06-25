# Multiple Positions Object

A Multiple Positions can be used to represent an actuator with many
discrete defined positions. Each discrete position is called a
*target*.

The actuator can be composed by one or more axis, so a target is a
combination of the positions of the involved axes.

Examples:

* beamstop holder with IN/OUT positions
* attenuator
* pinholes holder

It can also be used to represent targets specified by user.
example:

* to record points of interest to scan in a microscope view of a sample



## Features


## Configuration

### Multiple motors configuration example
```yaml
class: MultiplePositions
plugin: bliss
name: beamstop
positions:
    - label: IN
      description: Beamstop position IN the beam
      axes:
        - axis: $roby
          target: 2.5
          delta: 0.01
        - axis: $robz
          target: 1.0
          delta: 0.2
    - label: OUT
      description: Beamstop position OFF of the beam
      axes:
        - axis: $roby
          target: 7.5
          delta: 0.01
        - axis: $robz
          target: 4.0
          delta: 0.2
    - label: PARK
      description: Beamstop parking position
      axes:
        - axis: $roby
          target: 25.0
          delta: 0.01
        - axis: $robz
          target: 10.0
          delta: 0.2
```

### Single motor configuration example

```yaml
class: MultiplePositions
plugin: bliss
name: att1
positions:
    - label: Al3
      description: Aluminum filter 3 mmm
      axes:
        - axis: $filt1
          target: 2.5
          delta: 0.01
    - label: Al8
      description: Aluminum filter 8 mmm
      axes:
        - axis: $filt1
          target: 7.5
          delta: 0.01
```

## Usage examples:
```python

#
att1.move("Al3", wait=False)  # wait is True by default
att1.wait("Al3")

att1.status()  # display infos
  LABEL    DESCRIPTION             MOTOR POSITION(S)
* Al3      Aluminum filter 3 mm    filt1: 2.500  (± 0.010)

  Al8      Aluminum filter 8 mm    filt1: 7.500  (± 0.010)

filt1 = 2.7590

  
```


```
beamstop.status()
    LABEL    DESCRIPTION                          AXES
 * "IN"     "Beamstop position IN the beam"       roby:  2.5 (± 0.01)
                                                  robz:  1.0 (± 0.2)
   "OUT"    "Beamstop position OFF of the beam"   roby:  7.5 (± 0.01)
                                                  robz:  4.0 (± 0.2)
   "PARK"   "Beamstop parking position"           roby: 25.0 (± 0.01)
                                                  robz: 10.0 (± 0.2)
    roby = 2.5043
    robz = 1.0032
```
