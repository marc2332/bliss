# Diffractometer

## Description

This module is based on the F.Picca's [HKL library](https://github.com/picca/hkl) [(documentation)](https://people.debian.org/~picca/hkl/hkl.html).

The purpose of the library is to factorize single crystal diffraction angles computation for different kind of diffractometer geometries.

This module provides:

* Commands to interact with diffractometers
* Select between various geometries and engines
* Move in reciprocal space
* Perform scans on HKL values
* Axis freezing and constrains
* Spec-like end-user API
* Pseudoaxes (psi, eulerians, q, ...)
* UB matrix computation:
    - busing & Levy with 2 reflections
    - simplex computation with more than 2 reflections using the GSL library.
    - Eulerians angles to pre-orientate your sample.
* Crystal lattice refinement



## Configuration

```yaml
- controller:
    plugin: diffractometer
    name: zaxis 
    geometry: ZAXIS
    axes:

      - name: $roby
        tags: real mu
      - name: $robu
        tags: real omega
      - name: $robz
        tags: real delta
      - name: $robz2
        tags: real gamma

      - name: Hz
        tags: hkl_h
      - name: Kz
        tags: hkl_k
      - name: Lz
        tags: hkl_l
      - name: Qz
        tags: q2_q
      - name: Az
        tags: q2_alpha
```


## Usage

Use `from bliss.common.hkl import *` in order to import all spec-like commands.

```python
TEST_SESSION [1]: z=config.get('zaxis')
TEST_SESSION [2]: z
         Out [2]: GEOMETRY : ZAXIS
                  ENERGY : 25.39998811784638 KeV
                  PHYSICAL AXIS :
                   - mu       [roby    ] =   0.1000 Degree limits= (0.0,180.0)
                   - omega    [robu    ] =  58.8578 Degree limits= (-180.0,180.0)
                   - delta    [robz    ] =  11.6504 Degree limits= (-180.0,180.0)
                   - gamma    [robz2   ] =  13.0749 Degree limits= (-180.0,180.0)

                  MODES :
                   --engine--      - --mode--                       { --parameters-- }
                   HKL        [RW] * zaxis
                   HKL        [RW]   reflectivity
                   Q2         [RW] * q2
                   QPER_QPAR  [RW] * qper_qpar                      {'x': 0.0, 'y': 1.0, 'z': 0.0}
                   TTH2       [RW] * tth2
                   INCIDENCE  [RO] * incidence                      {'x': 0.0, 'y': 1.0, 'z': 0.0}
                   EMERGENCE  [RO] * emergence                      {'x': 0.0, 'y': 1.0, 'z': 0.0}

                  PSEUDO AXIS :
                   --engine-- - --name--   [-motor- ]
                   HKL        - h          [Hz      ] =   1.0000
                   HKL        - k          [Kz      ] =   1.0000
                   HKL        - l          [Lz      ] =   6.0000
                   Q2         - q          [        ] =   3.9208
                   Q2         - alpha      [        ] =  40.7994
                   QPER_QPAR  - qper       [        ] =   2.9344
                   QPER_QPAR  - qpar       [        ] =   2.6003
                   TTH2       - tth        [        ] =  17.5202
                   TTH2       - alpha      [        ] =  40.7994
                   INCIDENCE  - incidence  [        ] =   0.1000
                   INCIDENCE  - azimuth    [        ] =   0.0000
                   EMERGENCE  - emergence  [        ] =  13.0749
                   EMERGENCE  - azimuth    [        ] =   0.0000

TEST_SESSION [3]: z.lattice
         Out [3]: (4.765, 4.765, 12.994, 90.0, 90.0, 119.99999999999999)

TEST_SESSION [4]: z.energy
         Out [4]: 25.39998811784638

TEST_SESSION [5]: z.wavelength
         Out [5]: 0.488127

TEST_SESSION [13]: z.or0 = (1.0, 1.0, 3.0, 0.1, 53.2179, 11.7265, 6.5295)
TEST_SESSION [13]: z.or1 = (2.0, -1.0, 3.0, 0.1, -6.761, 11.7369, 6.5328)
TEST_SESSION [21]: z.reflist
         Out [21]: ((1.0, 1.0, 3.0, 0.1, 53.2179, 11.7265, 6.5295), (2.0, -1.0, 3.0, 0.1, -6.761, 11.7369, 6.5328))

TEST_SESSION [22]: z.hkl
         Out [22]: (0.9999975768216317, 0.9999962805126815, 6.000014154279113)

TEST_SESSION [23]: z.pos
         Out [23]: (0.1, 58.85779999999999, 11.6504, 13.0749)

TEST_SESSION [28]: z.move_hkl(1,1,3)
Moving Hz from 1 to 1
Moving Kz from 1 to 1
Moving Lz from 6. to 3
Moving robu from 58.8578 to 53.206
Moving robz from 11.6504 to 11.7084
Moving robz2 from 13.0749 to 6.5193
      roby       robu       robz      robz2
    0.1000    53.2060    11.7084     6.5193

TEST_SESSION [29]: z.pos
         Out [29]: (0.1, 53.206, 11.7084, 6.5193)

TEST_SESSION [24]: z.freeze(0.1)
Freeze roby [mu] to 0.1000

TEST_SESSION [25]: z.check_hklscan((1,1,3), (1,1,6), 10)
       H        K        L       roby       robu       robz      robz2
  1.0000   1.0000   3.0000     0.1000    53.2060    11.7084     6.5193
  1.0000   1.0000   3.3333     0.1000    53.6470    11.7050     7.2419
  1.0000   1.0000   3.6667     0.1000    54.1340    11.7016     7.9656
  1.0000   1.0000   4.0000     0.1000    54.6671    11.6977     8.6907
  1.0000   1.0000   4.3333     0.1000    55.2466    11.6932     9.4171
  1.0000   1.0000   4.6667     0.1000    55.8731    11.6879    10.1451
  1.0000   1.0000   5.0000     0.1000    56.5470    11.6812    10.8747
  1.0000   1.0000   5.3333     0.1000    57.2686    11.6731    11.6061
  1.0000   1.0000   5.6667     0.1000    58.0387    11.6629    12.3395
  1.0000   1.0000   6.0000     0.1000    58.8578    11.6504    13.0749

TEST_SESSION [26]: from bliss.common.hkl import *
TEST_SESSION [27]: hklscan((1,1,3), (1,1,6), 10, 0.1, diode)
   Thu Mar 25 15:04:37 2021: Scan(number=104, name=hklscan, path=/tmp/scans/test_session/data.h5)

   Took 0:00:04.764423[s]

         Out [27]: Scan(number=104, name=hklscan, path=/tmp/scans/test_session/data.h5)

```
