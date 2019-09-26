# Transfocator #

A Transfocator is a tunable X-ray focusing apparatus based on compound refractive lenses.
By varying the number of lenses in the beam, the energy focused and the focal length can be varied continuously throughout a large range of energies and distances.

## Underlining Control ##

Transfocators are controlled through a Wago PLC's output module that activates pneumatic actuators.
The state is read through Wago PLC's input module: every lens and pinhole has two limit switches that read IN or OUT state.

## Configuration ##

The configuration should define in particular the number of lenses and the number of pinholes.
Both lenses and pinholes have a binary state in the sense that they can only be inserted or removed.

### Example YAML configuration file, automatic layout ###

```yaml
name: tfmad
class: transfocator
controller_ip: 160.103.50.57
lenses: 7
pinhole: 2
safety: True
```

The number of lenses is mandatory.
The number of pinholes vary from 0 to 2, consider the following cases:

* If `pinhole: 1` we assume that the pinhole is at the beginning
* If `pinholes: 2` we assume that pinholes are one at the beginning and one at the end

If `safety: True` a pinhole is forced in whenever a lens is in.
Omitting safety parameters equals to `safety: False`.

### Alternative YAML configuration file, specifying layout ###

```yaml
name: tf
class: Transfocator
controller_ip: wcid232b
# beam from the left
layout: P L L L L X X X P
```

`layout` is a string separated by spaces, describing pinholes (`P`) and lenses (`L`)
within the transfocator, with incident beam coming from **left to right**.
`X` means: empty slot. 

### Additional settings

* `read_mode`: 0 (default) means **first transfocator lens in beam state switch is wired first in Wago**
    - any other value means the opposite, that the first transfocator state switch is wired last 
* `cmd_mode`: 0 (default) means **first transfocator lens action switch is wired first in Wago** 
    - any other value means the opposite, that the first transfocator action switch is wired last 
