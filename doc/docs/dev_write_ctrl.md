# Writing controllers for Bliss

Bliss put no constrains on controllers classes and developers can start from scratch and define everything.
However, there are several generic mechanisms, like loading the controller from a YML configuration (plugin) or managing the controller's counters and axes, which are already defined in Bliss and which can be inherited while writing a new controller class.

## BlissController base class

As a base for the implementation of controllers, Bliss provides the `BlissController` class.
This class already implements the plugin mechanisms and is designed to ease the management of sub-objects under a top controller. 

Examples of controllers that should inherit from `BlissController` class:

- a controller of axes

- a controller with counters

- a controller with axes and counter

- a top-controller (software) managing other sub-controllers (software/hardware)


Example of the YML structure:

```yml

- plugin: generic          <== BlissController works with generic plugin
  module: custom_module    <== module of the custom bliss controller
  class: BCMockup          <== class of the custom bliss controller
  name: bcmock             <== name of the custom bliss controller  (optional)

  param_1: value           <== a parameter for the custom bliss controller (optional)

  section_1:               <== a section where subitems config can be declared (ex: 'counters') (optional) 
    - name: subitem_1      <== name of a subitem
    - name: subitem_2      <== name of another subitem of the same type

  section_2:               <== another section for another type of subitems (ex: 'axes') (optional) 
    - name: subitem_2      <== name of another subitem type

```

The signature of a `BlissController` takes a single argument `config`.
It could be a `ConfigNode` object or a standard dictionary.

```python
class BlissController(CounterContainer):
    def __init__(self, config):
```

### BlissController and subitems

A `BlissController` subitem is an object managed by the controller and which could have a name declared under a sub-section of the controller's configuration. Usually subitems are counters and axes but could be anything else (known by the controller only). 

```yml

  section_1:
    - name: subitem_1   <== a subitem using the default class (defined by the controller)
    
    - name: subitem_2   <== a subitem using a given class path (from an absolute path)
      class: bliss.foo.custom.myclass

    - name: subitem_3   <== a subitem using a given class name (default path known by the controller)
      class: myitemclass    
```

Subitems can be declared in the controller's YML configuration if they are expected to be directly imported in a user session.
If not declared in the YML, they are still accessible via the controller (see `BlissController._get_subitem(name)`).

To retrieve the subitems that can be identified as counters or axes, `BlissController` class implements the `@counters` and `@axes` properties.

The `BlissController` identifies the subitem type thanks to the name of the sub-section where the item was found (aka `parent_key`).

Also, the controller must provides a default class for each kind of `parent_key` (see `BlissController._get_subitem_default_class_name`). 

Examples:

```python
def _get_subitem_default_class_name(self, cfg, parent_key):
    if parent_key == "axes":
        return "Axis"
    elif parent_key == "encoders":
        return "Encoder"
    elif parent_key == "shutters":
        return "Shutter"
    elif parent_key == "switches":
        return "Switch"
```

or

```python
def _get_subitem_default_class_name(self, cfg, parent_key):
    if parent_key == "counters":
        tag = cfg["tag"]
        if self._COUNTER_TAGS[tag][1] == "scc":
            return "SamplingCounter"
        elif self._COUNTER_TAGS[tag][1] == "icc":
            return "IntegratingCounter"
```


The default subitem class can be overridden by specifing the `class` key in its configuration.
The class can be given as an absolute path or as a class name. 

If providing a class name the controller tries to find the item class first at its module level, else it uses a default path defined by the controller (see `BlissController._get_subitem_default_module`).

Examples:

```python
def _get_subitem_default_module(self, class_name, cfg, parent_key):
    if parent_key == "axes":
        return "bliss.common.axis"

    elif parent_key == "encoders":
        return "bliss.common.encoder"

    elif parent_key == "shutters":
        return "bliss.common.shutter"

    elif parent_key == "switches":
        return "bliss.common.switch"
```

or

```python
def _get_subitem_default_module(self, class_name, cfg, parent_key):
    if class_name == "IntegratingCounter":
        return "bliss.common.counter"
```

### Bliss controller plugin

`BlissControllers` are created from the yml configuration using the `generic` plugin. 

The controlelr class is based on the `ConfigItemContainer` base class which deals with all the mechanisms of the `generic` plugin.

Any subitem can be imported in a Bliss session with the command `config.get('name')`.

The bliss controller itself can have a name (optional) and can be imported in the session.

The plugin ensures that the controller and subitems are only created once.

The effective creation of subitems is performed by the `BlissController` itself and the plugin just ensures that the controller is always created before subitems and only once.

The `generic` plugin will also manage the resolution order of the references to other objects within the `BlissController` configuration. It handles external and internal references and allows to use a reference for a subitem name.


Example of an advanced configuration using different kind of references:

```yml

- plugin: generic
  module: custom_module       
  class: BCMockup             
  name: bcmock                

  custom_param_1: value       
  custom_param_2: $ref1       <== a referenced object for the controller (optional/authorized)

  sub-section-1:              
    - name: sub_item_1        
      tag : item_tag_1        
      sub_param_1: value      
      device: $ref2           <== an external reference for this subitem (optional/authorized)

  sub-section-2:              
    - name: sub_item_2        
      tag : item_tag_2        
      input: $sub_item_1      <== an internal reference to another subitem owned by the same controller (optional/authorized)

      sub-section-2-1:        <== nested sub-sections are possible (optional)
        - name: sub_item_21
          tag : item_tag_21

  sub-section-3 :             
    - name: $ref3             <== a subitem as an external reference is possible (optional/authorized)
      something: value

```

### Subitem creation

In order to keep the plugin as generic as possible, all the knowledge specfic to the controller is asked by the plugin to the `BlissController`. 

In particular, when the plugin needs to instantiate a subitem it will call the method `BlissController._create_subitem_from_config`. This abstract method must be implemented and must return the subitem instance.

To be able to decide which instance should be created, the method receives 4 arguments:

- `name`: subitem name
- `cfg`: subitem config
- `parent_key`: name of the subsection where the item was found (in controller's config)
- `item_class`: class of the subitem (see [BlissController and sub-items](dev_write_ctrl.md#blisscontroller-and-subitems) ).
- `item_obj`: the object instance of an item referenced in the config (None if not a reference)

If `item_class` is `None` it means that the subitem was given as a reference. 
In that case the object is already instantiated and is contained in `item_obj`.
  

Examples:

```python
@check_disabled
def _create_subitem_from_config(self, name, cfg, parent_key, item_class, item_obj=None):

    if parent_key == "axes":
        if item_class is None:  # it means that item was referenced in config, 
            axis = item_obj     # so just grab the item object provided by 'item_obj'
        else:
            axis = item_class(name, self, cfg) # instantiate the item using the given class and decide the correct signature

        # === do anything custom here ================

        self._axes[name] = axis 

        axis_tags = cfg.get("tags")
        if axis_tags:
            for tag in axis_tags.split():
                self._tagged.setdefault(tag, []).append(axis)

        if axis.controller is self:
            set_custom_members(self, axis, self._initialize_axis)
        else:
            # reference axis
            return axis

        if axis.controller is self:
            axis_initialized = Cache(axis, "initialized", default_value=0)
            self.__initialized_hw_axis[axis] = axis_initialized
            self.__initialized_axis[axis] = False

        self._add_axis(axis)

        # ====================================================

        return axis   # return the created item

    elif parent_key == "encoders":  # deal with an other kind of items

        encoder = self._encoder_counter_controller.create_counter(
            item_class, name, motor_controller=self, config=cfg
        )
        
        self._encoders[name] = encoder
        self.__initialized_encoder[encoder] = False

        return encoder
```

or

```python

def _create_subitem_from_config(self, name, cfg, parent_key, item_class, item_obj=None):
    if parent_key == "counters":
        name = cfg["name"]
        tag = cfg["tag"]
        mode = cfg.get("mode")
        unit = cfg.get("unit")
        convfunc = cfg.get("convfunc")

        if self._COUNTER_TAGS[tag][1] == "scc":
            cnt = self._counter_controllers["scc"].create_counter(
                item_class, name, unit=unit, mode=mode
            )
            cnt.tag = tag

        elif self._COUNTER_TAGS[tag][1] == "icc":
            cnt = self._counter_controllers["icc"].create_counter(
                item_class, name, unit=unit
            )
            cnt.tag = tag

        else:
            raise ValueError(f"cannot identify counter tag {tag}")

        return cnt

    elif parent_key == "operators":
        return item_class(cfg)

    elif parent_key == "axes":
        if item_class is None:  # it is a referenced axis (i.e external axis)
            axis = item_obj  # the axis instance
            tag = cfg[
                "tag"
            ]  # ask for a tag which only concerns this ctrl (local tag)
            self._tag2axis[tag] = name  # store the axis tag
            return axis
        else:
            raise ValueError(
                f"{self} only accept referenced axes"
            )  # reject none-referenced axis
```



### Nested BlissControllers

A top-bliss-controller can have multiple sub-bliss-controllers. 
In that case there are two ways to create the sub-bliss-controllers:

The most simple way to do this is to declare a sub-bliss-controller as an independant object with its own yml config and use a reference to this object into the top-bliss-controller config.

Else, if a sub-bliss-controller has no reason to exist independently from the top-bliss-controller, then the top-bliss-controller will create and manage its sub-bliss-controllers from the knowledge of the top-bliss-controller configuration only.

In the second case, some items declared in the top-bliss-controller are, in fact, managed by one of the sub-bliss-controllers.
Then, the author of the top-bliss-controller class must overload the `_get_item_owner` method and specify which is the sub-bliss-controller that manages which items.

Example: 

Consider a top-bliss-controller which has internally another sub-bliss-controller that manages pseudo axes.
(`self._motor_controller = AxesBlissController(...)`)

```yml

- plugin: generic    
  module: custom_module       
  class: BCMockup             
  name: bcmock                

  axes:              
    
    - name: $xrot
      tags: real xrot

    - name: $yrot
      tags: real yrot

    - name: axis_1        
      tag : theta


```
 
The top-bliss-controller configuration declares the axes subitems but those items are in fact managed by the motors controller (`self._motor_controller`).

In that case, developers can override the `self._get_item_owner` method to specify the subitems that are managed by `self._motor_controller` instead of `self`.

```python
def _get_item_owner(self, name, cfg, pkey):
    """ Return the controller that owns the items declared in the config.
        By default, this controller is the owner of all config items.
        However if this controller has sub-controllers that are the real owners 
        of some items, this method should use to specify which sub-controller is
        the owner of which item (identified with name and pkey). 
    """
    if pkey == "axes":
        return self._motor_controller
    else:
        return self
```

The method receives the item name and the `parent_key`. So `self._motor_controller` can be associated to all subitems under the `axes` parent_key (instead of doing it for each subitem name).

Note: it would have been possible to not override `self._get_item_owner` and handle the `axes` items in the top-controller methods but it is not recommended as the code is already in the sub-bliss-controller that handles motors.



### Direct instantiation 

A BlissController can be instantiated directly (i.e. not instantiated by the plugin) providing a configuration as a dictionary.

In that case, users must call the method `self._initialize_config()` just after the controller instantiation to ensure that the controller is initialized in the same way as the plugin does.

The config dictionary should be structured like a YML file (i.e: nested dict and list) and references replaced by their corresponding object instances.

Example: `bctrl = BlissController( config_dict )` => `bctrl._initialize_config()`


### BlissController and default chain

The `DEFAULT_CHAIN` can be customized with `DEFAULT_CHAIN.set_settings` (see [Default chain](scan_default.md#default-chain)).

The devices introduced in the chain must be of the type `Counter`, `CounterController` or `BlissController`.

While introducing a `BlissController` in the default chain, the method `BlissController._get_default_chain_counter_controller` is called to obtain the `CounterController` object that should be used. By default this method is not implemented.



## Other tips

### @autocomplete_property decorator

In many controllers, the `@property` decorator is heavily used to protect certain
attributes of the instance or to limit the access to read-only. When using the
bliss command line interface the autocompletion will **not** suggest any
completion based on the return value of the method underneath the property.

This is a wanted behavior e.g. in case this would trigger hardware
communication. There are however also use cases where a *deeper* autocompletion
is wanted.

!!! note
     "↹" represents the action of pressing the "Tab" key of the keyboard.

Example: the `.counter` namespace of a controller. If implemented as
`@property`:
```
BLISS [1]: lima_simulator.counters. ↹
```

Would not show any autocompletion suggestions. To enable *deeper* autocompletion
a special decorator called `@autocomplete_property` must be used.
```python
from bliss.common.utils import autocomplete_property

class Lima(object):
    @autocomplete_property
    def counters(self):
        all_counters = [self.image]
        ...
```

Using this decorator would result in autocompletion suggestions:
```
BLISS [1]: lima_simulator.counters. ↹
                                   _roi1_
                                   _roi2_
                                   _bpm_
```

### The `__info__()` method for Bliss shell

!!! info

    - Any Bliss controller that is visible to the user in the command line
      should have an `__info__()` function implemented!
    - The return type of `__info__()` must be `str`, otherwhise it fails and
      `__repr__()` is used as fallback!
    - As a rule of thumb: the return value of a custom `__repr__()` implementation
      should not contain `\n` and should be inspired by the standard
      implementation of `__repr__()` in python.

In Bliss, `__info__()` is used by the command line interface (Bliss shell or Bliss
repl) to enquire information of the internal state of any object / controller in
case it is available.

That way, a user can get information how to use the object, detailed
**from the user perspective**. This is in contrast to the built-in python function
`__repr__()`, which should return a short summary of the concerned object from
the **developer perspective**. The Protocol that is put in place in the Bliss
shell is the following:

* if the return value of a statement entered into the Bliss shel is a python
  object with `__info__()` implemented this `__info__()` function will be called
  by the Bliss shell to display the output. As a fallback option (`__info__()`
  not implemented) the standard behavior of the interactive python interpreter
  involving `__repr__` is used. (For details about `__repr__` see next section.)

Here is an example for the lima controller that is using `__info__`:
```
LIMA_TEST_SESSION [3]: lima_simulator
              Out [3]: Simulator - Generator (Simulator) - Lima Simulator
                       
                       Image:
                       bin = [1 1]
                       flip = [False False]
                       height = 1024
                       roi = <0,0> <1024 x 1024>
                       rotation = rotation_enum.NONE
                       sizes = [   0    4 1024 1024]
                       type = Bpp32
                       width = 1024
                       
                       Acquisition:
                       expo_time = 1.0
                       mode = mode_enum.SINGLE
                       nb_frames = 1
                       status = Ready
                       status_fault_error = No error
                       trigger_mode = trigger_mode_enum.INTERNAL_TRIGGER
                       
                       ROI Counters:
                       [default]
                       
                       Name  ROI (<X, Y> <W x H>)
                       ----  ------------------
                         r1  <0, 0> <100 x 200>
```

The information given above is usefull from a **user point of view**. As a
**developer** one might want to work in the Bliss shell with live object e.g.

```python
LIMA [4]: my_detectors = {'my_lima':lima_simulator,'my_mca':simu1}
LIMA [5]: my_detectors
 Out [5]: {'my_lima': <Lima Controller for Simulator (Lima Simulator)>,
                        'my_mca': <bliss.controllers.mca.simulation.SimulatedMCA
                                   object at 0x7f2f535b5f60>}
```

In this case, it is desirable that the python objects themselves are clearly
represented, which is exactly the role of `__repr__` (in this example the
`lima_simulator` has a custom `__repr__` while in `simu1` there is no `__repr__`
implemented so the bulid in python implementation is used).

The signature of `__info__()` should be `def __info__(self):` the return value
must be a string.

```python
BLISS [1]: class A(object):
      ...:     def __repr__(self):
      ...:         return "my repl"
      ...:     def __str__(self):
      ...:         return "my str"
      ...:     def __info__(self):
      ...:         return "my info"

BLISS [2]: a=A()

BLISS [3]: a
  Out [3]: my info

BLISS [4]: [a]
  Out [4]: [my repl]
```

!!! warning

    If, for any reason, there is an exception raised inside `__info__`, the
    fallback option will be used and `__repr__` is evaluated in this case.

    And **this will hide the error**. So, *any* error must be treated
    before returning.


    Example:
    ```python
        def __info__(self):
            info_str = "bla \n"
            info_str += "bli \n"

            return info_str
    ```

The equivalent of `repr(obj)` or `str(obj)` is also available in
`bliss.shell.standard` as `info(obj)` which can be used also outside the Bliss
shell.

```
Python 3.7.3 (default, Mar 27 2019, 22:11:17)
[GCC 7.3.0] :: Anaconda, Inc. on linux
Type "help", "copyright", "credits" or "license" for more information.

>>> from bliss.shell.standard import info

>>> class A(object):
...     def __repr__(self):
...          return "my repl"
...     def __info__(self):
...          return "my info"
...
>>> info(A())
'my info'

>>> class B(object):
...     def __repr__(self):
...          return "my repl"
...

>>> info(B())
'my repl'
```

## `__str__()` and `__repr__()`

If implemented in a Python class, `__repr__` and `__str__` methods are
build-in functions Python to return information about an object instantiating this class.

* `__str__` should print a readable message
* `__repr__` should print a __short__ message about the object that is unambiguous (e.g. name of an identifier, class name, etc.).

* `__str__` is called:
    - when the object is passed to the print() function (e.g. `print(my_obj)`).
    - wheh the object is used in string operations (e.g. `str(my_obj)` or
      `'{}'.format(my_obj)` or `f'some text {my_obj}'`)
* `__repr__` method is called:
    - when user type the name of the object in an interpreter session (a python
      shell).
    - when displaying containers like lists and dicts (the result of `__repr__`
      is used to represent the objects they contain)
    - when explicitly asking for it in the print() function. (e.g. `print("%r" % my_object)`)


By default when no `__str__` or `__repr__` methods are defined, the `__repr__`
returns the name of the class (Length) and `__str__` calls `__repr__`.
