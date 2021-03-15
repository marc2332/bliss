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
    name: d4ch
    geometry: E4CH
    axes:
    
      - name: $roby
        tags: real omega
      - name: $robu
        tags: real chi
      - name: $robz
        tags: real phi
      - name: $robz2
        tags: real tth

      - name: $mono
        tags: real energy

      - name: H
        tags: hkl_h
      - name: K
        tags: hkl_k
      - name: L
        tags: hkl_l
      - name: Q
        tags: q_q
```


## Usage



### User API