


## Applying configuration changes

To apply a change in YML configuration, use `apply_config` method of
objects with `reload=True` keyword argument:

Example : after changing velocity of **ssu** motor in YML file:

    ssu.apply_config(reload=True)

