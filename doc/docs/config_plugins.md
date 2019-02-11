# Objects instantiation

The `config.get(<object_name>)` method returns a live object from the configuration:

```py
>>> from bliss.config.static import get_config
>>> config = get_config()
>>> obj = config.get("my_object_name") #my_object_name has to be one of config.names_list
```

## Configuration plugins

Every object in the configuration is associated with a *configuration
plugin*. The role of the configuration plugin is to instantiate the object
from the YAML mappings. It figures out:

* which class (or controller) needs to be instantiated
* which parameters have to be passed to the constructor
* which objects are finally exported
    * one, in case of a single class,
    * between 1 and 'N' for a controller

Beacon supports the following plugins:

* `default`, converts YAML data into a Python dictionary
    * if an object has no plugin information, this is the default
* `bliss`, general-purpose control objects
* `emotion`, axes, encoders, shutters and motor controllers configuration
* `temperature`, inputs, outputs, control loops for temperature controllers
* `session`, to configure `Session` objects
* `diffractometer`, to configure diffractometers

Configuration plugins are Python files located in `bliss.config.plugins`. The
name of the plugin Python module must correspond to the plugin name.

### Writing a configuration plugin

Each plugin module has to define a `create_objects_from_config_node` function,
that receives:

* the static configuration singleton
* the Node object that corresponds to the object configuration

#### `bliss` plugin example

The **bliss** plugin creates an object from a YAML mapping.

* it relies on the `find_class` utility function, to determine which class needs
to be instantiated
    - it looks for a `class` item in the object configuration, and tries to find
      the corresponding Python module in `bliss.controllers`. The module filename is
      expected to be the lower-case version of the class name. In case this basic mechanism
      is not enough to find the class definition module, it is possible to specify it
      explicitly with the `module:` item. In case the module cannot be found under
      `bliss.controllers`, it is also possible to specify the `package:` item.
* it uses the `replace_reference_by_object` helper to replace YAML items starting with
the dollar sign (`$`) with an instance of the corresponding object from the
configuration
    - the referenced objects are set as attributes of the instance
* the name of the object and the configuration is passed to the class
constructor. Each class depending on the `bliss` plugin has its own rules to interpret
the different YAML items: one has to refer to the documentation to know how to configure
each object
* finally, the created object is returned in a dictionary indexed by the object name

```py
from bliss/config.plugins.utils import find_class, replace_reference_by_object

def create_objects_from_config_node(config, cfg_node):
    item_cfg_node = cfg_node.deep_copy()
    klass = find_class(item_cfg_node)

    item_name = item_cfg_node["name"]
    referenced_objects = dict()

    replace_reference_by_object(config, item_cfg_node, referenced_objects)

    o = klass(item_name, item_cfg_node)

    for name, object in referenced_objects.items():
        if hasattr(o, name):
            continue
        else:
            setattr(o, name, object)

    return {item_name: o}
```

!!! note
    When grouping similar configuration information in a directory, it is
    quite useful to specify the plugin in a `__init__.yml` file:
    `plugin: <plugin_name>`


## Configuration tool UI panels

The other role of configuration plugins is to define a HTML render function for
generating graphical configuration panels for the Beacon configuration web
application, depending on the kind of object instantiated by the plugin.

Currently, the bliss plugin provides a special User Interface (UI) for P201/CT2 counting
card configuration.
Similarly the emotion plugin provides a special UI for IcePAP motor
controller configuration.
