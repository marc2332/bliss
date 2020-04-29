# White Beam Attenuator Object

The WhiteBeamAttenuator class handles the ESRF White Beam Attenuator.
The ESRF White Beam Attenuators are Icepap driven coper poles with sevaral
holes/filters.
Each attenuator pole has positive/negative limit switch and a home switch
active for each filter. The configuration procedure tries to find
the home switchwes and set the position of each filetr at the middle of the
home switch position.

The configuration is defined in .yml file, but can also be changed/removed
interactively. All the changes are saved in the corresponding .yml file.

A hook to the Frontend object is optional: if given no movement of the attenuator
will be possible when the frontend (a TangoShutter) is not on a state considered safe.


## YAML configuration example


```yaml
class: 
plugin: bliss
name: wba
attenuators:
    - attenuator: $wba_Al
    - attenuator: $wba_Mo
    - attenuator: $wba_Cu
frontend: $frontend
```

!!! warning "attenuator"
Each *attenuator* is confugured as [MultiplePosition object](config_mp.md).
