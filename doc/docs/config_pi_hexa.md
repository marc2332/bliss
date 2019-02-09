## Configuring an PI Hexapod motor controller

This chapter explains how to configure an PI Hexapod motor controller.

### Supported features

Encoder | Shutter | Trajectories 
------- | ------- | ------------ 
NO	| NO      | NO          

### Specific PI Hexapod controller parameters

* **model**: controller model either 850 or 887 (optional)

### Specific PI Hexapod axis parameters

* **channel**: X,Y,Z,U,V or W

### YAML configuration file example

```YAML
class: PI_HEXA
model: 850
serial:
  url: ser2net://lid133:28000/dev/ttyR37
axes:
- name: nnx
  channel: X
  low_limit: -0.2
  high_limit: 0.2
- name: nny
  channel: Y
  low_limit: -3.0
  high_limit: 3.0
- name: nnz
  channel: Z
  low_limit: -8.0
  high_limit: 8.0
- name: nnu
  channel: U
  low_limit: -1.0
  high_limit: 1.0
- name: nnv
  channel: V
  low_limit: -1.0
  high_limit: 1.0
- name: nnw
  channel: W
  low_limit: -2.0
  high_limit: 2.0
```