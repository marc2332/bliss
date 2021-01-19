
## KB Mirror control and focusing


A [Kirkpatrick-Baez mirror](https://en.wikipedia.org/wiki/Kirkpatrick-Baez_mirror),
or KB mirror for short, focuses beams of X-rays by reflecting them at grazing
incidence off a curved surface, usually coated with a layer of a heavy metal. It
is named after Paul Kirkpatrick and Albert Baez (father of Joan Baez), the
inventors of the X-ray microscope.

Although X-rays can be focused by compound refractive lenses, these also reduce
the intensity of the beam and are therefore undesirable. KB mirrors, on the
other hand, can focus beams to small spot sizes with minimal loss of
intensity. Typically they are used in pairs - one to focus horizontally and one
for vertical focus. When the horizontal and vertical focuses coincide, the X-ray
beam is focused to a small spot.


This chapter presents KB mirror control and focusing with BLISS.
These features are implemented as a `KbController` class offering:

* a focusing procedure (`KbFocus`)
* a calculation motor (`KbMirrorCalcMotor`)

### Configuration example


```yaml
- plugin: bliss
  package: bliss.controller.kb
  class: KbController
  name: kb
  saving: True               <- Save or not data during slits scans
  focus:
    - device: $hfocus
    - device: $vfocus

- plugin: bliss
  package: bliss.controller.kb
  class: KbFocus
  name: hfocus
  offset_motor: $kbho
  offset_start: 0.0          <- Start position of the iterative dscan
  bender_upstream: $kbh1
  bender_downstream: $kbh2
  bender_increment: 20       <- def. val., can be set when calling focus
  counter: $diagbpm.bpm.x

- plugin: bliss
  package: bliss.controller.kb
  class: KbFocus
  name: vfocus
  offset_motor: $kbvo
  offset_start: 0.0
  bender_upstream: $kbv1
  bender_downstream: $kbv2
  bender_increment: 20
  counter: $diagbpm.bpm.y

# KB Motors
- plugin: emotion
  class: KbMirrorCalcMotor
  name: kbmirror
  # distance in mm
  distance: 85          <- distance between the 2 rotation points in mm
  axes:
    - name: $kbvrot      <- Main rotation
      tags: real rot
    - name: $kbvecrot    <- eccentric rotation
      tags: real ecrot
    - name: kbvry       <- tilt rotation
      tags: tilt
    - name: kbvtz       <- vertical/horizontal translation
      tags: height

- plugin: emotion
  class: Kb2LegCalcMotor
  name: uxasx
  axes:
    - name: $tx1
      tags: real leg1
    - name: $tx2
      tags: real leg2
    - name: uxastx
      tags: trans

- plugin: emotion
  class: Kb3LegCalcMotor
  name: uxasz
  axes:
    - name: $tz1
      tags: real leg1
    - name: $tz2
      tags: real leg2
    - name: $tz3
      tags: real leg3
    - name: uxastz
      tags: trans

```
