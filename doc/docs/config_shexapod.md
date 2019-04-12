## Configuring a Symetrie Hexapod motor controller

This chapter explains how to configure a Symetrie Hexapod motor controller.

### Supported features

Encoder | Shutter | Trajectories 
------- | ------- | ------------ 
NO	| NO      | NO          

### Specific Symetrie Hexapod controller parameters

* **version**: 1 or 2 (optional, should be detected automaticaly
but recommanded)

### Specific Symetrie Hexapod axis parameters

* **role**: virtual axis in 3D -> 3 translations and 3 rotation.
  * tx: X translation
  * ty: Y translation
  * tz: Z translation
  * rx: Rotation on X
  * ry: Rotation on Y
  * rz: Rotation on Z

### YAML configuration file example

```YAML
class: SHexapod
version: 2          # (optional)
tcp:
    url: id99hexa1
axes:
    - name: h1tx
      role: tx
      unit: mm
    - name: h1ty
      role: ty
      unit: mm
    - name: h1tz
      role: tz
      unit: mm
    - name: h1rx
      role: rx
      unit: deg
    - name: h1ry
      role: ry
      unit: deg
    - name: h1rz
      role: rz
      unit: deg
```