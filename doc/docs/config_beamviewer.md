# Standard beamviewer (EBV: ESRF Beam Viewer)

![Screenshot](img/ebv.svg)

see also: http://wikiserv.esrf.fr/bliss/index.php/Bvb

These beamviewers visualise the various types of x-ray beam (white, pink and
monochromatic) into the visible spectrum, using a scintillator, a camera and
associated software to provide the beam shape and relative power
intensities. The maximum accommodated beam size (or potential beam movement) is
10mm x 10mm for the standard beamviewers.

ESRF "Standards" beamviewers (EBV) are composed by:

* a Control Box (ISG made)
* a fixed giga-ethernet basler camera+lens
    * powered by the Control box
* an extractable head that can be moved in or out of the beam (called *screen*)
    * pneumatic-mounted mirror+scintillator
    * scintillator
        * diamond for white beam
        * YAG for monochromatic beam
        * Energy dependent for pink beam
* a diode read by novelec module providing an output in frequency.
* a LED that can be swiched ON and OFF.
* optionnaly a foil to attenuate beam (on MX beamlines)

## Usage
Usage of an EBV is described here: [Beamviewer Usage](using_beamviewer.md).


## Control

Control is implemented using 2 bliss objects: 

* **EBV** bliss object controls the wago box (screen, led, foil, diode)
* **LIMA** bliss object controls the basler camera and the associated BPM
  counters computed on images

## Wagobox modules

Two type of wago box exist:

* 1-EBV wagobox able to control only one EBV :
    - *750-436* : 8-channel digital input; 24VDC
    - *750-530* : 8-channel digital output; 24 VDC; 0.5 A
    - *750-479* : 2-channel analog input module (ADC)

* 2-EBV wagobox able to control up to 2 EBV:
    - *750-436* : 8-channel digital input; 24VDC
    - *750-530* : 8-channel digital output; 24 VDC; 0.5 A
    - *750-530* : 8-channel digital output; 24 VDC; 0.5 A
    - *750-479* : 2-channel analog input module (ADC)

If the EBV has a foil to attenuate beam (MX case), two additionnal wago modules
are added:

- *750-436* : 8-channel digital input; 24VDC
- *750-504* : 4 Channel Digital Output


## Configuration

#### Configuration example
```
plugin: bliss                 (mandatory)
name: mywbv                   (mandatory)
class: EBV                    (mandatory)
modbustcp:                    (mandatory)
    url: wcidxxa              (mandatory)
single_model: False
has_foil: False
channel: 0
counter_name: mydiode
```

`modbustcp / url` defines the wago control box host as in standard wago
controller.

#### Configuration optionnal parameters

* `single_model`
    - default value : `False`
    - define which model of wago is used : if `single_model` is `True`, the wago
      box is a 1-EBV model otherwise it is 2-EBV model. Note that some 2-EVB
      models can be installed even if it controls only one BVB.

* `has_foil`
    - default value : `False`
    - define if a foil attenuator can be controlled or not

* `channel`
    - default value : `0`
    - in case of a 2-EBV wago box model, defines which EBV is used : 1st one or
      2nd one.

* `counter_name`
    - default value : `diode`
    - counter name of diode current reading when EBV is used in counts/scans


## Lima BPM counters

Recent Lima (⩾ 1.9.2) has a built-in BPM device server (no need for an extra
Tango server).

The BPM counter controller is integrated in BLISS as a Lima object.


Example of configuration:
```yaml
name: lima_bv1
plugin: bliss
class: Lima
tango_url: id42/limaccds/bv1
```
!!! note
    In case counter names are not appropriate, they can be changed using aliases.

The BPM counters are now available:

```python
SESSION_SXM [3]: ct(0.1, lima_bv1.counters)

    Activated counters not shown: image

    Wed Dec 04 17:04:18 2019
     acq_time =   0.13225 ( 1.3225/s)
       fwhm_x =   0.0
       fwhm_y =  31.8288  ( 318.2882/s)
    intensity =  26.8     ( 268.0/s)
            x =  -1.0     ( -10.0/s)
            y = 920.2379  ( 9202.3790/s)
            Out [3]: Scan(number=67, name=ct,
                     path=/data/id42/inhouse/session_sxm/data3.null)
```

Inline info of lima bpm prints info about:
* the associated camera
* BPM counters available

```python
DEMO [1]: lima_bv1
 Out [1]: Basler - acA1300-30gm (Basler) - Lima Basler

          Image:
          bin = [1 1]
          flip = [False False]
          height = 966
          roi = <0,0> <1296 x 966>
          rotation = rotation_enum.NONE
          sizes = [   0    2 1296  966]
          type = Bpp12
          width = 1296

          Acquisition:
          expo_time = 0.1
          mode = mode_enum.SINGLE
          nb_frames = 1
          status = Ready
          status_fault_error = No error
          trigger_mode = trigger_mode_enum.INTERNAL_TRIGGER_MULTI

          ROI Counters:
          [default]

          *** no ROIs defined ***

          COUNTERS:
              name       shape    type
              ---------  -------  ------------
              image      2d       unknown type
              acq_time   0d       float
              intensity  0d       float
              x          0d       float
              y          0d       float
              fwhm_x     0d       float
              fwhm_y     0d       float
```